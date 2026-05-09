@echo off
chcp 65001 >nul
setlocal

REM ── 便携版启动脚本 ─────────────────────────────────────────────────────
REM 优先使用同目录下的 python 环境（便携Python），否则使用系统 PATH 中的 python

set SCRIPT_DIR=%~dp0
set PORTABLE_PY=%SCRIPT_DIR%python\python.exe

if exist "%PORTABLE_PY%" (
    echo [INFO] 使用便携 Python: %PORTABLE_PY%
    "%PORTABLE_PY%" "%SCRIPT_DIR%invoice_tool.py"
) else (
    REM 使用系统 Python
    where python >nul 2>&1
    if %errorlevel%==0 (
        python "%SCRIPT_DIR%invoice_tool.py"
    ) else (
        echo [错误] 未找到 Python，请先安装 Python 3.9+ 并将其加入 PATH
        echo 或将便携版 Python 放置于软件目录下的 python\ 子文件夹中
        pause
        exit /b 1
    )
)

endlocal
