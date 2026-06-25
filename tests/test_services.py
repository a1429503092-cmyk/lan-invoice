# -*- coding: utf-8 -*-
"""invoice_service + export_service 单元测试"""

import sys
import os
import unittest
import tempfile
import shutil
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from models import Invoice
from repository import InvoiceRepository
from services.invoice_service import InvoiceService


class TestInvoiceService(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.data_file = os.path.join(self.tmp, "data.json")
        self.attachment_dir = os.path.join(self.tmp, "attachments")
        self.invoice_dir = os.path.join(self.tmp, "invoices")
        self.repo = InvoiceRepository(self.data_file)
        self.svc = InvoiceService(
            self.repo, self.attachment_dir, self.invoice_dir
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_invoice(self, **kwargs) -> Invoice:
        return Invoice(**kwargs)

    # ── load_all / save_all ───────────────────

    def test_load_all_empty(self):
        self.assertEqual(self.svc.load_all(), [])

    def test_save_and_load_roundtrip(self):
        invs = [self._make_invoice(file="a.pdf", invoice_no="111")]
        self.svc.save_all(invs)
        loaded = self.svc.load_all()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].invoice_no, "111")

    # ── find_by_invoice_no ────────────────────

    def test_find_existing(self):
        invs = [
            self._make_invoice(invoice_no="AAA"),
            self._make_invoice(invoice_no="BBB"),
        ]
        self.assertEqual(self.svc.find_by_invoice_no(invs, "BBB"), 1)

    def test_find_nonexistent(self):
        invs = [self._make_invoice(invoice_no="AAA")]
        self.assertIsNone(self.svc.find_by_invoice_no(invs, "ZZZ"))

    def test_find_empty_string(self):
        self.assertIsNone(self.svc.find_by_invoice_no([], ""))

    def test_find_none(self):
        self.assertIsNone(self.svc.find_by_invoice_no([], None))

    # ── init_record ───────────────────────────

    def test_init_record_sets_company(self):
        inv = Invoice()
        InvoiceService.init_record(inv, company="14786")
        self.assertEqual(inv.company, "14786")

    def test_init_record_negates_red(self):
        inv = Invoice(amount="550.00", is_red=True)
        InvoiceService.init_record(inv)
        self.assertEqual(inv.amount, "-550.00")

    # ── make_error_record ─────────────────────

    def test_make_error_record(self):
        inv = InvoiceService.make_error_record("/bad.pdf", "PDF损坏")
        self.assertEqual(inv.pdf_path, "/bad.pdf")
        self.assertEqual(inv.error, "PDF损坏")
        self.assertEqual(inv.file, "")

    # ── add_attachments ───────────────────────

    def test_add_screenshots(self):
        inv = Invoice(invoice_no="TEST001")
        src = os.path.join(self.tmp, "img.png")
        with open(src, "wb") as f:
            f.write(b"fake png")

        added = self.svc.add_attachments(
            inv, [src], "attachments", self.attachment_dir,
            self.svc.namer
        )
        self.assertEqual(added, 1)
        self.assertEqual(len(inv.attachments), 1)
        self.assertTrue(os.path.exists(inv.attachments[0]))
        self.assertIn("TEST001", os.path.basename(inv.attachments[0]))

    def test_add_contracts(self):
        inv = Invoice(invoice_no="TEST002")
        src = os.path.join(self.tmp, "合同.pdf")
        with open(src, "wb") as f:
            f.write(b"fake pdf")

        added = self.svc.add_attachments(
            inv, [src], "attachments", self.attachment_dir,
            self.svc.namer
        )
        self.assertEqual(added, 1)
        self.assertEqual(len(inv.attachments), 1)
        self.assertIn("合同", os.path.basename(inv.attachments[0]))

    def test_add_attachments_skip_missing(self):
        inv = Invoice()
        added = self.svc.add_attachments(
            inv, ["/nonexistent.png"], "attachments", self.attachment_dir,
            self.svc.namer
        )
        self.assertEqual(added, 0)

    def test_add_attachments_no_invoice_no(self):
        """没有发票号时用 file 名或 unnamed 作为安全名"""
        inv = Invoice(file="我的发票.pdf")
        src = os.path.join(self.tmp, "img.png")
        with open(src, "wb") as f:
            f.write(b"x")
        added = self.svc.add_attachments(
            inv, [src], "attachments", self.attachment_dir,
            self.svc.namer
        )
        self.assertEqual(added, 1)

    # ── delete_invoice_files ──────────────────

    def test_delete_existing_file(self):
        pdf = os.path.join(self.tmp, "test.pdf")
        with open(pdf, "w") as f:
            f.write("data")
        inv = Invoice(pdf_path=pdf)
        deleted, failed = InvoiceService.delete_invoice_files(inv)
        self.assertEqual(deleted, 1)
        self.assertEqual(failed, [])
        self.assertFalse(os.path.exists(pdf))

    def test_delete_nonexistent_file(self):
        inv = Invoice(pdf_path="/nonexistent.pdf")
        deleted, failed = InvoiceService.delete_invoice_files(inv)
        self.assertEqual(deleted, 0)

    def test_delete_empty_path(self):
        inv = Invoice(pdf_path="")
        deleted, failed = InvoiceService.delete_invoice_files(inv)
        self.assertEqual(deleted, 0)

    # ── copy_invoice_pdf ──────────────────────

    def test_copy_invoice_pdf(self):
        src = os.path.join(self.tmp, "original.pdf")
        with open(src, "w") as f:
            f.write("pdf content")
        dst = self.svc.copy_invoice_pdf(src)
        self.assertTrue(os.path.exists(dst))
        self.assertIn("invoices", dst)

    def test_namer(self):
        name = InvoiceService.namer("/path/to/img.PNG", "INV001")
        self.assertTrue(name.startswith("INV001_img_"))
        self.assertTrue(name.endswith(".png"))
        # 无扩展名文件默认 .dat
        name2 = InvoiceService.namer("/path/to/img", "INV001")
        self.assertTrue(name2.endswith(".dat"))

    def test_namer(self):
        name = InvoiceService.namer("/path/to/合同文件.pdf", "INV002")
        self.assertTrue(name.startswith("INV002_合同文件_"))
        self.assertTrue(name.endswith(".pdf"))


# ── init_record 补充 ────────────────────────

class TestInitRecordEdgeCases(unittest.TestCase):
    def test_blue_invoice_all_defaults(self):
        inv = Invoice()
        InvoiceService.init_record(inv)
        self.assertFalse(inv.is_red)
        self.assertEqual(inv.amount, "")

    def test_red_invoice_empty_amounts(self):
        inv = Invoice(is_red=True)
        InvoiceService.init_record(inv)
        # 空值不转负
        self.assertEqual(inv.amount, "")

    def test_company_overwrite(self):
        inv = Invoice(company="old")
        InvoiceService.init_record(inv, company="new")
        self.assertEqual(inv.company, "new")

    def test_company_no_overwrite_when_empty(self):
        inv = Invoice(company="old")
        InvoiceService.init_record(inv, company="")
        self.assertEqual(inv.company, "old")


# ── add_attachments 补充 ────────────────────

class TestAddAttachmentsEdgeCases(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.svc = InvoiceService(
            MagicMock(),  # repository not needed for attachment tests
            os.path.join(self.tmp, "att"),
            os.path.join(self.tmp, "inv"),
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_multiple_files(self):
        inv = Invoice(invoice_no="MULTI")
        files = []
        for i in range(3):
            p = os.path.join(self.tmp, f"img_{i}.png")
            with open(p, "wb") as f:
                f.write(b"data")
            files.append(p)

        added = self.svc.add_attachments(
            inv, files, "attachments", self.svc._attachment_dir,
            InvoiceService.namer
        )
        self.assertEqual(added, 3)
        self.assertEqual(len(inv.attachments), 3)

    def test_mixed_existing_and_missing(self):
        inv = Invoice(invoice_no="MIXED")
        good = os.path.join(self.tmp, "good.png")
        with open(good, "wb") as f:
            f.write(b"x")

        added = self.svc.add_attachments(
            inv, [good, "/nonexistent/bad.png"], "attachments",
            self.svc._attachment_dir, InvoiceService.namer
        )
        self.assertEqual(added, 1)

    def test_add_to_existing_attachments(self):
        inv = Invoice(invoice_no="APPEND", attachments=["existing.png"])
        src = os.path.join(self.tmp, "new.png")
        with open(src, "wb") as f:
            f.write(b"data")

        added = self.svc.add_attachments(
            inv, [src], "attachments", self.svc._attachment_dir,
            InvoiceService.namer
        )
        self.assertEqual(added, 1)
        self.assertEqual(len(inv.attachments), 2)


# ── delete_invoice_files 补充 ───────────────

class TestDeleteInvoiceFilesExtra(unittest.TestCase):
    def test_delete_multiple(self):
        tmp = tempfile.mkdtemp()
        try:
            p1 = os.path.join(tmp, "a.pdf")
            p2 = os.path.join(tmp, "b.pdf")
            with open(p1, "w") as f:
                f.write("a")
            with open(p2, "w") as f:
                f.write("b")

            inv = Invoice(pdf_path=p1)
            deleted, failed = InvoiceService.delete_invoice_files(inv)
            self.assertEqual(deleted, 1)

            inv2 = Invoice(pdf_path=p2)
            deleted2, _ = InvoiceService.delete_invoice_files(inv2)
            self.assertEqual(deleted2, 1)
            self.assertFalse(os.path.exists(p1))
            self.assertFalse(os.path.exists(p2))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ── add_attachments OSError 边界 ──────────────

class TestAddAttachmentsOSError(TestInvoiceService):

    def test_oserror_on_copy_is_skipped(self):
        """add_attachments: 单个文件复制失败（OSError）不阻止其他文件"""
        inv = Invoice(invoice_no="IOERR")
        src = os.path.join(self.tmp, "good.png")
        with open(src, "wb") as f:
            f.write(b"x")
        with unittest.mock.patch("shutil.copy2", side_effect=OSError("mock fail")):
            added = self.svc.add_attachments(
                inv, [src], "attachments", self.svc._attachment_dir,
                InvoiceService.namer
            )
        self.assertEqual(added, 0)


# ── delete_invoice_files OSError 边界 ────────

class TestDeleteInvoiceFilesOSError(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_oserror_on_remove_recorded_as_failed(self):
        """delete_invoice_files: 文件删除失败被记录到 failed 列表"""
        pdf = os.path.join(self.tmp, "locked.pdf")
        with open(pdf, "w") as f:
            f.write("data")
        inv = Invoice(pdf_path=pdf)
        with unittest.mock.patch("os.remove", side_effect=OSError("mock fail")):
            deleted, failed = InvoiceService.delete_invoice_files(inv)
        self.assertEqual(deleted, 0)
        self.assertEqual(len(failed), 1)
        self.assertIn("locked.pdf", failed[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
