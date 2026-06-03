# -*- coding: utf-8 -*-
"""dialogs 模块补充测试 — InvoiceManager / ContractManager / Settings"""

import sys
import os
import unittest
import tempfile
import shutil
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from PyQt5.QtWidgets import QApplication, QMessageBox

_app = QApplication.instance()
if _app is None:
    _app = QApplication(sys.argv)


# ── 辅助：mock QMessageBox 避免弹窗阻塞 ──────

def _patch_qmessagebox():
    """mock QMessageBox 的 question/warning/information/critical 方法"""
    patcher = patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes)
    patcher.start()
    patch.object(QMessageBox, 'warning', return_value=None).start()
    patch.object(QMessageBox, 'information', return_value=None).start()
    patch.object(QMessageBox, 'critical', return_value=None).start()
    return patcher


# ── InvoiceManagerDialog ────────────────────

class TestInvoiceManagerDialog(unittest.TestCase):

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

    def test_init_with_existing_pdf(self):
        pdf = os.path.join(self.tmp, "test.pdf")
        with open(pdf, "w") as f:
            f.write("pdf content" * 100)

        from ui.dialogs.invoice_manager import InvoiceManagerDialog
        dlg = InvoiceManagerDialog(pdf, rec_name="测试公司")
        self.assertIn("发票PDF", dlg.windowTitle())
        self.assertIn("测试公司", dlg.windowTitle())
        self.assertTrue(dlg.btn_preview.isEnabled())
        self.assertTrue(dlg.btn_download.isEnabled())
        dlg.close()

    def test_init_with_nonexistent_pdf(self):
        from ui.dialogs.invoice_manager import InvoiceManagerDialog
        dlg = InvoiceManagerDialog("/nonexistent/path.pdf")
        self.assertFalse(dlg.btn_preview.isEnabled())
        self.assertFalse(dlg.btn_download.isEnabled())
        dlg.close()

    def test_init_with_empty_path(self):
        from ui.dialogs.invoice_manager import InvoiceManagerDialog
        dlg = InvoiceManagerDialog("")
        self.assertFalse(dlg.btn_preview.isEnabled())
        dlg.close()

    def test_init_without_rec_name(self):
        from ui.dialogs.invoice_manager import InvoiceManagerDialog
        pdf = os.path.join(self.tmp, "test.pdf")
        with open(pdf, "w") as f:
            f.write("data")
        dlg = InvoiceManagerDialog(pdf)
        self.assertEqual(dlg.windowTitle(), "发票PDF")
        dlg.close()


# ── ContractManagerDialog ──────────────────

class TestContractManagerDialog(unittest.TestCase):

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

    def _make_file(self, name, content=b"data"):
        path = os.path.join(self.tmp, name)
        with open(path, "wb") as f:
            f.write(content)
        return path

    def test_init_with_contracts(self):
        from ui.dialogs.contract_manager import ContractManagerDialog
        p1 = self._make_file("合同1.pdf")
        p2 = self._make_file("合同2.docx")
        dlg = ContractManagerDialog([p1, p2], rec_name="测试")
        self.assertEqual(dlg.list_widget.count(), 2)
        dlg.close()

    def test_init_empty(self):
        from ui.dialogs.contract_manager import ContractManagerDialog
        dlg = ContractManagerDialog([])
        self.assertEqual(dlg.list_widget.count(), 0)
        self.assertFalse(dlg.btn_open.isEnabled())
        dlg.close()

    def test_remove_contract(self):
        from ui.dialogs.contract_manager import ContractManagerDialog
        p1 = self._make_file("合同1.pdf")
        p2 = self._make_file("合同2.pdf")
        dlg = ContractManagerDialog([p1, p2])
        self.assertEqual(len(dlg.contract_paths), 2)

        dlg.list_widget.setCurrentRow(1)
        dlg._remove_selected()
        self.assertEqual(len(dlg.contract_paths), 1)
        self.assertEqual(dlg.list_widget.count(), 1)
        dlg.close()

    def test_select_enables_buttons(self):
        from ui.dialogs.contract_manager import ContractManagerDialog
        p1 = self._make_file("c.pdf")
        dlg = ContractManagerDialog([p1])
        self.assertTrue(dlg.btn_open.isEnabled())
        self.assertTrue(dlg.btn_download.isEnabled())
        self.assertTrue(dlg.btn_del.isEnabled())
        dlg.close()

    def test_get_selected_path(self):
        from ui.dialogs.contract_manager import ContractManagerDialog
        p1 = self._make_file("c.pdf")
        dlg = ContractManagerDialog([p1])
        path = dlg._get_selected_path()
        self.assertEqual(path, p1)
        dlg.close()

    def test_get_selected_path_none(self):
        from ui.dialogs.contract_manager import ContractManagerDialog
        dlg = ContractManagerDialog([])
        self.assertIsNone(dlg._get_selected_path())
        dlg.close()

    def test_file_type_icons(self):
        from ui.dialogs.contract_manager import ContractManagerDialog
        p1 = self._make_file("a.pdf")
        p2 = self._make_file("b.docx")
        p3 = self._make_file("c.xlsx")
        dlg = ContractManagerDialog([p1, p2, p3])
        self.assertEqual(dlg.list_widget.count(), 3)
        dlg.close()

    def test_nonexistent_file_marked(self):
        from ui.dialogs.contract_manager import ContractManagerDialog
        dlg = ContractManagerDialog(["/nonexistent/c.pdf"])
        self.assertEqual(dlg.list_widget.count(), 1)
        item = dlg.list_widget.item(0)
        self.assertIn("文件已移动", item.text())
        dlg.close()


# ── ContractManager 错误路径 ──────────────────

class TestContractManagerErrorPaths(unittest.TestCase):

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

    def test_download_nonexistent_shows_warning(self):
        """下载不存在的文件时弹出警告"""
        from ui.dialogs.contract_manager import ContractManagerDialog
        dlg = ContractManagerDialog(["/nonexistent/f.pdf"])
        dlg.list_widget.setCurrentRow(0)
        dlg._download_selected()
        QMessageBox.warning.assert_called_once()
        dlg.close()

    def test_remove_confirmed_removes_item(self):
        """确认移除后条目从列表消失"""
        f = os.path.join(self.tmp, "valid.pdf")
        with open(f, "w") as fh:
            fh.write("pdf")
        from ui.dialogs.contract_manager import ContractManagerDialog
        dlg = ContractManagerDialog([f])
        self.assertEqual(dlg.list_widget.count(), 1)
        dlg.list_widget.setCurrentRow(0)
        dlg._remove_selected()
        self.assertEqual(dlg.list_widget.count(), 0)
        dlg.close()

    def test_download_with_no_selection_does_nothing(self):
        """无选中项时下载不崩溃"""
        from ui.dialogs.contract_manager import ContractManagerDialog
        dlg = ContractManagerDialog(["/nonexistent/f.pdf"])
        dlg._download_selected()
        dlg.close()


# ── InvoiceManager 错误路径 ───────────────────

class TestInvoiceManagerErrorPaths(unittest.TestCase):

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

    def test_open_nonexistent_pdf_warns(self):
        """打开不存在的PDF弹出警告"""
        from ui.dialogs.invoice_manager import InvoiceManagerDialog
        dlg = InvoiceManagerDialog("/nonexistent/invoice.pdf")
        dlg._open_system()
        QMessageBox.warning.assert_called()
        dlg.close()

    def test_download_nonexistent_pdf_warns(self):
        """下载不存在的PDF弹出警告"""
        from ui.dialogs.invoice_manager import InvoiceManagerDialog
        dlg = InvoiceManagerDialog("/nonexistent/invoice.pdf")
        dlg._download_pdf()
        QMessageBox.warning.assert_called()
        dlg.close()

    def test_open_existing_pdf_download_path(self):
        """存在的PDF可正常走下载路径（不崩溃）"""
        f = os.path.join(self.tmp, "real.pdf")
        with open(f, "w") as fh:
            fh.write("content")
        from ui.dialogs.invoice_manager import InvoiceManagerDialog
        dlg = InvoiceManagerDialog(f)
        # _refresh 调用了 _build_ui 里的 setStyleSheet → 确认 label 已更新
        self.assertIn("real.pdf", dlg.lbl_path.text())
        self.assertTrue(dlg.btn_preview.isEnabled())
        dlg.close()


# ── InvoiceManager 集成测试 ────────────────────

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
        from ui.dialogs.invoice_manager import InvoiceManagerDialog
        dlg = InvoiceManagerDialog(f)
        with patch("ui.dialogs.pdf_viewer.PdfViewerDialog") as mock_dlg:
            dlg._preview_pdf()
            mock_dlg.assert_called_once_with(f, parent=dlg)
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

    def test_title_contains_invoice_name_and_no(self):
        """测试 34: 标题包含购买方名称 + 发票号码"""
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
        """测试 35: 文件不存在时按钮全部禁用"""
        from ui.dialogs.invoice_manager import InvoiceManagerDialog
        dlg = InvoiceManagerDialog("/nonexistent.pdf")
        self.assertFalse(dlg.btn_preview.isEnabled())
        self.assertFalse(dlg.btn_sys_open.isEnabled())
        self.assertFalse(dlg.btn_download.isEnabled())
        dlg.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
