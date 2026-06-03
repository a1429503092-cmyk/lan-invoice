# -*- coding: utf-8 -*-
"""models 模块单元测试"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from models import Invoice


class TestInvoiceDefaults(unittest.TestCase):
    def test_default_values(self):
        inv = Invoice()
        self.assertEqual(inv.file, "")
        self.assertEqual(inv.pdf_path, "")
        self.assertEqual(inv.company, "")
        self.assertEqual(inv.invoice_type, "")
        self.assertEqual(inv.buyer_name, "")
        self.assertEqual(inv.buyer_tax_id, "")
        self.assertEqual(inv.seller_name, "")
        self.assertEqual(inv.amount, "")
        self.assertEqual(inv.tax_rate, "")
        self.assertEqual(inv.tax_amount, "")
        self.assertEqual(inv.total, "")
        self.assertEqual(inv.invoice_no, "")
        self.assertEqual(inv.invoice_date, "")
        self.assertFalse(inv.is_red)
        self.assertEqual(inv.screenshots, [])
        self.assertEqual(inv.contracts, [])
        self.assertEqual(inv.remark, "")
        self.assertEqual(inv.error, "")


class TestInvoiceToDict(unittest.TestCase):
    def test_empty_invoice(self):
        inv = Invoice()
        d = inv.to_dict()
        self.assertEqual(d["file"], "")
        self.assertEqual(d["is_red"], False)
        self.assertEqual(d["screenshots"], [])
        self.assertEqual(d["contracts"], [])

    def test_full_invoice(self):
        inv = Invoice(
            file="test.pdf",
            pdf_path="/data/test.pdf",
            company="14786",
            invoice_type="增值税专用发票",
            buyer_name="测试公司",
            buyer_tax_id="91350700156534567X",
            seller_name="销售方",
            amount="550.00",
            tax_rate="13%",
            tax_amount="71.50",
            total="621.50",
            invoice_no="24113000000012345678",
            invoice_date="2024年11月30日",
            is_red=False,
            screenshots=["/ss/1.png"],
            contracts=["/ct/1.pdf"],
            remark="备注",
            error="",
        )
        d = inv.to_dict()
        self.assertEqual(d["file"], "test.pdf")
        self.assertEqual(d["amount"], "550.00")
        self.assertEqual(d["screenshots"], ["/ss/1.png"])
        self.assertEqual(d["contracts"], ["/ct/1.pdf"])

    def test_screenshots_is_copy(self):
        inv = Invoice(screenshots=["a.png"])
        d = inv.to_dict()
        d["screenshots"].append("b.png")
        self.assertEqual(len(inv.screenshots), 1)  # 不影响原对象


class TestInvoiceFromDict(unittest.TestCase):
    def test_full_dict(self):
        d = {
            "file": "test.pdf",
            "pdf_path": "/data/test.pdf",
            "company": "14786",
            "invoice_type": "增值税专用发票",
            "buyer_name": "测试公司",
            "buyer_tax_id": "91350700156534567X",
            "seller_name": "销售方",
            "amount": "550.00",
            "tax_rate": "13%",
            "tax_amount": "71.50",
            "total": "621.50",
            "invoice_no": "24113000000012345678",
            "invoice_date": "2024年11月30日",
            "is_red": True,
            "screenshots": ["a.png", "b.png"],
            "contracts": ["c.pdf"],
            "remark": "ok",
            "error": "",
        }
        inv = Invoice.from_dict(d)
        self.assertEqual(inv.file, "test.pdf")
        self.assertEqual(inv.amount, "550.00")
        self.assertTrue(inv.is_red)
        self.assertEqual(inv.screenshots, ["a.png", "b.png"])
        self.assertEqual(inv.contracts, ["c.pdf"])

    def test_partial_dict(self):
        d = {"file": "x.pdf", "invoice_no": "12345"}
        inv = Invoice.from_dict(d)
        self.assertEqual(inv.file, "x.pdf")
        self.assertEqual(inv.invoice_no, "12345")
        self.assertEqual(inv.buyer_name, "")
        self.assertEqual(inv.screenshots, [])
        self.assertFalse(inv.is_red)

    def test_empty_dict(self):
        inv = Invoice.from_dict({})
        self.assertEqual(inv.file, "")


class TestEnsureDefaults(unittest.TestCase):
    def test_red_invoice_negates_amounts(self):
        inv = Invoice(amount="550.00", tax_amount="71.50", total="621.50", is_red=True)
        inv.ensure_defaults()
        self.assertEqual(inv.amount, "-550.00")
        self.assertEqual(inv.tax_amount, "-71.50")
        self.assertEqual(inv.total, "-621.50")

    def test_red_invoice_already_negative(self):
        inv = Invoice(amount="-550.00", is_red=True)
        inv.ensure_defaults()
        self.assertEqual(inv.amount, "-550.00")

    def test_blue_invoice_unchanged(self):
        inv = Invoice(amount="550.00", is_red=False)
        inv.ensure_defaults()
        self.assertEqual(inv.amount, "550.00")

    def test_empty_amounts_unchanged(self):
        inv = Invoice(is_red=True)
        inv.ensure_defaults()
        self.assertEqual(inv.amount, "")


class TestInvoiceDictCompat(unittest.TestCase):
    """Invoice 字典兼容方法测试"""

    def test_get_existing(self):
        inv = Invoice(file="test.pdf", amount="550.00")
        self.assertEqual(inv.get("file"), "test.pdf")
        self.assertEqual(inv.get("amount"), "550.00")

    def test_get_nonexistent_default(self):
        inv = Invoice()
        self.assertIsNone(inv.get("nonexist"))
        self.assertEqual(inv.get("nonexist", "fallback"), "fallback")

    def test_getitem(self):
        inv = Invoice(file="test.pdf")
        self.assertEqual(inv["file"], "test.pdf")

    def test_getitem_keyerror(self):
        inv = Invoice()
        with self.assertRaises(AttributeError):
            _ = inv["nonexist"]

    def test_setitem(self):
        inv = Invoice()
        inv["file"] = "new.pdf"
        inv["amount"] = "100.00"
        self.assertEqual(inv.file, "new.pdf")
        self.assertEqual(inv.amount, "100.00")

    def test_contains(self):
        inv = Invoice(file="test.pdf")
        self.assertIn("file", inv)
        self.assertIn("invoice_no", inv)
        self.assertNotIn("nonexist", inv)

    def test_setdefault_creates_new(self):
        inv = Invoice()
        inv.setdefault("remark", "✓")
        self.assertEqual(inv.remark, "✓")

    def test_setdefault_preserves_existing(self):
        inv = Invoice(remark="ok")
        inv.setdefault("remark", "✓")
        self.assertEqual(inv.remark, "ok")

    def test_setdefault_empty_string(self):
        inv = Invoice(remark="")
        inv.setdefault("remark", "✓")
        self.assertEqual(inv.remark, "✓")

    def test_setdefault_empty_list(self):
        inv = Invoice(screenshots=[])
        inv.setdefault("screenshots", ["default.png"])
        self.assertEqual(inv.screenshots, ["default.png"])

    def test_setdefault_preserves_nonempty_list(self):
        inv = Invoice(screenshots=["a.png"])
        inv.setdefault("screenshots", ["default.png"])
        self.assertEqual(inv.screenshots, ["a.png"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
