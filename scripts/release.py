# -*- coding: utf-8 -*-
"""一键构建 + 发布到 Gitee Releases

用法:
  uv run python scripts/release.py          # 构建并发布
  uv run python scripts/release.py --dry    # 仅构建，不发布
  uv run python scripts/release.py --ver 5.3.0  # 指定版本号

环境变量:
  GITEE_TOKEN  Gitee 私人令牌（发布时需要）
"""

import os
import sys
import re
import subprocess
import json
import shutil
import zipfile
import http.client
from urllib.parse import urlencode
from datetime import datetime

REPO_OWNER = "GUYI33"
REPO_NAME = "lan-invoice"
API_HOST = "gitee.com"
VERSION_FILE = "src/version.py"
SPEC_FILE = "发票归档.spec"
DIST_DIR = "dist"


def read_version():
    with open(VERSION_FILE, encoding="utf-8") as f:
        content = f.read()
    m = re.search(r'APP_VERSION\s*=\s*["\'](.+?)["\']', content)
    if not m:
        sys.exit(f"无法从 {VERSION_FILE} 提取版本号")
    return m.group(1)


def bump_version(old: str) -> str:
    parts = old.split(".")
    parts[-1] = str(int(parts[-1]) + 1)
    return ".".join(parts)


def write_version(old: str, new: str):
    content = open(VERSION_FILE, encoding="utf-8").read()
    content = re.sub(r'(APP_VERSION\s*=\s*)["\'].+?["\']', f'\\1"{new}"', content)
    with open(VERSION_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"版本号: {old} → {new}")


def smoke_test():
    print("冒烟测试…")
    result = subprocess.run(
        ["uv", "run", "python", "tests/test_smoke.py"],
        check=False,
    )
    if result.returncode != 0:
        sys.exit(f"冒烟测试失败 (exit={result.returncode})，中止发布")
    print("冒烟测试通过")


def build():
    print("构建 EXE...")
    subprocess.run(
        ["uv", "run", "pyinstaller", SPEC_FILE, "--clean", "--noconfirm"],
        check=True
    )
    print("构建完成")


def git_commit_and_tag(ver: str):
    subprocess.run(["git", "add", VERSION_FILE], check=True)
    subprocess.run(["git", "commit", "-m", f"release: v{ver}"], check=True)
    subprocess.run(["git", "tag", "-a", f"v{ver}", "-m", f"v{ver}"], check=True)
    subprocess.run(["git", "push", "origin", "master", "--tags"], check=True)
    print(f"已推送 tag v{ver}")


def create_release(ver: str, token: str) -> dict:
    body = f"""## v{ver}

构建日期：{datetime.now().strftime('%Y-%m-%d')}

| 文件 | 说明 |
|------|------|
| 发票归档.exe | Windows 桌面程序 |

### 安装说明
下载「发票归档.exe」放到任意目录，双击启动。
"""

    params = urlencode({
        "access_token": token,
        "tag_name": f"v{ver}",
        "name": f"v{ver}",
        "body": body,
        "target_commitish": "master",
        "prerelease": "false",
    })

    conn = http.client.HTTPSConnection(API_HOST)
    conn.request(
        "POST",
        f"/api/v5/repos/{REPO_OWNER}/{REPO_NAME}/releases",
        body=params,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    resp = conn.getresponse()
    data = json.loads(resp.read().decode())
    conn.close()

    if resp.status not in (200, 201):
        sys.exit(f"创建 Release 失败 ({resp.status}): {data}")

    release_id = data["id"]
    print(f"Release 已创建 (id={release_id})")
    return data


def upload_asset(release_id: int, filepath: str, token: str):
    """上传附件到 Release — 用 multipart 上传"""

    boundary = "----FormBoundary7MA4YWxkTrZu0gW"

    with open(filepath, "rb") as f:
        file_data = f.read()

    filename = os.path.basename(filepath)
    body = (
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"access_token\"\r\n\r\n"
        f"{token}\r\n"
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8")
    body += file_data
    body += f"\r\n--{boundary}--\r\n".encode("utf-8")

    conn = http.client.HTTPSConnection(API_HOST)
    conn.request(
        "POST",
        f"/api/v5/repos/{REPO_OWNER}/{REPO_NAME}/releases/{release_id}/attach_files",
        body=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        }
    )
    resp = conn.getresponse()
    data = json.loads(resp.read().decode())
    conn.close()

    if resp.status not in (200, 201):
        sys.exit(f"上传附件失败 ({resp.status}): {data}")
    print(f"附件已上传: {filename} → {data.get('browser_download_url', '')}")


def sync_version_info(ver: str):
    """将版本号写入 version_info.txt，确保 EXE 右键属性版本号正确"""
    vi = os.path.join(os.path.dirname(os.path.dirname(__file__)), "version_info.txt")
    if not os.path.exists(vi):
        print(f"version_info.txt 不存在，跳过: {vi}")
        return
    nums = tuple(int(x) for x in ver.split(".")) + (0,) * (4 - len(ver.split(".")))
    nums = nums[:4]
    content = f"""# UTF-8
#
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={nums},
    prodvers={nums},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        u'080404b0',
        [StringStruct(u'CompanyName', u'GUYI33'),
         StringStruct(u'FileDescription', u'发票归档 - 电子发票 PDF 批量识别与归档'),
         StringStruct(u'FileVersion', u'{ver}'),
         StringStruct(u'InternalName', u'发票归档'),
         StringStruct(u'LegalCopyright', u'Copyright (C) 2025-2026'),
         StringStruct(u'OriginalFilename', u'发票归档_v{ver}.exe'),
         StringStruct(u'ProductName', u'发票归档'),
         StringStruct(u'ProductVersion', u'{ver}')])
    ]),
    VarFileInfo([VarStruct(u'Translation', [0x0804, 0x04b0])])
  ]
)
"""
    with open(vi, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"version_info.txt → {ver}")


def main():
    dry = "--dry" in sys.argv
    ver_arg = None
    for a in sys.argv[1:]:
        if a.startswith("--ver"):
            ver_arg = a.split("=")[-1] if "=" in a else None

    old_ver = read_version()
    ver = ver_arg or bump_version(old_ver)

    if ver != old_ver:
        write_version(old_ver, ver)

    sync_version_info(ver)
    smoke_test()
    build()

    if dry:
        print(f"[dry] 跳过发布，EXE 在 {DIST_DIR}/")
        return

    # 从 .env 文件加载（优先级低于环境变量）
    env_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if os.path.exists(env_file):
        for line in open(env_file, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if k.strip() not in os.environ:
                    os.environ[k.strip()] = v.strip()

    token = os.environ.get("GITEE_TOKEN")
    if not token:
        sys.exit("请设置环境变量 GITEE_TOKEN 或在项目根目录创建 .env 文件")

    exe_path = os.path.join(DIST_DIR, f"发票归档_v{ver}.exe")
    src = os.path.join(DIST_DIR, "发票归档.exe")
    if os.path.exists(src):
        os.replace(src, exe_path)
    if not os.path.exists(exe_path):
        sys.exit(f"EXE 不存在: {exe_path}")

    # 便携版 ZIP
    zip_path = os.path.join(DIST_DIR, f"发票归档_v{ver}_portable.zip")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.write(exe_path, os.path.basename(exe_path))
    print(f"便携版 ZIP: {zip_path}")

    # Inno Setup 安装器（如果 ISCC 可用）
    setup_path = os.path.join(DIST_DIR, f"发票归档_v{ver}_setup.exe")
    iss_path = os.path.join(DIST_DIR, f"setup_v{ver}.iss")
    _write_iss(iss_path, "发票归档", os.path.basename(exe_path), ver)
    iscc = shutil.which("iscc")
    if iscc:
        subprocess.run([iscc, iss_path], check=True)
        print(f"安装器: {setup_path}")
    else:
        print("Inno Setup 未安装，跳过安装器打包")

    if ver != old_ver:
        git_commit_and_tag(ver)

    release = create_release(ver, token)
    upload_asset(release["id"], exe_path, token)
    upload_asset(release["id"], zip_path, token)
    if os.path.exists(setup_path):
        upload_asset(release["id"], setup_path, token)
    print(f"\n发布成功: https://gitee.com/{REPO_OWNER}/{REPO_NAME}/releases/tag/v{ver}")


def _write_iss(iss_path: str, app_name: str, exe_name: str, ver: str):
    """生成 Inno Setup 脚本"""
    content = f"""; Inno Setup Script — 自动生成
[Setup]
AppName={app_name}
AppVersion={ver}
AppPublisher=GUYI33
DefaultDirName={{pf}}\\{app_name}
DefaultGroupName={app_name}
OutputDir=.
OutputBaseFilename={exe_name.replace('.exe', '_setup')}
Compression=lzma2/ultra64
SolidCompression=yes
UninstallDisplayName={app_name}
PrivilegesRequired=admin

[Files]
Source: "{exe_name}"; DestDir: "{{app}}"

[Icons]
Name: "{{group}}\\{app_name}"; Filename: "{{app}}\\{exe_name}"
Name: "{{group}}\\卸载 {app_name}"; Filename: "{{uninstallexe}}"
Name: "{{commondesktop}}\\{app_name}"; Filename: "{{app}}\\{exe_name}"

[Run]
Filename: "{{app}}\\{exe_name}"; Description: "启动 {app_name}"; Flags: nowait postinstall
"""
    with open(iss_path, "w", encoding="utf-8") as f:
        f.write(content)


if __name__ == "__main__":
    main()
