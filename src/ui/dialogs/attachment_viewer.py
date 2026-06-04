# -*- coding: utf-8 -*-
"""统一附件预览对话框 — 按类型自动选择预览方式"""

import os
import shutil
from datetime import datetime

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QMessageBox, QListWidget, QListWidgetItem,
    QAbstractItemView
)
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QDesktopServices

from logger import getLogger
log = getLogger(__name__)

from ui.theme import ACCENT, RED, DARK_SURFACE, DARK_BG, DARK_TEXT, DARK_TEXT_DIM
from ui.dialogs.image_viewer import ImageViewerDialog
from ui.dialogs.pdf_viewer import PdfViewerDialog

IMG_EXTS = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.tiff', '.tif'}
PDF_EXTS = {'.pdf'}

TYPE_ICONS = {'image': '\U0001F5BC', 'pdf': '\U0001F4C4', 'doc': '\U0001F4CE'}


class AttachmentViewerDialog(QDialog):
    """统一附件预览对话框"""

    def __init__(self, attachment_paths: list[str], rec_name: str = "", parent=None):
        super().__init__(parent)
        self.attachment_paths = list(attachment_paths)
        self._rec_name = rec_name
        self.setWindowTitle(f"附件预览 — {rec_name}" if rec_name else "附件预览")
        self.resize(900, 600)
        self.setMinimumSize(500, 350)
        self._build_ui()
        self._populate_list()

    def _classify(self, path: str) -> str:
        ext = os.path.splitext(path)[1].lower()
        if ext in IMG_EXTS:
            return 'image'
        elif ext in PDF_EXTS:
            return 'pdf'
        else:
            return 'doc'

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        body = QHBoxLayout()
        body.setSpacing(8)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_widget.setFixedWidth(280)
        self.list_widget.setStyleSheet(
            f"QListWidget {{ background:{DARK_BG}; border:1px solid #444; }}"
            f"QListWidget::item {{ padding:6px; }}"
            f"QListWidget::item:selected {{ background:#3A5A8C; }}"
        )
        self.list_widget.currentRowChanged.connect(self._on_selection_changed)
        body.addWidget(self.list_widget)

        right = QVBoxLayout()
        right.setSpacing(8)
        self.lbl_info = QLabel("选择一个文件查看详情")
        self.lbl_info.setWordWrap(True)
        self.lbl_info.setStyleSheet(
            f"color:{DARK_TEXT}; font-size:13px; "
            f"background:{DARK_SURFACE}; padding:12px; border-radius:6px;"
        )
        right.addWidget(self.lbl_info, 1)
        body.addLayout(right, 1)
        layout.addLayout(body)

        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(8)

        self.btn_preview = QPushButton("预览")
        self.btn_preview.setFixedHeight(32)
        self.btn_preview.setEnabled(False)
        self.btn_preview.clicked.connect(self._preview_selected)

        self.btn_sys_open = QPushButton("系统打开")
        self.btn_sys_open.setFixedHeight(32)
        self.btn_sys_open.setEnabled(False)
        self.btn_sys_open.clicked.connect(self._open_system)

        self.btn_download = QPushButton("下载另存")
        self.btn_download.setFixedHeight(32)
        self.btn_download.setEnabled(False)
        self.btn_download.clicked.connect(self._download_selected)

        self.btn_remove = QPushButton("移除")
        self.btn_remove.setFixedHeight(32)
        self.btn_remove.setEnabled(False)
        self.btn_remove.setStyleSheet(
            f"background:{RED}; color:white; font-weight:bold; border-radius:4px; padding:0 12px;"
        )
        self.btn_remove.clicked.connect(self._remove_selected)

        btn_bar.addWidget(self.btn_preview)
        btn_bar.addWidget(self.btn_sys_open)
        btn_bar.addWidget(self.btn_download)
        btn_bar.addWidget(self.btn_remove)
        btn_bar.addStretch()

        btn_close = QPushButton("关闭")
        btn_close.setFixedHeight(32)
        btn_close.clicked.connect(self.accept)
        btn_bar.addWidget(btn_close)
        layout.addLayout(btn_bar)

        from ui.theme import DIALOG_QSS_DARK
        self.setStyleSheet(DIALOG_QSS_DARK)
        for btn in self.findChildren(QPushButton):
            btn.setCursor(Qt.PointingHandCursor)

    def _populate_list(self):
        for path in self.attachment_paths:
            name = os.path.basename(path)
            cat = self._classify(path)
            icon_text = TYPE_ICONS.get(cat, '\U0001F4CE')
            exists = os.path.exists(path)
            display = f"{icon_text} {name}" if exists else f"❌ {name}（已移动）"
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, path)
            self.list_widget.addItem(item)

    def _on_selection_changed(self, row):
        if row < 0:
            return
        item = self.list_widget.item(row)
        if not item:
            return
        path = item.data(Qt.UserRole)
        if not path:
            return
        exists = os.path.exists(path)
        name = os.path.basename(path)
        size = f"{os.path.getsize(path) / 1024:.1f} KB" if exists else "—"
        cat = self._classify(path)
        cat_label = {'image': '图片', 'pdf': 'PDF文档', 'doc': '文档'}.get(cat, '其他')
        self.lbl_info.setText(
            f"<b>{name}</b><br>"
            f"<span style='color:{DARK_TEXT_DIM};'>类型：{cat_label}</span><br>"
            f"<span style='color:{DARK_TEXT_DIM};'>大小：{size}</span><br>"
            f"<span style='color:{DARK_TEXT_DIM};'>路径：{path}</span>"
        )
        self.btn_preview.setEnabled(exists)
        self.btn_sys_open.setEnabled(exists)
        self.btn_download.setEnabled(exists)
        self.btn_remove.setEnabled(True)

    def _get_selected_path(self):
        item = self.list_widget.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _preview_selected(self):
        path = self._get_selected_path()
        if not path or not os.path.exists(path):
            return
        cat = self._classify(path)
        if cat == 'image':
            dialog = ImageViewerDialog([path], parent=self)
            dialog.exec_()
        elif cat == 'pdf':
            dialog = PdfViewerDialog(path, parent=self)
            dialog.exec_()
        else:
            self._open_system()

    def _open_system(self):
        path = self._get_selected_path()
        if not path or not os.path.exists(path):
            QMessageBox.warning(self, "文件不存在", "文件不存在或已被移动。")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _download_selected(self):
        path = self._get_selected_path()
        if not path or not os.path.exists(path):
            QMessageBox.warning(self, "文件不存在", "文件不存在或已被移动。")
            return
        dst, _ = QFileDialog.getSaveFileName(
            self, "另存附件", os.path.basename(path), "所有文件 (*)"
        )
        if dst:
            shutil.copy2(path, dst)
            QMessageBox.information(self, "保存成功", f"文件已保存到：\n{dst}")

    def _remove_selected(self):
        row = self.list_widget.currentRow()
        if row < 0:
            return
        item = self.list_widget.item(row)
        if not item:
            return
        path = item.data(Qt.UserRole)
        reply = QMessageBox.question(
            self, "确认移除",
            f"确定要移除「{os.path.basename(path)}」吗？\n\n"
            f"此操作仅从列表中移除记录，不会删除文件。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        if path in self.attachment_paths:
            self.attachment_paths.remove(path)
        self.list_widget.takeItem(row)
