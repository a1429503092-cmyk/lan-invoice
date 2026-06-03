# -*- coding: utf-8 -*-
"""dialogs 模块关键逻辑单元测试"""

import sys
import os
import unittest
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from PyQt5.QtWidgets import QApplication, QDialog
from PyQt5.QtCore import Qt

from dialogs import DeleteConfirmDialog


# 模块级 QApplication（所有测试共享）
_app = None


def setUpModule():
    global _app
    _app = QApplication.instance()
    if _app is None:
        _app = QApplication(sys.argv)


# ── DeleteConfirmDialog 测试 ──────────────────

class TestDeleteConfirmDialog(unittest.TestCase):

    def _make_records(self, count=1):
        records = []
        for i in range(count):
            records.append({
                "file": f"test_{i}.pdf",
                "invoice_no": f"241130{i:08d}",
                "invoice_date": "2024年11月30日",
                "seller_name": f"测试销售方{i}",
                "total": f"{100 * (i + 1)}.00",
            })
        return records

    def test_init_button_disabled(self):
        """确认按钮默认禁用"""
        dlg = DeleteConfirmDialog(self._make_records(1))
        self.assertFalse(dlg.btn_ok.isEnabled())
        dlg.close()

    def test_checkbox_enables_button(self):
        """勾选后按钮启用"""
        dlg = DeleteConfirmDialog(self._make_records(1))
        dlg.cb.setChecked(True)
        self.assertTrue(dlg.btn_ok.isEnabled())
        dlg.close()

    def test_uncheck_disables_button(self):
        """取消勾选后按钮禁用"""
        dlg = DeleteConfirmDialog(self._make_records(1))
        dlg.cb.setChecked(True)
        dlg.cb.setChecked(False)
        self.assertFalse(dlg.btn_ok.isEnabled())
        dlg.close()

    def test_accept_returns_accepted(self):
        """勾选后点击确认接受对话框"""
        dlg = DeleteConfirmDialog(self._make_records(1))
        dlg.cb.setChecked(True)
        dlg.btn_ok.click()
        # After accept, dialog should be accepted
        self.assertEqual(dlg.result(), QDialog.Accepted)
        dlg.close()

    def test_multiple_records_display(self):
        """多条记录正确展示"""
        recs = self._make_records(3)
        dlg = DeleteConfirmDialog(recs)
        # 验证对话框正常创建
        self.assertEqual(dlg.windowTitle(), "确认删除")
        dlg.close()

    def test_partial_record_fields(self):
        """部分字段缺失时不崩溃"""
        dlg = DeleteConfirmDialog([{"file": "test.pdf"}])
        self.assertFalse(dlg.btn_ok.isEnabled())
        dlg.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
