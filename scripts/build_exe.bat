@echo off
chcp 65001 >nul
echo ==============================================
echo          发票归档工具 - 打包脚本
echo ==============================================
echo.

:: 检查是否存在虚拟环境
if not exist ".venv\Scripts\python.exe" (
    echo 错误：未找到虚拟环境，请先安装依赖！
    pause
    exit /b 1
)

:: 激活虚拟环境并执行打包
echo 正在激活虚拟环境并执行打包...
echo.

".venv\Scripts\python.exe" -m PyInstaller invoice_tool.spec --clean

if %errorlevel% equ 0 (
    echo.
    echo ==============================================
    echo              打包成功！
    echo ==============================================
    echo 输出目录：dist\发票归档工具
    echo.
    echo 运行方式：
    echo   1. 进入 dist\发票归档工具 目录
    echo   2. 双击 发票归档工具.exe 运行
    echo.
) else (
    echo.
    echo ==============================================
    echo              打包失败！
    echo ==============================================
    echo 请检查错误信息并修复问题。
    echo.
)

pause
