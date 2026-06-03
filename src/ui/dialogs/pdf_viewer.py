# -*- coding: utf-8 -*-
"""PDF 预览对话框"""

import os

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QMessageBox, QApplication,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap, QImage

import pdfplumber

from ui.theme import DARK_SURFACE, DARK_TEXT, DIALOG_QSS_DARK


class RenderWorker(QThread):
    """后台渲染 PDF 页面，传 QImage 到主线程（QPixmap 不能在非 GUI 线程创建）"""
    finished = pyqtSignal(QImage, str)  # image, error_message

    def __init__(self, page, render_dpi: int = 150):
        super().__init__()
        self.page = page
        self.render_dpi = render_dpi

    def run(self):
        try:
            rotation = getattr(self.page, 'rotation', 0)
            img = self.page.to_image(resolution=self.render_dpi, antialias=True)
            pil_img = img.original
            if rotation:
                pil_img = pil_img.rotate(-rotation, expand=True)
            pil_img = pil_img.convert("RGBA")
            data = pil_img.tobytes("raw", "RGBA")
            qim = QImage(data, pil_img.width, pil_img.height, QImage.Format_RGBA8888)
            self.finished.emit(qim, "")
        except Exception as e:
            self.finished.emit(QImage(), str(e))


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
        self._render_dpi = 150
        self._worker = None
        self._rendering = False

        # 检测系统 DPI 缩放
        try:
            app = QApplication.instance()
            if app:
                screen = app.primaryScreen()
                if screen:
                    ratio = screen.devicePixelRatio()
                    if ratio >= 2.0:
                        self._render_dpi = 300
        except Exception:
            pass

        self.setWindowTitle(os.path.basename(pdf_path))
        self.resize(900, 700)
        self.setMinimumSize(400, 300)

        self._load_pdf()
        self._build_ui()
        self._update_ui_state()
        self._first_show = True

    # ── 加载 PDF ─────────────────────────────────

    def _load_pdf(self):
        try:
            self._pdf = pdfplumber.open(self.pdf_path)
            self._pages = self._pdf.pages
        except FileNotFoundError:
            self._load_error = "文件不存在"
            QMessageBox.warning(self, "错误",
                                f"PDF 文件不存在：\n{self.pdf_path}")
        except Exception as e:
            err_msg = str(e).lower()
            if "password" in err_msg:
                from PyQt5.QtWidgets import QInputDialog, QLineEdit
                pw, ok = QInputDialog.getText(
                    self, "密码保护", "此 PDF 需要密码才能打开：",
                    text="", echo=QLineEdit.Password)
                if ok and pw:
                    try:
                        self._pdf = pdfplumber.open(self.pdf_path, password=pw)
                        self._pages = self._pdf.pages
                        return
                    except Exception:
                        self._load_error = "密码错误"
                        QMessageBox.warning(self, "密码错误", "密码不正确，请用「系统打开」查看。")
                else:
                    self._load_error = "密码取消"
                    QMessageBox.information(self, "需要密码", "请用「系统打开」按钮在外部程序中查看。")
            else:
                self._load_error = "文件损坏或加密"
                QMessageBox.warning(self, "错误",
                                    f"无法打开 PDF 文件，文件可能已损坏或加密：\n{self.pdf_path}")
            self._pages = []

    # ── 后台渲染 ─────────────────────────────────

    def _start_render(self):
        if self._rendering or not self._pages:
            return
        self._rendering = True
        self._set_loading(True)
        page = self._pages[self._current_page]
        self._worker = RenderWorker(page, self._render_dpi)
        self._worker.finished.connect(self._on_render_done)
        self._worker.start()

    def _on_render_done(self, qimage: QImage, error: str):
        self._rendering = False
        self._worker = None
        self._set_loading(False)

        if error:
            QMessageBox.warning(self, "渲染失败",
                                f"第 {self._current_page + 1} 页渲染失败，"
                                f"请用「系统打开」查看完整内容。\n\n{error}")
            return

        # 在主线程将 QImage 转为 QPixmap（Qt 要求 QPixmap 在主线程创建）
        self._original_pixmap = QPixmap.fromImage(qimage)
        self._apply_zoom()

    def _set_loading(self, loading: bool):
        """显示/隐藏加载状态"""
        if loading:
            self.img_label.setText(f"正在加载第 {self._current_page + 1} 页…")
            self.img_label.setStyleSheet(
                f"color:{DARK_TEXT}; font-size:15px; background:{DARK_SURFACE};"
            )
        else:
            self.img_label.setStyleSheet(f"background:{DARK_SURFACE};")

    # ── 构建 UI ──────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

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

        self.setStyleSheet(DIALOG_QSS_DARK)
        for btn in self.findChildren(QPushButton):
            btn.setCursor(Qt.PointingHandCursor)

    # ── 渲染 ─────────────────────────────────────

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

    def _update_ui_state(self):
        n = len(self._pages)
        is_single = n <= 1

        self.btn_prev.setVisible(not is_single)
        self.btn_next.setVisible(not is_single)
        self.lbl_page.setVisible(not is_single)

        if n > 1:
            self.lbl_page.setText(f"{self._current_page + 1} / {n}")

        self.btn_prev.setEnabled(self._current_page > 0 and not self._rendering)
        self.btn_next.setEnabled(self._current_page < n - 1 and not self._rendering)

        # 无页面时禁用操作按钮
        has_pages = bool(self._pages) and not self._load_error
        for btn in (self.btn_fit_w, self.btn_fit_p, self.btn_1to1):
            btn.setEnabled(has_pages)
        self.btn_prev.setEnabled(self.btn_prev.isEnabled() and has_pages)
        self.btn_next.setEnabled(self.btn_next.isEnabled() and has_pages)

    # ── 翻页 ─────────────────────────────────────

    def _go_to_page(self, index):
        if not self._pages or self._rendering:
            return
        n = len(self._pages)
        index = max(0, min(index, n - 1))
        if index != self._current_page:
            self._current_page = index
            self._original_pixmap = None
            self.img_label.setPixmap(QPixmap())
            self._update_ui_state()
            self._start_render()

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

    def showEvent(self, e):
        super().showEvent(e)
        if getattr(self, '_first_show', False):
            self._first_show = False
            if self._pages and not self._load_error:
                # 延迟到事件循环就绪后启动渲染，确保信号能投递
                self._set_loading(True)
                from PyQt5.QtCore import QTimer
                QTimer.singleShot(50, self._start_render)

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
        # 取消正在进行的渲染
        if self._worker and self._worker.isRunning():
            self._worker.finished.disconnect()
            self._worker.quit()
            self._worker.wait(1000)
        self.img_label.setPixmap(QPixmap())
        if self._pdf:
            self._pdf.close()
        super().closeEvent(e)
