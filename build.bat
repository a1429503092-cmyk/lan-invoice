@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: ============================================================
::  发票归档 — 一键打包（便携版 + 安装包）
::
::  依赖：Python (uv)、Docker（安装包编译用，可选）
::  输出：dist\发票归档_X.X.X.exe（便携版）
::        dist\发票归档_X.X.X_setup.exe（安装包，需 Docker）
:: ============================================================

:: ---- 获取版本号 ----
for /f "tokens=2 delims= " %%v in ('uv run python -c "from src.version import APP_VERSION; print(APP_VERSION)"') do set VER=%%v
if "%VER%"=="" set VER=0.0.0

set "DIST_DIR=dist"
set "EXE_NAME=lan-invoice_%VER%"

echo ============================================================
echo     lan-invoice v%VER% 一键打包
echo ============================================================
echo.

:: ---- 检查 Python 环境 ----
uv run python -c "" 2>nul
if %errorlevel% neq 0 (
    echo [错误] uv/python 环境异常
    pause
    exit /b 1
)

:: ---- [1/2] PyInstaller 打包便携版 ----
echo [1/2] PyInstaller 打包便携版...
echo.

uv run pyinstaller ^
    --name="%EXE_NAME%" ^
    --windowed ^
    --onefile ^
    --paths=src ^
    --icon=icon.ico ^
    --add-data="src/ui/icons;ui/icons" ^
    --hidden-import=ui.theme ^
    --hidden-import=ui.dialogs.pdf_viewer ^
    --hidden-import=ui.dialogs.add_attachment ^
    --hidden-import=ui.dialogs.attachment_viewer ^
    --hidden-import=ui.dialogs.image_viewer ^
    --hidden-import=ui.dialogs.settings ^
    --hidden-import=ui.dialogs.delete_confirm ^
    --hidden-import=ui.dialogs.contract_manager ^
    --hidden-import=ui.dialogs.invoice_manager ^
    --hidden-import=ui.dialogs.import_preview ^
    --hidden-import=ui.widgets.strategy_card ^
    --hidden-import=services.export_service ^
    --hidden-import=services.invoice_service ^
    --hidden-import=database ^
    --hidden-import=backup ^
    --hidden-import=config_manager ^
    --hidden-import=invoice_parser ^
    --hidden-import=models ^
    --hidden-import=repository ^
    --hidden-import=filters ^
    --hidden-import=utils ^
    --hidden-import=worker ^
    --hidden-import=logger ^
    --hidden-import=version ^
    --hidden-import=storage ^
    --hidden-import=mcp_server ^
    --hidden-import=pdfplumber ^
    --hidden-import=openpyxl ^
    --hidden-import=docx ^
    --hidden-import=mammoth ^
    --hidden-import=matplotlib ^
    --hidden-import=matplotlib.backends.backend_qt5agg ^
    --exclude-module=tkinter ^
    --exclude-module=PyQt5.QtMultimedia ^
    --exclude-module=PyQt5.QtWebEngine ^
    --exclude-module=PyQt5.QtBluetooth ^
    --exclude-module=PyQt5.QtNfc ^
    --exclude-module=PyQt5.QtQuick ^
    --exclude-module=PyQt5.QtSvg ^
    --exclude-module=PyQt5.QtTest ^
    --exclude-module=PyQt5.QtXml ^
    --exclude-module=PyQt5.QtSql ^
    --clean ^
    --noconfirm ^
    src\invoice_tool.py

if %errorlevel% neq 0 (
    echo.
    echo [失败] PyInstaller 打包出错！
    pause
    exit /b 1
)

echo   [OK] 便携版: %DIST_DIR%\%EXE_NAME%.exe

:: ---- [2/2] 安装包 ----
echo.
echo [2/2] 创建安装包...
echo.

uv run python scripts\create_installer.py
if %errorlevel% neq 0 (
    echo   [WARN] 安装包创建失败（便携版已就绪）
) else (
    echo   [OK] 安装包已就绪
)

:: ---- 完成 ----
echo.
echo ============================================================
echo   打包完成！
echo.
dir /b %DIST_DIR%\*.exe 2>nul
echo ============================================================
echo.
echo   便携版: %EXE_NAME%.exe（直接运行）
echo   安装包: %EXE_NAME%_setup.exe（安装到 Program Files）

endlocal
pause
