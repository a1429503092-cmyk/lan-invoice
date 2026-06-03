# -*- coding: utf-8 -*-
"""repository 模块单元测试"""

import sys
import os
import json
import unittest
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from repository import InvoiceRepository
from models import Invoice


class TestInvoiceRepository(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.data_file = os.path.join(self.tmp, "invoices_data.json")
        self.repo = InvoiceRepository(self.data_file)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_invoice(self, **kwargs) -> Invoice:
        inv = Invoice(**kwargs)
        return inv

    # ── load ──────────────────────────────────

    def test_load_empty_when_no_file(self):
        self.assertEqual(self.repo.load(), [])

    def test_load_empty_when_empty_json(self):
        with open(self.data_file, "w") as f:
            json.dump([], f)
        self.assertEqual(self.repo.load(), [])

    def test_load_returns_invoices(self):
        invs = [self._make_invoice(file="a.pdf", invoice_no="111").to_dict()]
        with open(self.data_file, "w", encoding="utf-8") as f:
            json.dump(invs, f)
        result = self.repo.load()
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], Invoice)
        self.assertEqual(result[0].file, "a.pdf")

    def test_load_multiple(self):
        invs = [
            self._make_invoice(file="a.pdf", invoice_no="111").to_dict(),
            self._make_invoice(file="b.pdf", invoice_no="222").to_dict(),
        ]
        with open(self.data_file, "w", encoding="utf-8") as f:
            json.dump(invs, f)
        result = self.repo.load()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].invoice_no, "111")
        self.assertEqual(result[1].invoice_no, "222")

    def test_load_handles_corrupted_json(self):
        with open(self.data_file, "w") as f:
            f.write("not json")
        self.assertEqual(self.repo.load(), [])

    def test_load_handles_non_list_json(self):
        with open(self.data_file, "w") as f:
            json.dump({"a": 1}, f)
        self.assertEqual(self.repo.load(), [])

    def test_load_missing_fields_defaulted(self):
        invs = [{"file": "x.pdf"}]  # 只有 file 字段
        with open(self.data_file, "w", encoding="utf-8") as f:
            json.dump(invs, f)
        result = self.repo.load()
        self.assertEqual(result[0].file, "x.pdf")
        self.assertEqual(result[0].invoice_no, "")

    # ── save ──────────────────────────────────

    def test_save_creates_file(self):
        invs = [self._make_invoice(file="a.pdf")]
        self.repo.save(invs)
        self.assertTrue(os.path.exists(self.data_file))

    def test_save_roundtrip(self):
        invs = [
            self._make_invoice(file="a.pdf", invoice_no="111", amount="550.00"),
            self._make_invoice(file="b.pdf", invoice_no="222", is_red=True),
        ]
        self.repo.save(invs)
        loaded = self.repo.load()
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0].file, "a.pdf")
        self.assertEqual(loaded[0].amount, "550.00")
        self.assertTrue(loaded[1].is_red)

    def test_save_empty_list(self):
        self.repo.save([])
        loaded = self.repo.load()
        self.assertEqual(loaded, [])

    def test_save_creates_parent_dir(self):
        repo = InvoiceRepository(os.path.join(self.tmp, "subdir", "data.json"))
        repo.save([])
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "subdir", "data.json")))

    def test_data_file_property(self):
        self.assertEqual(self.repo.data_file, self.data_file)


if __name__ == "__main__":
    unittest.main(verbosity=2)
