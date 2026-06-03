# -*- coding: utf-8 -*-
"""PDF 预览对话框"""

import os

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QMessageBox,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QImage

import pdfplumber

from ui.theme import DARK_SURFACE, DARK_TEXT, DIALOG_QSS_DARK


class PdfViewerDialog(QDialog):
    """PDF 预览对话框，支持翻页、缩放、系统打开。"""

    def __init__(self, pdf_path: str, parent=None):
        super().__init__(parent)
        self.pdf_path = pdf_path
        self._pages = []
        self._current_page = 0
        self._zoom_mode = "fit_width"
        self._original_pixmap = None
        self._pdf = None
        self._load_error = None

        self.setWindowTitle(os.path.basename(pdf_path))
        self.resize(900, 700)
        self.setMinimumSize(400, 300)

        self._load_pdf()
        self._build_ui()

        if self._pages and not self._load_error:
            self._render_current()
        self._update_page_label()

    # ── 加载 PDF ─────────────────────────────────

    def _load_pdf(self):
        try:
            self._pdf = pdfplumber.open(self.pdf_path)
            self._pages = self._pdf.pages
        except FileNotFoundError:
            self._load_error = "文件不存在"
            QMessageBox.warning(self, "错误",
                                f"PDF 文件不存在：\n{self.pdf_path}")
        except Exception:
            self._load_error = "文件损坏或加密"
            QMessageBox.warning(self, "错误",
                                f"无法打开 PDF 文件，文件可能已损坏或加密：\n{self.pdf_path}")

    # ── 构建 UI ──────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 滚动区域
        self.scroll = QScrollArea()
        self.scroll.setAlignment(Qt.AlignCenter)
        self.scroll.setStyleSheet(
            f"QScrollArea {{ background:{DARK_SURFACE}; border:none; }}"
        )
        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignCenter)
        self.img_label.setStyleSheet(f"background:{DARK_SURFACE};")
        self.scroll.setWidget(self.img_label)
        self.scroll.setWidgetResizable(True)
        layout.addWidget(self.scroll, 1)

        # 导航栏
        nav = QHBoxLayout()
        nav.setSpacing(8)

        self.btn_prev = QPushButton("◀ 上一页")
        self.btn_prev.setFixedHeight(32)
        self.btn_prev.clicked.connect(self._prev_page)

        self.lbl_page = QLabel()
        self.lbl_page.setAlignment(Qt.AlignCenter)
        self.lbl_page.setStyleSheet(
            f"color:{DARK_TEXT}; font-size:13px; background:transparent;"
        )

        self.btn_next = QPushButton("下一页 ▶")
        self.btn_next.setFixedHeight(32)
        self.btn_next.clicked.connect(self._next_page)

        nav.addWidget(self.btn_prev)
        nav.addStretch()
        nav.addWidget(self.lbl_page)
        nav.addStretch()
        nav.addWidget(self.btn_next)
        layout.addLayout(nav)

        # 缩放栏
        zoom_row = QHBoxLayout()
        zoom_row.setSpacing(8)

        self.btn_fit_w = QPushButton("适应宽度")
        self.btn_fit_w.setFixedHeight(32)
        self.btn_fit_w.clicked.connect(lambda: self._set_zoom("fit_width"))

        self.btn_fit_p = QPushButton("适应页面")
        self.btn_fit_p.setFixedHeight(32)
        self.btn_fit_p.clicked.connect(lambda: self._set_zoom("fit_page"))

        self.btn_1to1 = QPushButton("100%")
        self.btn_1to1.setFixedHeight(32)
        self.btn_1to1.clicked.connect(lambda: self._set_zoom("1:1"))

        zoom_row.addStretch()
        zoom_row.addWidget(self.btn_fit_w)
        zoom_row.addWidget(self.btn_fit_p)
        zoom_row.addWidget(self.btn_1to1)
        zoom_row.addStretch()
        layout.addLayout(zoom_row)

        # 操作栏
        action_row = QHBoxLayout()
        action_row.setSpacing(8)

        self.btn_sys = QPushButton("系统打开")
        self.btn_sys.setFixedHeight(32)
        self.btn_sys.clicked.connect(self._open_system)

        self.btn_close = QPushButton("关闭")
        self.btn_close.setFixedHeight(32)
        self.btn_close.clicked.connect(self.accept)

        action_row.addStretch()
        action_row.addWidget(self.btn_sys)
        action_row.addWidget(self.btn_close)
        layout.addLayout(action_row)

        # 应用暗色主题
        self.setStyleSheet(DIALOG_QSS_DARK)
        for btn in self.findChildren(QPushButton):
            btn.setCursor(Qt.PointingHandCursor)

        # 单页 PDF 隐藏导航
        if len(self._pages) <= 1:
            self.btn_prev.setVisible(False)
            self.btn_next.setVisible(False)
            self.lbl_page.setVisible(False)

        # 无页面时禁用按钮
        if not self._pages:
            for btn in (self.btn_prev, self.btn_next,
                        self.btn_fit_w, self.btn_fit_p, self.btn_1to1,
                        self.btn_sys):
                btn.setEnabled(False)

    # ── 渲染 ─────────────────────────────────────

    def _render_current(self):
        if not self._pages or self._load_error:
            return
        page = self._pages[self._current_page]
        img = page.to_image(resolution=150, antialias=True)
        img = img.convert("RGBA")
        data = img.tobytes("raw", "RGBA")
        qim = QImage(data, img.width, img.height, QImage.Format_RGBA8888)
        self._original_pixmap = QPixmap.fromImage(qim)
        self._apply_zoom()

    def _apply_zoom(self):
        if self._original_pixmap is None:
            return
        vp = self.scroll.viewport()
        if vp is None:
            return
        if self._zoom_mode == "1:1":
            self.img_label.setPixmap(self._original_pixmap)
        elif self._zoom_mode == "fit_width":
            sw = max(vp.width() - 20, 50)
            pix = self._original_pixmap.scaledToWidth(
                sw, Qt.SmoothTransformation)
            self.img_label.setPixmap(pix)
        elif self._zoom_mode == "fit_page":
            sw = max(vp.width() - 20, 50)
            sh = max(vp.height() - 20, 50)
            pix = self._original_pixmap.scaled(
                sw, sh, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.img_label.setPixmap(pix)

    def _update_page_label(self):
        n = len(self._pages)
        if n > 1:
            self.lbl_page.setText(f"{self._current_page + 1} / {n}")
        self.btn_prev.setEnabled(self._current_page > 0)
        self.btn_next.setEnabled(self._current_page < n - 1)

    # ── 翻页 ─────────────────────────────────────

    def _go_to_page(self, index):
        if not self._pages:
            return
        n = len(self._pages)
        index = max(0, min(index, n - 1))
        if index != self._current_page:
            self._current_page = index
            self._render_current()
            self._update_page_label()

    def _prev_page(self):
        self._go_to_page(self._current_page - 1)

    def _next_page(self):
        self._go_to_page(self._current_page + 1)

    # ── 缩放 ─────────────────────────────────────

    def _set_zoom(self, mode):
        self._zoom_mode = mode
        self._apply_zoom()

    # ── 系统打开 ─────────────────────────────────

    def _open_system(self):
        if not os.path.exists(self.pdf_path):
            QMessageBox.warning(self, "错误",
                                f"PDF 文件不存在：\n{self.pdf_path}")
            return
        os.startfile(self.pdf_path)

    # ── 事件 ─────────────────────────────────────

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Left:
            self._prev_page()
        elif e.key() == Qt.Key_Right:
            self._next_page()
        elif e.key() == Qt.Key_Home:
            self._go_to_page(0)
        elif e.key() == Qt.Key_End:
            self._go_to_page(len(self._pages) - 1)
        elif e.key() == Qt.Key_Escape:
            self.accept()
        else:
            super().keyPressEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._apply_zoom()

    def closeEvent(self, e):
        self.img_label.setPixmap(QPixmap())
        if self._pdf:
            self._pdf.close()
        super().closeEvent(e)
