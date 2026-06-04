# -*- coding: utf-8 -*-
"""拖拽添加附件对话框 — 拖入文件预览列表 + 确认添加"""

import os

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QListWidget, QListWidgetItem, QAbstractItemView, QFrame
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QDragEnterEvent, QDropEvent

IMG_EXTS = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.tiff', '.tif'}
PDF_EXTS = {'.pdf'}
DOC_EXTS = {'.docx', '.doc', '.xlsx', '.xls'}
VALID_EXTS = IMG_EXTS | PDF_EXTS | DOC_EXTS

TYPE_ICONS = {'image': '\U0001F5BC', 'pdf': '\U0001F4C4', 'doc': '\U0001F4CE'}

PANEL_BG = "#2B2B2B"
PANEL_TEXT = "#CCCCCC"
PANEL_DIM = "#888888"
ACCENT = "#1E6FBF"
RED = "#D94A4A"
GREEN = "#3DA55D"


class AddAttachmentDialog(QDialog):
    """拖拽添加附件对话框"""

    files_added = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pending_files = []  # (path, type) tuples
        self.setWindowTitle("添加附件")
        self.resize(540, 460)
        self.setMinimumSize(400, 320)
        self.setAcceptDrops(True)
        self._build_ui()

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
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # ── 标题 ─────────────────────────────
        lbl_title = QLabel("拖拽文件到此处添加附件")
        lbl_title.setAlignment(Qt.AlignCenter)
        lbl_title.setFixedHeight(80)
        lbl_title.setStyleSheet(
            f"background:{PANEL_BG}; border:2px dashed #555; border-radius:10px;"
            f"color:{PANEL_DIM}; font-size:15px;"
        )
        layout.addWidget(lbl_title)

        # ── 文件计数 + 浏览按钮 ──────────────
        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        self.lbl_count = QLabel("暂未添加文件")
        self.lbl_count.setStyleSheet(f"color:{PANEL_DIM}; font-size:12px;")
        top_row.addWidget(self.lbl_count)
        top_row.addStretch()
        btn_browse = QPushButton("浏览文件…")
        btn_browse.setFixedHeight(30)
        btn_browse.clicked.connect(self._browse_files)
        top_row.addWidget(btn_browse)
        layout.addLayout(top_row)

        # ── 文件列表 ─────────────────────────
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_widget.setStyleSheet(
            f"QListWidget {{"
            f"  background:{PANEL_BG}; border:1px solid #444; border-radius:4px;"
            f"  color:{PANEL_TEXT}; font-size:12px;"
            f"}}"
            f"QListWidget::item {{ padding:6px 8px; color:{PANEL_TEXT}; }}"
            f"QListWidget::item:selected {{ background:#3A5A8C; color:white; }}"
        )
        layout.addWidget(self.list_widget, 1)

        # ── 底部按钮 ─────────────────────────
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(8)
        self.btn_remove = QPushButton("移除选中")
        self.btn_remove.setFixedHeight(32)
        self.btn_remove.setEnabled(False)
        self.btn_remove.setStyleSheet(
            f"color:{PANEL_TEXT}; border:1px solid #555; border-radius:4px; padding:0 12px; background:#333;"
        )
        self.btn_remove.clicked.connect(self._remove_selected)
        self.list_widget.itemSelectionChanged.connect(
            lambda: self.btn_remove.setEnabled(len(self.list_widget.selectedItems()) > 0)
        )

        btn_bar.addWidget(self.btn_remove)
        btn_bar.addStretch()

        self.btn_add = QPushButton("确认添加")
        self.btn_add.setFixedHeight(36)
        self.btn_add.setFixedWidth(120)
        self.btn_add.setEnabled(False)
        self.btn_add.setStyleSheet(
            f"background:{ACCENT}; color:white; font-weight:bold; font-size:13px;"
            f"border:none; border-radius:6px;"
        )
        self.btn_add.clicked.connect(self.accept)

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setFixedHeight(36)
        self.btn_cancel.setFixedWidth(80)
        self.btn_cancel.setStyleSheet(
            f"color:{PANEL_TEXT}; border:1px solid #555; border-radius:6px;"
            f"padding:0 12px; background:#333;"
        )
        self.btn_cancel.clicked.connect(self.reject)

        btn_bar.addWidget(self.btn_add)
        btn_bar.addWidget(self.btn_cancel)
        layout.addLayout(btn_bar)

        self.setStyleSheet(f"QDialog {{ background:#1E1E1E; }}")
        for btn in self.findChildren(QPushButton):
            btn.setCursor(Qt.PointingHandCursor)

    def _add_files(self, paths: list[str]):
        added = 0
        existing = {p for p, _ in self._pending_files}
        for path in paths:
            if not os.path.isfile(path):
                continue
            ext = os.path.splitext(path)[1].lower()
            if ext not in VALID_EXTS:
                continue
            if path in existing:
                continue
            cat = self._classify(path)
            icon = TYPE_ICONS.get(cat, '\U0001F4CE')
            name = os.path.basename(path)
            item = QListWidgetItem(f"{icon}  {name}")
            item.setData(Qt.UserRole, path)
            self.list_widget.addItem(item)
            self._pending_files.append((path, cat))
            existing.add(path)
            added += 1

        if added > 0:
            self._update_count()

    def _update_count(self):
        n = len(self._pending_files)
        self.lbl_count.setText(f"已添加 {n} 个文件")
        self.btn_add.setEnabled(n > 0)
        self.btn_add.setText(f"确认添加 ({n})" if n > 0 else "确认添加")

    def _remove_selected(self):
        rows = sorted([self.list_widget.row(item) for item in self.list_widget.selectedItems()], reverse=True)
        for row in rows:
            self.list_widget.takeItem(row)
            del self._pending_files[row]
        self._update_count()

    def _browse_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择附件文件", "",
            "附件文件 (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.pdf *.docx *.doc *.xlsx *.xls);;所有文件 (*)"
        )
        if files:
            self._add_files(files)

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent):
        paths = [u.toLocalFile() for u in e.mimeData().urls()]
        self._add_files(paths)

    def get_files(self) -> list[str]:
        return [p for p, _ in self._pending_files]
