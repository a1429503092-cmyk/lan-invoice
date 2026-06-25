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
        self.assertEqual(inv.remark, "")
        self.assertEqual(inv.error, "")
        self.assertEqual(inv.tags, {})
        self.assertEqual(inv.attachments, [])


class TestInvoiceToDict(unittest.TestCase):
    def test_empty_invoice(self):
        inv = Invoice()
        d = inv.to_dict()
        self.assertEqual(d["file"], "")
        self.assertEqual(d["is_red"], False)
        self.assertEqual(d["tags"], {})
        self.assertEqual(d["attachments"], [])

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
            attachments=["/att/1.png"],
            tags={"企业号": "A01"},
            remark="备注",
            error="",
        )
        d = inv.to_dict()
        self.assertEqual(d["file"], "test.pdf")
        self.assertEqual(d["amount"], "550.00")
        self.assertEqual(d["attachments"], ["/att/1.png"])
        self.assertEqual(d["tags"], {"企业号": "A01"})

    def test_attachments_is_copy(self):
        inv = Invoice(attachments=["a.png"])
        d = inv.to_dict()
        d["attachments"].append("b.png")
        self.assertEqual(len(inv.attachments), 1)  # 不影响原对象


class TestInvoiceFromDict(unittest.TestCase):
    def test_full_dict(self):
        d = {
            "file": "test.pdf", "pdf_path": "/data/test.pdf",
            "company": "14786", "invoice_type": "增值税专用发票",
            "buyer_name": "测试公司", "buyer_tax_id": "91350700156534567X",
            "seller_name": "销售方", "amount": "550.00", "tax_rate": "13%",
            "tax_amount": "71.50", "total": "621.50",
            "invoice_no": "24113000000012345678",
            "invoice_date": "2024年11月30日", "is_red": True,
            "attachments": ["a.png", "c.pdf"],
            "tags": {"企业号": "A01"},
            "remark": "ok", "error": "",
        }
        inv = Invoice.from_dict(d)
        self.assertEqual(inv.file, "test.pdf")
        self.assertEqual(inv.amount, "550.00")
        self.assertTrue(inv.is_red)
        self.assertEqual(inv.attachments, ["a.png", "c.pdf"])
        self.assertEqual(inv.tags, {"企业号": "A01"})

    def test_partial_dict(self):
        d = {"file": "x.pdf", "invoice_no": "12345"}
        inv = Invoice.from_dict(d)
        self.assertEqual(inv.file, "x.pdf")
        self.assertEqual(inv.invoice_no, "12345")
        self.assertEqual(inv.buyer_name, "")
        self.assertEqual(inv.attachments, [])
        self.assertFalse(inv.is_red)

    def test_migrates_old_screenshots_and_contracts(self):
        """旧数据 screenshots/contracts 自动合并到 attachments"""
        d = {
            "file": "old.pdf", "invoice_no": "999",
            "screenshots": ["/ss/1.png", "/ss/2.png"],
            "contracts": ["/ct/a.pdf"],
            "attachments": ["/att/existing.png"],
        }
        inv = Invoice.from_dict(d)
        self.assertIn("/ss/1.png", inv.attachments)
        self.assertIn("/ss/2.png", inv.attachments)
        self.assertIn("/ct/a.pdf", inv.attachments)
        self.assertIn("/att/existing.png", inv.attachments)

    def test_migrates_no_duplicates(self):
        """重复路径不重复添加"""
        d = {
            "file": "old.pdf", "invoice_no": "999",
            "screenshots": ["/dup.png"],
            "attachments": ["/dup.png"],
        }
        inv = Invoice.from_dict(d)
        self.assertEqual(inv.attachments, ["/dup.png"])

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
        inv = Invoice(attachments=[])
        inv.setdefault("attachments", ["default.png"])
        self.assertEqual(inv.attachments, ["default.png"])

    def test_setdefault_preserves_nonempty_list(self):
        inv = Invoice(attachments=["a.png"])
        inv.setdefault("attachments", ["default.png"])
        self.assertEqual(inv.attachments, ["a.png"])


class TestInvoiceTags(unittest.TestCase):
    def test_tags_default_empty(self):
        inv = Invoice()
        self.assertEqual(inv.tags, {})

    def test_tags_roundtrip(self):
        inv = Invoice(
            invoice_no="12345",
            tags={"企业号": "14786", "项目名称": "2026Q1"},
        )
        d = inv.to_dict()
        self.assertEqual(d["tags"]["企业号"], "14786")
        self.assertEqual(d["tags"]["项目名称"], "2026Q1")

    def test_tags_from_dict(self):
        d = {"invoice_no": "X", "tags": {"企业号": "A001", "负责人": "张三"}}
        inv = Invoice.from_dict(d)
        self.assertEqual(inv.tags["企业号"], "A001")
        self.assertEqual(inv.tags["负责人"], "张三")

    def test_tags_from_dict_none(self):
        inv = Invoice.from_dict({"invoice_no": "X"})
        self.assertEqual(inv.tags, {})

    def test_setitem_tags(self):
        inv = Invoice()
        inv["tags"] = {"企业号": "B001"}
        self.assertEqual(inv.tags, {"企业号": "B001"})

    def test_getitem_tags(self):
        inv = Invoice(tags={"企业号": "C001"})
        self.assertEqual(inv["tags"]["企业号"], "C001")


class TestInvoiceAttachments(unittest.TestCase):
    def test_attachments_default_empty(self):
        inv = Invoice()
        self.assertEqual(inv.attachments, [])

    def test_attachments_roundtrip(self):
        inv = Invoice(
            invoice_no="12345",
            attachments=["/data/attachments/a.png", "/data/attachments/b.pdf"],
        )
        d = inv.to_dict()
        self.assertEqual(d["attachments"], ["/data/attachments/a.png", "/data/attachments/b.pdf"])

    def test_attachments_from_dict(self):
        d = {"invoice_no": "X", "attachments": ["/path/a.png"]}
        inv = Invoice.from_dict(d)
        self.assertEqual(inv.attachments, ["/path/a.png"])

    def test_attachments_from_dict_none(self):
        inv = Invoice.from_dict({"invoice_no": "X"})
        self.assertEqual(inv.attachments, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
