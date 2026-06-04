# -*- coding: utf-8 -*-
"""
UI 主题 — 冷色系：冰蓝 + 钢灰
"""

# ── 色彩 ──────────────────────────────────────

ACCENT    = "#2879D0"   # 经典蓝
ACCENT_LIGHT = "#E8F1FB" # 浅蓝底

WHITE     = "#FFFFFF"
BG        = "#F2F4F6"   # 灰底
BG_ALT    = "#F8F9FA"   # 交替行
BG_HOVER  = "#EBEEF1"   # 悬浮
BG_SELECT = "#E3EDF7"   # 选中

BORDER    = "#CFD4DA"   # 边框
BORDER_LIGHT = "#E0E3E7"

TEXT      = "#1A2130"
TEXT_SEC  = "#5C6778"
TEXT_DIM  = "#657180"

RED       = "#DC2626"
GREEN     = "#16A34A"
ACCENT_BORDER = "#C5D4E8"   # 浅蓝底边框

# 暗色主题（沉浸式预览窗口：PDF 查看器、图片查看器）
DARK_BG            = "#1E1E1E"
DARK_SURFACE       = "#2B2B2B"
DARK_SURFACE_ALT   = "#353535"
DARK_BORDER        = "#444444"
DARK_HOVER         = "#3A3A3A"
DARK_HOVER_BORDER  = "#666666"
DARK_TEXT          = "#E0E0E0"
DARK_TEXT_DIM      = "#666666"
DARK_RED           = "#EF4444"

# ── 字体 ──────────────────────────────────────

FONT      = "Microsoft YaHei"
MONO_FONT = "Consolas"
FS_SM     = "11px"
FS        = "13px"
FS_LG     = "15px"
FS_XL     = "17px"

# ── 全局样式 ──────────────────────────────────

GLOBAL_QSS = f"""
QMainWindow {{
    background: {BG};
}}

QPushButton {{
    border: 1px solid {BORDER};
    padding: 5px 14px;
    background: {WHITE};
    color: {TEXT};
    font-size: {FS};
    font-family: "{FONT}";
    font-weight: 500;
}}
QPushButton:hover {{
    background: {BG_HOVER};
    border-color: {TEXT_DIM};
}}
QPushButton:pressed {{
    background: {BORDER_LIGHT};
}}
QPushButton:disabled {{
    background: {BG_ALT};
    color: {TEXT_DIM};
    border-color: {BORDER_LIGHT};
}}

QLineEdit {{
    border: 1px solid {BORDER};
    padding: 4px 8px;
    font-size: {FS};
    font-family: "{FONT}";
    background: {WHITE};
    color: {TEXT};
    font-weight: 500;
}}
QLineEdit:focus {{
    border-color: {ACCENT};
}}

QComboBox {{
    border: 1px solid {BORDER};
    padding: 3px 8px;
    font-size: {FS};
    font-family: "{FONT}";
    background: {WHITE};
    color: {TEXT};
    font-weight: 500;
}}
QComboBox:hover {{
    border-color: {TEXT_DIM};
}}
QComboBox::drop-down {{
    width: 18px;
    border: none;
    border-left: 1px solid {BORDER_LIGHT};
}}
QComboBox QAbstractItemView {{
    border: 1px solid {BORDER};
    background: {WHITE};
    selection-background-color: {BG_SELECT};
    selection-color: {TEXT};
    outline: none;
}}
"""

TABLE_QSS = f"""
QTableWidget {{
    font-size: {FS};
    gridline-color: transparent;
    background: {WHITE};
    border: 1px solid {BORDER};
    outline: none;
}}
QTableWidget:focus {{
    outline: none;
}}
QHeaderView::section {{
    background: {ACCENT};
    color: white;
    font-weight: 600;
    font-size: {FS};
    padding: 7px 8px;
    border: none;
    border-right: 1px solid rgba(255,255,255,0.15);
}}
QTableWidget::item {{
    padding: 5px 8px;
    background: {WHITE};
}}
QTableWidget::item:alternate {{
    background: {BG_ALT};
}}
QTableWidget::item:selected {{
    background: {ACCENT_LIGHT};
    color: {TEXT};
    border: none;
    outline: none;
}}
QTableWidget::item:focus {{
    outline: none;
    border: none;
    background: transparent;
}}
QTableWidget::item:hover:!selected {{
    background: {BG_HOVER};
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

DIALOG_QSS = f"""
QDialog {{
    background: {BG};
}}
"""

DIALOG_QSS_DARK = f"""
QDialog {{ background: {DARK_BG}; }}
QPushButton {{
    border: 1px solid {DARK_BORDER}; padding: 5px 14px;
    background: {DARK_SURFACE}; color: {DARK_TEXT};
    font-size: 13px; font-family: "{FONT}";
}}
QPushButton:hover {{
    background: {DARK_HOVER}; border-color: {DARK_HOVER_BORDER};
}}
QPushButton:pressed {{
    background: {DARK_SURFACE_ALT};
}}
QPushButton:disabled {{
    background: {DARK_SURFACE}; color: {DARK_TEXT_DIM};
    border-color: {DARK_BORDER};
}}
"""
