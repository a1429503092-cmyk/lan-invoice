# -*- coding: utf-8 -*-
"""导入预览对话框 — 展示解析结果，允许选择性导入"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox,
    QMessageBox, QAbstractItemView
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

from ui.theme import TEXT, TEXT_SEC, TEXT_DIM


class ImportPreviewDialog(QDialog):
    """解析结果预览：新发票（可勾选）+ 重复（灰显）+ 错误（红显）"""

    def __init__(self, results: list[dict], existing_nos: set[str], parent=None):
        """
        results: [{file, invoice_no, invoice_date, amount, invoice_type, error, ...}, ...]
        existing_nos: 已存在的发票号集合
        """
        super().__init__(parent)
        self._results = results
        self._existing = existing_nos
        self._selected: list[int] = []  # 用户勾选的 results 索引
        self.setWindowTitle("导入预览")
        self.setMinimumSize(680, 400)
        self._build_ui()
        self._populate()

    def get_selected_indices(self) -> list[int]:
        return list(self._selected)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        lbl = QLabel("解析完成，请确认要导入的发票（重复项已自动排除）")
        lbl.setStyleSheet(f"font-size:12px; color:{TEXT};")
        layout.addWidget(lbl)

        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(
            ["", "文件名", "发票号码", "开票日期", "金额"])
        h = self._table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Fixed)
        self._table.setColumnWidth(0, 30)
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table, 1)

        # 摘要行
        self._lbl_summary = QLabel()
        self._lbl_summary.setStyleSheet(f"font-size:11px; color:{TEXT_DIM};")
        layout.addWidget(self._lbl_summary)

        # 按钮
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._btn_select_all = QPushButton("全选")
        self._btn_select_all.clicked.connect(self._select_all)
        btn_row.addWidget(self._btn_select_all)
        btn_row.addStretch()
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        btn_import = QPushButton("导入选中")
        btn_import.setDefault(True)
        btn_import.clicked.connect(self._on_import)
        btn_row.addWidget(btn_import)
        layout.addLayout(btn_row)

    def _populate(self):
        new_count = 0
        dup_count = 0
        err_count = 0
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

        self._table.setRowCount(len(rows))
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

            fname = r.get("file", "")
            inv_no = r.get("invoice_no", "")
            inv_date = r.get("invoice_date", "")
            amt = r.get("amount", "")

            for col, text in enumerate([fname, inv_no, inv_date,
                                         f"{amt}  {status}"], 1):
                item = QTableWidgetItem(str(text) if text else "")
                item.setForeground(color)
                self._table.setItem(row_idx, col, item)

        self._lbl_summary.setText(
            f"新发票 {new_count} 张  |  重复 {dup_count} 张（自动跳过）"
            f"  |  解析失败 {err_count} 张")

    def _toggle(self, idx: int, checked: bool):
        if checked:
            if idx not in self._selected:
                self._selected.append(idx)
        else:
            self._selected = [i for i in self._selected if i != idx]

    def _select_all(self):
        self._selected.clear()
        for row in range(self._table.rowCount()):
            w = self._table.cellWidget(row, 0)
            if isinstance(w, QCheckBox):
                w.setChecked(True)

    def _on_import(self):
        if not self._selected:
            QMessageBox.information(self, "提示", "未选中任何发票。")
            return
        self.accept()
