# -*- coding: utf-8 -*-
"""合同管理对话框"""

import os
import shutil

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QMessageBox, QListWidget, QListWidgetItem
)
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QColor, QDesktopServices

from logger import getLogger
log = getLogger(__name__)

from ui.theme import TEXT, TEXT_DIM, RED, ACCENT_LIGHT, BG_ALT, BORDER


class ContractManagerDialog(QDialog):
    """合同列表管理对话框：查看、下载、打开合同"""

    def __init__(self, contract_paths, rec_name="", parent=None):
        super().__init__(parent)
        self.contract_paths = list(contract_paths)
        self.rec_name = rec_name
        self.setWindowTitle(f"合同管理 — {rec_name}" if rec_name else "合同管理")
        self.resize(600, 420)
        self.setMinimumSize(400, 300)
        self._build_ui()
        self._refresh_list()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        lbl = QLabel("合同文件列表（双击打开）")
        lbl.setStyleSheet(f"font-size:13px; font-weight:bold; color:{TEXT};")
        layout.addWidget(lbl)

        self.list_widget = QListWidget()
        self.list_widget.setAlternatingRowColors(True)
        self.list_widget.setStyleSheet(f"""
            QListWidget {{ font-size:13px; border:1px solid {BORDER}; border-radius:4px; }}
            QListWidget::item {{ padding:6px 8px; }}
            QListWidget::item:selected {{ background:{ACCENT_LIGHT}; color:{TEXT}; }}
            QListWidget::item:alternate {{ background:{BG_ALT}; }}
        """)
        self.list_widget.itemDoubleClicked.connect(self._open_selected)
        self.list_widget.currentItemChanged.connect(lambda *_: self._update_btn_state())
        layout.addWidget(self.list_widget)

        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(8)

        self.btn_open = QPushButton("打开")
        self.btn_open.setFixedHeight(32)
        self.btn_open.clicked.connect(self._open_selected)

        self.btn_download = QPushButton("下载另存")
        self.btn_download.setFixedHeight(32)
        self.btn_download.clicked.connect(self._download_selected)

        self.btn_del = QPushButton("移除")
        self.btn_del.setFixedHeight(32)
        self.btn_del.setStyleSheet(f"color:{RED};")
        self.btn_del.clicked.connect(self._remove_selected)

        self.btn_close = QPushButton("关闭")
        self.btn_close.setFixedHeight(32)
        self.btn_close.clicked.connect(self.accept)

        btn_bar.addWidget(self.btn_open)
        btn_bar.addWidget(self.btn_download)
        btn_bar.addWidget(self.btn_del)
        btn_bar.addStretch()
        btn_bar.addWidget(self.btn_close)
        layout.addLayout(btn_bar)

        hint = QLabel("提示：支持 PDF 和 Word（.docx/.doc）格式，用系统默认程序打开")
        hint.setStyleSheet(f"color:{TEXT_DIM}; font-size:11px;")
        layout.addWidget(hint)

        from ui.theme import DIALOG_QSS
        self.setStyleSheet(DIALOG_QSS)
        for btn in self.findChildren(QPushButton):
            btn.setCursor(Qt.PointingHandCursor)

    def _refresh_list(self):
        self.list_widget.clear()
        for path in self.contract_paths:
            fname = os.path.basename(path)
            exists = os.path.exists(path)
            item = QListWidgetItem()
            ext = os.path.splitext(fname)[1].lower()
            if ext == ".pdf":
                icon_txt = "[PDF]"
            elif ext in (".docx", ".doc"):
                icon_txt = "[DOC]"
            else:
                icon_txt = "[FILE]"
            status = "" if exists else "  ! 文件已移动"
            item.setText(f"  {icon_txt}  {fname}{status}")
            item.setData(Qt.UserRole, path)
            if not exists:
                item.setForeground(QColor(RED))
            self.list_widget.addItem(item)
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)
        self._update_btn_state()

    def _update_btn_state(self):
        has_sel = self.list_widget.currentRow() >= 0
        self.btn_open.setEnabled(has_sel)
        self.btn_download.setEnabled(has_sel)
        self.btn_del.setEnabled(has_sel)

    def _get_selected_path(self):
        item = self.list_widget.currentItem()
        if item:
            return item.data(Qt.UserRole)
        return None

    def _open_selected(self):
        path = self._get_selected_path()
        if not path:
            return
        if not os.path.exists(path):
            QMessageBox.warning(self, "文件不存在", f"找不到文件：\n{path}")
            return
        try:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        except Exception as e:
            QMessageBox.warning(self, "打开失败", f"无法打开文件：\n{e}")

    def _download_selected(self):
        path = self._get_selected_path()
        if not path:
            return
        if not os.path.exists(path):
            QMessageBox.warning(self, "文件不存在", f"找不到文件：\n{path}")
            return
        ext = os.path.splitext(path)[1]
        dst, _ = QFileDialog.getSaveFileName(
            self, "另存合同文件", os.path.basename(path),
            f"文件 (*{ext});;所有文件 (*)"
        )
        if dst:
            shutil.copy2(path, dst)
            QMessageBox.information(self, "下载成功", f"合同已保存到：\n{dst}")

    def _remove_selected(self):
        row = self.list_widget.currentRow()
        if row < 0:
            return
        fname = os.path.basename(self.contract_paths[row])
        reply = QMessageBox.question(
            self, "确认移除",
            f"确认从列表中移除「{fname}」？\n（文件本身不会被删除）",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.contract_paths.pop(row)
            self._refresh_list()
