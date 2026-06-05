# -*- coding: utf-8 -*-
"""export_service 模块单元测试"""

import sys
import os
import unittest
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from models import Invoice
from services.export_service import ExportService


class TestExportService(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.svc = ExportService()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_invoice(self, **kwargs) -> Invoice:
        defaults = {
            "file": "test.pdf",
            "invoice_type": "增值税专用发票",
            "buyer_name": "测试公司",
            "buyer_tax_id": "12345678901234567",
            "seller_name": "销售方公司",
            "amount": "550.00",
            "tax_rate": "13%",
            "tax_amount": "71.50",
            "total": "621.50",
            "invoice_no": "24113000000012345678",
            "invoice_date": "2024年11月30日",
            "company": "14786",
            "remark": "",
        }
        defaults.update(kwargs)
        return Invoice(**defaults)

    # ── _safe_float ───────────────────────────

    def test_safe_float_positive(self):
        self.assertEqual(self.svc._safe_float("550.00"), 550.0)
        self.assertEqual(self.svc._safe_float(100), 100.0)

    def test_safe_float_negative(self):
        self.assertEqual(self.svc._safe_float("-100.50"), -100.5)

    def test_safe_float_edge_cases(self):
        self.assertEqual(self.svc._safe_float(None), 0.0)
        self.assertEqual(self.svc._safe_float(""), 0.0)
        self.assertEqual(self.svc._safe_float("abc"), 0.0)

    # ── export ────────────────────────────────

    def test_export_creates_file(self):
        invs = [self._make_invoice()]
        path = os.path.join(self.tmp, "test.xlsx")
        self.svc.export(invs, path)
        self.assertTrue(os.path.exists(path))
        self.assertTrue(os.path.getsize(path) > 0)

    def test_export_empty_list(self):
        path = os.path.join(self.tmp, "empty.xlsx")
        self.svc.export([], path)
        self.assertTrue(os.path.exists(path))

    def test_export_multiple_invoices(self):
        invs = [self._make_invoice() for _ in range(5)]
        path = os.path.join(self.tmp, "multi.xlsx")
        self.svc.export(invs, path)
        self.assertTrue(os.path.exists(path))

        # 用 openpyxl 回读验证
        import openpyxl
        wb = openpyxl.load_workbook(path)
        ws = wb.active
        self.assertEqual(ws.title, "发票归档")
        # 1 header + 5 data + 1 empty + 1 summary
        self.assertEqual(ws.max_row, 8)

    def test_export_red_invoice_negative_amounts(self):
        inv = self._make_invoice(amount="-550.00", tax_amount="-71.50",
                                  total="-621.50", is_red=True)
        path = os.path.join(self.tmp, "red.xlsx")
        self.svc.export([inv], path)

        import openpyxl
        wb = openpyxl.load_workbook(path)
        ws = wb.active
        self.assertEqual(ws.cell(2, 5).value, "-550.00")  # 金额列

    def test_export_with_remark(self):
        inv = self._make_invoice(remark="加急处理")
        path = os.path.join(self.tmp, "remark.xlsx")
        self.svc.export([inv], path)

        import openpyxl
        wb = openpyxl.load_workbook(path)
        ws = wb.active
        self.assertEqual(ws.cell(2, 12).value, "加急处理")  # 备注列

    def test_export_fallback_remark(self):
        inv = self._make_invoice(remark="", error="")
        path = os.path.join(self.tmp, "fallback.xlsx")
        self.svc.export([inv], path)

        import openpyxl
        wb = openpyxl.load_workbook(path)
        ws = wb.active
        self.assertEqual(ws.cell(2, 12).value, "✓")

    def test_summary_row_calculations(self):
        invs = [
            self._make_invoice(amount="100", tax_amount="13", total="113"),
            self._make_invoice(amount="200", tax_amount="26", total="226"),
        ]
        path = os.path.join(self.tmp, "summary.xlsx")
        self.svc.export(invs, path)

        import openpyxl
        wb = openpyxl.load_workbook(path)
        ws = wb.active
        # 汇总行：header(1) + 2 data + empty(4) + summary(5)
        sum_row = 5
        self.assertEqual(ws.cell(sum_row, 1).value, "合计")
        self.assertEqual(float(ws.cell(sum_row, 5).value), 300.0)  # 金额合计
        self.assertEqual(float(ws.cell(sum_row, 7).value), 39.0)   # 税额合计
        self.assertEqual(float(ws.cell(sum_row, 8).value), 339.0)  # 价税合计


    def test_export_with_error_field(self):
        """错误字段应显示在备注列"""
        inv = self._make_invoice(remark="", error="PDF解析失败: 格式错误")
        path = os.path.join(self.tmp, "error.xlsx")
        self.svc.export([inv], path)

        import openpyxl
        wb = openpyxl.load_workbook(path)
        ws = wb.active
        self.assertEqual(ws.cell(2, 12).value, "PDF解析失败: 格式错误")

    def test_export_large_invoice_list(self):
        """大量发票导出不崩溃"""
        invs = [self._make_invoice(invoice_no=f"{i:020d}", amount=str(i * 100))
                for i in range(1, 51)]
        path = os.path.join(self.tmp, "large.xlsx")
        self.svc.export(invs, path)
        self.assertTrue(os.path.exists(path))
        self.assertGreater(os.path.getsize(path), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
