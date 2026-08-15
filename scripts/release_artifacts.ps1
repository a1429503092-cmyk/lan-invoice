# 发票归档 — 生成 Inno Setup 安装脚本（Nuitka standalone 产物）
# 由 GitHub Actions workflow（build-installer job）调用，也可本地手动运行：
#   pwsh -File scripts/release_artifacts.ps1
# 前置：dist/invoice_tool.dist/（Nuitka --mode=standalone --output-dir=dist 产物）

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# 读取版本号
$ver = (Get-Content "src/version.py" | Select-String 'APP_VERSION = "([^"]+)"').Matches[0].Groups[1].Value
if (-not $ver) {
    throw "无法从 src/version.py 读取版本号"
}
Write-Host "Version: $ver"

# 生成 Inno Setup 脚本
# 安装 Nuitka standalone 目录（invoice_tool.dist/*），启动免解压（0.2s vs
# onefile 2.15s）。EXE 固定名 lan-invoice.exe：MCP 配置/快捷方式指向固定
# 路径，覆盖更新后无需改动；同时清理旧版本号命名的遗留 EXE
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
CloseApplications=yes

[InstallDelete]
Type: files; Name: "{app}\lan-invoice_*.exe"

[Files]
Source: "invoice_tool.dist\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\发票归档"; Filename: "{app}\lan-invoice.exe"
Name: "{commondesktop}\发票归档"; Filename: "{app}\lan-invoice.exe"

[Run]
Filename: "{app}\lan-invoice.exe"; Description: "启动 发票归档"; Flags: nowait postinstall
"@
Set-Content -Path "dist/setup.iss" -Value $iss -Encoding UTF8
Write-Host "Generated dist/setup.iss for v$ver"
