#!/usr/bin/env python
"""
发票归档 Windows 安装包创建脚本（版本号自动从源码读取）

创建方式（按优先级）：
1. Docker + Inno Setup — 交叉编译标准 Windows 安装包（推荐）
2. NSIS — Nullsoft 安装包（Windows 本机）
3. IExpress — Windows 内置工具
4. ZIP — 纯 Python zipfile 打包（最终回退）
"""

import os
import sys
import shutil
import subprocess
import tempfile
import zipfile
import time
from pathlib import Path

# --- 从源码读取版本号 ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = PROJECT_ROOT / "src" / "version.py"

def _read_version():
    import re
    with open(VERSION_FILE, encoding="utf-8") as f:
        for line in f:
            m = re.match(r'\s*APP_VERSION\s*=\s*"([^"]+)"', line)
            if m:
                return m.group(1)
    return "0.0.0"

# 安装程序界面显示名（可以用中文，Inno Setup 支持 UTF-8 with BOM）
APP_NAME = "发票归档"
APP_VERSION = _read_version()
APP_DIR_NAME = "发票归档"

# 文件名：统一英文避免 Wine / Git Bash / CI 中文编码问题
VER_TAG = APP_VERSION.replace(".", "_")
EXE_NAME = f"lan-invoice_{APP_VERSION}.exe"          # 便携版
SETUP_NAME = f"lan-invoice_{APP_VERSION}_setup.exe"   # 安装包
ZIP_NAME = f"lan-invoice_{APP_VERSION}_portable.zip"  # 便携 ZIP

DIST_DIR = PROJECT_ROOT / "dist"
EXE_SRC = DIST_DIR / EXE_NAME
ICON_SRC = PROJECT_ROOT / "icon.ico"
SETUP_EXE = DIST_DIR / SETUP_NAME
SETUP_ZIP = DIST_DIR / ZIP_NAME

ASCII_EXE_NAME = f"lan_invoice_{VER_TAG}.exe"



# =============================================================================
# 安装脚本 (install.bat)
# =============================================================================

def create_install_bat(target_dir: Path) -> Path:
    """创建安装批处理脚本。

    功能：复制文件到 Program Files、创建桌面/开始菜单快捷方式。
    支持自动请求管理员权限（UAC 提权）。
    """
    content = r"""@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

set "APP_DIR=%ProgramFiles%\{app_dir}"
set "EXE_NAME={exe_name}"

:: ---- 检查并提权到管理员 ----
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  需要管理员权限才能安装到 Program Files。
    echo  正在请求管理员权限...
    echo.
    powershell -NoProfile -Command ^
        "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo ============================================
echo   正在安装 {app_name} {app_version}
echo ============================================
echo.

:: ---- 创建程序目录 ----
if not exist "!APP_DIR!" (
    mkdir "!APP_DIR!"
)

:: ---- 复制文件 ----
echo [1/3] 复制程序文件...
copy "%~dp0%EXE_NAME%" "!APP_DIR!\%EXE_NAME%" /Y >nul
if errorlevel 1 (
    echo [错误] 复制文件失败
    pause
    exit /b 1
)

if exist "%~dp0icon.ico" (
    copy "%~dp0icon.ico" "!APP_DIR!\icon.ico" /Y >nul
)

:: ---- 创建桌面快捷方式 ----
echo [2/3] 创建桌面快捷方式...
powershell -NoProfile -Command ^
    "$WS = New-Object -ComObject WScript.Shell; " ^
    "$SC = $WS.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\{app_name}.lnk'); " ^
    "$SC.TargetPath = '!APP_DIR!\%EXE_NAME%'; " ^
    "$SC.WorkingDirectory = '!APP_DIR!'; " ^
    "$SC.IconLocation = '!APP_DIR!\icon.ico,0'; " ^
    "$SC.Description = '{app_name} {app_version} - 电子发票PDF批量识别与归档'; " ^
    "$SC.Save()" 2>nul

:: ---- 创建开始菜单快捷方式 ----
echo [3/3] 创建开始菜单快捷方式...
set "SM=%APPDATA%\Microsoft\Windows\Start Menu\Programs\{app_dir}"
if not exist "!SM!" mkdir "!SM!"
powershell -NoProfile -Command ^
    "$WS = New-Object -ComObject WScript.Shell; " ^
    "$SC = $WS.CreateShortcut('!SM!\{app_name}.lnk'); " ^
    "$SC.TargetPath = '!APP_DIR!\%EXE_NAME%'; " ^
    "$SC.WorkingDirectory = '!APP_DIR!'; " ^
    "$SC.IconLocation = '!APP_DIR!\icon.ico,0'; " ^
    "$SC.Description = '{app_name} {app_version} - 电子发票PDF批量识别与归档'; " ^
    "$SC.Save()" 2>nul

:: ---- 完成 ----
echo.
echo ============================================
echo   安装完成！
echo.
echo   程序位置: !APP_DIR!
echo   桌面快捷方式: {app_name}.lnk
echo   开始菜单: {app_dir}
echo ============================================
echo.
pause
""".format(
        app_dir=APP_DIR_NAME,
        app_name=APP_NAME,
        app_version=APP_VERSION,
        exe_name=ASCII_EXE_NAME,
    )

    bat_path = target_dir / "install.bat"
    bat_path.write_text(content, encoding="utf-8")
    return bat_path


# =============================================================================
# 方式一：Docker + Inno Setup（首选）
# =============================================================================

_DOCKER_IMAGE = "lan-invoice-iss"
_DOCKERFILE = PROJECT_ROOT / "scripts" / "Dockerfile.innosetup"


def _docker_available() -> bool:
    """检查 docker 是否可用。"""
    try:
        result = subprocess.run(
            ["docker", "version"], capture_output=True, timeout=10)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _docker_image_ready() -> bool:
    """确保 Inno Setup Docker 镜像存在，不存在则构建。"""
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", _DOCKER_IMAGE],
            capture_output=True, timeout=10)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def build_with_docker_innosetup(source_dir: Path) -> bool:
    """使用 Docker + Wine + Inno Setup 交叉编译 Windows 安装包。

    适用于没有原生 Inno Setup 的环境（CI/CD、非 Windows 主机等）。
    Wine 下中文文件名会被写乱码，编译后自动重命名修复。
    """
    if not _docker_available():
        print("[INFO] Docker 不可用")
        return False

    print("[INFO] 使用 Docker + Inno Setup 编译安装包...")

    # 确保镜像存在
    if not _docker_image_ready():
        print("       [0/3] 构建 Docker 镜像（仅首次）...")
        result = subprocess.run(
            ["docker", "build", "-t", _DOCKER_IMAGE,
             "-f", str(_DOCKERFILE), "."],
            cwd=str(PROJECT_ROOT),
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            print(f"[WARN] Docker 镜像构建失败:\n{result.stderr[-500:]}")
            return False
        print("       [0/3] 镜像就绪")

    # 生成 .iss 脚本（引用 ASCII 安全文件名，输出中文文件名）
    iss_content = _generate_iss(source_dir)
    iss_path = source_dir / "setup.iss"
    # UTF-8 with BOM，Inno Setup 6 才能正确识别中文
    iss_path.write_text(iss_content, encoding="utf-8-sig")

    # 映射路径：Wine 下 Z:\work → 宿主 source_dir
    src_abs = str(source_dir.resolve()).replace("\\", "/")
    docker_vol = f"{src_abs}:/work"

    print("       [1/3] 编译 Inno Setup 脚本...")
    # 禁用 Git Bash 路径转换 (MSYS_NO_PATHCONV=1)
    env = os.environ.copy()
    env["MSYS_NO_PATHCONV"] = "1"

    result = subprocess.run(
        ["docker", "run", "--rm",
         "-v", docker_vol,
         _DOCKER_IMAGE,
         "Z:\\work\\setup.iss"],
        capture_output=True, text=True, timeout=120,
        env=env,
    )

    # 查找输出：Wine 下中文文件名变乱码，但文件会出现在 dist 目录
    # Inno Setup 输出时 filename 指定为 ASCII，避免乱码
    if result.returncode != 0:
        # 检查是否是因缺少 Xvfb 导致的 warning（可忽略）
        stderr_lines = result.stderr.strip().split("\n")
        actual_errors = [l for l in stderr_lines
                        if "err:" in l and "winediag" not in l
                        and "ole:" not in l and "marshal" not in l]
        if actual_errors:
            print(f"[WARN] Inno Setup 编译警告:\n" +
                  "\n".join(actual_errors[-5:]))

    # 查找输出文件（英文名，Wine 不会写乱码）
    output_exe = source_dir / SETUP_NAME
    if output_exe.exists():
        size_mb = output_exe.stat().st_size / 1024 / 1024
        print(f"       [2/3] 完成 ({size_mb:.1f} MB)")
        print(f"[OK] 安装包创建成功")
        return True

    # 兜底：Inno Setup 可能把文件写到不同位置
    cutoff = time.time() - 120
    for f in source_dir.iterdir():
        if f.suffix == ".exe" and "setup" in f.name.lower() \
           and f.stat().st_mtime > cutoff:
            shutil.move(str(f), str(output_exe))
            print(f"[OK] 安装包创建成功")
            return True

    print("[WARN] 安装包生成失败")
    if result.stdout:
        print(result.stdout[-500:])
    return False


def _generate_iss(source_dir: Path) -> str:
    """生成 Inno Setup 6 安装脚本（全部英文文件名，Wine/CI 友好）。"""
    return f"""; Inno Setup Script — auto-generated v{APP_VERSION}
; 界面文字用中文，文件名/路径用英文（Docker/Wine 中文文件名兼容问题）
[Setup]
AppName={APP_NAME}
AppVersion={APP_VERSION}
AppPublisher=GUYI33
DefaultDirName={{pf}}\\lan-invoice
DefaultGroupName={APP_DIR_NAME}
Compression=lzma2/ultra64
SolidCompression=yes
UninstallDisplayName={APP_NAME}
OutputDir=./
OutputBaseFilename={SETUP_NAME.replace('.exe', '')}

[Files]
Source: "{ASCII_EXE_NAME}"; DestDir: "{{app}}"; DestName: "{EXE_NAME}"

[Icons]
Name: "{{group}}\\{APP_NAME}"; Filename: "{{app}}\\{EXE_NAME}"
Name: "{{commondesktop}}\\{APP_NAME}"; Filename: "{{app}}\\{EXE_NAME}"

[Run]
Filename: "{{app}}\\{EXE_NAME}"; Description: "启动 {APP_NAME}"; \
Flags: nowait postinstall
"""


# =============================================================================
# 方式二：NSIS（备选）
# =============================================================================

def _find_makensis() -> str | None:
    """查找 makensis.exe。"""
    # 常见安装位置
    possible = [
        Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "NSIS" / "makensis.exe",
        Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "NSIS" / "makensis.exe",
    ]
    for p in possible:
        if p.exists():
            return str(p)

    # PATH 中查找
    try:
        result = subprocess.run(["makensis", "/VERSION"], capture_output=True, timeout=10)
        if result.returncode == 0:
            return "makensis"
    except FileNotFoundError:
        pass

    return None


def build_with_nsis(source_dir: Path) -> bool:
    """使用 NSIS 创建安装包。"""
    makensis = _find_makensis()
    if makensis is None:
        print("[INFO] NSIS 未安装")
        return False

    print("[INFO] 使用 NSIS 创建安装包...")

    # 生成 NSIS 脚本
    nsi_content = (
        '; 发票归档 — NSIS 安装脚本（自动生成）\n'
        '!define PRODUCT_NAME "{app_name}"\n'
        '!define PRODUCT_VERSION "{app_version}"\n'
        '!define PRODUCT_PUBLISHER "lan-invoice"\n'
        '!define EXE_NAME "{exe_name}"\n'
        '\n'
        'Name "${{PRODUCT_NAME}} v${{PRODUCT_VERSION}}"\n'
        'OutFile "{setup_exe}"\n'
        'InstallDir "$PROGRAMFILES\\${{PRODUCT_NAME}}"\n'
        'RequestExecutionLevel admin\n'
        'SetCompressor lzma\n'
        '\n'
        '!include "MUI2.nsh"\n'
        '\n'
        '!insertmacro MUI_PAGE_WELCOME\n'
        '!insertmacro MUI_PAGE_DIRECTORY\n'
        '!insertmacro MUI_PAGE_INSTFILES\n'
        '!insertmacro MUI_PAGE_FINISH\n'
        '!insertmacro MUI_LANGUAGE "SimpChinese"\n'
        '\n'
        'Section "Install"\n'
        '    SetOutPath "$INSTDIR"\n'
        '    File "{exe_src}"\n'
        '    File "{icon_src}"\n'
        '\n'
        '    CreateShortCut "$DESKTOP\\${{PRODUCT_NAME}}.lnk" "$INSTDIR\\${{EXE_NAME}}" "" "$INSTDIR\\icon.ico"\n'
        '    CreateDirectory "$SMPROGRAMS\\${{PRODUCT_NAME}}"\n'
        '    CreateShortCut "$SMPROGRAMS\\${{PRODUCT_NAME}}\\${{PRODUCT_NAME}}.lnk" "$INSTDIR\\${{EXE_NAME}}" "" "$INSTDIR\\icon.ico"\n'
        '    CreateShortCut "$SMPROGRAMS\\${{PRODUCT_NAME}}\\卸载.lnk" "$INSTDIR\\uninstall.exe"\n'
        '\n'
        '    WriteUninstaller "$INSTDIR\\uninstall.exe"\n'
        '    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${{PRODUCT_NAME}}" "DisplayName" "${{PRODUCT_NAME}}"\n'
        '    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${{PRODUCT_NAME}}" "UninstallString" "$INSTDIR\\uninstall.exe"\n'
        '    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${{PRODUCT_NAME}}" "DisplayVersion" "${{PRODUCT_VERSION}}"\n'
        '    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${{PRODUCT_NAME}}" "Publisher" "${{PRODUCT_PUBLISHER}}"\n'
        'SectionEnd\n'
        '\n'
        'Section "Uninstall"\n'
        '    Delete "$INSTDIR\\${{EXE_NAME}}"\n'
        '    Delete "$INSTDIR\\icon.ico"\n'
        '    Delete "$INSTDIR\\uninstall.exe"\n'
        '    Delete "$DESKTOP\\${{PRODUCT_NAME}}.lnk"\n'
        '    RMDir /r "$SMPROGRAMS\\${{PRODUCT_NAME}}"\n'
        '    RMDir "$INSTDIR"\n'
        '    DeleteRegKey HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${{PRODUCT_NAME}}"\n'
        'SectionEnd\n'
    ).format(
        app_name=APP_NAME,
        app_version=APP_VERSION,
        exe_name=EXE_NAME,
        setup_exe=str(SETUP_EXE).replace("\\", "\\\\"),
        exe_src=str(EXE_SRC).replace("\\", "\\\\"),
        icon_src=str(ICON_SRC).replace("\\", "\\\\"),
    )

    nsi_path = source_dir / "setup.nsi"
    # NSIS 在中文 Windows 上需要 GBK 编码
    try:
        nsi_path.write_text(nsi_content, encoding="gbk")
    except UnicodeEncodeError:
        nsi_path.write_text(nsi_content, encoding="utf-8")

    print(f"       [1/2] 编译 NSIS 脚本...")
    result = subprocess.run(
        [makensis, str(nsi_path)],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        print(f"[WARN] NSIS 编译失败:\n{result.stderr}")
        return False

    # 检查输出
    if SETUP_EXE.exists():
        size_mb = SETUP_EXE.stat().st_size / 1024 / 1024
        print(f"       [2/2] 完成 ({size_mb:.1f} MB)")
        print(f"[OK] NSIS 安装包创建成功")
        return True
    else:
        print("[WARN] NSIS 输出文件未找到")
        return False


# =============================================================================
# 方式二：IExpress（备选）
# =============================================================================

def build_with_iexpress(source_dir: Path) -> bool:
    """使用 Windows IExpress 工具创建安装包。"""
    iexpress = r"C:\Windows\System32\iexpress.exe"
    if not os.path.exists(iexpress):
        print("[INFO] IExpress 不可用")
        return False

    print("[INFO] 使用 IExpress 创建安装包...")

    # 构建 IExpress SED 文件
    source_dir_escaped = str(source_dir).replace("\\", "\\\\")

    strings_part = "[Strings]\r\n"
    strings_part += "AppName=" + APP_NAME + "\r\n"
    files = [ASCII_EXE_NAME, "icon.ico", "install.bat"]
    for i, fname in enumerate(files):
        strings_part += 'FILE%d="%s"\r\n' % (i, fname)

    source_files_part = ""
    for i in range(len(files)):
        source_files_part += '%%FILE%d%%="%s"\r\n' % (i, source_dir_escaped)

    sed_content = (
        "[Version]\r\n"
        "Class=IEXPRESS\r\n"
        "SEDVersion=3\r\n"
        "\r\n"
        "[Options]\r\n"
        "PackagePurpose=InstallApp\r\n"
        "ShowInstallProgramWindow=0\r\n"
        "HideExtractAnimation=1\r\n"
        "UseLongFileName=1\r\n"
        "InsideCompressed=1\r\n"
        "CAB_FixedSize=0\r\n"
        "CAB_ResvCodeSigning=0\r\n"
        "RebootMode=N\r\n"
    )
    sed_content += (
        'InstallPrompt="即将安装 ' + APP_NAME + " " + APP_VERSION + '，是否继续？"\r\n'
    )
    sed_content += 'LicensePrompt=\r\nDisplayLicense=\r\n'
    sed_content += (
        'FinishMessage="' + APP_NAME + " " + APP_VERSION + ' 安装完成！"\r\n'
    )
    sed_content += 'TargetName="' + str(SETUP_EXE) + '"\r\n'
    sed_content += (
        'FriendlyName="' + APP_NAME + " " + APP_VERSION + '"\r\n'
    )
    sed_content += 'AppLaunched="install.bat"\r\n'
    sed_content += "PostInstallCmd=<None>\r\n"
    sed_content += "AdminQuietInstCmd=\r\n"
    sed_content += "UserQuietInstCmd=\r\n"
    sed_content += "SourceFiles=SourceFiles\r\n"
    sed_content += "\r\n[SourceFiles]\r\n"
    sed_content += "SourceFiles0=SourceFiles0\r\n"
    sed_content += "\r\n[SourceFiles0]\r\n"
    sed_content += source_files_part
    sed_content += strings_part

    sed_path = source_dir / "setup.sed"
    sed_path.write_text(sed_content, encoding="gbk")

    # 运行 IExpress
    try:
        result = subprocess.run(
            [iexpress, "/Q", "/M", str(sed_path)],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0 and SETUP_EXE.exists():
            print("[OK] IExpress 构建成功")
            return True
        else:
            print(f"[WARN] IExpress 返回码: {result.returncode}")
            return False
    except Exception as e:
        print(f"[WARN] IExpress 异常: {e}")
        return False


# =============================================================================
# 方式三：ZIP（最终回退）
# =============================================================================

def build_with_zip(source_dir: Path) -> bool:
    """创建 ZIP 安装包。"""
    print("[INFO] 使用 ZIP 方式创建安装包...")

    try:
        with zipfile.ZipFile(SETUP_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(source_dir / ASCII_EXE_NAME, ASCII_EXE_NAME)
            zf.write(source_dir / "icon.ico", "icon.ico")
            zf.write(source_dir / "install.bat", "install.bat")

        print(f"[OK] ZIP 安装包创建成功: {SETUP_ZIP}")
        return True
    except Exception as e:
        print(f"[ERROR] 创建 ZIP 失败: {e}")
        return False


# =============================================================================
# 主流程
# =============================================================================

def main():
    print("=== 创建 {app_name} {version} Windows 安装包 ===".format(
        app_name=APP_NAME, version=APP_VERSION))
    print()

    # ---- 检查源文件 ----
    if not EXE_SRC.exists():
        print("[ERROR] 找不到主程序: %s" % EXE_SRC)
        print("       请先使用 PyInstaller 打包 EXE")
        return 1

    exe_size_mb = EXE_SRC.stat().st_size / 1024 / 1024
    print("[INFO] 主程序: %s (%.1f MB)" % (EXE_SRC.name, exe_size_mb))
    print()

    # ---- 创建临时工作目录 ----
    with tempfile.TemporaryDirectory(prefix="invoice_setup_") as tmp_dir:
        tmp_path = Path(tmp_dir)

        # 复制文件（使用 ASCII 安全文件名）
        shutil.copy2(EXE_SRC, tmp_path / ASCII_EXE_NAME)
        if ICON_SRC.exists():
            shutil.copy2(ICON_SRC, tmp_path / "icon.ico")
        print("[INFO] 文件已就绪")

        # 创建安装脚本
        create_install_bat(tmp_path)
        print("[INFO] 安装脚本已创建")

        print()

        # ---- 方式1: Docker + Inno Setup（首选） ----
        ok = build_with_docker_innosetup(tmp_path)

        # ---- 方式2: NSIS（Windows 本机） ----
        if not ok:
            print("[INFO] Docker 不可用，尝试 NSIS...")
            ok = build_with_nsis(tmp_path)

        # ---- 方式3: IExpress（Windows 内置） ----
        if not ok:
            print("[INFO] NSIS 不可用，尝试 IExpress...")
            ok = build_with_iexpress(tmp_path)

        # ---- 方式4: ZIP（纯 Python 回退） ----
        if not ok:
            print("[INFO] IExpress 也不可用，改用 ZIP...")
            ok = build_with_zip(tmp_path)

    print()

    # ---- 验证输出 ----
    if SETUP_EXE.exists():
        final_size = SETUP_EXE.stat().st_size
        final_size_mb = final_size / 1024 / 1024
        print("=" * 48)
        print("  安装包创建成功！")
        print("  路径: %s" % SETUP_EXE)
        print("  大小: %.1f MB" % final_size_mb)
        print("=" * 48)
    elif SETUP_ZIP.exists():
        print("-" * 48)
        print("  ZIP 安装包已创建：")
        print("  %s" % SETUP_ZIP)
        print()
        print("  请解压后运行 install.bat 完成安装")
        print("-" * 48)
    else:
        print("[ERROR] 安装包创建失败！")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
