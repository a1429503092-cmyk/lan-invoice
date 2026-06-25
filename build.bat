@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: ============================================================
::  发票归档工具 — 一键打包脚本
::  用法：双击运行，或在命令行执行 build.bat
::  输出：
::    dist\发票归档_x.x.x.exe          便携版
::    dist\发票归档_x.x.x_setup.exe    安装包
:: ============================================================

:: ---- 获取版本号 ----
".venv\Scripts\python.exe" -c "import sys; sys.path.insert(0,'src'); from version import APP_VERSION; print(APP_VERSION)" > "%TEMP%\iver.txt" 2>nul
set /p VER=<"%TEMP%\iver.txt"
del "%TEMP%\iver.txt" 2>nul
if "%VER%"=="" set VER=0.0.0
set "EXE_NAME=发票归档_%VER%"

echo ============================================================
echo     %EXE_NAME% 一键打包
echo ============================================================
echo.

:: ---- 检查虚拟环境 ----
if not exist ".venv\Scripts\python.exe" (
    echo [错误] 未找到 .venv，请先运行: uv sync
    pause
    exit /b 1
)

:: ---- 步骤1: PyInstaller 打包便携版 ----
echo [1/2] PyInstaller 打包便携版...
echo.

".venv\Scripts\python.exe" -m PyInstaller ^
    --name="%EXE_NAME%" ^
    --windowed ^
    --onefile ^
    --paths=src ^
    --icon=icon.ico ^
    --add-data="src/ui/icons;ui/icons" ^
    --clean ^
    --noconfirm ^
    src\invoice_tool.py

if %errorlevel% neq 0 (
    echo.
    echo ============================================================
    echo   [失败] PyInstaller 打包出错！
    echo ============================================================
    pause
    exit /b 1
)

echo.
echo   [OK] 便携版: dist\%EXE_NAME%.exe

:: ---- 步骤2: 创建安装包 ----
echo.
echo [2/2] 创建安装包...
echo.

".venv\Scripts\python.exe" scripts\create_installer.py

if %errorlevel% neq 0 (
    echo   [WARN] 安装包创建失败（便携版已就绪）
) else (
    echo   [OK] 安装包已就绪
)

:: ---- 验证启动 ----
echo.
echo [验证] 启动便携版验证...
start "" "dist\%EXE_NAME%.exe"

:: ---- 完成 ----
echo.
echo ============================================================
echo   打包完成！
echo.
dir /b dist\*.exe 2>nul
echo ============================================================
echo.
echo   %EXE_NAME%.exe       便携版，直接运行
echo   %EXE_NAME%_setup.exe 安装包，安装到 Program Files

endlocal
pause
