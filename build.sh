#!/usr/bin/env bash
# ============================================================
#  发票归档 — 一键打包（便携版 + 安装包）
#  用法：bash build.sh
# ============================================================

set -euo pipefail

cd "$(dirname "$0")"

# ---- 版本号 ----
VER=$(uv run python -c "from src.version import APP_VERSION; print(APP_VERSION)" 2>/dev/null || echo "0.0.0")
EXE_NAME="发票归档_${VER}"
DIST_DIR="dist"

echo "============================================================"
echo "    发票归档 v${VER} 一键打包"
echo "============================================================"
echo ""

# ---- [1/2] PyInstaller 打包便携版 ----
echo "[1/2] PyInstaller 打包便携版..."

uv run pyinstaller \
    --name="${EXE_NAME}" \
    --windowed \
    --onefile \
    --paths=src \
    --icon=icon.ico \
    --add-data="src/ui/icons;ui/icons" \
    --hidden-import=ui.theme \
    --hidden-import=ui.dialogs.pdf_viewer \
    --hidden-import=ui.dialogs.add_attachment \
    --hidden-import=ui.dialogs.attachment_viewer \
    --hidden-import=ui.dialogs.image_viewer \
    --hidden-import=ui.dialogs.settings \
    --hidden-import=ui.dialogs.delete_confirm \
    --hidden-import=ui.dialogs.contract_manager \
    --hidden-import=ui.dialogs.invoice_manager \
    --hidden-import=ui.dialogs.import_preview \
    --hidden-import=ui.widgets.strategy_card \
    --hidden-import=services.export_service \
    --hidden-import=services.invoice_service \
    --hidden-import=database \
    --hidden-import=backup \
    --hidden-import=config_manager \
    --hidden-import=invoice_parser \
    --hidden-import=models \
    --hidden-import=repository \
    --hidden-import=filters \
    --hidden-import=utils \
    --hidden-import=worker \
    --hidden-import=logger \
    --hidden-import=version \
    --hidden-import=storage \
    --hidden-import=mcp_server \
    --hidden-import=pdfplumber \
    --hidden-import=openpyxl \
    --hidden-import=docx \
    --hidden-import=mammoth \
    --hidden-import=matplotlib \
    --hidden-import=matplotlib.backends.backend_qt5agg \
    --exclude-module=tkinter \
    --exclude-module=PyQt5.QtMultimedia \
    --exclude-module=PyQt5.QtWebEngine \
    --exclude-module=PyQt5.QtBluetooth \
    --exclude-module=PyQt5.QtNfc \
    --exclude-module=PyQt5.QtQuick \
    --exclude-module=PyQt5.QtSvg \
    --exclude-module=PyQt5.QtTest \
    --exclude-module=PyQt5.QtXml \
    --exclude-module=PyQt5.QtSql \
    --clean \
    --noconfirm \
    src/invoice_tool.py

echo "  [OK] 便携版: ${DIST_DIR}/${EXE_NAME}.exe"
echo ""

# ---- [2/2] 安装包 ----
echo "[2/2] 创建安装包..."
uv run python scripts/create_installer.py && echo "  [OK] 安装包已就绪" || echo "  [WARN] 安装包创建失败（便携版已就绪）"

echo ""
echo "============================================================"
echo "  打包完成！"
ls -lh "${DIST_DIR}"/*.exe 2>/dev/null || true
echo "============================================================"
