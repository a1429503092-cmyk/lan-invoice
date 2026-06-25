# -*- coding: utf-8 -*-
"""统一附件预览对话框 — 左侧文件列表 + 右侧直接预览"""

import os
import shutil
import fitz

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QMessageBox, QListWidget, QListWidgetItem,
    QAbstractItemView, QScrollArea, QFrame, QSplitter, QWidget
)
from PyQt5 import QtCore
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QDesktopServices, QPixmap, QImage

from logger import getLogger
log = getLogger(__name__)

from ui.theme import ACCENT, RED, DARK_BG, DARK_TEXT
from ui.dialogs.image_viewer import ImageViewerDialog
from ui.dialogs.pdf_viewer import PdfViewerDialog

from ui.icons import get as get_icon

IMG_EXTS = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.tiff', '.tif'}
PDF_EXTS = {'.pdf'}

TYPE_ICONS = {'image': 'camera', 'pdf': 'document', 'doc': 'paperclip'}

# 明确定义样式常量，避免主题变量颜色冲突
LIST_BG = "#252525"
LIST_TEXT = "#CCCCCC"
LIST_SELECTED = "#3A5A8C"
PANEL_BG = "#2B2B2B"
PANEL_TEXT = "#D0D0D0"
PANEL_TEXT_SEC = "#999999"


class AttachmentViewerDialog(QDialog):
    """统一附件预览对话框"""

    def __init__(self, attachment_paths: list[str], rec_name: str = "", parent=None):
        super().__init__(parent)
        self.attachment_paths = list(attachment_paths)
        self._rec_name = rec_name
        self._preview_pixmap = None
        self.setWindowTitle(f"附件预览 — {rec_name}" if rec_name else "附件预览")
        self.resize(1000, 650)
        self.setMinimumSize(700, 400)
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

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)

        # ── 左侧文件列表 ──────────────────────
        left_widget = QWidget()
        left_panel = QVBoxLayout(left_widget)
        left_panel.setContentsMargins(0, 0, 0, 0)
        left_panel.setSpacing(6)

        lbl_list = QLabel("附件列表")
        lbl_list.setStyleSheet(f"color:{LIST_TEXT}; font-size:13px; font-weight:bold; background:transparent; padding:4px 8px;")
        left_panel.addWidget(lbl_list)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_widget.setMinimumWidth(180)
        self.list_widget.setIconSize(QtCore.QSize(16, 16))
        self.list_widget.setStyleSheet(
            f"QListWidget {{"
            f"  background:{LIST_BG}; border:1px solid #444; border-radius:4px;"
            f"  color:{LIST_TEXT}; font-size:12px;"
            f"}}"
            f"QListWidget::item {{"
            f"  padding:8px 10px; color:{LIST_TEXT};"
            f"}}"
            f"QListWidget::item:selected {{"
            f"  background:{LIST_SELECTED}; color:white;"
            f"}}"
            f"QListWidget::item:hover {{"
            f"  background:#333;"
            f"}}"
        )
        self.list_widget.currentRowChanged.connect(self._on_selection_changed)
        left_panel.addWidget(self.list_widget, 1)
        self.splitter.addWidget(left_widget)

        # ── 右侧预览区 ────────────────────────
        right_widget = QWidget()
        right_panel = QVBoxLayout(right_widget)
        right_panel.setContentsMargins(12, 0, 0, 0)
        right_panel.setSpacing(8)

        # 预览滚动区域
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setStyleSheet(
            f"QScrollArea {{ background:{PANEL_BG}; border:none; border-radius:6px; }}"
            f"QScrollArea > QWidget > QWidget {{ background:{PANEL_BG}; }}"
        )

        self.preview_container = QFrame()
        self.preview_container.setStyleSheet(f"background:{PANEL_BG}; border:none;")
        preview_layout = QVBoxLayout(self.preview_container)
        preview_layout.setAlignment(Qt.AlignCenter)
        preview_layout.setSpacing(12)

        self.lbl_preview = QLabel("选择一个文件即可预览")
        self.lbl_preview.setAlignment(Qt.AlignCenter)
        self.lbl_preview.setWordWrap(True)
        self.lbl_preview.setStyleSheet(
            f"color:{PANEL_TEXT_SEC}; font-size:14px; background:transparent; padding:20px;"
        )
        preview_layout.addWidget(self.lbl_preview)

        self.lbl_preview_img = QLabel()
        self.lbl_preview_img.setAlignment(Qt.AlignCenter)
        self.lbl_preview_img.hide()
        self.lbl_preview_img.setStyleSheet("background:transparent;")
        preview_layout.addWidget(self.lbl_preview_img)

        self.btn_inline_open = QPushButton()
        self.btn_inline_open.setFixedHeight(40)
        self.btn_inline_open.setFixedWidth(200)
        self.btn_inline_open.hide()
        self.btn_inline_open.setStyleSheet(
            f"background:{ACCENT}; color:white; font-weight:bold; "
            "font-size:14px; border-radius:6px; padding:0 20px;"
        )
        self.btn_inline_open.clicked.connect(self._inline_open)
        preview_layout.addWidget(self.btn_inline_open, alignment=Qt.AlignCenter)

        self.preview_scroll.setWidget(self.preview_container)
        right_panel.addWidget(self.preview_scroll, 1)

        # 文件信息条
        self.lbl_file_info = QLabel("")
        self.lbl_file_info.setStyleSheet(
            f"color:{PANEL_TEXT_SEC}; font-size:11px; background:transparent; padding:4px 8px;"
        )
        right_panel.addWidget(self.lbl_file_info)
        self.splitter.addWidget(right_widget)

        # 初始比例：左侧 260px，右侧占满
        self.splitter.setSizes([260, self.width() - 260])
        layout.addWidget(self.splitter, 1)

        # ── 底部操作栏 ──────────────────────────
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(8)

        self.btn_preview = QPushButton("独立窗口预览")
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

        # 对话框整体样式
        self.setStyleSheet(
            f"QDialog {{ background:{DARK_BG}; }}"
            f"QPushButton {{ color:{DARK_TEXT}; border:1px solid #555; border-radius:4px; padding:4px 12px; background:#333; }}"
            f"QPushButton:hover {{ background:#444; }}"
            f"QPushButton:pressed {{ background:#555; }}"
            f"QLabel {{ color:{DARK_TEXT}; background:transparent; }}"
        )
        for btn in self.findChildren(QPushButton):
            btn.setCursor(Qt.PointingHandCursor)

    def _populate_list(self):
        for path in self.attachment_paths:
            name = os.path.basename(path)
            cat = self._classify(path)
            icon_name = TYPE_ICONS.get(cat, 'paperclip')
            icon = get_icon(icon_name)
            exists = os.path.exists(path)
            display = name if exists else f"❌ {name}（已移动）"
            item = QListWidgetItem(icon, display)
            item.setData(Qt.UserRole, path)
            item.setForeground(Qt.gray if not exists else Qt.white)
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
        cat = self._classify(path)

        if exists:
            size_kb = os.path.getsize(path) / 1024
            size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb / 1024:.2f} MB"
        else:
            size_str = "—"

        cat_label = {'image': '图片', 'pdf': 'PDF文档', 'doc': '文档'}.get(cat, '其他')
        self.lbl_file_info.setText(f"{cat_label}  |  {size_str}  |  {name}")

        self.lbl_preview_img.hide()
        self.btn_inline_open.hide()
        self.lbl_preview.hide()

        if cat == 'image':
            self._show_image_preview(path, exists)
        elif cat == 'pdf':
            self._show_pdf_preview(path, exists)
        else:
            self._show_doc_preview(path, exists)

        self.btn_preview.setEnabled(exists)
        self.btn_sys_open.setEnabled(exists)
        self.btn_download.setEnabled(exists)
        self.btn_remove.setEnabled(True)

    def _show_image_preview(self, path, exists):
        if exists:
            pix = QPixmap(path)
            if not pix.isNull():
                avail_w = self.preview_scroll.width() - 30
                avail_h = self.preview_scroll.height() - 30
                if pix.width() > avail_w or pix.height() > avail_h:
                    pix = pix.scaled(avail_w, avail_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.lbl_preview_img.setPixmap(pix)
                self.lbl_preview_img.show()
                return
        self.lbl_preview.setText("无法预览此图片" if exists else "文件不存在")
        self.lbl_preview.show()

    def _show_pdf_preview(self, path, exists):
        if exists:
            try:
                doc = fitz.open(path)
                if doc.page_count > 0:
                    page = doc[0]
                    mat = fitz.Matrix(1.0, 1.0)
                    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
                    img_data = pix.samples
                    qimg = QImage(img_data, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
                    qpix = QPixmap.fromImage(qimg)
                    doc.close()
                    if not qpix.isNull():
                        avail_w = max(self.preview_scroll.width() - 30, 200)
                        avail_h = max(self.preview_scroll.height() - 60, 200)
                        if qpix.width() > avail_w or qpix.height() > avail_h:
                            qpix = qpix.scaled(avail_w, avail_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        self.lbl_preview_img.setPixmap(qpix)
                        self.lbl_preview_img.show()
                        self.lbl_preview.hide()
                        self.btn_inline_open.hide()
                        return
                doc.close()
            except Exception:
                pass
            self.btn_inline_open.setText("📄 打开 PDF 预览")
            self.btn_inline_open.show()
            self.lbl_preview.setText("PDF 文件 — 点击按钮打开完整预览")
            self.lbl_preview.show()
        else:
            self.lbl_preview.setText("文件不存在")
            self.lbl_preview.show()

    def _show_doc_preview(self, path, exists):
        if exists:
            self.btn_inline_open.setText("🔗 用系统程序打开")
            self.btn_inline_open.show()
            self.lbl_preview.setText(f"文档文件 — 点击下方按钮打开\n\n{os.path.basename(path)}")
            self.lbl_preview.show()
        else:
            self.lbl_preview.setText("文件不存在")
            self.lbl_preview.show()

    def _inline_open(self):
        path = self._get_selected_path()
        if not path or not os.path.exists(path):
            return
        cat = self._classify(path)
        if cat == 'pdf':
            dialog = PdfViewerDialog(path, parent=self)
            dialog.exec_()
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

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
