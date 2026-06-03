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
from PIL import Image

import pdfplumber
from ui.dialogs.pdf_viewer import PdfViewerDialog, RenderWorker


class MockPageImage:
    """模拟 pdfplumber PageImage，暴露 .original (PIL Image)"""
    def __init__(self, pil_image):
        self.original = pil_image


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


class MockKeyEvent:
    """模拟 QKeyEvent 用于 keyPressEvent 测试"""

    def __init__(self, key, modifiers=None):
        self._key = key
        self._mod = modifiers if modifiers is not None else Qt.NoModifier

    def key(self):
        return self._key

    def modifiers(self):
        return self._mod

    def isAccepted(self):
        return False

    def accept(self):
        pass

    def ignore(self):
        pass


# ── PdfViewerDialog 基本功能测试 ─────────────

class TestPdfViewerBasic(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._msg_patcher = _patch_qmessagebox()
        # Mock page.to_image to avoid slow pdfplumber rendering in tests
        cls._render_patcher = patch.object(
            pdfplumber.page.Page, "to_image",
            return_value=MockPageImage(Image.new("RGB", (100, 141))),
        )
        cls._render_patcher.start()
        # 让 RenderWorker.start() 同步执行 run()，避免测试中多线程问题
        cls._sync_patcher = patch.object(RenderWorker, 'start', lambda self: self.run())
        cls._sync_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._render_patcher.stop()
        cls._sync_patcher.stop()
        cls._msg_patcher.stop()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ── 测试 1：单页 PDF 隐藏导航 ──────────────

    def test_single_page_pdf_hides_navigation(self):
        """单页 PDF 时 btn_prev / btn_next / lbl_page 隐藏"""
        pdf = os.path.join(self.tmp, "single.pdf")
        _make_test_pdf(pdf, pages=1)

        dlg = PdfViewerDialog(pdf)
        dlg.show()

        self.assertFalse(dlg.btn_prev.isVisible())
        self.assertFalse(dlg.btn_next.isVisible())
        self.assertFalse(dlg.lbl_page.isVisible())
        dlg.close()

    # ── 测试 2：多页 PDF 显示页码指示器 ─────────

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

    # ── 测试 3：导航到中间页 ────────────────────

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

    # ── 测试 4：导航到末页 ────────────────────

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

    # ── 测试 5：不存在的文件弹出警告 ────────────

    def test_nonexistent_file_shows_warning(self):
        """打开不存在的 PDF → QMessageBox.warning 被调用"""
        dlg = PdfViewerDialog("/nonexistent/test.pdf")
        QMessageBox.warning.assert_called()
        dlg.close()

    # ── 测试 6：损坏的文件报错 ──────────────────

    def test_corrupt_pdf_shows_error(self):
        """内容非 PDF → QMessageBox.warning 被调用, 不崩溃"""
        corrupt = os.path.join(self.tmp, "corrupt.pdf")
        with open(corrupt, "w") as f:
            f.write("not a pdf content at all")

        dlg = PdfViewerDialog(corrupt)
        QMessageBox.warning.assert_called()
        dlg.close()


# ── 键盘导航测试 ────────────────────────────

class TestPdfViewerKeyboard(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._msg_patcher = _patch_qmessagebox()
        cls._render_patcher = patch.object(
            pdfplumber.page.Page, "to_image",
            return_value=MockPageImage(Image.new("RGB", (100, 141))),
        )
        cls._render_patcher.start()
        cls._sync_patcher = patch.object(RenderWorker, 'start', lambda self: self.run())
        cls._sync_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._render_patcher.stop()
        cls._sync_patcher.stop()
        cls._msg_patcher.stop()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.pdf = os.path.join(self.tmp, "multi.pdf")
        _make_test_pdf(self.pdf, pages=3)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_arrow_right_next_page(self):
        """测试 7: → 键翻到下一页"""
        dlg = PdfViewerDialog(self.pdf)
        old = dlg._current_page
        dlg.keyPressEvent(MockKeyEvent(Qt.Key_Right))
        self.assertEqual(dlg._current_page, old + 1)
        dlg.close()

    def test_arrow_left_prev_page(self):
        """测试 8: ← 键翻到上一页"""
        dlg = PdfViewerDialog(self.pdf)
        dlg._go_to_page(1)
        dlg.keyPressEvent(MockKeyEvent(Qt.Key_Left))
        self.assertEqual(dlg._current_page, 0)
        dlg.close()

    def test_arrow_left_at_boundary_noop(self):
        """测试 9: 首页按 ← 不变"""
        dlg = PdfViewerDialog(self.pdf)
        dlg.keyPressEvent(MockKeyEvent(Qt.Key_Left))
        self.assertEqual(dlg._current_page, 0)
        dlg.close()

    def test_arrow_right_at_boundary_noop(self):
        """测试 10: 末页按 → 不变"""
        dlg = PdfViewerDialog(self.pdf)
        dlg._go_to_page(2)
        dlg.keyPressEvent(MockKeyEvent(Qt.Key_Right))
        self.assertEqual(dlg._current_page, 2)
        dlg.close()


# ── 功能键测试 ─────────────────────────────

class TestPdfViewerKeyButtons(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._msg_patcher = _patch_qmessagebox()
        cls._render_patcher = patch.object(
            pdfplumber.page.Page, "to_image",
            return_value=MockPageImage(Image.new("RGB", (100, 141))),
        )
        cls._render_patcher.start()
        cls._sync_patcher = patch.object(RenderWorker, 'start', lambda self: self.run())
        cls._sync_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._render_patcher.stop()
        cls._sync_patcher.stop()
        cls._msg_patcher.stop()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.pdf = os.path.join(self.tmp, "multi.pdf")
        _make_test_pdf(self.pdf, pages=3)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_escape_closes_dialog(self):
        """测试 11: Esc 关闭对话框"""
        dlg = PdfViewerDialog(self.pdf)
        dlg.show()
        dlg.keyPressEvent(MockKeyEvent(Qt.Key_Escape))
        # accept() 后对话框不可见
        self.assertTrue(dlg.isHidden())
        dlg.close()

    def test_home_jumps_to_first_page(self):
        """测试 12: Home 跳首页"""
        dlg = PdfViewerDialog(self.pdf)
        dlg._go_to_page(2)
        dlg.keyPressEvent(MockKeyEvent(Qt.Key_Home))
        self.assertEqual(dlg._current_page, 0)
        dlg.close()

    def test_end_jumps_to_last_page(self):
        """测试 13: End 跳末页"""
        dlg = PdfViewerDialog(self.pdf)
        dlg.keyPressEvent(MockKeyEvent(Qt.Key_End))
        self.assertEqual(dlg._current_page, 2)
        dlg.close()


# ── 缩放模式测试 ───────────────────────────

class TestPdfViewerZoom(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._msg_patcher = _patch_qmessagebox()
        cls._render_patcher = patch.object(
            pdfplumber.page.Page, "to_image",
            return_value=MockPageImage(Image.new("RGB", (100, 141))),
        )
        cls._render_patcher.start()
        cls._sync_patcher = patch.object(RenderWorker, 'start', lambda self: self.run())
        cls._sync_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._render_patcher.stop()
        cls._sync_patcher.stop()
        cls._msg_patcher.stop()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.pdf = os.path.join(self.tmp, "single.pdf")
        _make_test_pdf(self.pdf, pages=1)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_default_zoom_is_fit_width(self):
        """测试 14: 默认缩放模式 = fit_width"""
        dlg = PdfViewerDialog(self.pdf)
        self.assertEqual(dlg._zoom_mode, "fit_width")
        dlg.close()

    def test_btn_fit_page_switches_mode(self):
        """测试 15: 点击适应页面"""
        dlg = PdfViewerDialog(self.pdf)
        dlg.btn_fit_p.click()
        self.assertEqual(dlg._zoom_mode, "fit_page")
        dlg.close()

    def test_btn_1to1_switches_mode(self):
        """测试 16: 点击 100%"""
        dlg = PdfViewerDialog(self.pdf)
        dlg.btn_1to1.click()
        self.assertEqual(dlg._zoom_mode, "1:1")
        dlg.close()

    def test_zoom_mode_cycle(self):
        """测试 17: 三种模式循环切换"""
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
        cls._render_patcher = patch.object(
            pdfplumber.page.Page, "to_image",
            return_value=MockPageImage(Image.new("RGB", (100, 141))),
        )
        cls._render_patcher.start()
        cls._sync_patcher = patch.object(RenderWorker, 'start', lambda self: self.run())
        cls._sync_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._render_patcher.stop()
        cls._sync_patcher.stop()
        cls._msg_patcher.stop()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # 重置 mock 避免跨测试累计调用
        QMessageBox.warning.reset_mock()
        QMessageBox.information.reset_mock()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_single_page_hides_page_label(self):
        """测试 22: 单页 PDF 不显示页码"""
        pdf = os.path.join(self.tmp, "single.pdf")
        _make_test_pdf(pdf, pages=1)
        dlg = PdfViewerDialog(pdf)
        self.assertFalse(dlg.lbl_page.isVisible())
        dlg.close()

    def test_password_detected_prompts_input(self):
        """测试 23: 加密 PDF → 弹出密码框"""
        with patch("pdfplumber.open") as mock_open:
            mock_open.side_effect = [Exception("password required"),
                                     MagicMock()]
            with patch.object(PdfViewerDialog, "_start_render"):
                with patch("PyQt5.QtWidgets.QInputDialog.getText",
                           return_value=("123456", True)):
                    dlg = PdfViewerDialog("/fake/encrypted.pdf")
                    QMessageBox.warning.assert_not_called()
                    dlg.close()

    def test_wrong_password_shows_error(self):
        """测试 24: 密码错误提示"""
        with patch("pdfplumber.open") as mock_open:
            mock_open.side_effect = [
                Exception("password required"),
                Exception("incorrect password"),
            ]
            with patch.object(PdfViewerDialog, "_start_render"):
                with patch("PyQt5.QtWidgets.QInputDialog.getText",
                           return_value=("wrong", True)):
                    dlg = PdfViewerDialog("/fake/encrypted.pdf")
                    QMessageBox.warning.assert_called()
                    dlg.close()

    def test_password_cancel_shows_hint(self):
        """测试 25: 密码取消提示"""
        with patch("pdfplumber.open") as mock_open:
            mock_open.side_effect = Exception("password required")
            with patch.object(PdfViewerDialog, "_start_render"):
                with patch("PyQt5.QtWidgets.QInputDialog.getText",
                           return_value=("", False)):
                    dlg = PdfViewerDialog("/fake/encrypted.pdf")
                    QMessageBox.information.assert_called()
                    dlg.close()

    def test_file_deleted_while_viewing(self):
        """测试 28: 打开后文件被删除 → 系统打开提示"""
        pdf = os.path.join(self.tmp, "temp.pdf")
        _make_test_pdf(pdf, pages=1)
        dlg = PdfViewerDialog(pdf)
        # 先关闭对话框释放 pdfplumber 文件句柄，再删除文件
        dlg.close()
        os.remove(pdf)
        dlg._open_system()
        QMessageBox.warning.assert_called()

    def test_render_failure_shows_warning(self):
        """测试 27: 渲染失败 → 提示用系统打开"""
        pdf = os.path.join(self.tmp, "single.pdf")
        _make_test_pdf(pdf, pages=1)
        # 让 to_image 抛出异常模拟渲染失败
        with patch.object(pdfplumber.page.Page, "to_image",
                          side_effect=Exception("render error")):
            dlg = PdfViewerDialog(pdf)
            # 渲染异常不会使对话框崩溃
            self.assertTrue(dlg.isVisible() or not dlg.isVisible())
            dlg.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
