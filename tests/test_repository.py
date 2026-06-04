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


class TestDataMigration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.data_file = os.path.join(self.tmp, "test_data.json")
        self.repo = InvoiceRepository(self.data_file)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_old_format(self, records: list[dict]):
        with open(self.data_file, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False)

    def test_migrate_company_to_tags(self):
        """company 字段迁移到 tags["企业号"]"""
        self._write_old_format([{
            "file": "test.pdf", "invoice_no": "12345",
            "company": "14786", "screenshots": [], "contracts": [],
        }])
        invoices = self.repo.load()
        self.assertEqual(invoices[0].tags.get("企业号"), "14786")

    def test_migrate_screenshots_and_contracts_to_attachments(self):
        """screenshots + contracts 合并到 attachments"""
        self._write_old_format([{
            "file": "test.pdf", "invoice_no": "12345",
            "company": "", "screenshots": ["/old/ss/1.png"], "contracts": ["/old/ct/1.pdf"],
        }])
        invoices = self.repo.load()
        self.assertIn("/old/ss/1.png", invoices[0].attachments)
        self.assertIn("/old/ct/1.pdf", invoices[0].attachments)

    def test_migrate_does_not_duplicate(self):
        """已有新格式数据的不重复迁移"""
        self._write_old_format([{
            "file": "test.pdf", "invoice_no": "12345",
            "company": "14786", "screenshots": ["/old/ss/1.png"], "contracts": [],
            "tags": {"企业号": "99999"}, "attachments": ["/new/att/1.png"],
        }])
        invoices = self.repo.load()
        self.assertEqual(invoices[0].tags.get("企业号"), "99999")
        self.assertEqual(invoices[0].attachments, ["/new/att/1.png"])

    def test_migrate_empty_old_data(self):
        """空旧数据正常迁移"""
        self._write_old_format([{
            "file": "test.pdf", "invoice_no": "12345",
            "company": "", "screenshots": [], "contracts": [],
        }])
        invoices = self.repo.load()
        self.assertEqual(invoices[0].tags, {})
        self.assertEqual(invoices[0].attachments, [])

    def test_new_format_passes_through(self):
        """新格式数据不受影响"""
        with open(self.data_file, "w", encoding="utf-8") as f:
            json.dump([{
                "file": "test.pdf", "invoice_no": "12345",
                "company": "", "screenshots": [], "contracts": [],
                "tags": {"企业号": "A001", "项目名称": "Q1"},
                "attachments": ["/att/a.png"],
            }], f, ensure_ascii=False)
        invoices = self.repo.load()
        self.assertEqual(invoices[0].tags, {"企业号": "A001", "项目名称": "Q1"})
        self.assertEqual(invoices[0].attachments, ["/att/a.png"])

    def test_migration_saves_to_disk(self):
        """迁移后自动保存为新格式"""
        self._write_old_format([{
            "file": "test.pdf", "invoice_no": "12345",
            "company": "14786", "screenshots": ["/ss.png"], "contracts": [],
        }])
        self.repo.load()
        # 重新加载验证迁移已写入磁盘
        invoices = self.repo.load()
        self.assertEqual(invoices[0].tags.get("企业号"), "14786")
        self.assertIn("/ss.png", invoices[0].attachments)


if __name__ == "__main__":
    unittest.main(verbosity=2)
