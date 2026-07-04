# -*- coding: utf-8 -*-
"""导入预览对话框 — 展示解析结果，列齐全、可排序、汇总金额"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox,
    QMessageBox, QAbstractItemView
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor

from ui.theme import TEXT, TEXT_SEC, TEXT_DIM, ACCENT, BORDER_LIGHT
from utils import safe_float

# 表格列定义
_COLUMNS = [
    "", "文件名", "发票类型", "购买方名称", "销售方名称",
    "金额", "税额", "价税合计", "发票号码", "开票日期", "状态",
]
_COL_WIDTHS = [30, 0, 0, 0, 0, 80, 80, 90, 130, 90, 0]
# 0=自动/Stretch, >0=固定宽度


class ImportPreviewDialog(QDialog):
    """解析结果预览：新发票（可勾选）+ 重复（灰显）+ 错误（红显）"""

    def __init__(self, results: list[dict], existing_nos: set[str], parent=None):
        super().__init__(parent)
        self._results = results
        self._existing = existing_nos
        self._selected: list[int] = []
        self._select_events: set[int] = set()
        self.setWindowTitle("导入预览")
        self.setMinimumSize(960, 500)
        self._build_ui()
        self._populate()

    def get_selected_indices(self) -> list[int]:
        return list(self._selected)

    # ── UI 构建 ─────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # 顶部标题
        lbl = QLabel("解析完成，请勾选要导入的发票（重复项已自动排除）")
        lbl.setStyleSheet(f"font-size:12px; color:{TEXT};")
        layout.addWidget(lbl)

        # 表格
        self._table = QTableWidget()
        self._table.setColumnCount(len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        h = self._table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Fixed)
        self._table.setColumnWidth(0, _COL_WIDTHS[0])
        for i, w in enumerate(_COL_WIDTHS[1:], 1):
            if w > 0:
                h.setSectionResizeMode(i, QHeaderView.Fixed)
                self._table.setColumnWidth(i, w)
            else:
                h.setSectionResizeMode(i, QHeaderView.Stretch if i == 1
                                       else QHeaderView.ResizeToContents)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        # 点击表头排序
        h.sectionClicked.connect(self._on_header_clicked)
        layout.addWidget(self._table, 1)

        # 底部：摘要 + 汇总
        bottom = QHBoxLayout()
        bottom.setSpacing(24)
        self._lbl_counts = QLabel()
        self._lbl_counts.setStyleSheet(f"font-size:11px; color:{TEXT_DIM};")
        bottom.addWidget(self._lbl_counts)
        self._lbl_selection = QLabel()
        self._lbl_selection.setStyleSheet(
            f"font-size:11px; font-weight:bold; color:{ACCENT};")
        bottom.addWidget(self._lbl_selection)
        bottom.addStretch()
        layout.addLayout(bottom)

        # 按钮栏
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._btn_select_all = QPushButton("全选")
        self._btn_select_all.clicked.connect(self._select_all)
        btn_row.addWidget(self._btn_select_all)
        btn_deselect_all = QPushButton("取消全选")
        btn_deselect_all.clicked.connect(self._deselect_all)
        btn_row.addWidget(btn_deselect_all)
        btn_row.addStretch()
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        btn_import = QPushButton("导入选中")
        btn_import.setDefault(True)
        btn_import.clicked.connect(self._on_import)
        btn_row.addWidget(btn_import)
        layout.addLayout(btn_row)

    # ── 填充数据 ─────────────────────────────────

    def _populate(self):
        new_count = 0; dup_count = 0; err_count = 0
        rows = []

        for i, r in enumerate(self._results):
            inv_no = r.get("invoice_no", "")
            if r.get("error"):
                err_count += 1
                status = "解析失败"
                color = QColor("#c0392b")
                checkable = False
            elif inv_no and inv_no in self._existing:
                dup_count += 1
                status = "重复"
                color = QColor("#7f8c8d")
                checkable = False
            else:
                new_count += 1
                status = "新"
                color = QColor("#27ae60")
                checkable = True
            rows.append((i, r, status, color, checkable))

        self._checkable_rows = [i for _, _, s, _, c in rows if c]
        self._table.setRowCount(len(rows))
        self._table.blockSignals(True)

        for row_idx, (orig_i, r, status, color, checkable) in enumerate(rows):
            # 复选框
            if checkable:
                cb = QCheckBox()
                cb.setChecked(True)
                self._selected.append(orig_i)
                cb.toggled.connect(
                    lambda checked, oi=orig_i: self._toggle(oi, checked))
                self._table.setCellWidget(row_idx, 0, cb)
            else:
                item = QTableWidgetItem("")
                item.setFlags(Qt.NoItemFlags)
                self._table.setItem(row_idx, 0, item)

            # 各列数据
            cells = [
                r.get("file", ""),
                r.get("invoice_type", ""),
                r.get("buyer_name", ""),
                r.get("seller_name", ""),
                r.get("amount", ""),
                r.get("tax_amount", ""),
                r.get("total", ""),
                r.get("invoice_no", ""),
                r.get("invoice_date", ""),
                status,
            ]
            for col, text in enumerate(cells, 1):
                item = QTableWidgetItem(str(text) if text else "")
                item.setForeground(color)
                item.setData(Qt.UserRole, (orig_i, col))
                self._table.setItem(row_idx, col, item)

        self._table.blockSignals(False)
        self._lbl_counts.setText(
            f"新发票 {new_count} 张  |  重复 {dup_count} 张（自动跳过）"
            f"  |  解析失败 {err_count} 张")
        self._refresh_selection_summary()

    # ── 排序 ─────────────────────────────────────

    def _on_header_clicked(self, col: int):
        """点击表头排序（简单字符串比较）"""
        if col == 0:
            return  # 复选框列不排序
        # 先按状态分组（新→重复→错误），组内按列排序
        order = {"新": 0, "重复": 1, "解析失败": 2}

        def sort_key(row):
            item = self._table.item(row, col)
            text = item.text() if item else ""
            status_item = self._table.item(row, len(_COLUMNS) - 1)
            stat = status_item.text() if status_item else "新"
            return (order.get(stat, 99), text)
        # 简单翻转切换（不支持多列，仅切换升/降序）
        self._sort_asc = not getattr(self, '_sort_asc', True)

        rows = list(range(self._table.rowCount()))
        rows.sort(key=sort_key, reverse=not self._sort_asc)
        # 重新排列行（保持 checkbox 绑定不变）
        for vis_idx, src_idx in enumerate(rows):
            if vis_idx != src_idx:
                self._swap_rows(vis_idx, src_idx)

    def _swap_rows(self, a: int, b: int):
        """交换 table 两行（widget+item 全搬）"""
        if a == b:
            return
        widgets_a = [self._table.cellWidget(a, c) for c in range(self._table.columnCount())]
        widgets_b = [self._table.cellWidget(b, c) for c in range(self._table.columnCount())]
        items_a = [self._table.takeItem(a, c) for c in range(self._table.columnCount())]
        items_b = [self._table.takeItem(b, c) for c in range(self._table.columnCount())]
        for c in range(self._table.columnCount()):
            self._table.setItem(a, c, items_b[c])
            if widgets_b[c]:
                self._table.setCellWidget(a, c, widgets_b[c])
            self._table.setItem(b, c, items_a[c])
            if widgets_a[c]:
                self._table.setCellWidget(b, c, widgets_a[c])

    # ── 选择 ─────────────────────────────────────

    def _toggle(self, idx: int, checked: bool):
        if idx in self._select_events:
            return
        self._select_events.add(idx)
        try:
            if checked:
                if idx not in self._selected:
                    self._selected.append(idx)
            else:
                self._selected = [i for i in self._selected if i != idx]
            self._refresh_selection_summary()
        finally:
            self._select_events.discard(idx)

    def _select_all(self):
        self._table.blockSignals(True)
        for orig_i in self._checkable_rows:
            if orig_i not in self._selected:
                self._selected.append(orig_i)
        for r in range(self._table.rowCount()):
            cb = self._table.cellWidget(r, 0)
            if isinstance(cb, QCheckBox):
                cb.setChecked(True)
        self._table.blockSignals(False)
        self._refresh_selection_summary()

    def _deselect_all(self):
        self._table.blockSignals(True)
        self._selected.clear()
        for r in range(self._table.rowCount()):
            cb = self._table.cellWidget(r, 0)
            if isinstance(cb, QCheckBox):
                cb.setChecked(False)
        self._table.blockSignals(False)
        self._refresh_selection_summary()

    def _refresh_selection_summary(self):
        total_amt = 0.0; total_tax = 0.0; total_all = 0.0
        for i in self._selected:
            r = self._results[i]
            total_amt += safe_float(r.get("amount"))
            total_tax += safe_float(r.get("tax_amount"))
            total_all += safe_float(r.get("total"))
        self._lbl_selection.setText(
            f"已选 {len(self._selected)} 张  |  "
            f"金额合计 ¥{total_amt:,.2f}  |  "
            f"税额合计 ¥{total_tax:,.2f}  |  "
            f"价税合计 ¥{total_all:,.2f}"
        )

    def _on_import(self):
        if not self._selected:
            QMessageBox.information(self, "提示", "未选中任何发票。")
            return
        self.accept()
