# PDF 软件内预览 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 pdfplumber 渲染 PDF 页面为图片，在软件内置多页查看器中预览，保留系统打开回退。

**Architecture:** 新增 `PdfViewerDialog(QDialog)` 复用 ImageViewerDialog 的导航交互模式。pdfplumber `page.to_image()` 渲染页面为 PIL Image → QPixmap，QScrollArea 中 QLabel 显示。修改 `InvoiceManagerDialog` 按钮布局：预览（内置）/系统打开/下载另存/关闭。

**Tech Stack:** PyQt5, pdfplumber (已有), Pillow (已有)

---

## File Structure

```
src/ui/dialogs/pdf_viewer.py    # 新建 — PdfViewerDialog
src/ui/dialogs/invoice_manager.py  # 修改 — 按钮重排，标题增强
tests/test_pdf_viewer.py         # 新建 — 37 条测试用例
tests/test_dialogs_extra.py      # 修改 — InvoiceManagerDialog 集成测试
```

---

### Task 1: 创建 PdfViewerDialog — 基础框架

**Files:**
- Create: `src/ui/dialogs/pdf_viewer.py`
- Test: `tests/test_pdf_viewer.py` (基础测试 1-6)

- [ ] **Step 1: 创建测试文件 + 测试 1（单页 PDF 对话框结构）**

```python
# tests/test_pdf_viewer.py
# -*- coding: utf-8 -*-
"""PdfViewerDialog 单元测试"""

import sys, os, unittest, tempfile, shutil
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import Qt

_app = QApplication.instance()
if _app is None:
    _app = QApplication(sys.argv)


def _patch_qmessagebox():
    patcher = patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes)
    patcher.start()
    patch.object(QMessageBox, 'warning', return_value=None).start()
    patch.object(QMessageBox, 'information', return_value=None).start()
    patch.object(QMessageBox, 'critical', return_value=None).start()
    return patcher


def _make_test_pdf(path, pages=1):
    """用 pypdf 生成测试用 PDF，返回路径"""
    from pypdf import PdfWriter
    writer = PdfWriter()
    for i in range(pages):
        writer.add_blank_page(width=595, height=842)  # A4
    with open(path, "wb") as f:
        writer.write(f)
    return path


class TestPdfViewerBasic(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._msg_patcher = _patch_qmessagebox()

    @classmethod
    def tearDownClass(cls):
        cls._msg_patcher.stop()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_single_page_pdf_hides_navigation(self):
        """测试 1: 单页 PDF — 翻页按钮和页码隐藏"""
        pdf = os.path.join(self.tmp, "single.pdf")
        _make_test_pdf(pdf, pages=1)
        from ui.dialogs.pdf_viewer import PdfViewerDialog
        dlg = PdfViewerDialog(pdf)
        self.assertFalse(dlg.btn_prev.isVisible())
        self.assertFalse(dlg.btn_next.isVisible())
        self.assertFalse(dlg.lbl_page.isVisible())
        dlg.close()

    def test_multi_page_pdf_shows_page_indicator(self):
        """测试 2: 3 页 PDF — 显示 1/3，首页禁用 prev"""
        pdf = os.path.join(self.tmp, "multi.pdf")
        _make_test_pdf(pdf, pages=3)
        from ui.dialogs.pdf_viewer import PdfViewerDialog
        dlg = PdfViewerDialog(pdf)
        self.assertIn("1 / 3", dlg.lbl_page.text())
        self.assertFalse(dlg.btn_prev.isEnabled())
        self.assertTrue(dlg.btn_next.isEnabled())
        dlg.close()

    def test_navigate_to_middle_page(self):
        """测试 3: 翻到第 2 页 — 双侧按钮可用"""
        pdf = os.path.join(self.tmp, "multi.pdf")
        _make_test_pdf(pdf, pages=3)
        from ui.dialogs.pdf_viewer import PdfViewerDialog
        dlg = PdfViewerDialog(pdf)
        dlg._go_to_page(1)  # 0-indexed page 2
        self.assertIn("2 / 3", dlg.lbl_page.text())
        self.assertTrue(dlg.btn_prev.isEnabled())
        self.assertTrue(dlg.btn_next.isEnabled())
        dlg.close()

    def test_navigate_to_last_page(self):
        """测试 4: 翻到末页 — next 禁用"""
        pdf = os.path.join(self.tmp, "multi.pdf")
        _make_test_pdf(pdf, pages=3)
        from ui.dialogs.pdf_viewer import PdfViewerDialog
        dlg = PdfViewerDialog(pdf)
        dlg._go_to_page(2)
        self.assertIn("3 / 3", dlg.lbl_page.text())
        self.assertFalse(dlg.btn_next.isEnabled())
        self.assertTrue(dlg.btn_prev.isEnabled())
        dlg.close()

    def test_nonexistent_file_shows_warning(self):
        """测试 5: 文件不存在 — 弹出警告"""
        from ui.dialogs.pdf_viewer import PdfViewerDialog
        dlg = PdfViewerDialog("/nonexistent/test.pdf")
        QMessageBox.warning.assert_called()
        dlg.close()

    def test_corrupt_pdf_shows_error(self):
        """测试 6: 非 PDF 文件 — 不崩溃"""
        f = os.path.join(self.tmp, "bad.pdf")
        with open(f, "w") as fh:
            fh.write("not a pdf")
        from ui.dialogs.pdf_viewer import PdfViewerDialog
        dlg = PdfViewerDialog(f)
        QMessageBox.warning.assert_called()
        dlg.close()
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run python -m pytest tests/test_pdf_viewer.py -v
# Expected: ImportError / ModuleNotFoundError for ui.dialogs.pdf_viewer
```

- [ ] **Step 3: 创建 pdf_viewer.py 最小实现**

```python
# src/ui/dialogs/pdf_viewer.py
# -*- coding: utf-8 -*-
"""PDF 内置预览对话框 — 用 pdfplumber 渲染页面为图片"""

import os
import pdfplumber
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QMessageBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QImage

from ui.theme import (ACCENT, DARK_SURFACE, DARK_TEXT, DARK_BG,
                       DIALOG_QSS_DARK, RED)


class PdfViewerDialog(QDialog):
    """PDF 页面图片预览，支持翻页/缩放/系统打开"""

    def __init__(self, pdf_path: str, parent=None):
        super().__init__(parent)
        self.pdf_path = pdf_path
        self._pages = []
        self._current_index = 0
        self._zoom_mode = "fit_width"  # fit_width | fit_page | 1:1
        self._render_dpi = 150

        self.setWindowTitle(f"PDF 预览 — {os.path.basename(pdf_path)}")
        self.resize(900, 700)
        self.setMinimumSize(400, 300)

        try:
            if not os.path.exists(pdf_path):
                raise FileNotFoundError("文件不存在")
            self._pdf = pdfplumber.open(pdf_path)
            self._pages = self._pdf.pages
        except FileNotFoundError:
            QMessageBox.warning(self, "文件不存在", f"找不到文件：\n{pdf_path}")
            self._pages = []
        except Exception:
            QMessageBox.warning(self, "无法打开", "文件可能已损坏或加密，请用「系统打开」查看。")
            self._pages = []

        self._is_single = len(self._pages) <= 1
        self._build_ui()

        if self._pages:
            self._render_current()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 滚动区域 — PDF 页面显示
        self.scroll = QScrollArea()
        self.scroll.setAlignment(Qt.AlignCenter)
        self.scroll.setStyleSheet(f"QScrollArea {{ background:{DARK_SURFACE}; border:none; }}")
        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignCenter)
        self.img_label.setStyleSheet(f"background:{DARK_SURFACE};")
        self.scroll.setWidget(self.img_label)
        self.scroll.setWidgetResizable(False)
        layout.addWidget(self.scroll)

        # 导航栏
        nav = QHBoxLayout()
        nav.setSpacing(8)

        self.btn_prev = QPushButton("◀ 上一页")
        self.btn_prev.setFixedHeight(32)
        self.btn_prev.clicked.connect(self._prev_page)

        self.lbl_page = QLabel()
        self.lbl_page.setAlignment(Qt.AlignCenter)
        self.lbl_page.setStyleSheet(f"color:{DARK_TEXT}; font-size:13px; background:transparent;")

        self.btn_next = QPushButton("下一页 ▶")
        self.btn_next.setFixedHeight(32)
        self.btn_next.clicked.connect(self._next_page)

        nav.addWidget(self.btn_prev)
        nav.addStretch()
        nav.addWidget(self.lbl_page)
        nav.addStretch()
        nav.addWidget(self.btn_next)
        layout.addLayout(nav)

        # 缩放模式 + 操作按钮
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(6)

        self.btn_fit_w = QPushButton("适应宽度")
        self.btn_fit_w.setFixedHeight(28)
        self.btn_fit_w.clicked.connect(lambda: self._set_zoom("fit_width"))

        self.btn_fit_p = QPushButton("适应页面")
        self.btn_fit_p.setFixedHeight(28)
        self.btn_fit_p.clicked.connect(lambda: self._set_zoom("fit_page"))

        self.btn_1to1 = QPushButton("100%")
        self.btn_1to1.setFixedHeight(28)
        self.btn_1to1.clicked.connect(lambda: self._set_zoom("1:1"))

        self.btn_sys = QPushButton("系统打开")
        self.btn_sys.setFixedHeight(28)
        self.btn_sys.clicked.connect(self._open_system)

        self.btn_close = QPushButton("关闭")
        self.btn_close.setFixedHeight(28)
        self.btn_close.clicked.connect(self.accept)

        btn_bar.addWidget(self.btn_fit_w)
        btn_bar.addWidget(self.btn_fit_p)
        btn_bar.addWidget(self.btn_1to1)
        btn_bar.addStretch()
        btn_bar.addWidget(self.btn_sys)
        btn_bar.addWidget(self.btn_close)
        layout.addLayout(btn_bar)

        # 单页时隐藏导航
        if self._is_single:
            self.btn_prev.setVisible(False)
            self.btn_next.setVisible(False)
            self.lbl_page.setVisible(False)

        # 暗色主题
        self.setStyleSheet(DIALOG_QSS_DARK)
        for btn in self.findChildren(QPushButton):
            btn.setCursor(Qt.PointingHandCursor)

    # ── 页面渲染 ────────────────────────────

    def _render_current(self):
        if not self._pages:
            return
        page = self._pages[self._current_index]
        img = page.to_image(resolution=self._render_dpi, antialias=True)
        pil_img = img.original

        # PIL → QPixmap
        data = pil_img.convert("RGBA").tobytes("raw", "RGBA")
        qimg = QImage(data, pil_img.width, pil_img.height, QImage.Format_RGBA8888)
        pix = QPixmap.fromImage(qimg)

        self._current_pixmap = pix
        self._apply_zoom()
        self._update_page_label()

    def _apply_zoom(self):
        if not hasattr(self, '_current_pixmap') or self._current_pixmap is None:
            return
        pix = self._current_pixmap
        vp_w = self.scroll.viewport().width()
        vp_h = self.scroll.viewport().height()

        if self._zoom_mode == "fit_width":
            if pix.width() > vp_w:
                pix = pix.scaledToWidth(vp_w, Qt.SmoothTransformation)
        elif self._zoom_mode == "fit_page":
            pix = pix.scaled(vp_w, vp_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        # "1:1" — 不缩放

        self.img_label.setPixmap(pix)
        self.img_label.resize(pix.size())

    def _update_page_label(self):
        n = len(self._pages)
        if n > 1:
            self.lbl_page.setText(f"{self._current_index + 1} / {n}")
            self.btn_prev.setEnabled(self._current_index > 0)
            self.btn_next.setEnabled(self._current_index < n - 1)

    # ── 导航 ────────────────────────────────

    def _go_to_page(self, index):
        if 0 <= index < len(self._pages):
            self._current_index = index
            self._render_current()

    def _prev_page(self):
        self._go_to_page(self._current_index - 1)

    def _next_page(self):
        self._go_to_page(self._current_index + 1)

    def _set_zoom(self, mode):
        self._zoom_mode = mode
        self._apply_zoom()

    def _open_system(self):
        if os.path.exists(self.pdf_path):
            os.startfile(self.pdf_path)
        else:
            QMessageBox.warning(self, "文件不存在", "PDF 文件已被移动或删除。")

    # ── 键盘快捷键 ──────────────────────────

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_Right:
            self._next_page()
        elif key == Qt.Key_Left:
            self._prev_page()
        elif key == Qt.Key_Home:
            self._go_to_page(0)
        elif key == Qt.Key_End:
            self._go_to_page(len(self._pages) - 1)
        elif key == Qt.Key_Escape:
            self.accept()
        else:
            super().keyPressEvent(event)

    # ── 资源释放 ────────────────────────────

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_current_pixmap') and self._current_pixmap:
            self._apply_zoom()

    def closeEvent(self, event):
        if hasattr(self, '_current_pixmap') and self._current_pixmap:
            self.img_label.setPixmap(QPixmap())
            self._current_pixmap = None
        if hasattr(self, '_pdf'):
            self._pdf.close()
        super().closeEvent(event)
```

- [ ] **Step 4: 运行测试验证通过**

```bash
uv run python -m pytest tests/test_pdf_viewer.py -v
# Expected: 6 tests PASS
```

- [ ] **Step 5: 提交**

```bash
git add src/ui/dialogs/pdf_viewer.py tests/test_pdf_viewer.py
git commit -m "feat: add PdfViewerDialog — in-app PDF preview via pdfplumber"
```

---

### Task 2: PdfViewerDialog — 键盘导航 + 缩放

**Files:**
- Modify: `src/ui/dialogs/pdf_viewer.py` (已创建)
- Modify: `tests/test_pdf_viewer.py` (追加测试 7-17)

- [ ] **Step 1: 追加键盘导航测试（7-10）**

在 `tests/test_pdf_viewer.py` 中追加：

```python
class TestPdfViewerKeyboard(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._msg_patcher = _patch_qmessagebox()

    @classmethod
    def tearDownClass(cls):
        cls._msg_patcher.stop()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.pdf = os.path.join(self.tmp, "multi.pdf")
        _make_test_pdf(self.pdf, pages=3)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_arrow_right_next_page(self):
        """测试 7: → 键翻到下一页"""
        from ui.dialogs.pdf_viewer import PdfViewerDialog
        dlg = PdfViewerDialog(self.pdf)
        old = dlg._current_index
        dlg.keyPressEvent(MockKeyEvent(Qt.Key_Right))
        self.assertEqual(dlg._current_index, old + 1)
        dlg.close()

    def test_arrow_left_prev_page(self):
        """测试 8: ← 键翻到上一页"""
        from ui.dialogs.pdf_viewer import PdfViewerDialog
        dlg = PdfViewerDialog(self.pdf)
        dlg._go_to_page(1)
        dlg.keyPressEvent(MockKeyEvent(Qt.Key_Left))
        self.assertEqual(dlg._current_index, 0)
        dlg.close()

    def test_arrow_left_at_boundary_noop(self):
        """测试 9: 首页按 ← 不变"""
        from ui.dialogs.pdf_viewer import PdfViewerDialog
        dlg = PdfViewerDialog(self.pdf)
        dlg.keyPressEvent(MockKeyEvent(Qt.Key_Left))
        self.assertEqual(dlg._current_index, 0)
        dlg.close()

    def test_arrow_right_at_boundary_noop(self):
        """测试 10: 末页按 → 不变"""
        from ui.dialogs.pdf_viewer import PdfViewerDialog
        dlg = PdfViewerDialog(self.pdf)
        dlg._go_to_page(2)
        dlg.keyPressEvent(MockKeyEvent(Qt.Key_Right))
        self.assertEqual(dlg._current_index, 2)
        dlg.close()


class MockKeyEvent:
    """模拟 QKeyEvent 供 keyPressEvent 测试"""
    def __init__(self, key):
        self._key = key

    def key(self):
        return self._key

    def modifiers(self):
        return Qt.NoModifier

    def isAccepted(self):
        return False

    def accept(self):
        pass

    def ignore(self):
        pass
```

- [ ] **Step 2: 运行测试 — 键盘导航应全部通过（7-10，代码已在 Task 1 实现）**

```bash
uv run python -m pytest tests/test_pdf_viewer.py -v -k "Keyboard"
# Expected: 4 tests PASS
```

- [ ] **Step 3: 追加键盘按钮测试（11-13）**

```python
class TestPdfViewerKeyButtons(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._msg_patcher = _patch_qmessagebox()

    @classmethod
    def tearDownClass(cls):
        cls._msg_patcher.stop()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.pdf = os.path.join(self.tmp, "multi.pdf")
        _make_test_pdf(self.pdf, pages=3)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_escape_closes_dialog(self):
        """测试 11: Esc 关闭对话框"""
        from ui.dialogs.pdf_viewer import PdfViewerDialog
        dlg = PdfViewerDialog(self.pdf)
        dlg.keyPressEvent(MockKeyEvent(Qt.Key_Escape))
        # accept() 被调用后 dialog 不可见或已关闭
        self.assertFalse(dlg.isVisible())
        dlg.close()

    def test_home_jumps_to_first_page(self):
        """测试 12: Home 跳首页"""
        from ui.dialogs.pdf_viewer import PdfViewerDialog
        dlg = PdfViewerDialog(self.pdf)
        dlg._go_to_page(2)
        dlg.keyPressEvent(MockKeyEvent(Qt.Key_Home))
        self.assertEqual(dlg._current_index, 0)
        dlg.close()

    def test_end_jumps_to_last_page(self):
        """测试 13: End 跳末页"""
        from ui.dialogs.pdf_viewer import PdfViewerDialog
        dlg = PdfViewerDialog(self.pdf)
        dlg.keyPressEvent(MockKeyEvent(Qt.Key_End))
        self.assertEqual(dlg._current_index, 2)
        dlg.close()
```

- [ ] **Step 4: 运行测试确认 Key 按钮通过**

```bash
uv run python -m pytest tests/test_pdf_viewer.py -v -k "KeyButtons"
```

- [ ] **Step 5: 追加缩放测试（14-17）**

```python
class TestPdfViewerZoom(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._msg_patcher = _patch_qmessagebox()

    @classmethod
    def tearDownClass(cls):
        cls._msg_patcher.stop()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.pdf = os.path.join(self.tmp, "single.pdf")
        _make_test_pdf(self.pdf, pages=1)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_default_zoom_is_fit_width(self):
        """测试 14: 默认缩放模式 = fit_width"""
        from ui.dialogs.pdf_viewer import PdfViewerDialog
        dlg = PdfViewerDialog(self.pdf)
        self.assertEqual(dlg._zoom_mode, "fit_width")
        dlg.close()

    def test_btn_fit_page_switches_mode(self):
        """测试 15: 点击适应页面"""
        from ui.dialogs.pdf_viewer import PdfViewerDialog
        dlg = PdfViewerDialog(self.pdf)
        dlg.btn_fit_p.click()
        self.assertEqual(dlg._zoom_mode, "fit_page")
        dlg.close()

    def test_btn_1to1_switches_mode(self):
        """测试 16: 点击 100%"""
        from ui.dialogs.pdf_viewer import PdfViewerDialog
        dlg = PdfViewerDialog(self.pdf)
        dlg.btn_1to1.click()
        self.assertEqual(dlg._zoom_mode, "1:1")
        dlg.close()

    def test_zoom_mode_cycle(self):
        """测试 17: 三种模式循环切换"""
        from ui.dialogs.pdf_viewer import PdfViewerDialog
        dlg = PdfViewerDialog(self.pdf)
        dlg._set_zoom("fit_page")
        self.assertEqual(dlg._zoom_mode, "fit_page")
        dlg._set_zoom("1:1")
        self.assertEqual(dlg._zoom_mode, "1:1")
        dlg._set_zoom("fit_width")
        self.assertEqual(dlg._zoom_mode, "fit_width")
        dlg.close()
```

- [ ] **Step 6: 运行缩放测试**

```bash
uv run python -m pytest tests/test_pdf_viewer.py -v -k "Zoom"
# Expected: 4 tests PASS
```

- [ ] **Step 7: 提交**

```bash
git add tests/test_pdf_viewer.py
git commit -m "test: add keyboard nav + zoom tests for PdfViewerDialog"
```

---

### Task 3: PdfViewerDialog — 边界情况 + 异常恢复

**Files:**
- Modify: `src/ui/dialogs/pdf_viewer.py` (增加密码/DPI/渲染超时处理)
- Modify: `tests/test_pdf_viewer.py` (测试 20-29)

- [ ] **Step 1: 在 pdf_viewer.py 的 __init__ 中增加密码检测**

修改 `PdfViewerDialog.__init__` 中 pdfplumber.open 的异常处理：

```python
# 替换 __init__ 中的 try/except 块：
try:
    if not os.path.exists(pdf_path):
        raise FileNotFoundError("文件不存在")
    self._pdf = pdfplumber.open(pdf_path)
    self._pages = self._pdf.pages
except FileNotFoundError:
    QMessageBox.warning(self, "文件不存在", f"找不到文件：\n{pdf_path}")
    self._pages = []
except pdfplumber.exceptions.PDFSyntaxError:
    QMessageBox.warning(self, "无法打开", "文件可能已损坏，请用「系统打开」查看。")
    self._pages = []
except Exception as e:
    if "password" in str(e).lower():
        # 密码保护 — 尝试弹框
        from PyQt5.QtWidgets import QInputDialog
        pw, ok = QInputDialog.getText(
            self, "密码保护", "此 PDF 需要密码才能打开：",
            text="", echo=QInputDialog.Password)
        if ok and pw:
            try:
                self._pdf = pdfplumber.open(pdf_path, password=pw)
                self._pages = self._pdf.pages
            except Exception:
                QMessageBox.warning(self, "密码错误", "密码不正确，请用「系统打开」查看。")
                self._pages = []
        else:
            QMessageBox.information(self, "需要密码", "请用「系统打开」按钮在外部程序中查看。")
            self._pages = []
    else:
        QMessageBox.warning(self, "无法打开", "文件可能已损坏或加密，请用「系统打开」查看。")
        self._pages = []
```

同时增加 DPI 自动检测：

```python
# 在 __init__ 中 _render_dpi 初始化后添加：
# 检测系统 DPI 缩放
try:
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance()
    if app:
        screen = app.primaryScreen()
        if screen:
            ratio = screen.devicePixelRatio()
            if ratio >= 2.0:
                self._render_dpi = 300
except Exception:
    pass
```

在 `_render_current` 中增加超时保护：

```python
def _render_current(self):
    if not self._pages:
        return
    try:
        page = self._pages[self._current_index]
        # 检测页面旋转
        rotation = getattr(page, 'rotation', 0)
        img = page.to_image(resolution=self._render_dpi, antialias=True)

        if rotation:
            pil_img = img.original.rotate(-rotation, expand=True)
        else:
            pil_img = img.original

        data = pil_img.convert("RGBA").tobytes("raw", "RGBA")
        qimg = QImage(data, pil_img.width, pil_img.height, QImage.Format_RGBA8888)
        pix = QPixmap.fromImage(qimg)

        self._current_pixmap = pix
        self._apply_zoom()
        self._update_page_label()
    except Exception:
        QMessageBox.warning(self, "渲染失败",
            f"第 {self._current_index + 1} 页渲染失败，\n请用「系统打开」查看完整内容。")
```

- [ ] **Step 2: 追加边界情况测试（20-26）**

```python
class TestPdfViewerEdgeCases(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._msg_patcher = _patch_qmessagebox()

    @classmethod
    def tearDownClass(cls):
        cls._msg_patcher.stop()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_single_page_hides_page_label(self):
        """测试 22: 单页 PDF 不显示页码"""
        pdf = os.path.join(self.tmp, "single.pdf")
        _make_test_pdf(pdf, pages=1)
        from ui.dialogs.pdf_viewer import PdfViewerDialog
        dlg = PdfViewerDialog(pdf)
        self.assertFalse(dlg.lbl_page.isVisible())
        dlg.close()

    def test_password_pdf_prompts_input(self):
        """测试 23: 加密 PDF 弹出密码框"""
        with patch("pdfplumber.open") as mock_open:
            mock_open.side_effect = Exception("password required")
            from ui.dialogs.pdf_viewer import PdfViewerDialog
            with patch("PyQt5.QtWidgets.QInputDialog.getText",
                       return_value=("123456", True)):
                dlg = PdfViewerDialog("/fake/encrypted.pdf")
                # 不崩溃即通过
                dlg.close()

    def test_wrong_password_shows_error(self):
        """测试 24: 密码错误提示"""
        with patch("pdfplumber.open") as mock_open:
            mock_open.side_effect = Exception("password required")
            from ui.dialogs.pdf_viewer import PdfViewerDialog
            with patch("PyQt5.QtWidgets.QInputDialog.getText",
                       return_value=("wrong", True)):
                with patch("pdfplumber.open", side_effect=Exception("bad pw")):
                    dlg = PdfViewerDialog("/fake/encrypted.pdf")
                    QMessageBox.warning.assert_called()
                    dlg.close()

    def test_password_cancel_shows_hint(self):
        """测试 25: 密码取消提示"""
        with patch("pdfplumber.open") as mock_open:
            mock_open.side_effect = Exception("password required")
            from ui.dialogs.pdf_viewer import PdfViewerDialog
            with patch("PyQt5.QtWidgets.QInputDialog.getText",
                       return_value=("", False)):
                dlg = PdfViewerDialog("/fake/encrypted.pdf")
                QMessageBox.information.assert_called()
                dlg.close()

    def test_file_deleted_while_viewing(self):
        """测试 28: 打开后文件被删除"""
        pdf = os.path.join(self.tmp, "temp.pdf")
        _make_test_pdf(pdf, pages=1)
        from ui.dialogs.pdf_viewer import PdfViewerDialog
        dlg = PdfViewerDialog(pdf)
        os.remove(pdf)
        dlg._open_system()
        QMessageBox.warning.assert_called()
        dlg.close()
```

- [ ] **Step 3: 运行边界测试**

```bash
uv run python -m pytest tests/test_pdf_viewer.py -v -k "EdgeCases"
# Expected: all PASS
```

- [ ] **Step 4: 提交**

```bash
git add src/ui/dialogs/pdf_viewer.py tests/test_pdf_viewer.py
git commit -m "feat: add password-protected PDF handling + edge case tests"
```

---

### Task 4: 修改 InvoiceManagerDialog

**Files:**
- Modify: `src/ui/dialogs/invoice_manager.py`
- Modify: `tests/test_dialogs_extra.py` (集成测试 32-35)

- [ ] **Step 1: 修改 invoice_manager.py**

将「打开」按钮改为「预览」（调用 PdfViewerDialog），新增「系统打开」按钮：

```python
# 修改 _build_ui 中的按钮栏部分：
btn_bar = QHBoxLayout()
btn_bar.setSpacing(8)

self.btn_preview = QPushButton("预览")
self.btn_preview.setFixedHeight(32)
self.btn_preview.clicked.connect(self._open_pdf)  # 改为打开 PdfViewerDialog

self.btn_sys_open = QPushButton("系统打开")
self.btn_sys_open.setFixedHeight(32)
self.btn_sys_open.setToolTip("在系统默认程序中打开")
self.btn_sys_open.clicked.connect(self._open_system)

self.btn_download = QPushButton("下载另存")
self.btn_download.setFixedHeight(32)
self.btn_download.clicked.connect(self._download_pdf)

self.btn_close = QPushButton("关闭")
self.btn_close.setFixedHeight(32)
self.btn_close.clicked.connect(self.accept)

btn_bar.addWidget(self.btn_preview)
btn_bar.addWidget(self.btn_sys_open)
btn_bar.addWidget(self.btn_download)
btn_bar.addStretch()
btn_bar.addWidget(self.btn_close)
layout.addLayout(btn_bar)
```

修改 `_open_pdf` 方法：

```python
def _open_pdf(self):
    if not self.pdf_path or not os.path.exists(self.pdf_path):
        QMessageBox.warning(self, "文件不存在", f"找不到文件：\n{self.pdf_path}")
        return
    from ui.dialogs.pdf_viewer import PdfViewerDialog
    dlg = PdfViewerDialog(self.pdf_path, parent=self)
    dlg.exec_()
```

新增 `_open_system` 方法：

```python
def _open_system(self):
    if not self.pdf_path or not os.path.exists(self.pdf_path):
        QMessageBox.warning(self, "文件不存在", f"找不到文件：\n{self.pdf_path}")
        return
    try:
        os.startfile(self.pdf_path)
    except Exception as e:
        QMessageBox.warning(self, "打开失败", f"无法打开文件：\n{e}")
```

修改 `_refresh` 中的标题显示（增加发票号信息 — 从 pdf_path 目录文件名提取，或从调用方传入）：

```python
# __init__ 增加 rec_no 参数
def __init__(self, pdf_path: str, rec_name: str = "", rec_no: str = "", parent=None):
    super().__init__(parent)
    self.pdf_path = pdf_path
    self.rec_name = rec_name
    self.rec_no = rec_no
    # 标题
    parts = ["发票PDF"]
    if rec_name:
        parts.append(rec_name)
    if rec_no:
        parts.append(f"№ {rec_no}")
    self.setWindowTitle(" — ".join(parts))
    self.resize(520, 220)
    ...
```

- [ ] **Step 2: 更新 InvoiceManagerDialog 集成测试（32-35）**

在 `tests/test_dialogs_extra.py` 中追加：

```python
class TestInvoiceManagerIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._msg_patcher = _patch_qmessagebox()

    @classmethod
    def tearDownClass(cls):
        cls._msg_patcher.stop()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_preview_button_opens_pdf_viewer(self):
        """测试 32: 预览按钮打开 PdfViewerDialog"""
        f = os.path.join(self.tmp, "test.pdf")
        from pypdf import PdfWriter
        w = PdfWriter(); w.add_blank_page(595, 842)
        with open(f, "wb") as fh:
            w.write(fh)

        with patch("ui.dialogs.pdf_viewer.PdfViewerDialog.exec_") as mock_exec:
            from ui.dialogs.invoice_manager import InvoiceManagerDialog
            dlg = InvoiceManagerDialog(f)
            dlg._open_pdf()
            mock_exec.assert_called_once()
            dlg.close()

    def test_system_open_calls_startfile(self):
        """测试 33: 系统打开调用 os.startfile"""
        f = os.path.join(self.tmp, "test.pdf")
        with open(f, "w") as fh:
            fh.write("fake pdf")
        from ui.dialogs.invoice_manager import InvoiceManagerDialog
        dlg = InvoiceManagerDialog(f)
        with patch("os.startfile") as mock_start:
            dlg._open_system()
            mock_start.assert_called_once_with(f)
        dlg.close()

    def test_title_contains_invoice_no(self):
        """测试 34: 标题包含发票号码"""
        f = os.path.join(self.tmp, "test.pdf")
        with open(f, "w") as fh:
            fh.write("fake pdf")
        from ui.dialogs.invoice_manager import InvoiceManagerDialog
        dlg = InvoiceManagerDialog(f, rec_name="测试公司", rec_no="12345678")
        title = dlg.windowTitle()
        self.assertIn("测试公司", title)
        self.assertIn("12345678", title)
        dlg.close()

    def test_buttons_disabled_when_file_missing(self):
        """测试 35: 文件不存在时按钮禁用"""
        from ui.dialogs.invoice_manager import InvoiceManagerDialog
        dlg = InvoiceManagerDialog("/nonexistent.pdf")
        self.assertFalse(dlg.btn_preview.isEnabled())
        self.assertFalse(dlg.btn_sys_open.isEnabled())
        self.assertFalse(dlg.btn_download.isEnabled())
        dlg.close()
```

- [ ] **Step 3: 更新 invoice_tool.py 中传给 InvoiceManagerDialog 的参数**

在 `_view_invoice_pdf` 方法中增加发票号传入：

```python
# 修改 _view_invoice_pdf (invoice_tool.py)
def _view_invoice_pdf(self, row):
    rec = self._get_record_by_row(row)
    if rec is None:
        return
    dlg = InvoiceManagerDialog(
        pdf_path=rec.get("pdf_path", ""),
        rec_name=rec.get("buyer_name", "") or rec.get("file", ""),
        rec_no=rec.get("invoice_no", ""),
        parent=self
    )
    dlg.exec_()
```

- [ ] **Step 4: 运行全部测试**

```bash
uv run python -m pytest tests/ -v 2>&1 | tail -5
# Expected: ALL PASS
```

- [ ] **Step 5: 提交**

```bash
git add src/ui/dialogs/invoice_manager.py src/invoice_tool.py tests/test_dialogs_extra.py
git commit -m "feat: PdfViewerDialog integration — preview button replaces open, add system-open fallback"
```

---

### Task 5: 最终验证

- [ ] **Step 1: 运行全部测试套件**

```bash
uv run python -m coverage run --source=src -m pytest tests/ -v
uv run python -m coverage report --show-missing
```

- [ ] **Step 2: 启动应用手动验证**

```bash
uv run python src/invoice_tool.py
```
手动测试：
1. 导入一份 PDF 发票 → 双击行 → 点「预览」
2. 验证翻页、缩放、快捷键
3. 点「系统打开」确认外部程序打开
4. 文件名/发票号/购买方 是否显示在标题栏

- [ ] **Step 3: 提交**

```bash
git add -A
git commit -m "chore: final verification after PdfViewerDialog integration"
```
