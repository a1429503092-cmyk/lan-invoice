# -*- coding: utf-8 -*-
"""PdfViewerDialog 单元测试"""

import sys
import os
import unittest
import tempfile
import shutil
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PyQt5.QtWidgets import QApplication, QMessageBox
from PIL import Image

import pdfplumber
from ui.dialogs.pdf_viewer import PdfViewerDialog


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
        # Mock page.to_image to avoid slow pdfplumber rendering in tests
        cls._render_patcher = patch.object(
            pdfplumber.page.Page, "to_image",
            return_value=Image.new("RGB", (100, 141)),
        )
        cls._render_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._render_patcher.stop()
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
