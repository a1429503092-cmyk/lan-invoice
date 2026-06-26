# -*- coding: utf-8 -*-
"""PDF 预览对话框 — 图片底层 + 可选文字覆盖层"""

import os

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QMessageBox, QApplication, QGraphicsView, QGraphicsScene,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QEvent, QSize, QUrl
from PyQt5.QtGui import QPixmap, QImage, QColor, QDesktopServices, QPainter, QFont, QIcon

from ui.theme import DARK_SURFACE, DARK_TEXT, DIALOG_QSS_DARK
from logger import getLogger

log = getLogger(__name__)

# 文字识别图标 — 20×20 的 "T" 字母 + 选中高亮下划线
_TEXT_ICON = None


def _get_text_icon() -> QIcon:
    """懒加载生成文字识别图标"""
    global _TEXT_ICON
    if _TEXT_ICON is not None:
        return _TEXT_ICON
    size = 20
    pix_on = QPixmap(size, size)
    pix_on.fill(Qt.transparent)
    p = QPainter(pix_on)
    p.setRenderHint(QPainter.Antialiasing)
    # T 字母
    f = QFont("Microsoft YaHei", 10, QFont.Bold)
    p.setFont(f)
    p.setPen(QColor("#D0D8E8"))
    p.drawText(1, 2, size - 2, size - 4, Qt.AlignCenter, "T")
    # 选中高亮线
    p.fillRect(3, size - 5, 14, 2, QColor("#FFEB50"))
    p.end()

    pix_off = QPixmap(size, size)
    pix_off.fill(Qt.transparent)
    p = QPainter(pix_off)
    p.setRenderHint(QPainter.Antialiasing)
    p.setFont(f)
    p.setPen(QColor("#5A6070"))
    p.drawText(1, 2, size - 2, size - 4, Qt.AlignCenter, "T")
    p.fillRect(3, size - 5, 14, 2, QColor("#5A6070"))
    p.end()

    icon = QIcon()
    icon.addPixmap(pix_on, QIcon.Normal, QIcon.On)
    icon.addPixmap(pix_off, QIcon.Normal, QIcon.Off)
    _TEXT_ICON = icon
    return icon


class RenderWorker(QThread):
    """后台渲染 PDF 页面为图片 + 提取文字块坐标"""
    finished = pyqtSignal(QImage, list, str)  # image, text_blocks, error

    def __init__(self, pdf_path: str, page_index: int, render_dpi: int = 200):
        # 默认值仅作回退，实际由 PdfViewerDialog._screen_dpi() 决定
        super().__init__()
        self.pdf_path = pdf_path
        self.page_index = page_index
        self.render_dpi = render_dpi

    def run(self):
        import fitz
        try:
            doc = fitz.open(self.pdf_path)
            page = doc[self.page_index]
            zoom = self.render_dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
            samples = bytes(pix.samples)

            # 用 word 级别坐标按行分组，精确匹配文字实际区域
            text_blocks = []
            words = page.get_text("words")
            if words:
                lines = {}
                for w in words:
                    x0, y0, x1, y1, word_text = w[:5]
                    if not word_text.strip():
                        continue
                    block_no = w[5] if len(w) > 5 else 0
                    line_no = w[6] if len(w) > 6 else 0
                    key = (block_no, line_no)
                    if key not in lines:
                        lines[key] = {"x0": x0, "y0": y0, "x1": x1, "y1": y1,
                                       "words": []}
                    entry = lines[key]
                    entry["x0"] = min(entry["x0"], x0)
                    entry["y0"] = min(entry["y0"], y0)
                    entry["x1"] = max(entry["x1"], x1)
                    entry["y1"] = max(entry["y1"], y1)
                    entry["words"].append(word_text)

                for entry in lines.values():
                    text_blocks.append({
                        "text": " ".join(entry["words"]),
                        "x": entry["x0"] * zoom,
                        "y": entry["y0"] * zoom,
                        "w": max((entry["x1"] - entry["x0"]) * zoom, 10),
                        "h": max((entry["y1"] - entry["y0"]) * zoom, 10),
                    })

            doc.close()
            qim = QImage(samples, pix.width, pix.height,
                         pix.width * pix.n, QImage.Format_RGB888).copy()
            self.finished.emit(qim, text_blocks, "")
        except Exception as e:
            log.error("PDF 渲染失败: %s 第%d页 | %s",
                      os.path.basename(self.pdf_path), self.page_index, e)
            self.finished.emit(QImage(), [], str(e))


class PdfViewerDialog(QDialog):
    """PDF 预览对话框，支持翻页、缩放、文字框选复制、系统打开。"""

    def __init__(self, pdf_path: str, parent=None):
        super().__init__(parent)
        self.pdf_path = pdf_path
        self._page_count = 0
        self._current_page = 0
        self._zoom_mode = "fit_width"
        self._load_error = None
        self._render_dpi = self._screen_dpi()
        self._worker = None
        self._rendering = False
        self._pixmap_item = None
        self._text_items = []
        self._text_blocks_data = []
        self._text_mode = False  # 文字识别默认关闭

        self.setWindowTitle(os.path.basename(pdf_path))
        self.resize(900, 700)
        self.setMinimumSize(400, 300)

        self._load_pdf()
        self._build_ui()
        self._update_ui_state()
        self._first_show = True

    # ── 加载 PDF（仅获取页数）────────────────────

    @staticmethod
    def _screen_dpi() -> int:
        """获取渲染分辨率：取屏幕物理 DPI × 1.5，保证缩放不糊"""
        try:
            from PyQt5.QtWidgets import QApplication
            app = QApplication.instance()
            if app and app.primaryScreen():
                dpi = int(app.primaryScreen().physicalDotsPerInch() * 1.5)
                return max(300, min(dpi, 600))
        except Exception:
            pass
        return 300

    def _load_pdf(self):
        import fitz
        try:
            doc = fitz.open(self.pdf_path)
            self._page_count = len(doc)
            doc.close()
            log.info("PDF 已打开: %s | %d 页",
                     os.path.basename(self.pdf_path), self._page_count)
        except FileNotFoundError:
            log.warning("PDF 文件不存在: %s", self.pdf_path)
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
                        doc = fitz.open(self.pdf_path)
                        doc.authenticate(pw)
                        self._page_count = len(doc)
                        doc.close()
                        return
                    except Exception:
                        self._load_error = "密码错误"
                        QMessageBox.warning(self, "密码错误", "密码不正确，请用「系统打开」查看。")
                else:
                    self._load_error = "密码取消"
                    QMessageBox.information(self, "需要密码", "请用「系统打开」按钮在外部程序中查看。")
            else:
                self._load_error = "文件损坏或加密"
                log.warning("PDF 打开异常: %s | %s", self.pdf_path, e)
                QMessageBox.warning(self, "错误",
                                    f"无法打开 PDF 文件，文件可能已损坏或加密：\n{self.pdf_path}")
            self._page_count = 0

    # ── 后台渲染 ─────────────────────────────────

    def _start_render(self):
        if self._rendering or self._page_count == 0:
            return
        self._rendering = True
        self._set_loading(True)
        self._worker = RenderWorker(self.pdf_path, self._current_page, self._render_dpi)
        self._worker.finished.connect(self._on_render_done)
        self._worker.start()

    def _on_render_done(self, qimage: QImage, text_blocks: list, error: str):
        self._rendering = False
        self._worker = None
        self._set_loading(False)

        if error:
            QMessageBox.warning(self, "渲染失败",
                                f"第 {self._current_page + 1} 页渲染失败，"
                                f"请用「系统打开」查看完整内容。\n\n{error}")
            return

        self.scene.clear()
        self._pixmap_item = None
        self._text_items = []
        self._text_blocks_data = text_blocks

        pixmap = QPixmap.fromImage(qimage)
        self._pixmap_item = self.scene.addPixmap(pixmap)
        self.scene.setSceneRect(self._pixmap_item.boundingRect())

        if self._text_mode:
            self._add_text_items()

        self._apply_zoom()

    def _add_text_items(self):
        """根据缓存的文字块数据创建可选文字叠加层"""
        for block in self._text_blocks_data:
            item = self.scene.addText(block["text"])
            item.setPos(block["x"], block["y"])
            item.setTextWidth(block["w"])
            item.setDefaultTextColor(QColor(0, 0, 0, 0))
            item.setTextInteractionFlags(Qt.TextSelectableByMouse)
            item.setCursor(Qt.IBeamCursor)
            font = QFont("Microsoft YaHei")
            font.setPixelSize(max(int(block["h"] * 0.7), 9))
            item.setFont(font)
            self._text_items.append(item)

    def _remove_text_items(self):
        """移除所有文字叠加层"""
        for item in self._text_items:
            self.scene.removeItem(item)
        self._text_items = []

    def _toggle_text_mode(self, enabled: bool):
        self._text_mode = enabled
        if self._pixmap_item is None:
            return
        if enabled:
            self._add_text_items()
        else:
            self._remove_text_items()

    def _set_loading(self, loading: bool):
        if loading:
            self.scene.clear()
            self._pixmap_item = None
            self._text_items = []
            msg = self.scene.addText(f"正在加载第 {self._current_page + 1} 页…")
            msg.setDefaultTextColor(QColor(DARK_TEXT))

    # ── 构建 UI ──────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setAlignment(Qt.AlignCenter)
        self.view.setStyleSheet(
            f"QGraphicsView {{ background:{DARK_SURFACE}; border:none; }}"
        )
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setRenderHint(QPainter.SmoothPixmapTransform)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.view.viewport().installEventFilter(self)
        layout.addWidget(self.view, 1)

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

        self.btn_text_mode = QPushButton()
        self.btn_text_mode.setFixedSize(36, 32)
        self.btn_text_mode.setIcon(_get_text_icon())
        self.btn_text_mode.setIconSize(QSize(20, 20))
        self.btn_text_mode.setCheckable(True)
        self.btn_text_mode.setChecked(False)
        self.btn_text_mode.setToolTip("文字识别：选中后可框选复制")
        self.btn_text_mode.clicked.connect(self._toggle_text_mode)

        self.btn_copy = QPushButton("复制全部")
        self.btn_copy.setFixedHeight(32)
        self.btn_copy.setToolTip("复制当前页全部文字到剪贴板")
        self.btn_copy.clicked.connect(self._copy_all_text)

        self.btn_download = QPushButton("下载另存")
        self.btn_download.setFixedHeight(32)
        self.btn_download.clicked.connect(self._download_pdf)

        self.btn_sys = QPushButton("系统打开")
        self.btn_sys.setFixedHeight(32)
        self.btn_sys.clicked.connect(self._open_system)

        self.btn_close = QPushButton("关闭")
        self.btn_close.setFixedHeight(32)
        self.btn_close.clicked.connect(self.accept)

        action_row.addStretch()
        action_row.addWidget(self.btn_text_mode)
        action_row.addWidget(self.btn_copy)
        action_row.addWidget(self.btn_download)
        action_row.addWidget(self.btn_sys)
        action_row.addWidget(self.btn_close)
        layout.addLayout(action_row)

        self.setStyleSheet(DIALOG_QSS_DARK)
        for btn in self.findChildren(QPushButton):
            btn.setCursor(Qt.PointingHandCursor)

    # ── 事件过滤 ─────────────────────────────────

    def eventFilter(self, obj, event):
        if obj is self.view.viewport():
            if event.type() == QEvent.Wheel:
                if event.modifiers() == Qt.ControlModifier:
                    factor = 1.12 if event.angleDelta().y() > 0 else 0.89
                    self.view.scale(factor, factor)
                    self._zoom_mode = ""  # 自定义缩放
                    return True
            elif event.type() == QEvent.KeyPress:
                key = event.key()
                if key == Qt.Key_Left:
                    self._prev_page()
                    return True
                elif key == Qt.Key_Right:
                    self._next_page()
                    return True
                elif key == Qt.Key_Home:
                    self._go_to_page(0)
                    return True
                elif key == Qt.Key_End:
                    self._go_to_page(self._page_count - 1)
                    return True
                elif key == Qt.Key_Escape:
                    self.accept()
                    return True
        return super().eventFilter(obj, event)

    # ── 渲染 ─────────────────────────────────────

    def _apply_zoom(self):
        if self._pixmap_item is None:
            return
        vp = self.view.viewport()
        if vp is None:
            return
        vw, vh = vp.width(), vp.height()
        sr = self.scene.sceneRect()
        sw, sh = sr.width(), sr.height()

        self.view.resetTransform()
        if self._zoom_mode == "1:1":
            return
        elif self._zoom_mode == "fit_width":
            s = (vw - 20) / sw if sw > 0 else 1.0
            self.view.scale(s, s)
        elif self._zoom_mode == "fit_page":
            sx = (vw - 20) / sw if sw > 0 else 1.0
            sy = (vh - 20) / sh if sh > 0 else 1.0
            s = min(sx, sy)
            self.view.scale(s, s)

    def _update_ui_state(self):
        n = self._page_count
        is_single = n <= 1

        self.btn_prev.setVisible(not is_single)
        self.btn_next.setVisible(not is_single)
        self.lbl_page.setVisible(not is_single)

        if n > 1:
            self.lbl_page.setText(f"{self._current_page + 1} / {n}")

        self.btn_prev.setEnabled(self._current_page > 0 and not self._rendering)
        self.btn_next.setEnabled(self._current_page < n - 1 and not self._rendering)

        has_pages = self._page_count > 0 and not self._load_error
        for btn in (self.btn_fit_w, self.btn_fit_p, self.btn_1to1):
            btn.setEnabled(has_pages)
        self.btn_prev.setEnabled(self.btn_prev.isEnabled() and has_pages)
        self.btn_next.setEnabled(self.btn_next.isEnabled() and has_pages)

    # ── 翻页 ─────────────────────────────────────

    def _go_to_page(self, index):
        if self._page_count == 0 or self._rendering:
            return
        index = max(0, min(index, self._page_count - 1))
        if index != self._current_page:
            self._current_page = index
            self.scene.clear()
            self._pixmap_item = None
            self._text_items = []
            self._text_blocks_data = []
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
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.pdf_path))

    def _copy_all_text(self):
        import fitz
        try:
            doc = fitz.open(self.pdf_path)
            page = doc[self._current_page]
            text = page.get_text()
            doc.close()
            if text.strip():
                QApplication.clipboard().setText(text.strip())
            else:
                QMessageBox.information(self, "提示", "当前页面无可复制的文字内容")
        except Exception as e:
            QMessageBox.warning(self, "复制失败", f"无法提取文字：\n{e}")

    def _download_pdf(self):
        import shutil
        from PyQt5.QtWidgets import QFileDialog
        dst, _ = QFileDialog.getSaveFileName(
            self, "另存发票PDF", os.path.basename(self.pdf_path),
            "PDF 文件 (*.pdf);;所有文件 (*)"
        )
        if dst:
            shutil.copy2(self.pdf_path, dst)

    # ── 事件 ─────────────────────────────────────

    def showEvent(self, e):
        super().showEvent(e)
        if getattr(self, '_first_show', False):
            self._first_show = False
            if self._page_count > 0 and not self._load_error:
                self._set_loading(True)
                from PyQt5.QtCore import QTimer
                QTimer.singleShot(50, self._start_render)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._apply_zoom()

    def closeEvent(self, e):
        if self._worker and self._worker.isRunning():
            self._worker.finished.disconnect()
            self._worker.quit()
            self._worker.wait(1000)
        self.scene.clear()
        super().closeEvent(e)
