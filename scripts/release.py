# -*- coding: utf-8 -*-
"""发布 CI 产物到 GitHub Releases（主）+ Gitee Releases（可选镜像）

用法:
  uv run python scripts/release.py --ver 5.6.4           # 发布到 GitHub
  uv run python scripts/release.py --ver 5.6.4 --mirror-gitee  # GitHub + Gitee
  uv run python scripts/release.py --dry                  # 仅检查产物，不发布

前置: CI（build-installer / build-portable）构建完成后，
下载两个 artifact 到 dist/：
  dist/lan-invoice_{ver}_setup.exe  （安装版，Nuitka standalone）
  dist/lan-invoice_{ver}.exe        （便携版，PyInstaller）

环境变量:
  GITHUB_TOKEN       GitHub 私人令牌（发布 GitHub 需要）
  GITEE_ACCESSTOKEN  Gitee 私人令牌（--mirror-gitee 时需要）
"""

import os
import sys
import re
import subprocess
import json
import http.client
import urllib.request
import urllib.error
from urllib.parse import urlencode
from datetime import datetime

GITHUB_REPO = "a1429503092-cmyk/lan-invoice"
GITEE_OWNER = "GUYI33"
GITEE_NAME = "lan-invoice"
VERSION_FILE = "src/version.py"
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


def git_commit_and_tag(ver: str):
    subprocess.run(["git", "add", VERSION_FILE], check=True)
    subprocess.run(["git", "commit", "-m", f"release: v{ver}"], check=True)
    subprocess.run(["git", "tag", "-a", f"v{ver}", "-m", f"v{ver}"], check=True)
    subprocess.run(["git", "push", "origin", "master", "--tags"], check=True)
    print(f"已推送 tag v{ver}")


def _release_body(ver: str, changelog: str) -> str:
    if changelog:
        changes_section = changelog
    else:
        changes_section = "详见提交记录"
    return f"""## v{ver}

构建日期：{datetime.now().strftime('%Y-%m-%d')}

### 本次更新

{changes_section}

### 下载说明

| 文件 | 说明 |
|------|------|
| lan-invoice_{ver}_setup.exe | 安装版（推荐）：standalone 启动免解压，自动覆盖更新 |
| lan-invoice_{ver}.exe | 便携版：单文件，解压即用（启动稍慢） |

> 如遇到 SmartScreen 拦截，点击「更多信息」→「仍要运行」即可。
"""


def create_github_release(ver: str, token: str, changelog: str = "") -> dict:
    """创建 GitHub Release（tag 需已推送）"""
    body = _release_body(ver, changelog)
    payload = json.dumps({
        "tag_name": f"v{ver}",
        "name": f"v{ver}",
        "body": body,
        "target_commitish": "master",
        "prerelease": False,
    }).encode()

    req = urllib.request.Request(
        f"https://api.github.com/repos/{GITHUB_REPO}/releases",
        data=payload, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "lan-invoice-release")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        sys.exit(f"创建 GitHub Release 失败 ({e.code}): {e.read().decode()[:400]}")

    print(f"GitHub Release 已创建 (id={data['id']})")
    return data


def upload_github_asset(release_id: int, filepath: str, token: str):
    """上传附件到 GitHub Release"""
    fname = os.path.basename(filepath)
    with open(filepath, "rb") as f:
        file_data = f.read()
    req = urllib.request.Request(
        f"https://uploads.github.com/repos/{GITHUB_REPO}/releases/"
        f"{release_id}/assets?name={urllib.request.quote(fname)}",
        data=file_data, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/octet-stream")
    req.add_header("User-Agent", "lan-invoice-release")
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        sys.exit(f"上传附件失败 ({e.code}): {e.read().decode()[:400]}")
    print(f"附件已上传: {fname} → {data.get('browser_download_url', '')}")


def create_gitee_release(ver: str, token: str, changelog: str = "") -> dict:
    """创建 Gitee Release（镜像）"""
    body = _release_body(ver, changelog)
    params = urlencode({
        "access_token": token,
        "tag_name": f"v{ver}",
        "name": f"v{ver}",
        "body": body,
        "target_commitish": "master",
        "prerelease": "false",
    })

    conn = http.client.HTTPSConnection("gitee.com")
    conn.request(
        "POST",
        f"/api/v5/repos/{GITEE_OWNER}/{GITEE_NAME}/releases",
        body=params,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    resp = conn.getresponse()
    data = json.loads(resp.read().decode())
    conn.close()

    if resp.status not in (200, 201):
        sys.exit(f"创建 Gitee Release 失败 ({resp.status}): {data}")

    release_id = data["id"]
    print(f"Gitee Release 已创建 (id={release_id})")
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

    conn = http.client.HTTPSConnection("gitee.com")
    conn.request(
        "POST",
        f"/api/v5/repos/{GITEE_OWNER}/{GITEE_NAME}/releases/{release_id}/attach_files",
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
    """发布流程（构建由 CI 完成，本脚本仅发布 CI 产物）。

    用法:
      uv run python scripts/release.py --ver 5.6.4   # 发布（需 dist/ 有 CI 产物）
      uv run python scripts/release.py --dry          # 仅检查产物，不发布

    前置: CI（build-installer / build-portable）构建完成后，
    下载两个 artifact 到 dist/：
      dist/lan-invoice_{ver}_setup.exe  （安装版，Nuitka standalone）
      dist/lan-invoice_{ver}.exe        （便携版，PyInstaller）
    """
    dry = "--dry" in sys.argv
    ver_arg = None
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "--ver" and i + 1 < len(args):
            ver_arg = args[i + 1]
        elif a.startswith("--ver="):
            ver_arg = a.split("=", 1)[1]

    old_ver = read_version()
    ver = ver_arg or bump_version(old_ver)

    # dry 模式只检查产物，不写版本/不打 tag
    if ver != old_ver and not dry:
        write_version(old_ver, ver)
        sync_version_info(ver)

    # ── 检查 CI 产物 ──
    setup_exe = os.path.join(DIST_DIR, f"lan-invoice_{ver}_setup.exe")
    portable_exe = os.path.join(DIST_DIR, f"lan-invoice_{ver}.exe")
    missing = [p for p in (setup_exe, portable_exe) if not os.path.exists(p)]
    if missing:
        sys.exit(
            f"缺少 CI 产物（{len(missing)} 个）:\n  " +
            "\n  ".join(missing) +
            "\n请先从 GitHub Actions 下载 artifact 到 dist/ 再发布")
    print(f"产物就绪: {os.path.basename(setup_exe)} / {os.path.basename(portable_exe)}")

    if dry:
        print("[dry] 跳过发布")
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

    if ver != old_ver:
        git_commit_and_tag(ver)

    changelog = """\
• MCP 导入修复：代理字符（surrogate）导致的无响应/超时问题
• 更新自动化：软件内直接下载安装包并自动覆盖更新（无需浏览器）
• 安装版切 Nuitka standalone：启动 0.2s、杀毒软件零误报
• GUI 启动提速：字体按需加载（约快 1.8s）
• 安装版固定 EXE 名：覆盖更新后 MCP 配置永久有效
• MCP 无头模式接入文件日志"""

    # ── 主发布：GitHub ──
    gh_token = os.environ.get("GITHUB_TOKEN")
    if not gh_token:
        sys.exit("请设置环境变量 GITHUB_TOKEN（GitHub 私人令牌）")
    release = create_github_release(ver, gh_token, changelog)
    upload_github_asset(release["id"], setup_exe, gh_token)
    upload_github_asset(release["id"], portable_exe, gh_token)
    print(f"GitHub 发布成功: https://github.com/{GITHUB_REPO}/releases/tag/v{ver}")

    # ── 可选镜像：Gitee（--mirror-gitee）──
    if "--mirror-gitee" in sys.argv:
        g_token = os.environ.get("GITEE_TOKEN") or os.environ.get("GITEE_ACCESSTOKEN")
        if not g_token:
            sys.exit("--mirror-gitee 需要 GITEE_ACCESSTOKEN 环境变量")
        g_release = create_gitee_release(ver, g_token, changelog)
        upload_asset(g_release["id"], setup_exe, g_token)
        upload_asset(g_release["id"], portable_exe, g_token)
        print(f"Gitee 镜像发布成功: https://gitee.com/{GITEE_OWNER}/{GITEE_NAME}/releases/tag/v{ver}")


if __name__ == "__main__":
    main()
