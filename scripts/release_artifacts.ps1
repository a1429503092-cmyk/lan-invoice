# 发票归档 — 生成发布产物（便携版 EXE 副本 + Inno Setup 脚本）
# 由 GitHub Actions workflow 调用，也可本地手动运行：
#   pwsh -File scripts/release_artifacts.ps1

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# 读取版本号
$ver = (Get-Content "src/version.py" | Select-String 'APP_VERSION = "([^"]+)"').Matches[0].Groups[1].Value
if (-not $ver) {
    throw "无法从 src/version.py 读取版本号"
}
Write-Host "Version: $ver"

# 便携版副本
Copy-Item "dist/lan-invoice.exe" "dist/lan-invoice_$ver.exe" -Force

# ASCII 文件名（Inno Setup 编译用，避免中文/点号问题）
$ascii = "lan_invoice_" + ($ver -replace '\.', '_') + ".exe"
Copy-Item "dist/lan-invoice_$ver.exe" "dist/$ascii" -Force

# 生成 Inno Setup 脚本
$iss = @"
; Inno Setup Script - auto-generated v$ver
[Setup]
AppName=发票归档
AppVersion=$ver
AppPublisher=GUYI33
DefaultDirName={pf}\lan-invoice
DefaultGroupName=发票归档
Compression=lzma2/ultra64
SolidCompression=yes
UninstallDisplayName=发票归档
OutputDir=./
OutputBaseFilename=lan-invoice_${ver}_setup

[Files]
Source: "$ascii"; DestDir: "{app}"; DestName: "lan-invoice_$ver.exe"

[Icons]
Name: "{group}\发票归档"; Filename: "{app}\lan-invoice_$ver.exe"
Name: "{commondesktop}\发票归档"; Filename: "{app}\lan-invoice_$ver.exe"

[Run]
Filename: "{app}\lan-invoice_$ver.exe"; Description: "启动 发票归档"; Flags: nowait postinstall
"@
Set-Content -Path "dist/setup.iss" -Value $iss -Encoding UTF8
Write-Host "Generated dist/setup.iss for v$ver"
