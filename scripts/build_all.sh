#!/usr/bin/env bash
# ============================================================
#  发票归档 — 容器内一键打包（Wine 交叉编译 Windows 产物）
#
#  用法（Docker）：
#    docker build -t lan-invoice-builder -f Dockerfile.build .
#    docker run --rm -v $PWD:/src -v $PWD/dist:/out lan-invoice-builder
#
#  产物：/out/lan-invoice_X.Y.Z.exe（便携版）+ _setup.exe（安装包）
# ============================================================

set -euo pipefail

cd /src

PY="C:\\Python312\\python.exe"
ISCC="C:\\Program Files (x86)\\Inno Setup 6\\ISCC.exe"

echo "==== [1/4] 读取版本号 ===="
VER=$(wine "$PY" -c "import sys; sys.path.insert(0,'src'); from version import APP_VERSION; print(APP_VERSION)" | tr -d '\r')
echo "版本: $VER"

echo "==== [2/4] PyInstaller 打包便携版（Wine）===="
wine "$PY" -m PyInstaller "发票归档.spec" --clean --noconfirm
cp dist/lan-invoice.exe "dist/lan-invoice_${VER}.exe"

echo "==== [3/4] Inno Setup 编译安装包（Wine）===="
ASCII=$(echo "lan_invoice_${VER}" | tr '.' '_')
cp "dist/lan-invoice_${VER}.exe" "dist/${ASCII}.exe"
cat > dist/setup.iss <<EOF
; Inno Setup Script — auto-generated v$VER
[Setup]
AppName=发票归档
AppVersion=$VER
AppPublisher=GUYI33
DefaultDirName={pf}\\lan-invoice
DefaultGroupName=发票归档
Compression=lzma2/ultra64
SolidCompression=yes
UninstallDisplayName=发票归档
OutputDir=./
OutputBaseFilename=lan-invoice_${VER}_setup

[Files]
Source: "${ASCII}.exe"; DestDir: "{app}"; DestName: "lan-invoice_${VER}.exe"

[Icons]
Name: "{group}\\发票归档"; Filename: "{app}\\lan-invoice_${VER}.exe"
Name: "{commondesktop}\\发票归档"; Filename: "{app}\\lan-invoice_${VER}.exe"

[Run]
Filename: "{app}\\lan-invoice_${VER}.exe"; Description: "启动 发票归档"; Flags: nowait postinstall
EOF
wine "$ISCC" "Z:\\src\\dist\\setup.iss" || true  # Wine 下输出中文名可能乱码，文件仍在

echo "==== [4/4] 修复文件名 + 拷贝到 /out ===="
# Wine 写中文文件名可能乱码，用 ASCII 输出名兜底重命名
for f in dist/lan-invoice_${VER}_setup*.exe dist/InvoiceArchive*.exe; do
    [ -f "$f" ] && mv "$f" "dist/lan-invoice_${VER}_setup.exe" && break
done
rm -f "dist/${ASCII}.exe" dist/setup.iss
mkdir -p /out
cp "dist/lan-invoice_${VER}.exe" "dist/lan-invoice_${VER}_setup.exe" /out/

echo "==== 打包完成 ===="
ls -lh /out/
