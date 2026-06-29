# -*- coding: utf-8 -*-
"""
发票归档
功能：发票PDF识别、附件管理、按月筛选、导出Excel
"""

import sys
import os
import re
import shutil
import time
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QTableWidget, QTableWidgetItem,
    QFileDialog, QMessageBox, QHeaderView, QStatusBar, QFrame,
    QProgressBar, QAbstractItemView, QDialog,
    QComboBox, QMenu, QSizePolicy
)
from PyQt5 import QtCore
from PyQt5.QtCore import Qt, QTimer, QUrl, QEvent
from PyQt5.QtGui import QColor, QDesktopServices, QDragEnterEvent, QDropEvent, QFont, QFontDatabase

from dialogs import SettingsDialog, DeleteConfirmDialog
from worker import ParseWorker
from filters import (record_matches_filter, get_available_years,
                     get_available_inv_types, get_available_sellers)
from models import Invoice
from database import Database
from backup import BackupService
from config_manager import ConfigManager
from utils import safe_float
from services.invoice_service import InvoiceService
from update_checker import UpdateChecker
from ui.icons import get as get_icon
from ui.theme import (TABLE_QSS, PROGRESS_QSS, SUMMARY_FRAME_QSS,
                       ACCENT, ACCENT_LIGHT, RED, WHITE,
                       TEXT, TEXT_SEC, TEXT_DIM,
                       BORDER, BORDER_LIGHT, MONO_FONT, FS)
from version import APP_VERSION
from logger import setup_logging, shutdown_logging, getLogger
log = getLogger(__name__)


# 表格列定义
COLUMNS = ["发票类型", "购买方名称", "纳税人识别号",
           "销售方名称", "金额(元)", "征收率", "税额(元)", "价税合计(元)",
           "发票号码", "开票日期", "附件", "备注"]
TABLE_ROW_HEIGHT = 36
FREEZE_COL_WIDTH = 110  # 冻结操作列宽度
COL_IDX = {c: i for i, c in enumerate(COLUMNS)}

# 支持的文件扩展名
IMG_EXTS = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.tiff', '.tif'}
ATTACH_EXTS = {'.pdf', '.docx', '.doc', '.xlsx', '.xls'}  # 附件文档格式


class InvoiceApp(QMainWindow):

    def __init__(self):
        super().__init__()
        self.records = []
        self._current_col_idx = COL_IDX
        self._duplicate_invoices = []
        log.info("InvoiceApp 初始化开始")

        # 配置文件路径：%APPDATA%\lan-invoice\config.json
        appdata = os.environ.get('APPDATA', os.path.expanduser('~'))
        self._config = ConfigManager(os.path.join(appdata, 'lan-invoice', 'config.json'))
        self._tag_templates = self._config.tag_templates

        # 读取/初始化数据目录（直接存储 _data_dir，不再嵌套 data 子目录）
        self._data_dir = self._init_data_dir()
        self._data_file      = os.path.join(self._data_dir, "invoices.db")
        self._attachment_dir = self._data_dir
        os.makedirs(self._data_dir, exist_ok=True)

        # SQLite + 备份
        self._db = Database(self._data_file)
        self._backup = BackupService()
        self._init_storage()

        self._svc = InvoiceService(self._db, self._backup, self._config,
                                    self._data_dir, os.path.join(self._data_dir, "invoices"))
        self._svc.enable_webdav_sync(True)

        self._filter_year        = None
        self._filter_month       = None
        self._filter_inv_type    = None   # 发票类型筛选
        self._filter_seller      = None   # 销售方名称筛选
        self._filter_company     = ""     # 企业号搜索（模糊匹配）
        self._filter_buyer       = ""     # 购买方名称/税号搜索（模糊匹配）
        self._show_advanced_filter = False
        self._shown_records = []   # 当前筛选后的记录缓存，_rebuild_table 时更新
        self._sort_column = None
        self._sort_ascending = True
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.timeout.connect(self._apply_filter)

        # 定时备份策略
        self._backup_timer = QTimer(self)
        self._backup_timer.timeout.connect(self._check_scheduled_backups)
        self._backup_timer.start(60_000)  # 每分钟检查一次
        self._last_scheduled_backup: dict[str, float] = {"local": 0, "webdav": 0}

        self._init_ui()
        self.setAcceptDrops(True)
        self._load_data()
        log.info("InvoiceApp 初始化完成 | 版本=%s | 数据目录=%s",
                 APP_VERSION, self._data_dir)
        QTimer.singleShot(500, self._check_desktop_shortcut)
        self._update_checker = UpdateChecker(APP_VERSION, self)
        self._update_checker.new_version_found.connect(self._on_new_version)
        self._update_checker.check_finished.connect(self._on_check_finished)
        QTimer.singleShot(3000, self._update_checker.check)
        self._manual_check_pending = False

    # ── 记录辅助方法 ────────────────────────────

    def _init_data_dir(self):
        """确定数据目录：优先用配置中保存的路径，否则用默认"""
        configured = self._config.data_dir
        if configured and os.path.isdir(configured):
            return configured
        default_dir = os.path.join(os.path.dirname(self._config.path), "data")
        # 旧版配置迁移：项目根目录 config.json → %APPDATA%\lan-invoice\
        old_config = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "config.json"
        )
        if os.path.exists(old_config) and not os.path.exists(self._config.path):
            try:
                os.makedirs(os.path.dirname(self._config.path), exist_ok=True)
                shutil.copy2(old_config, self._config.path)
            except OSError:
                pass
        return default_dir

    def _init_storage(self):
        """初始化存储：迁移旧 JSON → 完整性检查 → 自动恢复"""
        json_path = os.path.join(self._data_dir, "invoices_data.json")
        if os.path.exists(json_path):
            migrated = self._db.migrate_from_json(json_path)
            if migrated > 0:
                log.info("已从 JSON 迁移 %d 条记录到 SQLite", migrated)
        if not self._db.integrity_check():
            log.warning("数据库完整性检查失败，尝试从备份恢复…")
            if self._backup.restore(self._db.data_file):
                log.info("已从备份恢复数据库")
            else:
                # 尝试从 JSON 备份文件重新迁移
                bak_path = json_path + ".bak"
                if os.path.exists(bak_path):
                    log.info("尝试从 JSON 备份重新迁移…")
                    try:
                        os.remove(self._db.data_file)
                    except OSError:
                        pass
                    self._db = Database(self._db.data_file)
                    migrated = self._db.migrate_from_json(bak_path)
                    if migrated > 0:
                        log.info("已从 JSON 备份恢复 %d 条记录", migrated)
                        return
                log.warning("无可用备份，重建空数据库")
                try:
                    os.remove(self._db.data_file)
                except OSError:
                    pass
                self._db = Database(self._db.data_file)

    def _init_record_fields(self, data):
        """统一初始化记录字段默认值；红票金额转负数"""
        if isinstance(data, Invoice):
            data.ensure_defaults()
            return
        # 兼容旧 dict（逐步淘汰）
        for field in ("pdf_path", "invoice_type", "seller_name", "remark"):
            data.setdefault(field, "")
        data.setdefault("attachments", [])
        data.setdefault("tags", {})
        data.setdefault("is_red", False)
        if data.get("is_red"):
            for f in ("amount", "tax_amount", "total"):
                v = data.get(f, "")
                if v and not str(v).startswith('-'):
                    data[f] = '-' + str(v)

    def _find_record_index(self, inv_no: str):
        """在 self.records 中按发票号码查找索引，返回 int 或 None"""
        if not inv_no:
            return None
        for i, r in enumerate(self.records):
            no = r.invoice_no if isinstance(r, Invoice) else r.get("invoice_no", "")
            if no == inv_no:
                return i
        return None

    # ── UI 构建 ─────────────────────────────────
    def _init_ui(self):
        self.setWindowTitle(f"发票归档 v{APP_VERSION}")
        self._set_app_icon()
        self.resize(1480, 820)
        self.setMinimumSize(1000, 640)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(12, 12, 12, 8)
        main_layout.setSpacing(12)

        # ── 工具栏第一行 ──────────────────────────
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        self.btn_open = QPushButton(" 导入发票PDF")
        self.btn_open.setIcon(get_icon('folder'))
        self.btn_open.setFixedHeight(36)
        self.btn_open.setToolTip("选择一个或多个PDF发票文件（也可直接拖拽PDF到窗口）")
        self.btn_open.clicked.connect(self.open_files)

        self.btn_settings = QPushButton(" 设置")
        self.btn_settings.setIcon(get_icon('settings'))
        self.btn_settings.setFixedHeight(36)
        self.btn_settings.setToolTip("数据目录设置")
        self.btn_settings.clicked.connect(self._open_settings)

        self.btn_export = QPushButton(" 导出 Excel")
        self.btn_export.setIcon(get_icon('export'))
        self.btn_export.setFixedHeight(36)
        self.btn_export.clicked.connect(self.export_excel)

        top_bar.addWidget(self.btn_open)
        top_bar.addWidget(self.btn_settings)
        top_bar.addStretch()
        top_bar.addSpacing(12)
        top_bar.addWidget(self.btn_export)
        main_layout.addLayout(top_bar)

        # ── 工具栏第二行：多维筛选 ───────────────
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(8)

        filter_bar.addWidget(QLabel("筛选："))

        self.combo_year = QComboBox()
        self.combo_year.setFixedWidth(90)
        self.combo_year.addItem("全部", None)
        filter_bar.addWidget(QLabel("年份"))
        filter_bar.addWidget(self.combo_year)

        self.combo_month = QComboBox()
        self.combo_month.setFixedWidth(80)
        self.combo_month.addItem("全部", None)
        for i in range(1, 13):
            self.combo_month.addItem(f"{i:02d} 月", i)
        filter_bar.addWidget(QLabel("月份"))
        filter_bar.addWidget(self.combo_month)

        self.combo_year.currentIndexChanged.connect(self._apply_filter)
        self.combo_month.currentIndexChanged.connect(self._apply_filter)

        self.btn_advanced_filter = QPushButton("▸ 高级筛选")
        self.btn_advanced_filter.setFlat(True)
        self.btn_advanced_filter.clicked.connect(self._toggle_advanced_filter)

        self.btn_reset = QPushButton("清除筛选")
        self.btn_reset.clicked.connect(self._reset_filter)

        self.lbl_filter_hint = QLabel("")

        filter_bar.addWidget(self.btn_advanced_filter)
        filter_bar.addWidget(self.btn_reset)
        filter_bar.addStretch()
        filter_bar.addWidget(self.lbl_filter_hint)
        main_layout.addLayout(filter_bar)

        # ── 高级筛选面板（默认隐藏）───────────────
        self._advanced_filter_frame = QFrame()
        self._advanced_filter_frame.setVisible(False)
        adv_layout = QHBoxLayout(self._advanced_filter_frame)
        adv_layout.setContentsMargins(0, 0, 0, 0)
        adv_layout.setSpacing(8)

        adv_layout.addWidget(QLabel("发票类型"))
        self.combo_inv_type = QComboBox()
        self.combo_inv_type.setMinimumWidth(100)
        self.combo_inv_type.addItem("全部", None)

        adv_layout.addWidget(QLabel("销售方"))
        self.combo_seller = QComboBox()
        self.combo_seller.setMinimumWidth(120)
        self.combo_seller.addItem("全部", None)

        self.combo_inv_type.currentIndexChanged.connect(self._apply_filter)
        self.combo_seller.currentIndexChanged.connect(self._apply_filter)

        adv_layout.addWidget(QLabel("购买方"))
        self.edit_buyer_search = QLineEdit()
        self.edit_buyer_search.setPlaceholderText("名称或税号")
        self.edit_buyer_search.setMinimumWidth(100)
        self.edit_buyer_search.textChanged.connect(lambda: self._filter_timer.start(300))

        adv_layout.addWidget(QLabel("标签"))
        self.edit_company_search = QLineEdit()
        self.edit_company_search.setPlaceholderText("输入标签搜索")
        self.edit_company_search.setMinimumWidth(100)
        self.edit_company_search.textChanged.connect(lambda: self._filter_timer.start(300))

        adv_layout.addWidget(QLabel("发票类型"))
        adv_layout.addWidget(self.combo_inv_type, 1)
        adv_layout.addWidget(QLabel("销售方"))
        adv_layout.addWidget(self.combo_seller, 1)
        adv_layout.addWidget(QLabel("购买方"))
        adv_layout.addWidget(self.edit_buyer_search, 2)
        adv_layout.addWidget(QLabel("标签"))
        adv_layout.addWidget(self.edit_company_search, 2)
        adv_layout.addStretch()
        main_layout.addWidget(self._advanced_filter_frame)

        # ── 进度条 ───────────────────────────────
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(PROGRESS_QSS)
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        # ── 统计汇总栏 ───────────────────────────
        self.summary_frame = QFrame()
        self.summary_frame.setFrameShape(QFrame.StyledPanel)
        sum_layout = QHBoxLayout(self.summary_frame)
        sum_layout.setContentsMargins(0, 0, 0, 0)
        sum_layout.setSpacing(0)

        self.lbl_count     = self._stat_label("发票总数", "0 张")
        self.lbl_total_amt = self._stat_label("金额合计", "¥ 0.00")
        self.lbl_total_tax = self._stat_label("税额合计", "¥ 0.00")
        self.lbl_total_all = self._stat_label("价税合计", "¥ 0.00")

        stat_widgets = [self.lbl_count, self.lbl_total_amt, self.lbl_total_tax, self.lbl_total_all]
        for i, w in enumerate(stat_widgets):
            sum_layout.addWidget(w, 1)
            if i < len(stat_widgets) - 1:
                sep = QFrame()
                sep.setFrameShape(QFrame.VLine)
                sum_layout.addWidget(sep)
        main_layout.addWidget(self.summary_frame)

        # ── 主表格 ───────────────────────────────
        self.table = QTableWidget()
        self.table.setColumnCount(len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.verticalHeader().setDefaultSectionSize(TABLE_ROW_HEIGHT)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        header = self.table.horizontalHeader()
        # 数值类短列：固定宽度
        fixed_cols = {4: 88, 5: 55, 6: 88, 7: 98, 10: 100}
        # 文本类长列：可拖动，但宽度保持不变
        interactive_cols = {0: 110, 1: 180, 2: 200, 3: 170,
                            8: 170, 9: 110, 11: 100}
        for col, width in fixed_cols.items():
            header.setSectionResizeMode(col, QHeaderView.Fixed)
            self.table.setColumnWidth(col, width)
        for col, width in interactive_cols.items():
            header.setSectionResizeMode(col, QHeaderView.Interactive)
            self.table.setColumnWidth(col, width)

        # QHeaderView.Stretch 模式自动管理列宽，无需手动计时器
        self.table.setStyleSheet(TABLE_QSS)

        header.setSortIndicatorShown(True)
        header.sectionClicked.connect(self._on_header_clicked)

        # ── 表格区域：主表格横向滚动，右侧操作列冻结 ──
        table_area = QWidget()
        table_area_layout = QHBoxLayout(table_area)
        table_area_layout.setContentsMargins(0, 0, 0, 0)
        table_area_layout.setSpacing(0)
        table_area_layout.addWidget(self.table, 1)

        self._freeze_table = QTableWidget(table_area)
        self._freeze_table.setColumnCount(1)
        self._freeze_table.setHorizontalHeaderLabels(["操作"])
        self._freeze_table.setFixedWidth(FREEZE_COL_WIDTH)
        self._freeze_table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._freeze_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._freeze_table.verticalHeader().hide()
        self._freeze_table.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self._freeze_table.setColumnWidth(0, FREEZE_COL_WIDTH)
        self._freeze_table.verticalHeader().setDefaultSectionSize(TABLE_ROW_HEIGHT)
        self._freeze_table.setShowGrid(True)
        self._freeze_table.setFocusPolicy(Qt.NoFocus)
        self._freeze_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._freeze_table.setSelectionMode(QAbstractItemView.NoSelection)
        self._freeze_table.setStyleSheet(
            "QTableWidget { border: none; }"
            "QHeaderView::section { border-right: none; }"
        )
        self._freeze_table.hide()
        table_area_layout.addWidget(self._freeze_table, 0)
        main_layout.addWidget(table_area)

        # 同步垂直滚动
        self.table.verticalScrollBar().valueChanged.connect(
            self._freeze_table.verticalScrollBar().setValue)
        self._freeze_table.verticalScrollBar().valueChanged.connect(
            self.table.verticalScrollBar().setValue)

        # ── 空状态引导 ────────────────────────────
        self._empty_overlay = QLabel(self.table.viewport())
        self._empty_overlay.setAlignment(Qt.AlignCenter)
        self._empty_overlay.setWordWrap(True)
        self._empty_overlay.setText(
            "拖拽 PDF 文件到此处导入发票\n"
            "或点击「打开」按钮选择文件"
        )
        self._empty_overlay.hide()
        # 跟随 viewport 居中
        self._recenter_empty_overlay()

        # ── 状态栏 ───────────────────────────────
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage(
            "就绪 — 拖拽 PDF 导入发票 | 选中行后拖拽图片/文档添加附件 | Ctrl+V 粘贴附件")

        # ── 全局搜索条（默认隐藏）────────────────────
        self._search_bar = QWidget(self)
        search_layout = QHBoxLayout(self._search_bar)
        search_layout.setContentsMargins(4, 2, 4, 2)
        search_layout.setSpacing(4)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("搜索…")

        self._search_count = QLabel("")

        btn_search_close = QPushButton("✕")
        btn_search_close.setFlat(True)
        btn_search_close.clicked.connect(self._close_search)

        btn_search_prev = QPushButton("▲")
        btn_search_prev.setFlat(True)
        btn_search_prev.setToolTip("上一个匹配")
        btn_search_prev.clicked.connect(self._prev_search_match)

        btn_search_next = QPushButton("▼")
        btn_search_next.setFlat(True)
        btn_search_next.setToolTip("下一个匹配")
        btn_search_next.clicked.connect(self._next_search_match)

        search_layout.addWidget(QLabel("🔍"))
        search_layout.addWidget(self._search_input, 1)
        search_layout.addWidget(btn_search_prev)
        search_layout.addWidget(btn_search_next)
        search_layout.addWidget(self._search_count)
        search_layout.addWidget(btn_search_close)

        self._search_bar.setGeometry(self.width() - 360, 8, 350, 32)
        self._search_bar.hide()

        self._save_locked = False
        self.table.cellChanged.connect(self._on_cell_changed)
        self.table.clicked.connect(self._on_table_clicked)
        self.table.viewport().installEventFilter(self)

    def _stat_label(self, title, value):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(12, 8, 12, 8)
        v.setSpacing(2)
        lbl_t = QLabel(title)
        lbl_v = QLabel(value)
        v.addWidget(lbl_t)
        v.addWidget(lbl_v)
        w._value_label = lbl_v
        return w

    def _resize_stretch_cols(self):
        if not self._stretch_cols or self._stretch_total_weight == 0:
            return
        available = self.table.viewport().width()
        free = available - self._stretch_fixed_total
        if free <= 0:
            return
        # 最大余数法：避免取整误差累积导致右侧空白
        raw = {}
        remainders = []
        for col, min_w in self._stretch_cols.items():
            exact = free * self._stretch_factors[col] / self._stretch_total_weight
            raw[col] = max(min_w, int(exact))
            remainders.append((col, exact - int(exact)))
        remainders.sort(key=lambda x: x[1], reverse=True)
        for i in range(free - sum(raw.values())):
            raw[remainders[i][0]] += 1
        for col, w in raw.items():
            self.table.setColumnWidth(col, w)

    def _set_app_icon(self):
        from PyQt5.QtGui import QIcon
        import os
        # 打包后从资源路径加载，开发时从文件加载
        paths = [
            os.path.join(os.path.dirname(__file__), "ui", "icons", "app_icon.png"),
            os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "ui", "icons", "app_icon.png"),
            "icon.ico",
        ]
        for p in paths:
            if os.path.exists(p):
                self.setWindowIcon(QIcon(p))
                return

    # ── 筛选条件 ─────────────────────────────────
    def _get_available_years(self):
        return get_available_years(self.records)

    def _get_available_inv_types(self):
        return get_available_inv_types(self.records)

    def _get_available_sellers(self):
        return get_available_sellers(self.records)

    def _refresh_year_combo(self):
        current = self.combo_year.currentData()
        self.combo_year.blockSignals(True)
        self.combo_year.clear()
        self.combo_year.addItem("全部", None)
        for y in self._get_available_years():
            self.combo_year.addItem(str(y), y)
        idx = self.combo_year.findData(current)
        if idx >= 0:
            self.combo_year.setCurrentIndex(idx)
        self.combo_year.blockSignals(False)

    def _refresh_filter_combos(self):
        """动态刷新发票类型、销售方下拉选项（保留当前选中值）"""
        # 发票类型
        cur_type = self.combo_inv_type.currentData()
        self.combo_inv_type.blockSignals(True)
        self.combo_inv_type.clear()
        self.combo_inv_type.addItem("全部", None)
        for t in self._get_available_inv_types():
            self.combo_inv_type.addItem(t, t)
        idx = self.combo_inv_type.findData(cur_type)
        self.combo_inv_type.setCurrentIndex(idx if idx >= 0 else 0)
        self.combo_inv_type.blockSignals(False)

        # 销售方名称
        cur_seller = self.combo_seller.currentData()
        self.combo_seller.blockSignals(True)
        self.combo_seller.clear()
        self.combo_seller.addItem("全部", None)
        for s in self._get_available_sellers():
            self.combo_seller.addItem(s, s)
        idx = self.combo_seller.findData(cur_seller)
        self.combo_seller.setCurrentIndex(idx if idx >= 0 else 0)
        self.combo_seller.blockSignals(False)

        self._refresh_year_combo()

    def _apply_filter(self):
        self._filter_year     = self.combo_year.currentData()
        self._filter_month    = self.combo_month.currentData()
        self._filter_inv_type = self.combo_inv_type.currentData()
        self._filter_seller   = self.combo_seller.currentData()
        self._filter_buyer    = self.edit_buyer_search.text().strip()
        self._filter_company  = self.edit_company_search.text().strip()
        self._rebuild_table()
        parts = []
        if self._filter_year:
            parts.append(f"{self._filter_year}年")
        if self._filter_month:
            parts.append(f"{self._filter_month:02d}月")
        if self._filter_inv_type:
            parts.append(self._filter_inv_type)
        if self._filter_seller:
            parts.append(f"销售方:{self._filter_seller}")
        if self._filter_buyer:
            parts.append(f"购买方:{self._filter_buyer}")
        if self._filter_company:
            parts.append(f"标签:{self._filter_company}")
        self.lbl_filter_hint.setText(f"筛选：{'  '.join(parts)}" if parts else "")

    def _toggle_advanced_filter(self):
        self._show_advanced_filter = not self._show_advanced_filter
        self._advanced_filter_frame.setVisible(self._show_advanced_filter)
        if self._show_advanced_filter:
            self.btn_advanced_filter.setText("▾ 高级筛选")
        else:
            self.btn_advanced_filter.setText("▸ 高级筛选")

    def _reset_filter(self):
        self._filter_year     = None
        self._filter_month    = None
        self._filter_inv_type = None
        self._filter_seller   = None
        self._filter_buyer    = ""
        self._filter_company  = ""
        self.combo_year.setCurrentIndex(0)
        self.combo_month.setCurrentIndex(0)
        self.combo_inv_type.setCurrentIndex(0)
        self.combo_seller.setCurrentIndex(0)
        self.edit_buyer_search.clear()
        self.edit_company_search.clear()
        self.lbl_filter_hint.setText("")
        self._rebuild_table()

    def _record_matches_filter(self, rec) -> bool:
        return record_matches_filter(
            rec, self._filter_year, self._filter_month,
            self._filter_inv_type, self._filter_seller,
            self._filter_buyer, self._filter_company)

    def _on_header_clicked(self, logical_index):
        """列头点击排序：升序→降序→取消"""
        header_labels = self._get_effective_columns()
        if logical_index >= len(header_labels):
            return
        col_name = header_labels[logical_index]

        current_order = getattr(self, '_sort_column', None)
        current_asc = getattr(self, '_sort_ascending', True)

        if current_order == col_name:
            if current_asc:
                self._sort_ascending = False
            else:
                self._sort_column = None
                self._rebuild_table()
                return
        else:
            self._sort_column = col_name
            self._sort_ascending = True

        self._rebuild_table()

    def _sort_records(self, records: list, col_name: str, ascending: bool) -> list:
        """对记录列表排序"""
        numeric_cols = {"金额(元)", "征收率", "税额(元)", "价税合计(元)"}
        if col_name in numeric_cols:
            key_fn = lambda r: safe_float(r.get(col_name, ""))
        else:
            key_fn = lambda r: str(r.get(col_name, "")).lower()
        return sorted(records, key=key_fn, reverse=not ascending)

    def _recenter_empty_overlay(self):
        """让空状态提示在 viewport 中居中"""
        if not hasattr(self, '_empty_overlay'):
            return
        vp = self.table.viewport()
        w = vp.width() - 60
        self._empty_overlay.setGeometry(30, (vp.height() - 100) // 2, w, 100)

    def _update_empty_state(self):
        """根据记录数显示/隐藏空状态引导"""
        if not hasattr(self, '_empty_overlay'):
            return
        if len(self.records) == 0:
            self._empty_overlay.show()
            self._recenter_empty_overlay()
        else:
            self._empty_overlay.hide()

    def _rebuild_table(self):
        self._save_locked = True
        scroll_val = self.table.verticalScrollBar().value()
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(0)

        # Dynamic columns
        effective_cols = self._get_effective_columns()
        self.table.setColumnCount(len(effective_cols))
        self.table.setHorizontalHeaderLabels(effective_cols)
        # Rebuild COL_IDX
        self._current_col_idx = {c: i for i, c in enumerate(effective_cols)}

        # Set column resize modes: 短列固定，长列可拖动
        header = self.table.horizontalHeader()
        fixed_widths = {"金额(元)": 88, "征收率": 55, "税额(元)": 88, "价税合计(元)": 98, "附件": 100}
        interactive_widths = {"发票类型": 110, "购买方名称": 180, "纳税人识别号": 200,
                              "销售方名称": 170, "发票号码": 170, "开票日期": 110, "备注": 100}
        for col_name, width in fixed_widths.items():
            col_idx = self._current_col_idx.get(col_name, -1)
            if col_idx >= 0:
                header.setSectionResizeMode(col_idx, QHeaderView.Fixed)
                self.table.setColumnWidth(col_idx, width)
        for col_name, width in interactive_widths.items():
            col_idx = self._current_col_idx.get(col_name, -1)
            if col_idx >= 0:
                header.setSectionResizeMode(col_idx, QHeaderView.Interactive)
                self.table.setColumnWidth(col_idx, width)
        # Tag columns — 可拖动
        for tag_name in self._tag_templates:
            col_idx = self._current_col_idx.get(tag_name, -1)
            if col_idx >= 0:
                header.setSectionResizeMode(col_idx, QHeaderView.Interactive)
                self.table.setColumnWidth(col_idx, 90)

        # Disable auto-stretch — keep user-resized widths stable
        self._stretch_cols = {}
        self._stretch_factors = {}
        self._stretch_total_weight = 0
        self._stretch_fixed_total = 0

        shown = [r for r in self.records if self._record_matches_filter(r)]
        # Apply sort if any
        if getattr(self, '_sort_column', None):
            shown = self._sort_records(shown, self._sort_column, getattr(self, '_sort_ascending', True))
        self._shown_records = shown
        # 预分配所有行（避免逐行 insertRow 的 O(n²) 开销）
        self.table.setRowCount(len(shown))
        for i, data in enumerate(shown):
            self._fill_row(i, data)
        self.table.setUpdatesEnabled(True)
        self.table.verticalScrollBar().setValue(min(scroll_val, self.table.verticalScrollBar().maximum()))
        self._refresh_summary_from_list(shown)
        self._save_locked = False
        active = any([self._filter_year, self._filter_month,
                      self._filter_inv_type, self._filter_seller])
        if active:
            self.status.showMessage(f"筛选结果：显示 {len(shown)} 张 / 共 {len(self.records)} 张")
        elif len(self.records) == 0:
            self.status.showMessage(
                "开始使用：拖拽 PDF 发票到窗口即可自动识别归档 | "
                "Ctrl+O 导入 PDF | Ctrl+E 导出 Excel | Delete 删除选中行")
        self._update_empty_state()
        self._rebuild_freeze_table()

    # ── 数据持久化 ──────────────────────────────

    def _persist_data(self):
        """同步表格 → 写入 DB（不含备份策略触发）"""
        try:
            self._sync_records_from_table()
            self._db.save(self.records)
            log.debug("数据已保存: %d 条", len(self.records))
        except Exception as e:
            log.error("数据保存失败: %s", e)
            self.status.showMessage(f"数据保存失败: {e}")
            raise

    def _save_data(self):
        try:
            self._persist_data()
        except Exception:
            return
        # 本地策略 on_save
        local_s = self._config.get_local_strategy()
        if local_s["enabled"] and local_s["trigger"] == "on_save":
            self._do_local_backup(local_s)
        # WebDAV 策略 on_save
        webdav_s = self._config.get_webdav_strategy()
        if webdav_s["enabled"] and webdav_s["url"] and webdav_s["trigger"] == "on_save":
            self._do_webdav_sync(silent=True)

    def _sync_records_from_table(self):
        shown = self._shown_records
        for i in range(self.table.rowCount()):
            inv_no_item = self.table.item(i, self._current_col_idx["发票号码"])
            inv_no = inv_no_item.text() if inv_no_item else ""

            idx = self._find_record_index(inv_no)
            rec = self.records[idx] if idx is not None else None
            if rec is None and 0 <= i < len(shown):
                rec = shown[i]
            if rec is None:
                continue

            bk_item = self.table.item(i, self._current_col_idx["备注"])
            if bk_item and bk_item.text() != "✓":
                if isinstance(rec, Invoice):
                    rec.remark = bk_item.text()
                else:
                    rec["remark"] = bk_item.text()

            # Save tag values from tag columns
            if isinstance(rec, Invoice):
                tags = rec.tags
            else:
                tags = rec.setdefault("tags", {})
            for tag_name in self._tag_templates:
                tag_col = self._current_col_idx.get(tag_name, -1)
                if tag_col >= 0:
                    tag_item = self.table.item(i, tag_col)
                    if tag_item:
                        tags[tag_name] = tag_item.text()

    def _get_effective_columns(self):
        """返回固定列 + 标签列"""
        return COLUMNS[:10] + self._tag_templates + COLUMNS[10:]

    def _load_data(self):
        invoices = self._db.load()
        if not invoices:
            log.info("无历史数据，初始化空列表")
            return
        log.info("加载 %d 条历史记录", len(invoices))
        self.records = invoices
        for inv in self.records:
            self._init_record_fields(inv)
        # Migrate old "company" field to tags
        for inv in self.records:
            company = inv.company if isinstance(inv, Invoice) else inv.get("company", "")
            if company:
                tags = inv.tags if isinstance(inv, Invoice) else inv.get("tags", {})
                if "企业号" not in tags:
                    tags["企业号"] = company
                if not isinstance(inv, Invoice):
                    inv["tags"] = tags
        self._rebuild_table()
        self._refresh_filter_combos()
        self._save_locked = False
        self.status.showMessage(f"已自动加载 {len(self.records)} 条历史记录")

    # ── 键盘快捷键 ──────────────────────────────
    def keyPressEvent(self, event):
        """全局键盘快捷键"""
        mod = event.modifiers()
        key = event.key()

        if mod == Qt.ControlModifier:
            if key == Qt.Key_O:
                self.open_files()
                return
            elif key == Qt.Key_E:
                self.export_excel()
                return
            elif key == Qt.Key_F:
                self._open_search()
                return
            elif key == Qt.Key_V:
                # Ctrl+V 粘贴附件
                rows = sorted(set(item.row() for item in self.table.selectedItems()))
                if not rows:
                    self.status.showMessage("请先选中一行，再按 Ctrl+V 粘贴附件")
                    return
                self._paste_from_clipboard(rows[0])
                return

        if key == Qt.Key_Delete:
            # 删除选中行（仅在表格有焦点时）
            if self.table.hasFocus():
                self._delete_selected_rows()
                return
        elif key == Qt.Key_Escape:
            self._reset_filter()
            return

        super().keyPressEvent(event)

    # ── 拖拽支持 ────────────────────────────────
    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._show_drop_overlay(e.mimeData().urls())

    def dragLeaveEvent(self, e):
        self._hide_drop_overlay()

    def dropEvent(self, e: QDropEvent):
        self._hide_drop_overlay()
        urls = e.mimeData().urls()
        pdf_files = []
        att_files = []

        for u in urls:
            path = u.toLocalFile()
            ext = os.path.splitext(path)[1].lower()
            if ext == '.pdf':
                pdf_files.append(path)
            elif ext in IMG_EXTS or ext in ATTACH_EXTS:
                att_files.append(path)

        if pdf_files:
            self._start_parse(pdf_files)

        if att_files:
            rows = sorted(set(item.row() for item in self.table.selectedItems()))
            if not rows:
                QMessageBox.information(
                    self, "提示",
                    "请先选中一行，再将文件拖入作为附件添加。"
                )
            else:
                self._add_attachments_from_paths(rows[0], att_files)

    def _show_drop_overlay(self, urls):
        if not hasattr(self, '_drop_overlay'):
            self._drop_overlay = QLabel(self)
            self._drop_overlay.setAlignment(Qt.AlignCenter)
        pdf_count = sum(1 for u in urls if u.toLocalFile().lower().endswith('.pdf'))
        other_count = len(urls) - pdf_count
        parts = []
        if pdf_count:
            parts.append(f"导入 {pdf_count} 个发票 PDF")
        if other_count:
            rows = set(item.row() for item in self.table.selectedItems())
            if rows:
                parts.append(f"添加 {other_count} 个附件到选中行")
            else:
                parts.append(f"⚠ 需选中行以添加 {other_count} 个附件")
        self._drop_overlay.setText("\n".join(parts))
        self._drop_overlay.setGeometry(0, 0, self.width(), self.height())
        self._drop_overlay.show()

    def _hide_drop_overlay(self):
        if hasattr(self, '_drop_overlay'):
            self._drop_overlay.hide()

    # ── 槽函数 ───────────────────────────────────
    def _on_table_clicked(self, index):
        """点击表格行时，在状态栏显示当前行摘要信息"""
        row = index.row()
        try:
            rec = self._get_record_by_row(row)
            if rec:
                seller = rec.get("seller_name", "") or "—"
                date   = rec.get("invoice_date", "") or "—"
                total  = rec.get("total", "") or "—"
                self.status.showMessage(
                    f"第 {row + 1} 行 | {seller} | {date} | 价税合计：¥{total}"
                    "  ·  Ctrl+V 粘贴附件"
                )
        except Exception:
            pass

    def _on_cell_changed(self, row, col):
        if self._save_locked:
            return
        header = self.table.horizontalHeaderItem(col).text()
        if header in ("备注",) or header in self._tag_templates:
            self._save_data()

    def closeEvent(self, event):
        log.info("应用关闭…")
        if hasattr(self, '_worker') and self._worker.isRunning():
            log.debug("等待后台线程结束…")
            self._worker.abort()
            if not self._worker.wait(3000):
                log.warning("后台线程未在3秒内结束")
        try:
            self._persist_data()
        except Exception:
            pass
        # 退出时强制执行一次无防抖备份（遵循策略 on_close/scheduled 触发条件）
        local_s = self._config.get_local_strategy()
        if hasattr(self, '_backup') and hasattr(self, '_db') and local_s["enabled"] \
                and local_s["trigger"] in ("on_close", "scheduled"):
            self._db.optimize()
            self._backup._last_backup_time = 0  # 绕过防抖
            count = self._backup.backup(self._db.data_file)
            self._backup.cleanup(keep_days=local_s["retention_days"],
                                 min_keep=local_s["min_keep"],
                                 max_keep=local_s["max_keep"])
            if count == 0:
                QMessageBox.warning(
                    self, "备份失败",
                    "退出时自动备份失败，请检查磁盘空间或权限。\n"
                    "数据已保存，可下次启动后手动备份。"
                )
        webdav_s = self._config.get_webdav_strategy()
        if webdav_s["enabled"] and webdav_s["url"] \
                and webdav_s["trigger"] in ("on_close", "scheduled"):
            self._do_webdav_sync(silent=False)
        event.accept()

    def _open_settings(self):
        """打开设置对话框"""
        dlg = SettingsDialog(self, parent=self)
        dlg.exec_()

    def _check_desktop_shortcut(self):
        """首次启动检测桌面快捷方式，不存在则提示创建"""
        import subprocess
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        lnk_path = os.path.join(desktop, "发票归档.lnk")
        if os.path.exists(lnk_path):
            return
        reply = QMessageBox.question(
            self, "创建快捷方式",
            "是否在桌面创建「发票归档」快捷方式？\n\n"
            "创建后可从桌面直接双击启动软件。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if reply != QMessageBox.Yes:
            return
        try:
            exe_path = sys.executable
            # 打包后 EXE 路径，开发时用脚本路径
            if not exe_path.endswith(".exe") or "python" in exe_path.lower():
                script = os.path.abspath(sys.argv[0]) if sys.argv[0] else __file__
                ps_cmd = (
                    f"$ws = New-Object -ComObject WScript.Shell; "
                    f"$sc = $ws.CreateShortcut('{lnk_path}'); "
                    f"$sc.TargetPath = 'pythonw'; "
                    f"$sc.Arguments = '{script}'; "
                    f"$sc.WorkingDirectory = '{os.path.dirname(script)}'; "
                    f"$sc.Save()"
                )
            else:
                ps_cmd = (
                    f"$ws = New-Object -ComObject WScript.Shell; "
                    f"$sc = $ws.CreateShortcut('{lnk_path}'); "
                    f"$sc.TargetPath = '{exe_path}'; "
                    f"$sc.Save()"
                )
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True, timeout=10
            )
            if os.path.exists(lnk_path):
                self.status.showMessage("桌面快捷方式已创建")
        except Exception:
            pass    # 静默失败，不影响主流程

    def _on_new_version(self, version: str, url: str):
        reply = QMessageBox.question(
            self, "发现新版本",
            f"检测到新版本 v{version}\n当前版本：v{APP_VERSION}\n\n是否前往下载？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if reply == QMessageBox.Yes:
            QDesktopServices.openUrl(QUrl(url))
        self._manual_check_pending = False

    def _on_check_finished(self, ok: bool, current: str, _url: str):
        if not self._manual_check_pending:
            return
        self._manual_check_pending = False
        if ok:
            QMessageBox.information(self, "检查更新", f"当前已是最新版本 v{current}")
        else:
            QMessageBox.warning(self, "检查更新", "无法连接到 Gitee，请检查网络后重试。")

    def check_update(self):
        self._manual_check_pending = True
        self.status.showMessage("正在检查更新…")
        self._update_checker.check()

    def _do_webdav_sync(self, silent=True):
        webdav_s = self._config.get_webdav_strategy()
        if not webdav_s["enabled"] or not webdav_s["url"]:
            return
        from webdav_sync import sync_to_webdav
        from PyQt5.QtCore import QThread
        url = webdav_s["url"]
        user = webdav_s["username"]
        pw = webdav_s["password"]
        data_dir = self._data_dir

        def run():
            try:
                result = sync_to_webdav(data_dir, url, user, pw)
                if result.get("failed", 0) > 0:
                    log.warning("WebDAV 同步部分失败: %s", result)
            except Exception as e:
                log.warning("WebDAV 同步失败: %s", e)

        class _SyncThread(QThread):
            def run(self):
                run()

        if not silent:
            self.status.showMessage("WebDAV 同步中…")
        thread = _SyncThread(self)
        thread.start()

    def _do_local_backup(self, strategy: dict | None = None):
        """执行本地多盘备份，备份前清理数据库碎片，使用策略中的保留参数"""
        if strategy is None:
            strategy = self._config.get_local_strategy()
        self._db.optimize()
        try:
            self._backup.backup(self._db.data_file)
            self._backup.cleanup(keep_days=strategy["retention_days"],
                                 min_keep=strategy["min_keep"],
                                 max_keep=strategy["max_keep"])
        except OSError as e:
            log.warning("备份失败（数据已保存）: %s", e)
            self.status.showMessage(f"备份失败，但数据已保存: {e}")

    def _check_scheduled_backups(self):
        """定时器回调：检查各策略是否需要触发定时备份"""
        now = time.time()
        local_s = self._config.get_local_strategy()
        if local_s["enabled"] and local_s["trigger"] == "scheduled" \
                and local_s["interval_minutes"] > 0:
            interval = local_s["interval_minutes"] * 60
            if now - self._last_scheduled_backup["local"] >= interval:
                self._last_scheduled_backup["local"] = now
                self._do_local_backup(local_s)
                log.info("定时本地备份完成 (间隔 %d 分钟)", local_s["interval_minutes"])

        webdav_s = self._config.get_webdav_strategy()
        if webdav_s["enabled"] and webdav_s["url"] \
                and webdav_s["trigger"] == "scheduled" \
                and webdav_s["interval_minutes"] > 0:
            interval = webdav_s["interval_minutes"] * 60
            if now - self._last_scheduled_backup["webdav"] >= interval:
                self._last_scheduled_backup["webdav"] = now
                self._do_webdav_sync(silent=True)
                log.info("定时 WebDAV 同步完成 (间隔 %d 分钟)", webdav_s["interval_minutes"])

    def open_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择发票PDF文件", "",
            "PDF文件 (*.pdf);;所有文件 (*)"
        )
        if files:
            self._start_parse(files)

    def clear_records(self):
        if not self.records:
            return
        reply = QMessageBox.question(self, "确认清空", "确定要清空所有记录吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.records.clear()
            self.table.setRowCount(0)
            self._refresh_summary()
            self._refresh_filter_combos()
            self._save_data()
            self.status.showMessage("已清空")

    # ── 解析流程 ─────────────────────────────────
    def _start_parse(self, files):
        self.btn_open.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status.showMessage(f"正在解析 {len(files)} 个文件...")
        self._parse_errors = []
        self._duplicate_invoices = []
        self._batch_count_before = len(self.records)

        # data_dir 传给 Worker，让文件复制在后台完成
        self._worker = ParseWorker(files, data_dir=self._data_dir)
        self._worker.progress.connect(self.progress_bar.setValue)
        self._worker.result_ready.connect(self._add_record_batch)
        self._worker.error_occurred.connect(self._on_parse_error)
        self._worker.finished.connect(self._parse_done)
        self._worker.start()

    def _on_parse_error(self, error_msg):
        self._parse_errors.append(error_msg)
        log.warning("解析错误: %s", error_msg)
        self.status.showMessage(f"解析错误: {error_msg}")

    # ── 批量导入专用槽（纯内存操作，不碰 UI）────────────────
    def _add_record_batch(self, data: dict):
        """后台每解析完一条调此槽；重复检测 + 写入"""
        inv = Invoice.from_dict(data)
        # 重复发票号检测：收集重复记录供结果摘要展示
        if inv.invoice_no and self._find_record_index(inv.invoice_no) is not None:
            self._duplicate_invoices.append(inv)
            return
        self._init_record_fields(inv)
        self.records.append(inv)

    def _fill_row(self, row: int, data, scroll: bool = False):
        """向已有行索引填充数据（不调用 insertRow，调用方需预分配行数）"""
        self.table.setRowHeight(row, TABLE_ROW_HEIGHT)

        is_red = data.get("is_red", False)

        def cell(text, editable=False, fg=None, bg=None):
            it = QTableWidgetItem(str(text) if text else "")
            if not editable:
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            if fg:
                it.setForeground(QColor(fg))
            if bg:
                it.setBackground(QColor(bg))
            return it

        def amount_item(field):
            v = data.get(field, "")
            v = str(v) if v is not None else ""
            neg = v.startswith('-')
            it = QTableWidgetItem(v)
            it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            if neg:
                it.setForeground(QColor(RED))
            if row_bg:
                it.setBackground(QColor(row_bg))
            elif neg:
                it.setBackground(QColor("#FFF0F0"))
            return it

        # 红票整行浅红背景
        row_bg = "#FFE4E4" if is_red else None


        # 发票类型：红票显示"● 红票-类型"，蓝票显示"● 类型"
        inv_type = data.get("invoice_type", "")
        if is_red:
            type_text = f"● 红票{'-' + inv_type if inv_type else ''}"
            type_fg   = RED
        else:
            type_text = f"● {inv_type}" if inv_type else ""
            type_fg   = ACCENT
        type_item = cell(type_text, fg=type_fg, bg=row_bg)
        self.table.setItem(row, self._current_col_idx["发票类型"], type_item)

        # 金额列：右对齐，负数标红
        self.table.setItem(row, self._current_col_idx["购买方名称"],   cell(data.get("buyer_name", ""), bg=row_bg))
        self.table.setItem(row, self._current_col_idx["纳税人识别号"],  cell(data.get("buyer_tax_id", ""), bg=row_bg))
        self.table.setItem(row, self._current_col_idx["销售方名称"],   cell(data.get("seller_name", ""), bg=row_bg))
        self.table.setItem(row, self._current_col_idx["金额(元)"],     amount_item("amount"))
        self.table.setItem(row, self._current_col_idx["征收率"],       cell(data.get("tax_rate", ""), bg=row_bg))
        self.table.setItem(row, self._current_col_idx["税额(元)"],     amount_item("tax_amount"))
        self.table.setItem(row, self._current_col_idx["价税合计(元)"],  amount_item("total"))

        # 数字列使用等宽字体，保证金额对齐扫描
        _mono = QFont(MONO_FONT, 12)
        for c in (self._current_col_idx["金额(元)"], self._current_col_idx["征收率"], self._current_col_idx["税额(元)"], self._current_col_idx["价税合计(元)"]):
            it = self.table.item(row, c)
            if it:
                it.setFont(_mono)

        self.table.setItem(row, self._current_col_idx["发票号码"], cell(data.get("invoice_no", ""), bg=row_bg))
        self.table.setItem(row, self._current_col_idx["开票日期"], cell(data.get("invoice_date", ""), bg=row_bg))

        # Write tag columns
        tags = data.get("tags", {})
        for tag_name in self._tag_templates:
            tag_col = self._current_col_idx.get(tag_name, -1)
            if tag_col >= 0:
                tag_value = tags.get(tag_name, "")
                self.table.setItem(row, tag_col, cell(tag_value, editable=True, bg=row_bg))

        self._set_attachment_cell(row, data)

        error_msg = data.get("error", "")
        remark_val = data.get("remark", "")
        if error_msg:
            display_text = f"⚠ {error_msg}"
            display_fg = RED
        elif remark_val:
            display_text = remark_val
            display_fg = RED if is_red else TEXT
        elif is_red:
            display_text = "红票"
            display_fg = RED
        else:
            display_text = ""
            display_fg = TEXT_DIM
        remark_item = cell(display_text, editable=True, fg=display_fg, bg=row_bg)
        self.table.setItem(row, self._current_col_idx["备注"], remark_item)

        if scroll:
            self.table.scrollToBottom()

    # ── 冻结操作列 ────────────────────────────────

    def _rebuild_freeze_table(self):
        """重建冻结表格（与 _rebuild_table 同步调用）"""
        freeze = self._freeze_table
        freeze.setRowCount(0)
        shown = self._shown_records
        if not shown:
            freeze.hide()
            return
        freeze.setRowCount(len(shown))
        freeze.horizontalHeader().setFixedHeight(self.table.horizontalHeader().height())

        for i, rec in enumerate(shown):
            freeze.setRowHeight(i, self.table.rowHeight(i))
            w = QWidget()
            lay = QHBoxLayout(w)
            lay.setContentsMargins(2, 2, 2, 2)
            lay.setSpacing(2)

            pdf_path = rec.get("pdf_path", "")
            if pdf_path and os.path.exists(pdf_path):
                btn_pdf = QPushButton("查看")
                btn_pdf.setFlat(True)
                btn_pdf.clicked.connect(self._make_pdf_handler(rec))
                lay.addWidget(btn_pdf)

            btn_del = QPushButton("删除")
            btn_del.setFlat(True)
            btn_del.clicked.connect(self._make_delete_handler(rec))
            lay.addWidget(btn_del)
            lay.addStretch()
            freeze.setCellWidget(i, 0, w)

        freeze.show()
        freeze.verticalScrollBar().setValue(self.table.verticalScrollBar().value())

    def _make_pdf_handler(self, rec):
        return lambda: self._view_invoice_pdf_by_rec(rec)

    def _make_delete_handler(self, rec):
        return lambda: self._delete_record(rec)

    def _view_invoice_pdf_by_rec(self, rec):
        path = rec.get("pdf_path", "")
        if not path or not os.path.exists(path):
            QMessageBox.warning(self, "文件不存在", "PDF 文件不存在或已被移动。")
            return
        from ui.dialogs.pdf_viewer import PdfViewerDialog
        PdfViewerDialog(path, parent=self).exec_()

    def _delete_record(self, rec):
        if rec not in self.records:
            return
        for i in range(self.table.rowCount()):
            inv_no_item = self.table.item(i, self._current_col_idx["发票号码"])
            inv_no = inv_no_item.text() if inv_no_item else ""
            if inv_no == rec.get("invoice_no", ""):
                self.table.selectRow(i)
                break
        self._delete_selected_rows()

    def _view_invoice_pdf(self, row):
        """打开 PDF 预览窗口（内嵌下载/系统打开等操作）"""
        rec = self._get_record_by_row(row)
        if rec is None:
            return
        path = rec.get("pdf_path", "")
        if not path or not os.path.exists(path):
            QMessageBox.warning(self, "文件不存在", "PDF 文件不存在或已被移动。")
            return
        from ui.dialogs.pdf_viewer import PdfViewerDialog
        dlg = PdfViewerDialog(path, parent=self)
        dlg.exec_()

    # ── 附件单元格 ────────────────────────────────
    def _set_attachment_cell(self, row, data):
        attachments = data.get("attachments", [])
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(3)

        if attachments:
            btn_v = QPushButton()
            btn_v.setIcon(get_icon('paperclip'))
            btn_v.setIconSize(QtCore.QSize(14, 14))
            btn_v.setText(f"  {len(attachments)}")
            btn_v.setFlat(True)
            btn_v.setToolTip(f"共 {len(attachments)} 个附件，点击查看")
            btn_v.clicked.connect(lambda _, r=row: self._view_attachments(r))
            lay.addWidget(btn_v)
        else:
            btn_v = QPushButton()
            btn_v.setIcon(get_icon('paperclip'))
            btn_v.setIconSize(QtCore.QSize(14, 14))
            btn_v.setFlat(True)
            btn_v.setEnabled(False)
            btn_v.setToolTip("暂无附件")
            lay.addWidget(btn_v)

        btn_add = QPushButton("+")
        btn_add.setFlat(True)
        btn_add.setToolTip("添加附件（支持拖拽）")
        btn_add.clicked.connect(lambda _, r=row: self._add_attachment(r))
        lay.addWidget(btn_add)
        lay.addStretch()
        self.table.setCellWidget(row, self._current_col_idx["附件"], w)

    # ── 截图操作 ─────────────────────────────────
    def _get_record_by_row(self, row):
        inv_no_item = self.table.item(row, self._current_col_idx["发票号码"])
        inv_no = inv_no_item.text() if inv_no_item else ""
        idx = self._find_record_index(inv_no)
        if idx is not None:
            return self.records[idx]
        shown = self._shown_records
        if 0 <= row < len(shown):
            return shown[row]
        return None

    # ── 附件操作 ─────────────────────────────────
    def _add_attachments_from_paths(self, row, src_paths):
        """添加附件（图片+文档）"""
        rec = self._get_record_by_row(row)
        if rec is None:
            return
        added = self._svc.add_attachments(rec, src_paths, "attachments",
                                          self._attachment_dir,
                                          InvoiceService.namer)
        if added > 0:
            self._set_attachment_cell(row, rec)
            self._save_data()
            self.status.showMessage(f"已添加 {added} 个附件")
    def _add_attachment(self, row):
        from ui.dialogs.add_attachment import AddAttachmentDialog
        dlg = AddAttachmentDialog(parent=self)
        if dlg.exec_() != QDialog.Accepted:
            return
        files = dlg.get_files()
        if files:
            self._add_attachments_from_paths(row, files)

    def _view_attachments(self, row):
        rec = self._get_record_by_row(row)
        if rec is None:
            return
        atts = rec.get("attachments", [])
        if not atts:
            QMessageBox.information(self, "提示", "该发票暂无附件")
            return
        from ui.dialogs.attachment_viewer import AttachmentViewerDialog
        dlg = AttachmentViewerDialog(
            atts, rec_name=rec.get("buyer_name", "") or rec.get("file", ""),
            parent=self
        )
        dlg.exec_()
        if dlg.attachment_paths != atts:
            rec["attachments"] = dlg.attachment_paths
            self._set_attachment_cell(row, rec)
            self._save_data()

    # ── 剪贴板粘贴 ──────────────────────────────
    def _paste_from_clipboard(self, row):
        """Ctrl+V：图片数据→截图，文件路径→按扩展名分类"""
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()

        # 图片像素数据（截图工具）
        if mime.hasImage():
            img = clipboard.image()
            if not img.isNull():
                rec = self._get_record_by_row(row)
                if rec is None:
                    return
                inv_no    = rec.get("invoice_no", "") or rec.get("file", "unnamed")
                safe_name = re.sub(r'[\\/:*?"<>|]', '_', inv_no)
                ts  = datetime.now().strftime("%Y%m%d%H%M%S%f")
                dst = os.path.join(self._attachment_dir, f"{safe_name}_{ts}.png")
                try:
                    img.save(dst, "PNG")
                    rec.setdefault("attachments", []).append(dst)
                    self._set_attachment_cell(row, rec)
                    self._save_data()
                    self.status.showMessage("已从剪贴板粘贴图片并添加为附件")
                except Exception as ex:
                    QMessageBox.warning(self, "粘贴失败", f"保存剪贴板图片失败：{ex}")
                return

        # 文件路径
        if mime.hasUrls():
            other_files = []
            for u in mime.urls():
                path = u.toLocalFile()
                ext  = os.path.splitext(path)[1].lower()
                if ext in IMG_EXTS or ext in ATTACH_EXTS:
                    other_files.append(path)
            if other_files:
                self._add_attachments_from_paths(row, other_files)
                return

        self.status.showMessage("剪贴板中没有可用内容，请先复制图片或文件后再粘贴")

    # ── viewport 事件过滤器 ────────────────────────
    def eventFilter(self, obj, event):
        if obj is self.table.viewport():
            if event.type() == QEvent.Resize:
                self._recenter_empty_overlay()
        return super().eventFilter(obj, event)


    # ── 全局搜索 ──────────────────────────────────

    def resizeEvent(self, event):
        """窗口大小改变时重新定位搜索条"""
        super().resizeEvent(event)
        if hasattr(self, '_search_bar') and self._search_bar.isVisible():
            self._search_bar.setGeometry(self.width() - 420, 8, 400, 40)
        if hasattr(self, '_drop_overlay'):
            self._drop_overlay.setGeometry(0, 0, self.width(), self.height())

    def _open_search(self):
        """打开全局搜索条"""
        self._search_bar.setGeometry(self.width() - 420, 8, 400, 40)
        self._search_bar.show()
        self._search_bar.raise_()
        self._search_input.setFocus()
        self._search_input.selectAll()
        # Connect text change to search
        try:
            self._search_input.textChanged.disconnect()
        except TypeError:
            pass
        self._search_input.textChanged.connect(lambda: QTimer.singleShot(200, self._do_search))
        self._search_matches = []
        self._current_match_index = -1

    def _close_search(self):
        """关闭全局搜索条"""
        self._search_bar.hide()
        self._search_matches = []
        self._current_match_index = -1
        self._highlight_search_row(-1)

    def _do_search(self):
        """执行搜索"""
        keyword = self._search_input.text().strip().lower()
        self._search_matches = []
        self._current_match_index = -1

        if not keyword:
            self._search_count.setText("")
            self._highlight_search_row(-1)
            return

        # 搜索所有行所有列
        for row in range(self.table.rowCount()):
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if item and keyword in item.text().lower():
                    self._search_matches.append(row)
                    break

        self._search_count.setText(f"{len(self._search_matches)} 个匹配")
        if self._search_matches:
            self._current_match_index = 0
            self._jump_to_match(0)
        else:
            self._highlight_search_row(-1)

    def _jump_to_match(self, idx):
        """跳转到第 idx 个匹配行"""
        if not self._search_matches or idx < 0 or idx >= len(self._search_matches):
            return
        self._current_match_index = idx
        row = self._search_matches[idx]
        self.table.selectRow(row)
        self.table.scrollToItem(self.table.item(row, 0), QAbstractItemView.PositionAtCenter)
        self._highlight_search_row(row)
        self._search_count.setText(f"{idx + 1} / {len(self._search_matches)}")

    def _next_search_match(self):
        if not self._search_matches:
            return
        idx = (self._current_match_index + 1) % len(self._search_matches)
        self._jump_to_match(idx)

    def _prev_search_match(self):
        if not self._search_matches:
            return
        idx = (self._current_match_index - 1) % len(self._search_matches)
        self._jump_to_match(idx)

    def _highlight_search_row(self, row):
        """高亮搜索匹配行"""
        # Reset all row backgrounds
        for r in range(self.table.rowCount()):
            for c in range(self.table.columnCount()):
                item = self.table.item(r, c)
                if item:
                    bg = item.data(Qt.UserRole + 1)
                    if bg:
                        item.setBackground(QColor(bg))
                    else:
                        item.setBackground(QColor("transparent" if r % 2 == 0 else "#F8F9FA"))

    # ── 右键菜单 ─────────────────────────────────
    def _show_context_menu(self, pos):
        menu = QMenu(self)

        menu.addAction(get_icon('camera'), "添加附件", self._ctx_add_attachment)
        menu.addAction(get_icon('clipboard'), "粘贴附件（Ctrl+V）", self._ctx_paste_attachment)
        menu.addAction(get_icon('search'), "查看附件", self._ctx_view_attachments)
        menu.addAction(get_icon('delete'), "清除附件", self._ctx_delete_attachments)
        menu.addSeparator()

        menu.addAction(get_icon('delete'), "删除选中行", self._delete_selected_rows)
        menu.addSeparator()
        menu.addAction(get_icon('clear'), "清空列表…", self.clear_records)
        menu.exec_(self.table.viewport().mapToGlobal(pos))

    def _selected_rows(self):
        return sorted(set(item.row() for item in self.table.selectedItems()))

    def _ctx_add_attachment(self):
        for row in self._selected_rows():
            self._add_attachment(row)

    def _ctx_paste_attachment(self):
        rows = self._selected_rows()
        if rows:
            self._paste_from_clipboard(rows[0])

    def _ctx_view_attachments(self):
        rows = self._selected_rows()
        if rows:
            self._view_attachments(rows[0])

    def _ctx_delete_attachments(self):
        for row in self._selected_rows():
            rec = self._get_record_by_row(row)
            if rec:
                rec["attachments"] = []
                self._set_attachment_cell(row, rec)
        self._save_data()
        self.status.showMessage("已清除选中行的附件记录")

    def _delete_selected_rows(self):
        rows = sorted(set(item.row() for item in self.table.selectedItems()), reverse=True)
        if not rows:
            return

        # 收集待删除记录信息（先收集再删）
        shown = self._shown_records
        to_delete = []
        for row in rows:
            inv_no_item = self.table.item(row, self._current_col_idx["发票号码"])
            inv_no = inv_no_item.text() if inv_no_item else ""
            idx = self._find_record_index(inv_no)
            rec = self.records[idx] if idx is not None else None
            if rec is None and 0 <= row < len(shown):
                rec = shown[row]
            if rec and rec not in to_delete:
                to_delete.append(rec)

        if not to_delete:
            return

        # 双重确认弹窗：必须勾选才能点删除
        dlg = DeleteConfirmDialog(to_delete, self)
        if dlg.exec_() != QDialog.Accepted:
            return

        # 删除原始PDF并从 records 移除
        deleted_files = 0
        failed_files  = []
        for rec in to_delete:
            pdf_path = rec.get("pdf_path", "")
            if pdf_path and os.path.exists(pdf_path):
                try:
                    os.remove(pdf_path)
                    deleted_files += 1
                except Exception as ex:
                    failed_files.append(f"{os.path.basename(pdf_path)}：{ex}")
            self.records.remove(rec)

        # 重建表格
        self._rebuild_table()
        self._refresh_filter_combos()
        self._save_data()

        msg = f"已删除 {len(to_delete)} 条记录"
        log.info("删除 %d 条记录 (PDF 成功 %d, 失败 %d)",
                 len(to_delete), deleted_files, len(failed_files))
        if deleted_files:
            msg += f"，{deleted_files} 个PDF文件已删除"
        if failed_files:
            msg += f"，{len(failed_files)} 个文件删除失败"
            QMessageBox.warning(self, "部分文件删除失败",
                "以下文件删除失败（记录已从列表移除）：\n\n" +
                "\n".join(failed_files))
        self.status.showMessage(msg)

    # ── 统计汇总 ─────────────────────────────────
    def _refresh_summary(self):
        self._refresh_summary_from_list(self.records)

    def _refresh_summary_from_list(self, recs):
        count     = len(recs)
        total_amt = sum(safe_float(r.get("amount"))     for r in recs)
        total_tax = sum(safe_float(r.get("tax_amount")) for r in recs)
        total_all = sum(safe_float(r.get("total"))      for r in recs)
        self.lbl_count._value_label.setText(f"{count} 张")
        self.lbl_total_amt._value_label.setText(f"¥ {total_amt:,.2f}")
        self.lbl_total_tax._value_label.setText(f"¥ {total_tax:,.2f}")
        self.lbl_total_all._value_label.setText(f"¥ {total_all:,.2f}")

    def _parse_done(self):
        self._rebuild_table()
        self._refresh_filter_combos()
        self._save_data()

        self.btn_open.setEnabled(True)
        self.progress_bar.setVisible(False)
        batch_count = len(self.records) - getattr(self, '_batch_count_before', 0)
        fail_count = len(getattr(self, '_parse_errors', []))
        dup_count = len(getattr(self, '_duplicate_invoices', []))
        ok_count = max(0, batch_count - fail_count)

        # 结果摘要弹窗（有失败或重复时才弹出）
        if fail_count > 0 or dup_count > 0:
            msg_parts = []
            if ok_count > 0:
                msg_parts.append(f"成功导入 {ok_count} 张")
            if fail_count > 0:
                msg_parts.append(f"解析失败 {fail_count} 张")
            if dup_count > 0:
                msg_parts.append(f"重复跳过 {dup_count} 张")

            detail = "\n\n"
            if fail_count > 0:
                detail += "解析失败：\n" + "\n".join(f"  · {e}" for e in self._parse_errors)
            if dup_count > 0:
                dup_nos = [inv.invoice_no for inv in self._duplicate_invoices]
                detail += "\n重复发票号：\n" + "\n".join(f"  · {n}" for n in dup_nos)

            QMessageBox.information(
                self, "导入结果",
                "\n".join(msg_parts) + detail
            )

        status_msg = " | ".join(msg_parts) if (fail_count > 0 or dup_count > 0) else f"导入完成：{ok_count} 张"
        self.status.showMessage(status_msg)

        # 清理临时状态
        self._parse_errors = []
        self._duplicate_invoices = []

    # ── 导出 Excel ───────────────────────────────
    def export_excel(self):
        export_records = [r for r in self.records if self._record_matches_filter(r)]
        if not export_records:
            QMessageBox.information(self, "提示", "暂无数据，请先导入发票")
            return
        log.info("开始导出 Excel: %d 条记录", len(export_records))

        month_hint = ""
        if self._filter_year or self._filter_month:
            y  = self._filter_year or "全年"
            mo = f"{self._filter_month:02d}月" if self._filter_month else ""
            month_hint = f"_{y}{mo}"

        default_name = f"发票归档{month_hint}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        save_path, _ = QFileDialog.getSaveFileName(
            self, "保存Excel文件", default_name, "Excel文件 (*.xlsx)"
        )
        if not save_path:
            return

        try:
            from services.export_service import ExportService
            svc = ExportService()
            svc.export(export_records, save_path, tag_columns=self._tag_templates)
            log.info("Excel 导出成功: %s (%d 条)", save_path, len(export_records))
            QMessageBox.information(self, "导出成功",
                f"已成功导出 {len(export_records)} 条记录\n\n路径：{save_path}")
            self.status.showMessage(f"Excel 已保存：{save_path}")
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(save_path)))

        except Exception as e:
            log.error("Excel 导出失败: %s", e, exc_info=True)
            QMessageBox.critical(self, "导出失败", f"导出时出错：\n{e}")

# ─────────────────────────────────────────────
#  入口
# ─────────────────────────────────────────────

def main():
    # 单实例检测
    from PyQt5.QtCore import QSharedMemory
    _singleton = QSharedMemory("lan-invoice-app")
    if not _singleton.create(1) and _singleton.error() == QSharedMemory.AlreadyExists:
        QMessageBox.warning(None, "提示", "发票归档工具已在运行中。\n请查看任务栏或系统托盘。")
        sys.exit(0)

    # 先创建 QApplication（日志 setup 内的 Qt 钩子需要它）
    app = QApplication(sys.argv)
    app.setApplicationName("发票归档")
    app.setStyle("Fusion")
    app.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    # PyQt5 默认不加载系统字体到 Qt 的字体数据库
    # 主动扫描 Windows 系统字体目录并加载
    if sys.platform == "win32":
        windir = os.environ.get("WINDIR", "C:\\Windows")
        fonts_dir = os.path.join(windir, "Fonts")
        if os.path.isdir(fonts_dir):
            for f in os.listdir(fonts_dir):
                if f.lower().endswith((".ttf", ".otf", ".ttc")):
                    try:
                        QFontDatabase.addApplicationFont(os.path.join(fonts_dir, f))
                    except Exception:
                        pass

    # 选择实际可用的中文字体
    available_fonts = set(QFontDatabase().families())
    preferred = ["Microsoft YaHei UI", "Microsoft YaHei", "微软雅黑", "SimHei", "Arial"]
    chosen = next((f for f in preferred if f in available_fonts), "Arial")
    base_font = QFont(chosen, 10)
    base_font.setWeight(QFont.Medium)
    app.setFont(base_font)
    log.info("字体：%s | 重量：%d | 大小：%d | 可用字体数：%d",
             chosen, base_font.weight(), base_font.pointSize(), len(available_fonts))

    # 日志初始化
    def _gui_error(title, msg):
        QMessageBox(QMessageBox.Critical, title, msg, QMessageBox.Ok, None).exec_()
    setup_logging(gui_error_callback=_gui_error)

    # 应用级图标（任务栏显示）
    from PyQt5.QtGui import QIcon
    icon_paths = [
        os.path.join(os.path.dirname(__file__), "ui", "icons", "app_icon.png"),
        "icon.ico",
    ]
    for p in icon_paths:
        if os.path.exists(p):
            app.setWindowIcon(QIcon(p))
            break

    win = InvoiceApp()
    win.show()
    exit_code = app.exec_()
    shutdown_logging()
    sys.exit(exit_code)


if __name__ == "__main__":
    if "--mcp" in sys.argv:
        from mcp_server import McpServer
        McpServer().run()
    else:
        main()
