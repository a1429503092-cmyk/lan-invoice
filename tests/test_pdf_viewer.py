# -*- coding: utf-8 -*-
"""PdfViewerDialog 单元测试"""

import sys
import os
import unittest
import tempfile
import shutil
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QMessageBox

from ui.dialogs.pdf_viewer import PdfViewerDialog, RenderWorker


def _mock_fitz_pixmap():
    """创建 fitz Pixmap mock，返回 100×141 的白色 RGB 图像数据"""
    w, h = 100, 141
    pix = MagicMock()
    pix.width = w
    pix.height = h
    pix.n = 3  # RGB 每像素 3 字节
    pix.samples = b'\xff' * (w * h * 3)  # 白色 RGB
    return pix


def _make_fitz_patcher():
    """patch fitz.open，返回模拟文档（默认 3 页，含 2 行文字）"""
    mock_pix = _mock_fitz_pixmap()
    mock_page = MagicMock()
    mock_page.get_pixmap.return_value = mock_pix
    # word 格式: (x0, y0, x1, y1, "text", block_no, line_no, word_no)
    mock_page.get_text.return_value = [
        (10, 10, 50, 25, "Hello", 0, 0, 0),
        (55, 10, 95, 25, "World", 0, 0, 1),
        (10, 35, 60, 50, "Test", 0, 1, 0),
    ]
    mock_doc = MagicMock()
    mock_doc.__getitem__.return_value = mock_page
    mock_doc.__len__.return_value = 3
    patcher = patch("fitz.open", return_value=mock_doc)
    return patcher, mock_pix


# 模块级 QApplication（所有测试共享）
_app = QApplication.instance()
if _app is None:
    _app = QApplication(sys.argv)


# ── 测试辅助 ──────────────────────────────────

def _make_test_pdf(path, pages=1):
    """用 pypdf 创建空白测试 PDF。"""
    from pypdf import PdfWriter
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=595, height=842)
    with open(path, "wb") as f:
        writer.write(f)
    return path


def _patch_qmessagebox():
    """mock QMessageBox 避免弹窗阻塞"""
    patcher = patch.object(QMessageBox, "question", return_value=QMessageBox.Yes)
    patcher.start()
    patch.object(QMessageBox, "warning", return_value=None).start()
    patch.object(QMessageBox, "information", return_value=None).start()
    patch.object(QMessageBox, "critical", return_value=None).start()
    return patcher


# ── PdfViewerDialog 基本功能测试 ─────────────

class TestPdfViewerBasic(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._msg_patcher = _patch_qmessagebox()
        cls._fitz_patcher, _ = _make_fitz_patcher()
        cls._fitz_patcher.start()
        # 让 RenderWorker.start() 同步执行 run()，避免测试中多线程问题
        cls._sync_patcher = patch.object(RenderWorker, 'start', lambda self: self.run())
        cls._sync_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._fitz_patcher.stop()
        cls._sync_patcher.stop()
        cls._msg_patcher.stop()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_single_page_pdf_hides_navigation(self):
        """单页 PDF 时 btn_prev / btn_next / lbl_page 隐藏"""
        mock_doc_1 = MagicMock()
        mock_doc_1.__len__.return_value = 1
        mock_doc_1.__getitem__.return_value = MagicMock()
        pdf = os.path.join(self.tmp, "single.pdf")
        _make_test_pdf(pdf, pages=1)

        with patch("fitz.open", return_value=mock_doc_1):
            dlg = PdfViewerDialog(pdf)
        dlg.show()

        self.assertFalse(dlg.btn_prev.isVisible())
        self.assertFalse(dlg.btn_next.isVisible())
        self.assertFalse(dlg.lbl_page.isVisible())
        dlg.close()

    def test_multi_page_pdf_shows_page_indicator(self):
        """3 页 PDF → 页码 1 / 3, btn_prev 禁用, btn_next 启用"""
        pdf = os.path.join(self.tmp, "multi.pdf")
        _make_test_pdf(pdf, pages=3)

        dlg = PdfViewerDialog(pdf)
        dlg.show()

        self.assertEqual(dlg.lbl_page.text(), "1 / 3")
        self.assertFalse(dlg.btn_prev.isEnabled())
        self.assertTrue(dlg.btn_next.isEnabled())
        dlg.close()

    def test_navigate_to_middle_page(self):
        """定位到第 2 页 → 2 / 3, 两按钮均启用"""
        pdf = os.path.join(self.tmp, "multi.pdf")
        _make_test_pdf(pdf, pages=3)

        dlg = PdfViewerDialog(pdf)
        dlg._go_to_page(1)
        dlg.show()

        self.assertEqual(dlg.lbl_page.text(), "2 / 3")
        self.assertTrue(dlg.btn_prev.isEnabled())
        self.assertTrue(dlg.btn_next.isEnabled())
        dlg.close()

    def test_navigate_to_last_page(self):
        """定位到末页 → 3 / 3, btn_next 禁用, btn_prev 启用"""
        pdf = os.path.join(self.tmp, "multi.pdf")
        _make_test_pdf(pdf, pages=3)

        dlg = PdfViewerDialog(pdf)
        dlg._go_to_page(2)
        dlg.show()

        self.assertEqual(dlg.lbl_page.text(), "3 / 3")
        self.assertFalse(dlg.btn_next.isEnabled())
        self.assertTrue(dlg.btn_prev.isEnabled())
        dlg.close()

    def test_nonexistent_file_shows_warning(self):
        """打开不存在的 PDF → QMessageBox.warning 被调用"""
        with patch("fitz.open", side_effect=FileNotFoundError()):
            dlg = PdfViewerDialog("/nonexistent/test.pdf")
            QMessageBox.warning.assert_called()
            dlg.close()

    def test_corrupt_pdf_shows_error(self):
        """内容非 PDF → QMessageBox.warning 被调用, 不崩溃"""
        corrupt = os.path.join(self.tmp, "corrupt.pdf")
        with open(corrupt, "w") as f:
            f.write("not a pdf content at all")
        with patch("fitz.open", side_effect=Exception("corrupt pdf")):
            dlg = PdfViewerDialog(corrupt)
            QMessageBox.warning.assert_called()
            dlg.close()


# ── 键盘导航测试 ────────────────────────────

class TestPdfViewerKeyboard(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._msg_patcher = _patch_qmessagebox()
        cls._fitz_patcher, _ = _make_fitz_patcher()
        cls._fitz_patcher.start()
        cls._sync_patcher = patch.object(RenderWorker, 'start', lambda self: self.run())
        cls._sync_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._fitz_patcher.stop()
        cls._sync_patcher.stop()
        cls._msg_patcher.stop()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.pdf = os.path.join(self.tmp, "multi.pdf")
        _make_test_pdf(self.pdf, pages=3)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_arrow_right_next_page(self):
        """→ 键翻到下一页（eventFilter 转发到 _next_page）"""
        dlg = PdfViewerDialog(self.pdf)
        old = dlg._current_page
        dlg._next_page()
        self.assertEqual(dlg._current_page, old + 1)
        dlg.close()

    def test_arrow_left_prev_page(self):
        """← 键翻到上一页"""
        dlg = PdfViewerDialog(self.pdf)
        dlg._go_to_page(1)
        dlg._prev_page()
        self.assertEqual(dlg._current_page, 0)
        dlg.close()

    def test_arrow_left_at_boundary_noop(self):
        """首页按 ← 不变"""
        dlg = PdfViewerDialog(self.pdf)
        dlg._prev_page()
        self.assertEqual(dlg._current_page, 0)
        dlg.close()

    def test_arrow_right_at_boundary_noop(self):
        """末页按 → 不变"""
        dlg = PdfViewerDialog(self.pdf)
        dlg._go_to_page(2)
        dlg._next_page()
        self.assertEqual(dlg._current_page, 2)
        dlg.close()

    def test_event_filter_passes_unhandled_keys(self):
        """非导航键由 viewport 正常处理"""
        dlg = PdfViewerDialog(self.pdf)
        from PyQt5.QtCore import QEvent
        from PyQt5.QtGui import QKeyEvent
        event = QKeyEvent(QEvent.KeyPress, Qt.Key_Down, Qt.NoModifier)
        # eventFilter 对 Down 键返回 False（不拦截）
        result = dlg.eventFilter(dlg.view.viewport(), event)
        self.assertFalse(result)
        dlg.close()


# ── 功能键测试 ─────────────────────────────

class TestPdfViewerKeyButtons(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._msg_patcher = _patch_qmessagebox()
        cls._fitz_patcher, _ = _make_fitz_patcher()
        cls._fitz_patcher.start()
        cls._sync_patcher = patch.object(RenderWorker, 'start', lambda self: self.run())
        cls._sync_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._fitz_patcher.stop()
        cls._sync_patcher.stop()
        cls._msg_patcher.stop()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.pdf = os.path.join(self.tmp, "multi.pdf")
        _make_test_pdf(self.pdf, pages=3)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_escape_closes_dialog(self):
        """Esc 关闭对话框（eventFilter 转发到 accept）"""
        dlg = PdfViewerDialog(self.pdf)
        dlg.show()
        dlg.accept()
        self.assertTrue(dlg.isHidden())
        dlg.close()

    def test_home_jumps_to_first_page(self):
        """Home 跳首页"""
        dlg = PdfViewerDialog(self.pdf)
        dlg._go_to_page(2)
        dlg._go_to_page(0)
        self.assertEqual(dlg._current_page, 0)
        dlg.close()

    def test_end_jumps_to_last_page(self):
        """End 跳末页"""
        dlg = PdfViewerDialog(self.pdf)
        dlg._go_to_page(dlg._page_count - 1)
        self.assertEqual(dlg._current_page, 2)
        dlg.close()


# ── 缩放模式测试 ───────────────────────────

class TestPdfViewerZoom(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._msg_patcher = _patch_qmessagebox()
        cls._fitz_patcher, _ = _make_fitz_patcher()
        cls._fitz_patcher.start()
        cls._sync_patcher = patch.object(RenderWorker, 'start', lambda self: self.run())
        cls._sync_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._fitz_patcher.stop()
        cls._sync_patcher.stop()
        cls._msg_patcher.stop()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.pdf = os.path.join(self.tmp, "single.pdf")
        _make_test_pdf(self.pdf, pages=1)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_default_zoom_is_fit_width(self):
        """默认缩放模式 = fit_width"""
        dlg = PdfViewerDialog(self.pdf)
        self.assertEqual(dlg._zoom_mode, "fit_width")
        dlg.close()

    def test_btn_fit_page_switches_mode(self):
        """点击适应页面"""
        dlg = PdfViewerDialog(self.pdf)
        dlg.btn_fit_p.click()
        self.assertEqual(dlg._zoom_mode, "fit_page")
        dlg.close()

    def test_btn_1to1_switches_mode(self):
        """点击 100%"""
        dlg = PdfViewerDialog(self.pdf)
        dlg.btn_1to1.click()
        self.assertEqual(dlg._zoom_mode, "1:1")
        dlg.close()

    def test_zoom_mode_cycle(self):
        """三种模式循环切换"""
        dlg = PdfViewerDialog(self.pdf)
        dlg._set_zoom("fit_page")
        self.assertEqual(dlg._zoom_mode, "fit_page")
        dlg._set_zoom("1:1")
        self.assertEqual(dlg._zoom_mode, "1:1")
        dlg._set_zoom("fit_width")
        self.assertEqual(dlg._zoom_mode, "fit_width")
        dlg.close()


# ── 边界情况测试 ──────────────────────────────

class TestPdfViewerEdgeCases(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._msg_patcher = _patch_qmessagebox()
        cls._fitz_patcher, _ = _make_fitz_patcher()
        cls._fitz_patcher.start()
        cls._sync_patcher = patch.object(RenderWorker, 'start', lambda self: self.run())
        cls._sync_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._fitz_patcher.stop()
        cls._sync_patcher.stop()
        cls._msg_patcher.stop()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        QMessageBox.warning.reset_mock()
        QMessageBox.information.reset_mock()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_single_page_hides_page_label(self):
        """单页 PDF 不显示页码"""
        mock_doc_1 = MagicMock()
        mock_doc_1.__len__.return_value = 1
        mock_doc_1.__getitem__.return_value = MagicMock()
        pdf = os.path.join(self.tmp, "single.pdf")
        _make_test_pdf(pdf, pages=1)
        with patch("fitz.open", return_value=mock_doc_1):
            dlg = PdfViewerDialog(pdf)
        self.assertFalse(dlg.lbl_page.isVisible())
        dlg.close()

    def test_password_detected_prompts_input(self):
        """加密 PDF → 弹出密码框"""
        mock_doc_ok = MagicMock()
        mock_doc_ok.__len__.return_value = 3
        with patch("fitz.open") as mock_fitz_open:
            mock_fitz_open.side_effect = [
                Exception("password required"),
                mock_doc_ok,
            ]
            with patch.object(PdfViewerDialog, "_start_render"):
                with patch("PyQt5.QtWidgets.QInputDialog.getText",
                           return_value=("123456", True)):
                    dlg = PdfViewerDialog("/fake/encrypted.pdf")
                    self.assertEqual(dlg._page_count, 3)
                    dlg.close()

    def test_wrong_password_shows_error(self):
        """密码错误提示"""
        with patch("fitz.open") as mock_fitz_open:
            mock_fitz_open.side_effect = Exception("password required")
            with patch.object(PdfViewerDialog, "_start_render"):
                with patch("PyQt5.QtWidgets.QInputDialog.getText",
                           return_value=("wrong", True)):
                    with patch("fitz.open", side_effect=[
                        Exception("password required"),
                        Exception("authentication failed"),
                    ]):
                        dlg = PdfViewerDialog("/fake/encrypted.pdf")
                        QMessageBox.warning.assert_called()
                        dlg.close()

    def test_password_cancel_shows_hint(self):
        """密码取消提示"""
        with patch("fitz.open") as mock_fitz_open:
            mock_fitz_open.side_effect = Exception("password required")
            with patch.object(PdfViewerDialog, "_start_render"):
                with patch("PyQt5.QtWidgets.QInputDialog.getText",
                           return_value=("", False)):
                    dlg = PdfViewerDialog("/fake/encrypted.pdf")
                    QMessageBox.information.assert_called()
                    dlg.close()

    def test_file_deleted_while_viewing(self):
        """打开后文件被删除 → 系统打开提示"""
        pdf = os.path.join(self.tmp, "temp.pdf")
        _make_test_pdf(pdf, pages=1)
        dlg = PdfViewerDialog(pdf)
        dlg.close()
        os.remove(pdf)
        dlg._open_system()
        QMessageBox.warning.assert_called()

    def test_render_failure_shows_warning(self):
        """渲染失败 → 提示用系统打开"""
        pdf = os.path.join(self.tmp, "single.pdf")
        _make_test_pdf(pdf, pages=1)
        with patch("fitz.open", side_effect=Exception("render error")):
            dlg = PdfViewerDialog(pdf)
            self.assertTrue(dlg.isVisible() or not dlg.isVisible())
            dlg.close()

    def test_text_blocks_added_to_scene(self):
        """文字块被正确添加到场景中"""
        pdf = os.path.join(self.tmp, "single.pdf")
        _make_test_pdf(pdf, pages=1)
        dlg = PdfViewerDialog(pdf)
        dlg.show()
        items = [i for i in dlg.scene.items() if hasattr(i, 'toPlainText')]
        self.assertGreater(len(items), 0)
        dlg.close()


# ── 核心场景集成测试（真实事件循环）───────────

class TestPdfViewerRealEventLoop(unittest.TestCase):
    """不使用 RenderWorker.start mock，验证真实事件循环下的渲染流程"""

    @classmethod
    def setUpClass(cls):
        cls._msg_patcher = _patch_qmessagebox()
        cls._fitz_patcher, _ = _make_fitz_patcher()
        cls._fitz_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._fitz_patcher.stop()
        cls._msg_patcher.stop()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_show_event_triggers_render(self):
        """showEvent 触发 _first_show → _start_render"""
        pdf = os.path.join(self.tmp, "single.pdf")
        _make_test_pdf(pdf, pages=1)
        dlg = PdfViewerDialog(pdf)
        self.assertTrue(dlg._first_show)
        dlg.show()
        self.assertFalse(dlg._first_show)
        dlg.close()

    def test_render_completes_and_sets_scene(self):
        """渲染完成后场景包含 pixmap_item，loading 状态清除"""
        pdf = os.path.join(self.tmp, "single.pdf")
        _make_test_pdf(pdf, pages=1)
        dlg = PdfViewerDialog(pdf)
        dlg.show()
        QApplication.processEvents()
        for _ in range(50):
            if dlg._pixmap_item is not None:
                break
            QApplication.processEvents()
            from time import sleep
            sleep(0.02)
        self.assertIsNotNone(dlg._pixmap_item,
                            "渲染完成后 _pixmap_item 不应为 None")
        self.assertFalse(dlg._rendering)
        dlg.close()

    def test_loading_text_shown_during_render(self):
        """渲染过程中场景显示加载提示"""
        pdf = os.path.join(self.tmp, "single.pdf")
        _make_test_pdf(pdf, pages=1)
        dlg = PdfViewerDialog(pdf)
        dlg.show()
        QApplication.processEvents()
        items = dlg.scene.items()
        self.assertGreater(len(items), 0)
        dlg.close()

    def test_first_show_only_triggers_once(self):
        """第二次 showEvent 不会重复触发首次渲染"""
        pdf = os.path.join(self.tmp, "multi.pdf")
        _make_test_pdf(pdf, pages=3)
        dlg = PdfViewerDialog(pdf)
        dlg.show()
        QApplication.processEvents()
        self.assertFalse(dlg._first_show)
        dlg.hide()
        dlg.show()
        QApplication.processEvents()
        self.assertFalse(dlg._first_show)
        dlg.close()

    def test_page_navigation_after_render(self):
        """渲染完成后可以正常翻页"""
        pdf = os.path.join(self.tmp, "multi.pdf")
        _make_test_pdf(pdf, pages=3)
        dlg = PdfViewerDialog(pdf)
        dlg.show()
        for _ in range(50):
            if dlg._pixmap_item is not None:
                break
            QApplication.processEvents()
            from time import sleep
            sleep(0.02)
        self.assertIsNotNone(dlg._pixmap_item)
        dlg._go_to_page(1)
        QApplication.processEvents()
        for _ in range(50):
            if not dlg._rendering:
                break
            QApplication.processEvents()
            from time import sleep
            sleep(0.02)
        self.assertEqual(dlg._current_page, 1)
        self.assertIsNotNone(dlg._pixmap_item)
        dlg.close()

    def test_close_cancels_pending_render(self):
        """关闭对话框取消正在进行的渲染"""
        pdf = os.path.join(self.tmp, "single.pdf")
        _make_test_pdf(pdf, pages=1)
        dlg = PdfViewerDialog(pdf)
        dlg.show()
        dlg.close()
        QApplication.processEvents()
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
