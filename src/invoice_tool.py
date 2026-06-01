# -*- coding: utf-8 -*-
"""
发票归档 v4.0
功能：发票PDF识别、付款截图管理、合同附件管理、按月筛选、导出Excel
"""

import sys
import os
import re
import json
import shutil
from datetime import datetime

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QTableWidget, QTableWidgetItem,
    QFileDialog, QMessageBox, QHeaderView, QStatusBar, QFrame,
    QProgressBar, QAbstractItemView, QDialog,
    QComboBox, QMenu, QInputDialog
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QMimeData, QUrl, QEvent
from PyQt5.QtGui import QColor, QDragEnterEvent, QDropEvent

from invoice_parser import parse_invoice_pdf
from dialogs import (ImageViewerDialog, InvoiceManagerDialog,
                     ContractManagerDialog, SettingsDialog, DeleteConfirmDialog)


# ─────────────────────────────────────────────
#  工具函数
# ─────────────────────────────────────────────

def _copy_file_to_dir(src: str, dst_dir: str) -> str:
    """复制文件到目标目录，自动处理重名冲突；返回目标路径。失败返回原路径。"""
    if not src or not os.path.isfile(src):
        return src
    os.makedirs(dst_dir, exist_ok=True)
    fname = os.path.basename(src)
    dst = os.path.join(dst_dir, fname)
    counter = 1
    while os.path.exists(dst):
        name, ext = os.path.splitext(fname)
        dst = os.path.join(dst_dir, f"{name}_{counter}{ext}")
        counter += 1
    try:
        shutil.copy2(src, dst)
        return dst
    except OSError:
        return src


# ─────────────────────────────────────────────
#  后台解析线程
# ─────────────────────────────────────────────

class ParseWorker(QThread):
    progress = pyqtSignal(int)
    result_ready = pyqtSignal(dict)
    finished = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self, files, data_dir: str = ""):
        super().__init__()
        self.files    = files
        self.data_dir = data_dir   # 目标目录；非空时在后台完成文件复制
        self._abort   = False

    def abort(self):
        self._abort = True

    def _copy_pdf(self, src: str) -> str:
        if not self.data_dir:
            return src
        return _copy_file_to_dir(src, os.path.join(self.data_dir, "invoices"))

    def run(self):
        total = len(self.files)
        for i, f in enumerate(self.files, 1):
            if self._abort:
                break
            try:
                data = parse_invoice_pdf(f)
                # 文件复制在后台完成，主线程槽无需做 IO
                data["pdf_path"] = self._copy_pdf(data.get("pdf_path", "") or f)
            except Exception as e:
                self.error_occurred.emit(f"解析 {os.path.basename(f)} 时出错: {str(e)}")
                data = {
                    "pdf_path": f,
                    "error": str(e),
                    "invoice_type": "", "buyer_name": "", "buyer_tax_id": "",
                    "seller_name": "", "amount": "", "tax_rate": "",
                    "tax_amount": "", "total": "", "invoice_no": "",
                    "invoice_date": "", "company": "",
                    "screenshots": [], "contracts": [], "remark": "", "is_red": False
                }
            self.result_ready.emit(data)
            self.progress.emit(int(i / total * 100))
        self.finished.emit()
#  主窗口
# ─────────────────────────────────────────────

# 表格列定义
COLUMNS = ["序号", "发票PDF", "发票类型", "购买方名称", "纳税人识别号",
           "销售方名称", "金额(元)", "征收率", "税额(元)", "价税合计(元)",
           "发票号码", "开票日期", "企业号", "付款截图", "合同", "备注"]
COL_IDX = {c: i for i, c in enumerate(COLUMNS)}

# 支持的文件扩展名
IMG_EXTS      = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.tiff', '.tif'}
CONTRACT_EXTS = {'.pdf', '.docx', '.doc', '.xlsx', '.xls'}  # 合同支持格式


class InvoiceApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.records = []
        self.pending_company = ""
        
        # 配置文件路径：%APPDATA%\lan-invoice\config.json
        appdata = os.environ.get('APPDATA', os.path.expanduser('~'))
        self._config_file = os.path.join(appdata, 'lan-invoice', 'config.json')
        
        # 先读取配置文件获取数据目录（直接存储 _data_dir，不再嵌套 data 子目录）
        self._data_dir = self._load_config_dir()
        self._data_file      = os.path.join(self._data_dir, "invoices_data.json")
        self._screenshot_dir = os.path.join(self._data_dir, "screenshots")
        self._contract_dir   = os.path.join(self._data_dir, "contracts")
        os.makedirs(self._data_dir,       exist_ok=True)
        os.makedirs(self._screenshot_dir, exist_ok=True)
        os.makedirs(self._contract_dir,   exist_ok=True)

        self._filter_year        = None
        self._filter_month       = None
        self._filter_inv_type    = None   # 发票类型筛选
        self._filter_seller      = None   # 销售方名称筛选
        self._filter_company     = ""     # 企业号搜索（模糊匹配）
        self._filter_buyer       = ""     # 购买方名称/税号搜索（模糊匹配）

        # 拖拽模式：'pdf'=导入发票, 'screenshot'=添加截图, 'contract'=添加合同
        # 通过键盘修饰键区分：Alt=截图, Shift=合同, 无修饰=PDF
        self._drag_mode = None
        self._shown_records = []   # 当前筛选后的记录缓存，_rebuild_table 时更新

        self._init_ui()
        self.setAcceptDrops(True)
        self._load_data()

    # ── 记录辅助方法 ────────────────────────────

    def _init_record_fields(self, data: dict):
        """统一初始化记录字段默认值；红票金额转负数"""
        for field in ("pdf_path", "invoice_type", "seller_name", "remark"):
            data.setdefault(field, "")
        data.setdefault("screenshots", [])
        data.setdefault("contracts", [])
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
            if r.get("invoice_no") == inv_no:
                return i
        return None

    # ── UI 构建 ─────────────────────────────────
    def _init_ui(self):
        self.setWindowTitle("发票归档 v4.0")
        self.resize(1480, 820)
        self.setMinimumSize(1000, 640)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 6)
        main_layout.setSpacing(8)

        # ── 工具栏第一行 ──────────────────────────
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        self.btn_open = QPushButton("📂 导入发票PDF")
        self.btn_open.setFixedHeight(36)
        self.btn_open.setToolTip("选择一个或多个PDF发票文件（也可直接拖拽PDF到窗口）")
        self.btn_open.clicked.connect(self.open_files)

        self.btn_clear = QPushButton("🗑 清空列表")
        self.btn_clear.setFixedHeight(36)
        self.btn_clear.clicked.connect(self.clear_records)

        self.btn_settings = QPushButton("⚙️ 设置")
        self.btn_settings.setFixedHeight(36)
        self.btn_settings.setToolTip("数据目录设置 / 软件另存")
        self.btn_settings.clicked.connect(self._open_settings)

        self.btn_export = QPushButton("📊 导出 Excel")
        self.btn_export.setFixedHeight(36)
        self.btn_export.setStyleSheet(
            "background:#1E6FBF; color:white; font-weight:bold; border-radius:4px;")
        self.btn_export.clicked.connect(self.export_excel)

        top_bar.addWidget(self.btn_open)
        top_bar.addWidget(self.btn_clear)
        top_bar.addWidget(self.btn_settings)
        top_bar.addStretch()

        lbl = QLabel("企业号（手动）：")
        lbl.setFixedWidth(110)
        self.edit_company = QLineEdit()
        self.edit_company.setPlaceholderText("输入后新导入发票自动填入")
        self.edit_company.setFixedWidth(220)
        self.edit_company.setFixedHeight(32)
        self.edit_company.textChanged.connect(self._on_company_changed)

        self.btn_apply = QPushButton("应用到已选行")
        self.btn_apply.setFixedHeight(32)
        self.btn_apply.clicked.connect(self.apply_company_to_selected)

        top_bar.addWidget(lbl)
        top_bar.addWidget(self.edit_company)
        top_bar.addWidget(self.btn_apply)
        top_bar.addSpacing(12)
        top_bar.addWidget(self.btn_export)
        main_layout.addLayout(top_bar)

        # ── 工具栏第二行：多维筛选 ───────────────
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(6)

        lbl_filter = QLabel("🔍 筛选：")
        lbl_filter.setStyleSheet("font-size:13px; color:#333;")

        # 年份
        lbl_y = QLabel("年份")
        lbl_y.setStyleSheet("font-size:12px; color:#666;")
        self.combo_year = QComboBox()
        self.combo_year.setFixedWidth(90)
        self.combo_year.setFixedHeight(30)
        self.combo_year.addItem("全部", None)

        # 月份
        lbl_m = QLabel("月份")
        lbl_m.setStyleSheet("font-size:12px; color:#666;")
        self.combo_month = QComboBox()
        self.combo_month.setFixedWidth(80)
        self.combo_month.setFixedHeight(30)
        self.combo_month.addItem("全部", None)
        for i in range(1, 13):
            self.combo_month.addItem(f"{i:02d} 月", i)

        # 发票类型
        lbl_type = QLabel("发票类型")
        lbl_type.setStyleSheet("font-size:12px; color:#666;")
        self.combo_inv_type = QComboBox()
        self.combo_inv_type.setFixedWidth(130)
        self.combo_inv_type.setFixedHeight(30)
        self.combo_inv_type.addItem("全部", None)

        # 销售方名称
        lbl_seller = QLabel("销售方")
        lbl_seller.setStyleSheet("font-size:12px; color:#666;")
        self.combo_seller = QComboBox()
        self.combo_seller.setFixedWidth(160)
        self.combo_seller.setFixedHeight(30)
        self.combo_seller.addItem("全部", None)

        # 购买方名称/税号搜索
        lbl_buyer_search = QLabel("购买方")
        lbl_buyer_search.setStyleSheet("font-size:12px; color:#666;")
        self.edit_buyer_search = QLineEdit()
        self.edit_buyer_search.setPlaceholderText("名称或税号")
        self.edit_buyer_search.setFixedWidth(160)
        self.edit_buyer_search.setFixedHeight(30)
        # 回车直接触发筛选
        self.edit_buyer_search.returnPressed.connect(self._apply_filter)

        # 企业号搜索
        lbl_company_search = QLabel("企业号")
        lbl_company_search.setStyleSheet("font-size:12px; color:#666;")
        self.edit_company_search = QLineEdit()
        self.edit_company_search.setPlaceholderText("输入企业号搜索")
        self.edit_company_search.setFixedWidth(130)
        self.edit_company_search.setFixedHeight(30)
        # 回车直接触发筛选
        self.edit_company_search.returnPressed.connect(self._apply_filter)

        self.btn_filter = QPushButton("筛 选")
        self.btn_filter.setFixedHeight(30)
        self.btn_filter.setFixedWidth(70)
        self.btn_filter.clicked.connect(self._apply_filter)

        self.btn_reset = QPushButton("重置")
        self.btn_reset.setFixedHeight(30)
        self.btn_reset.setFixedWidth(60)
        self.btn_reset.clicked.connect(self._reset_filter)

        self.lbl_filter_hint = QLabel("")
        self.lbl_filter_hint.setStyleSheet("color:#E06020; font-size:12px;")

        filter_bar.addWidget(lbl_filter)
        filter_bar.addWidget(lbl_y)
        filter_bar.addWidget(self.combo_year)
        filter_bar.addWidget(lbl_m)
        filter_bar.addWidget(self.combo_month)
        filter_bar.addWidget(lbl_type)
        filter_bar.addWidget(self.combo_inv_type)
        filter_bar.addWidget(lbl_seller)
        filter_bar.addWidget(self.combo_seller)
        filter_bar.addWidget(lbl_buyer_search)
        filter_bar.addWidget(self.edit_buyer_search)
        filter_bar.addWidget(lbl_company_search)
        filter_bar.addWidget(self.edit_company_search)
        filter_bar.addWidget(self.btn_filter)
        filter_bar.addWidget(self.btn_reset)
        filter_bar.addWidget(self.lbl_filter_hint)
        filter_bar.addStretch()
        main_layout.addLayout(filter_bar)

        # ── 进度条 ───────────────────────────────
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(
            "QProgressBar { border:none; background:#ddd; border-radius:3px; }"
            "QProgressBar::chunk { background:#1E6FBF; border-radius:3px; }")
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        # ── 统计汇总栏 ───────────────────────────
        self.summary_frame = QFrame()
        self.summary_frame.setFrameShape(QFrame.StyledPanel)
        self.summary_frame.setStyleSheet(
            "QFrame { background:#F0F7FF; border:1px solid #B8D4F0; border-radius:5px; }")
        sum_layout = QHBoxLayout(self.summary_frame)
        sum_layout.setContentsMargins(16, 6, 16, 6)
        sum_layout.setSpacing(40)

        self.lbl_count     = self._stat_label("发票总数", "0 张")
        self.lbl_total_amt = self._stat_label("金额合计", "¥ 0.00")
        self.lbl_total_tax = self._stat_label("税额合计", "¥ 0.00")
        self.lbl_total_all = self._stat_label("价税合计", "¥ 0.00")

        for w in [self.lbl_count, self.lbl_total_amt, self.lbl_total_tax, self.lbl_total_all]:
            sum_layout.addWidget(w)
        sum_layout.addStretch()
        main_layout.addWidget(self.summary_frame)

        # ── 主表格 ───────────────────────────────
        self.table = QTableWidget()
        self.table.setColumnCount(len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.verticalHeader().setDefaultSectionSize(36)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        # 列宽：序号, 发票PDF, 发票类型, 购买方名称, 税号, 销售方名称, 金额, 税率, 税额, 合计, 发票号, 日期, 企业号, 截图, 合同, 备注
        col_widths = [45, 160, 120, 150, 155, 150, 88, 55, 88, 98, 135, 100, 105, 90, 90, 100]
        for i, w in enumerate(col_widths):
            self.table.setColumnWidth(i, w)

        self.table.setStyleSheet("""
            QTableWidget { font-size:13px; gridline-color:#dce6f1; }
            QHeaderView::section {
                background-color: #1E6FBF; color: white;
                font-weight: bold; font-size: 13px;
                padding: 5px; border: none;
                border-right: 1px solid #4A90D9;
            }
            QTableWidget::item {
                padding: 2px 6px;
                background-color: white;
            }
            QTableWidget::item:alternate { background:#EEF4FB; }
            QTableWidget::item:selected {
                background: #FFA500;
                color: #1A1A1A;
                font-weight: bold;
            }
            QTableWidget::item:hover:!selected { background:#FFF3CD; }
            QTableWidget::item:selected:hover {
                background: #FF8C00;
            }
        """)
        main_layout.addWidget(self.table)

        # ── 状态栏 ───────────────────────────────
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage(
            "就绪 — 拖拽 PDF 导入发票 | 选中行后拖拽图片添加截图 | 选中行后拖拽合同文件添加合同 | Ctrl+V 粘贴截图/合同")

        self._set_global_style()
        self._save_locked = False
        self.table.cellChanged.connect(self._on_cell_changed)
        self.table.clicked.connect(self._on_table_clicked)
        # 安装 viewport 事件过滤器：点击已选中行取消选中
        self.table.viewport().installEventFilter(self)

    def _stat_label(self, title, value):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(1)
        lbl_t = QLabel(title)
        lbl_t.setStyleSheet("color:#666; font-size:11px;")
        lbl_v = QLabel(value)
        lbl_v.setStyleSheet("color:#1E6FBF; font-size:16px; font-weight:bold;")
        v.addWidget(lbl_t)
        v.addWidget(lbl_v)
        w._value_label = lbl_v
        return w

    def _set_global_style(self):
        self.setStyleSheet("""
            QMainWindow { background: #F5F8FC; }
            QPushButton {
                border: 1px solid #B0C4DE; border-radius: 4px;
                padding: 4px 14px; background: #FFFFFF; font-size: 13px;
            }
            QPushButton:hover { background: #E8F0FE; border-color: #1E6FBF; }
            QPushButton:pressed { background: #CCE0FF; }
            QLineEdit {
                border: 1px solid #B0C4DE; border-radius: 4px;
                padding: 4px 8px; font-size: 13px; background: white;
            }
            QComboBox {
                border: 1px solid #B0C4DE; border-radius: 4px;
                padding: 2px 8px; font-size: 13px; background: white;
            }
        """)

    # ── 筛选条件 ─────────────────────────────────
    def _get_available_years(self):
        years = set()
        for r in self.records:
            m = re.match(r'(\d{4})年', r.get("invoice_date", ""))
            if m:
                years.add(int(m.group(1)))
        return sorted(years)

    def _get_available_inv_types(self):
        types = set()
        for r in self.records:
            t = r.get("invoice_type", "").strip()
            if t:
                types.add(t)
        return sorted(types)

    def _get_available_sellers(self):
        sellers = set()
        for r in self.records:
            s = r.get("seller_name", "").strip()
            if s:
                sellers.add(s)
        return sorted(sellers)

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
            parts.append(f"企业号:{self._filter_company}")
        self.lbl_filter_hint.setText(f"当前筛选：{'  '.join(parts)}" if parts else "")

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
        # 年月筛选
        if self._filter_year is not None or self._filter_month is not None:
            m = re.match(r'(\d{4})年(\d{2})月', rec.get("invoice_date", ""))
            if not m:
                return False
            y, mo = int(m.group(1)), int(m.group(2))
            if self._filter_year  is not None and y  != self._filter_year:
                return False
            if self._filter_month is not None and mo != self._filter_month:
                return False
        # 发票类型筛选
        if self._filter_inv_type is not None:
            if rec.get("invoice_type", "").strip() != self._filter_inv_type:
                return False
        # 销售方筛选
        if self._filter_seller is not None:
            if rec.get("seller_name", "").strip() != self._filter_seller:
                return False
        # 购买方名称/税号模糊搜索（不区分大小写）
        if self._filter_buyer:
            buyer_name = rec.get("buyer_name", "").lower()
            buyer_tax_id = rec.get("buyer_tax_id", "").lower()
            search_text = self._filter_buyer.lower()
            if search_text not in buyer_name and search_text not in buyer_tax_id:
                return False
        # 企业号模糊搜索（不区分大小写）
        if self._filter_company:
            company = rec.get("company", "")
            if self._filter_company.lower() not in company.lower():
                return False
        return True

    def _rebuild_table(self):
        self._save_locked = True
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(0)
        self._shown_records = [r for r in self.records if self._record_matches_filter(r)]
        shown = self._shown_records
        for data in shown:
            self._insert_row(data, scroll=False)
        self.table.setUpdatesEnabled(True)    # 恢复 UI，一次性刷新
        self._refresh_summary_from_list(shown)
        self._save_locked = False
        active = any([self._filter_year, self._filter_month,
                      self._filter_inv_type, self._filter_seller])
        if active:
            self.status.showMessage(f"筛选结果：显示 {len(shown)} 张 / 共 {len(self.records)} 张")

    # ── 数据持久化 ──────────────────────────────
    def _save_data(self):
        try:
            self._sync_records_from_table()
            with open(self._data_file, "w", encoding="utf-8") as f:
                json.dump(self.records, f, ensure_ascii=False, indent=2)
        except (OSError, IOError) as e:
            self.status.showMessage(f"数据保存失败: {e}")

    def _sync_records_from_table(self):
        shown = self._shown_records
        for i in range(self.table.rowCount()):
            inv_no_item = self.table.item(i, COL_IDX["发票号码"])
            inv_no = inv_no_item.text() if inv_no_item else ""

            idx = self._find_record_index(inv_no)
            rec = self.records[idx] if idx is not None else None
            if rec is None and 0 <= i < len(shown):
                rec = shown[i]
            if rec is None:
                continue

            co_item = self.table.item(i, COL_IDX["企业号"])
            bk_item = self.table.item(i, COL_IDX["备注"])
            if co_item:
                rec["company"] = co_item.text()
            if bk_item and bk_item.text() != "✓":
                rec["remark"] = bk_item.text()

    def _load_config_dir(self):
        default_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data"
        )
        # 旧版配置迁移：项目根目录 config.json → %APPDATA%\lan-invoice\
        old_config = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "config.json"
        )
        if os.path.exists(old_config) and not os.path.exists(self._config_file):
            try:
                os.makedirs(os.path.dirname(self._config_file), exist_ok=True)
                shutil.copy2(old_config, self._config_file)
            except OSError:
                pass
        if not os.path.exists(self._config_file):
            return default_dir
        try:
            with open(self._config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
                data_dir = config.get("data_dir", "")
                if data_dir and os.path.isdir(data_dir):
                    return data_dir
        except (OSError, json.JSONDecodeError):
            pass
        return default_dir

    def _save_config_dir(self, data_dir):
        try:
            os.makedirs(os.path.dirname(self._config_file), exist_ok=True)
            with open(self._config_file, "w", encoding="utf-8") as f:
                json.dump({"data_dir": data_dir}, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def _load_data(self):
        if not os.path.exists(self._data_file):
            return
        try:
            with open(self._data_file, "r", encoding="utf-8") as f:
                self.records = json.load(f)
            if not isinstance(self.records, list):
                self.records = []
            self._save_locked = True
            self.table.setUpdatesEnabled(False)
            for data in self.records:
                data.setdefault("company", "")
                self._init_record_fields(data)
                self._insert_row(data, scroll=False)
            self.table.setUpdatesEnabled(True)
            self._shown_records = list(self.records)
            self._refresh_summary()
            self._refresh_filter_combos()
            if self.records:
                self.status.showMessage(f"已自动加载 {len(self.records)} 条历史记录")
            self._save_locked = False
        except (OSError, json.JSONDecodeError) as e:
            self._save_locked = False
            self.table.setUpdatesEnabled(True)
            self.status.showMessage(f"历史数据加载失败: {e}")

    # ── 拖拽支持 ────────────────────────────────
    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent):
        urls = e.mimeData().urls()
        pdf_files      = []
        img_files      = []
        contract_files = []

        for u in urls:
            path = u.toLocalFile()
            ext  = os.path.splitext(path)[1].lower()
            if ext in IMG_EXTS:
                img_files.append(path)
            elif ext in CONTRACT_EXTS:
                # PDF 需区分：是发票还是合同？
                # 规则：如果有选中行 → 作为合同；没有选中行 → 作为发票
                rows = set(item.row() for item in self.table.selectedItems())
                if ext == '.pdf' and not rows:
                    pdf_files.append(path)
                else:
                    contract_files.append(path)

        if pdf_files:
            self._start_parse(pdf_files)

        rows = sorted(set(item.row() for item in self.table.selectedItems()))

        if img_files:
            if not rows:
                QMessageBox.information(
                    self, "提示",
                    "请先在表格中选中一行，再将图片拖拽到窗口，\n图片将被添加到该行的付款截图。"
                )
            else:
                self._add_screenshots_from_paths(rows[0], img_files)

        if contract_files:
            if not rows:
                QMessageBox.information(
                    self, "提示",
                    "请先在表格中选中一行，再将合同文件拖拽到窗口，\n文件将被添加到该行的合同。"
                )
            else:
                self._add_contracts_from_paths(rows[0], contract_files)

    # ── 槽函数 ───────────────────────────────────
    def _on_company_changed(self, text):
        self.pending_company = text.strip()

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
                    "  ·  Ctrl+V 粘贴截图/合同"
                )
        except Exception:
            pass

    def _on_cell_changed(self, row, col):
        if self._save_locked:
            return
        header = self.table.horizontalHeaderItem(col).text()
        if header in ("企业号", "备注"):
            self._save_data()

    def closeEvent(self, event):
        if hasattr(self, '_worker') and self._worker.isRunning():
            self._worker.abort()
            self._worker.wait(3000)
        self._save_data()
        event.accept()

    def _open_settings(self):
        """打开设置对话框"""
        dlg = SettingsDialog(self, parent=self)
        dlg.exec_()

    def keyPressEvent(self, event):
        """
        Ctrl+V：根据剪贴板内容类型判断操作：
          - 图片数据 → 添加截图
          - 文件路径（图片扩展名）→ 添加截图
          - 文件路径（合同扩展名）→ 添加合同
        """
        if event.key() == Qt.Key_V and event.modifiers() == Qt.ControlModifier:
            rows = sorted(set(item.row() for item in self.table.selectedItems()))
            if not rows:
                self.status.showMessage("请先选中一行，再按 Ctrl+V 粘贴截图或合同")
                return
            self._paste_from_clipboard(rows[0])
            return
        super().keyPressEvent(event)

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

    def apply_company_to_selected(self):
        rows = set(item.row() for item in self.table.selectedItems())
        if not rows:
            QMessageBox.information(self, "提示", "请先在表格中选中需要修改的行")
            return
        company = self.pending_company
        if not company:
            company, ok = QInputDialog.getText(self, "输入企业号", "企业号：")
            if not ok or not company:
                return
        col = COL_IDX["企业号"]
        shown = self._shown_records
        for row in rows:
            self.table.setItem(row, col, QTableWidgetItem(company))
            inv_no_item = self.table.item(row, COL_IDX["发票号码"])
            inv_no = inv_no_item.text() if inv_no_item else ""
            idx = self._find_record_index(inv_no)
            rec = self.records[idx] if idx is not None else None
            if rec is None and 0 <= row < len(shown):
                rec = shown[row]
            if rec:
                rec["company"] = company
        self.status.showMessage(f"已将企业号「{company}」应用到 {len(rows)} 行")
        self._save_data()

    # ── 解析流程 ─────────────────────────────────
    def _start_parse(self, files):
        self.btn_open.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status.showMessage(f"正在解析 {len(files)} 个文件...")
        self._parse_errors = []
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
        self.status.showMessage(f"解析错误: {error_msg}")

    # ── 批量导入专用槽（纯内存操作，不碰 UI）────────────────
    def _add_record_batch(self, data: dict):
        """后台每解析完一条调此槽；只写 self.records，UI 留给 _parse_done 统一渲染。"""
        if self.pending_company:
            data["company"] = self.pending_company
        self._init_record_fields(data)
        self.records.append(data)

    def _add_record(self, data: dict):
        """单条记录添加（拖放/非批量场景），保留 save + refresh"""
        if self.pending_company:
            data["company"] = self.pending_company
        self._init_record_fields(data)

        original_pdf_path = data.get("pdf_path", "")
        if original_pdf_path:
            data["pdf_path"] = _copy_file_to_dir(original_pdf_path,
                                                  os.path.join(self._data_dir, "invoices"))

        self.records.append(data)
        if self._record_matches_filter(data):
            self._insert_row(data)
        self._refresh_summary()
        self._refresh_filter_combos()
        self._save_data()

    def _insert_row(self, data: dict, scroll: bool = True):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setRowHeight(row, 36)

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

        # 红票整行浅红背景
        row_bg = "#FFE4E4" if is_red else None

        self.table.setItem(row, COL_IDX["序号"],         cell(row + 1, bg=row_bg))
        # 发票PDF列：显示文件名 + 查看按钮（内嵌 widget）
        self._set_invoice_pdf_cell(row, data)

        # 发票类型：红票显示"🔴 红票-类型"，蓝票显示"🔵 类型"
        inv_type = data.get("invoice_type", "")
        if is_red:
            type_text = f"🔴 红票{'-' + inv_type if inv_type else ''}"
            type_fg   = "#CC0000"
        else:
            type_text = f"🔵 {inv_type}" if inv_type else ""
            type_fg   = "#1E6FBF"
        type_item = cell(type_text, fg=type_fg, bg=row_bg)
        self.table.setItem(row, COL_IDX["发票类型"], type_item)

        # 金额列：负数标红（红票金额已在入库时转负）
        def amount_cell(field):
            v = data.get(field, "")
            v = str(v) if v is not None else ""
            neg = v.startswith('-')
            return cell(v, fg="#CC0000" if neg else None, bg=row_bg if row_bg else ("#FFF0F0" if neg else None))

        self.table.setItem(row, COL_IDX["购买方名称"],   cell(data.get("buyer_name", ""), bg=row_bg))
        self.table.setItem(row, COL_IDX["纳税人识别号"],  cell(data.get("buyer_tax_id", ""), bg=row_bg))
        self.table.setItem(row, COL_IDX["销售方名称"],   cell(data.get("seller_name", ""), bg=row_bg))
        self.table.setItem(row, COL_IDX["金额(元)"],     amount_cell("amount"))
        self.table.setItem(row, COL_IDX["征收率"],       cell(data.get("tax_rate", ""), bg=row_bg))
        self.table.setItem(row, COL_IDX["税额(元)"],     amount_cell("tax_amount"))
        self.table.setItem(row, COL_IDX["价税合计(元)"],  amount_cell("total"))
        self.table.setItem(row, COL_IDX["发票号码"],      cell(data.get("invoice_no", ""), bg=row_bg))
        self.table.setItem(row, COL_IDX["开票日期"],      cell(data.get("invoice_date", ""), bg=row_bg))
        self.table.setItem(row, COL_IDX["企业号"],        cell(data.get("company", ""), editable=True, bg=row_bg))

        self._set_screenshot_cell(row, data)
        self._set_contract_cell(row, data)

        remark_val  = data.get("remark", "") or data.get("error", "") or "✓"
        remark_item = cell(remark_val, editable=True,
                           fg="#CC0000" if data.get("error") else ("#CC0000" if is_red else ("#1E8B1E" if remark_val == "✓" else "#333")),
                           bg=row_bg)
        self.table.setItem(row, COL_IDX["备注"], remark_item)

        if scroll:
            self.table.scrollToBottom()

    # ── 发票PDF单元格 ────────────────────────────
    def _set_invoice_pdf_cell(self, row, data):
        """发票PDF列：文件名 + 查看按钮"""
        fname    = data.get("file", "")
        pdf_path = data.get("pdf_path", "")
        exists   = bool(pdf_path) and os.path.exists(pdf_path)

        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(4, 1, 2, 1)
        lay.setSpacing(3)

        lbl = QLabel(fname)
        lbl.setStyleSheet(
            f"font-size:12px; color:{'#1E6FBF' if exists else '#999'};"
        )
        lbl.setToolTip(pdf_path or "（路径未记录）")
        lay.addWidget(lbl, 1)

        if exists:
            btn_v = QPushButton("查看")
            btn_v.setFixedHeight(24)
            btn_v.setFixedWidth(40)
            btn_v.setStyleSheet("font-size:11px; padding:1px 4px; color:#1E6FBF;")
            btn_v.setToolTip("打开 / 下载发票原文件")
            btn_v.clicked.connect(lambda _, r=row: self._view_invoice_pdf(r))
            lay.addWidget(btn_v)

        self.table.setCellWidget(row, COL_IDX["发票PDF"], w)

    def _view_invoice_pdf(self, row):
        """打开发票PDF查看/下载对话框"""
        rec = self._get_record_by_row(row)
        if rec is None:
            return
        dlg = InvoiceManagerDialog(
            pdf_path=rec.get("pdf_path", ""),
            rec_name=rec.get("buyer_name", "") or rec.get("file", ""),
            parent=self
        )
        dlg.exec_()

    # ── 截图单元格 ───────────────────────────────
    def _set_screenshot_cell(self, row, data):
        screenshots = data.get("screenshots", [])
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(2, 1, 2, 1)
        lay.setSpacing(3)

        if screenshots:
            lbl = QLabel(f"📷{len(screenshots)}")
            lbl.setStyleSheet("color:#1E6FBF; font-size:12px;")
            btn_v = QPushButton("查看")
            btn_v.setFixedHeight(24)
            btn_v.setFixedWidth(40)
            btn_v.setStyleSheet("font-size:11px; padding:1px 4px;")
            btn_v.clicked.connect(lambda _, r=row: self._view_screenshots(r))
            lay.addWidget(lbl)
            lay.addWidget(btn_v)
        else:
            lbl = QLabel("—")
            lbl.setStyleSheet("color:#aaa; font-size:12px;")
            lay.addWidget(lbl)

        btn_add = QPushButton("＋")
        btn_add.setFixedHeight(24)
        btn_add.setFixedWidth(26)
        btn_add.setToolTip("添加付款截图")
        btn_add.setStyleSheet("font-size:13px; padding:0; color:#1E6FBF;")
        btn_add.clicked.connect(lambda _, r=row: self._add_screenshot(r))
        lay.addWidget(btn_add)
        lay.addStretch()
        self.table.setCellWidget(row, COL_IDX["付款截图"], w)

    # ── 合同单元格 ───────────────────────────────
    def _set_contract_cell(self, row, data):
        contracts = data.get("contracts", [])
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(2, 1, 2, 1)
        lay.setSpacing(3)

        if contracts:
            lbl = QLabel(f"📄{len(contracts)}")
            lbl.setStyleSheet("color:#2E7D32; font-size:12px;")
            btn_v = QPushButton("查看")
            btn_v.setFixedHeight(24)
            btn_v.setFixedWidth(40)
            btn_v.setStyleSheet("font-size:11px; padding:1px 4px; color:#2E7D32;")
            btn_v.clicked.connect(lambda _, r=row: self._view_contracts(r))
            lay.addWidget(lbl)
            lay.addWidget(btn_v)
        else:
            lbl = QLabel("—")
            lbl.setStyleSheet("color:#aaa; font-size:12px;")
            lay.addWidget(lbl)

        btn_add = QPushButton("＋")
        btn_add.setFixedHeight(24)
        btn_add.setFixedWidth(26)
        btn_add.setToolTip("添加合同文件（PDF/Word）")
        btn_add.setStyleSheet("font-size:13px; padding:0; color:#2E7D32;")
        btn_add.clicked.connect(lambda _, r=row: self._add_contract(r))
        lay.addWidget(btn_add)
        lay.addStretch()
        self.table.setCellWidget(row, COL_IDX["合同"], w)

    # ── 截图操作 ─────────────────────────────────
    def _get_record_by_row(self, row):
        inv_no_item = self.table.item(row, COL_IDX["发票号码"])
        inv_no = inv_no_item.text() if inv_no_item else ""
        idx = self._find_record_index(inv_no)
        if idx is not None:
            return self.records[idx]
        shown = self._shown_records
        if 0 <= row < len(shown):
            return shown[row]
        return None

    def _add_screenshot(self, row):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择付款截图", "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;所有文件 (*)"
        )
        if files:
            self._add_screenshots_from_paths(row, files)

    def _add_screenshots_from_paths(self, row, src_paths):
        rec = self._get_record_by_row(row)
        if rec is None:
            return
        inv_no    = rec.get("invoice_no", "") or rec.get("file", "unnamed")
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', inv_no)
        added = 0
        for src in src_paths:
            if not os.path.exists(src):
                continue
            ext = os.path.splitext(src)[1].lower() or ".png"
            ts  = datetime.now().strftime("%Y%m%d%H%M%S%f")
            dst = os.path.join(self._screenshot_dir, f"{safe_name}_{ts}{ext}")
            try:
                shutil.copy2(src, dst)
                rec.setdefault("screenshots", []).append(dst)
                added += 1
            except Exception as ex:
                QMessageBox.warning(self, "复制失败",
                    f"文件 {os.path.basename(src)} 复制失败：{ex}")
        if added > 0:
            self._set_screenshot_cell(row, rec)
            self._save_data()
            self.status.showMessage(f"已为该发票添加 {added} 张付款截图")

    def _view_screenshots(self, row):
        rec = self._get_record_by_row(row)
        if rec is None:
            return
        screenshots = rec.get("screenshots", [])
        if not screenshots:
            QMessageBox.information(self, "提示", "该发票暂无付款截图")
            return
        dlg = ImageViewerDialog(screenshots, parent=self)
        dlg.exec_()

    # ── 合同操作 ─────────────────────────────────
    def _add_contract(self, row):
        """通过文件选择对话框添加合同"""
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择合同文件", "",
            "合同文件 (*.pdf *.docx *.doc *.xlsx *.xls);;所有文件 (*)"
        )
        if files:
            self._add_contracts_from_paths(row, files)

    def _add_contracts_from_paths(self, row, src_paths):
        """将合同文件复制到 contracts 目录并绑定到指定行"""
        rec = self._get_record_by_row(row)
        if rec is None:
            return
        inv_no    = rec.get("invoice_no", "") or rec.get("file", "unnamed")
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', inv_no)
        added = 0
        for src in src_paths:
            if not os.path.exists(src):
                continue
            ext      = os.path.splitext(src)[1].lower()
            orig_base = os.path.splitext(os.path.basename(src))[0]
            ts       = datetime.now().strftime("%Y%m%d%H%M%S%f")
            dst_name = f"{safe_name}_{orig_base}_{ts}{ext}"
            dst      = os.path.join(self._contract_dir, dst_name)
            try:
                shutil.copy2(src, dst)
                rec.setdefault("contracts", []).append(dst)
                added += 1
            except Exception as ex:
                QMessageBox.warning(self, "复制失败",
                    f"文件 {os.path.basename(src)} 复制失败：{ex}")
        if added > 0:
            self._set_contract_cell(row, rec)
            self._save_data()
            self.status.showMessage(f"已为该发票添加 {added} 份合同")

    def _view_contracts(self, row):
        """打开合同管理对话框"""
        rec = self._get_record_by_row(row)
        if rec is None:
            return
        contracts = rec.get("contracts", [])
        if not contracts:
            QMessageBox.information(self, "提示", "该发票暂无合同文件")
            return
        dlg = ContractManagerDialog(
            contracts,
            rec_name=rec.get("buyer_name", "") or rec.get("file", ""),
            parent=self
        )
        dlg.exec_()
        # 同步对话框中可能的删除操作
        if dlg.contract_paths != contracts:
            rec["contracts"] = dlg.contract_paths
            self._set_contract_cell(row, rec)
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
                dst = os.path.join(self._screenshot_dir, f"{safe_name}_{ts}.png")
                try:
                    img.save(dst, "PNG")
                    rec.setdefault("screenshots", []).append(dst)
                    self._set_screenshot_cell(row, rec)
                    self._save_data()
                    self.status.showMessage("已从剪贴板粘贴图片并添加为付款截图")
                except Exception as ex:
                    QMessageBox.warning(self, "粘贴失败", f"保存剪贴板图片失败：{ex}")
                return

        # 文件路径
        if mime.hasUrls():
            img_files      = []
            contract_files = []
            for u in mime.urls():
                path = u.toLocalFile()
                ext  = os.path.splitext(path)[1].lower()
                if ext in IMG_EXTS:
                    img_files.append(path)
                elif ext in CONTRACT_EXTS:
                    contract_files.append(path)
            if img_files:
                self._add_screenshots_from_paths(row, img_files)
            if contract_files:
                self._add_contracts_from_paths(row, contract_files)
            if img_files or contract_files:
                return

        self.status.showMessage("剪贴板中没有可用内容（图片或合同文件），请先复制后再粘贴")

    # ── 点击同一行取消选中（viewport 事件过滤器）────
    def eventFilter(self, obj, event):
        if obj is self.table.viewport() and event.type() == QEvent.MouseButtonPress:
            if event.button() == Qt.LeftButton:
                row = self.table.rowAt(event.pos().y())
                selected = self._selected_rows()
                if row >= 0 and selected == [row]:
                    # 再次点击同一已选中行 → 取消选中
                    self.table.clearSelection()
                    return True   # 消费事件，不再触发选中
        return super().eventFilter(obj, event)



    # ── 右键菜单 ─────────────────────────────────
    def _show_context_menu(self, pos):
        menu = QMenu(self)

        # 截图区
        menu.addAction("📷 添加付款截图（文件选择）", self._ctx_add_screenshot)
        menu.addAction("📋 粘贴截图（Ctrl+V）",        self._ctx_paste_screenshot)
        menu.addAction("🔍 查看付款截图",               self._ctx_view_screenshot)
        menu.addAction("🗑 清除此行截图",               self._ctx_delete_screenshots)
        menu.addSeparator()

        # 合同区
        menu.addAction("📄 添加合同（文件选择）",       self._ctx_add_contract)
        menu.addAction("📋 粘贴合同文件（Ctrl+V）",     self._ctx_paste_contract)
        menu.addAction("📂 查看/管理合同",              self._ctx_view_contracts)
        menu.addAction("🗑 清除此行合同",               self._ctx_delete_contracts)
        menu.addSeparator()

        menu.addAction("❌ 删除选中行", self._delete_selected_rows)
        menu.exec_(self.table.viewport().mapToGlobal(pos))

    def _selected_rows(self):
        return sorted(set(item.row() for item in self.table.selectedItems()))

    def _ctx_add_screenshot(self):
        for row in self._selected_rows():
            self._add_screenshot(row)

    def _ctx_paste_screenshot(self):
        rows = self._selected_rows()
        if rows:
            self._paste_from_clipboard(rows[0])

    def _ctx_view_screenshot(self):
        rows = self._selected_rows()
        if rows:
            self._view_screenshots(rows[0])

    def _ctx_delete_screenshots(self):
        for row in self._selected_rows():
            rec = self._get_record_by_row(row)
            if rec:
                rec["screenshots"] = []
                self._set_screenshot_cell(row, rec)
        self._save_data()
        self.status.showMessage("已清除选中行的截图记录")

    def _ctx_add_contract(self):
        for row in self._selected_rows():
            self._add_contract(row)

    def _ctx_paste_contract(self):
        rows = self._selected_rows()
        if rows:
            self._paste_from_clipboard(rows[0])

    def _ctx_view_contracts(self):
        rows = self._selected_rows()
        if rows:
            self._view_contracts(rows[0])

    def _ctx_delete_contracts(self):
        for row in self._selected_rows():
            rec = self._get_record_by_row(row)
            if rec:
                rec["contracts"] = []
                self._set_contract_cell(row, rec)
        self._save_data()
        self.status.showMessage("已清除选中行的合同记录")

    def _delete_selected_rows(self):
        rows = sorted(set(item.row() for item in self.table.selectedItems()), reverse=True)
        if not rows:
            return

        # 收集待删除记录信息（先收集再删）
        shown = self._shown_records
        to_delete = []
        for row in rows:
            inv_no_item = self.table.item(row, COL_IDX["发票号码"])
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
        total_amt = sum(self._safe_float(r.get("amount"))     for r in recs)
        total_tax = sum(self._safe_float(r.get("tax_amount")) for r in recs)
        total_all = sum(self._safe_float(r.get("total"))      for r in recs)
        self.lbl_count._value_label.setText(f"{count} 张")
        self.lbl_total_amt._value_label.setText(f"¥ {total_amt:,.2f}")
        self.lbl_total_tax._value_label.setText(f"¥ {total_tax:,.2f}")
        self.lbl_total_all._value_label.setText(f"¥ {total_all:,.2f}")

    def _parse_done(self):
        # 所有记录已在 self.records，一次性重建表格（比逐行 insertRow 快得多）
        self._rebuild_table()
        self._refresh_filter_combos()
        self._save_data()

        self.btn_open.setEnabled(True)
        self.progress_bar.setVisible(False)
        batch_count = len(self.records) - getattr(self, '_batch_count_before', 0)
        recent = self.records[-batch_count:] if batch_count > 0 else []
        ok = sum(1 for r in recent if not r.get("error"))
        fail = batch_count - ok
        msg = f"导入完成：本次 {batch_count} 张，成功识别 {ok} 张"
        if fail:
            msg += f"，{fail} 张解析异常（查看备注列）"
        if self._parse_errors:
            msg += f"  |  {len(self._parse_errors)} 个错误"
        self.status.showMessage(msg)

    # ── 导出 Excel ───────────────────────────────
    def export_excel(self):
        export_records = [r for r in self.records if self._record_matches_filter(r)]
        if not export_records:
            QMessageBox.information(self, "提示", "暂无数据，请先导入发票")
            return

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

        # 导出列：不含「付款截图」和「合同」
        xl_columns = [c for c in COLUMNS if c not in ("付款截图", "合同")]

        try:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "发票归档"

            header_fill  = PatternFill("solid", fgColor="1E6FBF")
            header_font  = Font(color="FFFFFF", bold=True, size=12)
            header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
            thin   = Side(style="thin", color="AAAAAA")
            border = Border(left=thin, right=thin, top=thin, bottom=thin)

            ws.append(xl_columns)
            for cell in ws[1]:
                cell.fill      = header_fill
                cell.font      = header_font
                cell.alignment = header_align
                cell.border    = border
            ws.row_dimensions[1].height = 28

            alt_fill     = PatternFill("solid", fgColor="EEF4FB")
            normal_align = Alignment(horizontal="left",   vertical="center")
            center_align = Alignment(horizontal="center", vertical="center")

            for i, rec in enumerate(export_records, 2):
                row_data = [
                    i - 1,
                    rec.get("file", ""),
                    rec.get("invoice_type", ""),
                    rec.get("buyer_name", ""),
                    rec.get("buyer_tax_id", ""),
                    rec.get("seller_name", ""),
                    rec.get("amount", ""),
                    rec.get("tax_rate", ""),
                    rec.get("tax_amount", ""),
                    rec.get("total", ""),
                    rec.get("invoice_no", ""),
                    rec.get("invoice_date", ""),
                    rec.get("company", ""),
                    rec.get("remark", "") or rec.get("error", "") or "✓"
                ]
                ws.append(row_data)
                fill = alt_fill if i % 2 == 0 else None
                for j, cell in enumerate(ws[i]):
                    if fill:
                        cell.fill = fill
                    cell.border    = border
                    cell.alignment = center_align if j in [0, 5] else normal_align
                ws.row_dimensions[i].height = 20

            # 汇总行
            ws.append([])
            sum_row   = ws.max_row + 1
            total_amt = sum(self._safe_float(r.get("amount"))     for r in export_records)
            total_tax = sum(self._safe_float(r.get("tax_amount")) for r in export_records)
            total_all = sum(self._safe_float(r.get("total"))      for r in export_records)
            ws.cell(sum_row, 1, "合计")
            ws.cell(sum_row, 7, round(total_amt, 2))
            ws.cell(sum_row, 9, round(total_tax, 2))
            ws.cell(sum_row, 10, round(total_all, 2))
            sum_font = Font(bold=True, color="1E6FBF", size=12)
            sum_fill = PatternFill("solid", fgColor="D6E4F5")
            for cell in ws[sum_row]:
                cell.font      = sum_font
                cell.fill      = sum_fill
                cell.border    = border
                cell.alignment = center_align
            ws.row_dimensions[sum_row].height = 24

            # 列宽：序号, 发票PDF, 发票类型, 购买方名称, 税号, 销售方名称, 金额, 税率, 税额, 合计, 发票号, 日期, 企业号, 备注
            xl_widths = [6, 26, 16, 20, 22, 20, 12, 8, 12, 14, 20, 14, 15, 14]
            for i, w in enumerate(xl_widths, 1):
                ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

            ws.freeze_panes = "A2"
            wb.save(save_path)
            QMessageBox.information(self, "导出成功",
                f"已成功导出 {len(export_records)} 条记录\n\n路径：{save_path}")
            self.status.showMessage(f"Excel 已保存：{save_path}")
            os.startfile(os.path.dirname(save_path))

        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出时出错：\n{e}")

    @staticmethod
    def _safe_float(val):
        try:
            return float(val or 0)
        except (ValueError, TypeError):
            return 0.0


# ─────────────────────────────────────────────
#  入口
# ─────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("发票归档")
    app.setStyle("Fusion")
    app.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    win = InvoiceApp()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
