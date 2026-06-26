# -*- coding: utf-8 -*-
"""UI 主题 — 最小化：仅保留必要的颜色常量和关键 QSS，其余交由 Qt Fusion 默认样式"""

# ── 色彩 ──────────────────────────────────────

ACCENT = "#2879D0"
ACCENT_LIGHT = "#E8F1FB"
RED = "#DC2626"
GREEN = "#16A34A"
WHITE = "#FFFFFF"
BG_ALT = "#F8F9FA"
TEXT = "#1A2130"
TEXT_SEC = "#5C6778"
TEXT_DIM = "#657180"
BORDER = "#CFD4DA"
BORDER_LIGHT = "#E0E3E7"
FS = "13px"
MONO_FONT = "Consolas"

# 暗色预览用
DARK_BG = "#1E1E1E"
DARK_SURFACE = "#2B2B2B"
DARK_BORDER = "#444444"
DARK_HOVER = "#3A3A3A"
DARK_TEXT = "#E0E0E0"
DARK_TEXT_DIM = "#666666"

# ── 关键 QSS（仅表单元素和表格，不含全局按钮/输入框）─────────────────

TABLE_QSS = f"""
QHeaderView::section {{
    background: {ACCENT};
    color: white;
    font-weight: 600;
    padding: 6px 8px;
    border: none;
    border-right: 1px solid rgba(255,255,255,0.15);
}}
QTableWidget {{
    gridline-color: {BORDER_LIGHT};
}}
QTableWidget::item:selected {{
    background: {ACCENT_LIGHT};
    color: {TEXT};
}}
"""

PROGRESS_QSS = f"""
QProgressBar {{
    border: none;
    background: {BORDER_LIGHT};
    height: 4px;
}}
QProgressBar::chunk {{
    background: {ACCENT};
}}
"""

SUMMARY_FRAME_QSS = f"""
QFrame {{
    background: {WHITE};
    border: 1px solid {BORDER_LIGHT};
    border-radius: 6px;
}}
"""

DIALOG_QSS = ""

DIALOG_QSS_DARK = f"""
QDialog {{ background: {DARK_BG}; }}
QPushButton {{
    border: 1px solid {DARK_BORDER}; padding: 5px 14px;
    background: {DARK_SURFACE}; color: {DARK_TEXT};
}}
QPushButton:hover {{ background: {DARK_HOVER}; }}
QPushButton:disabled {{
    background: {DARK_SURFACE}; color: {DARK_TEXT_DIM};
    border-color: {DARK_BORDER};
}}
"""
