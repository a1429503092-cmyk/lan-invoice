# -*- coding: utf-8 -*-
"""database 模块单元测试"""
import sys, os, json, unittest, tempfile, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from database import Database
from models import Invoice


class TestDatabaseInit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_init_creates_db_file(self):
        db = Database(self.db_path)
        self.assertTrue(os.path.exists(self.db_path))

    def test_init_creates_table(self):
        db = Database(self.db_path)
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='invoices'")
        self.assertIsNotNone(cur.fetchone())
        conn.close()

    def test_init_idempotent(self):
        Database(self.db_path)
        Database(self.db_path)  # 不抛异常

    def test_auto_creates_parent_dir(self):
        p = os.path.join(self.tmp, "sub1", "sub2", "data.db")
        Database(p)
        self.assertTrue(os.path.exists(p))


class TestDatabaseSaveLoad(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        self.db = Database(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make(self, **kw) -> Invoice:
        return Invoice(**kw)

    def test_save_and_load_empty(self):
        self.db.save([])
        self.assertEqual(self.db.load(), [])

    def test_save_and_load_single(self):
        inv = self._make(file="a.pdf", invoice_no="111", amount="100.00")
        self.db.save([inv])
        result = self.db.load()
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], Invoice)
        self.assertEqual(result[0].file, "a.pdf")
        self.assertEqual(result[0].amount, "100.00")

    def test_save_and_load_multiple(self):
        invs = [
            self._make(file="a.pdf", invoice_no="111"),
            self._make(file="b.pdf", invoice_no="222"),
            self._make(file="c.pdf", invoice_no="333"),
        ]
        self.db.save(invs)
        result = self.db.load()
        self.assertEqual(len(result), 3)
        self.assertEqual(result[1].invoice_no, "222")

    def test_save_replaces_all(self):
        self.db.save([self._make(file="a.pdf", invoice_no="111")])
        self.db.save([self._make(file="b.pdf", invoice_no="222")])
        result = self.db.load()
        self.assertEqual(len(result), 1)

    def test_load_roundtrip_all_fields(self):
        inv = self._make(
            file="f.pdf", pdf_path="/p/f.pdf", company="C001",
            invoice_type="增值税专用发票", buyer_name="买方", buyer_tax_id="TAX123",
            seller_name="卖方", amount="1000.00", tax_rate="13%",
            tax_amount="130.00", total="1130.00", invoice_no="NO001",
            invoice_date="2025年01月15日", is_red=True,
            screenshots=["/ss/1.png"], contracts=["/ct/1.pdf"],
            tags={"企业号": "A01", "项目": "P1"},
            attachments=["/att/1.png"], remark="备注内容", error=""
        )
        self.db.save([inv])
        loaded = self.db.load()[0]
        self.assertEqual(loaded.file, "f.pdf")
        self.assertEqual(loaded.pdf_path, "/p/f.pdf")
        self.assertEqual(loaded.company, "C001")
        self.assertEqual(loaded.invoice_type, "增值税专用发票")
        self.assertEqual(loaded.buyer_name, "买方")
        self.assertEqual(loaded.buyer_tax_id, "TAX123")
        self.assertEqual(loaded.seller_name, "卖方")
        self.assertEqual(loaded.amount, "1000.00")
        self.assertEqual(loaded.tax_rate, "13%")
        self.assertEqual(loaded.tax_amount, "130.00")
        self.assertEqual(loaded.total, "1130.00")
        self.assertEqual(loaded.invoice_no, "NO001")
        self.assertEqual(loaded.invoice_date, "2025年01月15日")
        self.assertTrue(loaded.is_red)
        self.assertEqual(loaded.screenshots, ["/ss/1.png"])
        self.assertEqual(loaded.contracts, ["/ct/1.pdf"])
        self.assertEqual(loaded.tags, {"企业号": "A01", "项目": "P1"})
        self.assertEqual(loaded.attachments, ["/att/1.png"])
        self.assertEqual(loaded.remark, "备注内容")

    def test_load_returns_list_copy(self):
        invs = [self._make(file="a.pdf", invoice_no="111")]
        self.db.save(invs)
        result = self.db.load()
        result.append(self._make(file="b.pdf", invoice_no="222"))
        self.assertEqual(len(self.db.load()), 1)


class TestDatabaseDelete(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        self.db = Database(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make(self, **kw) -> Invoice:
        return Invoice(**kw)

    def test_delete_existing(self):
        invs = [
            self._make(file="a.pdf", invoice_no="111"),
            self._make(file="b.pdf", invoice_no="222"),
        ]
        self.db.save(invs)
        self.db.delete("111")
        result = self.db.load()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].invoice_no, "222")

    def test_delete_nonexistent_no_error(self):
        self.db.save([self._make(file="a.pdf", invoice_no="111")])
        self.db.delete("999")
        self.assertEqual(len(self.db.load()), 1)

    def test_delete_empty_table_no_error(self):
        self.db.delete("111")  # 不抛异常


class TestDatabaseIntegrity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_integrity_check_passes_on_valid_db(self):
        db = Database(self.db_path)
        db.save([Invoice(file="a.pdf", invoice_no="111")])
        self.assertTrue(db.integrity_check())

    def test_handles_corrupt_db_file(self):
        """损坏文件：构造不抛异常，integrity_check 返回 False"""
        with open(self.db_path, "wb") as f:
            f.write(b"not a valid sqlite file")
        db = Database(self.db_path)  # 不抛异常
        self.assertFalse(db.integrity_check())
        self.assertTrue(os.path.exists(self.db_path))

    def test_integrity_check_empty_db(self):
        db = Database(self.db_path)
        self.assertTrue(db.integrity_check())


class TestDatabaseMigration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        self.json_path = os.path.join(self.tmp, "old_data.json")
        self.db = Database(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_json(self, data: list[dict]):
        with open(self.json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    def _base_record(self, **kw):
        d = {"file": "", "invoice_no": "", "screenshots": [], "contracts": [],
             "tags": {}, "attachments": [], "remark": "", "error": ""}
        d.update(kw)
        return d

    def test_migrate_empty_json(self):
        self._write_json([])
        count = self.db.migrate_from_json(self.json_path)
        self.assertEqual(count, 0)
        self.assertEqual(self.db.load(), [])

    def test_migrate_single_record(self):
        self._write_json([self._base_record(
            file="a.pdf", invoice_no="111", buyer_name="测试", amount="100.00")])
        count = self.db.migrate_from_json(self.json_path)
        self.assertEqual(count, 1)
        result = self.db.load()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].invoice_no, "111")

    def test_migrate_multiple_records(self):
        self._write_json([
            self._base_record(file="a.pdf", invoice_no="111"),
            self._base_record(file="b.pdf", invoice_no="222"),
            self._base_record(file="c.pdf", invoice_no="333"),
        ])
        count = self.db.migrate_from_json(self.json_path)
        self.assertEqual(count, 3)
        self.assertEqual(len(self.db.load()), 3)

    def test_migrate_skips_if_data_exists(self):
        self._write_json([self._base_record(file="a.pdf", invoice_no="111")])
        self.db.save([Invoice(file="existing.pdf", invoice_no="000")])
        count = self.db.migrate_from_json(self.json_path)
        self.assertEqual(count, 0)
        result = self.db.load()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].invoice_no, "000")

    def test_migrate_handles_corrupted_json(self):
        with open(self.json_path, "w") as f:
            f.write("not json")
        count = self.db.migrate_from_json(self.json_path)
        self.assertEqual(count, 0)

    def test_migrate_handles_missing_file(self):
        count = self.db.migrate_from_json("/nonexistent/path.json")
        self.assertEqual(count, 0)

    def test_migrate_preserves_list_fields(self):
        self._write_json([self._base_record(
            file="a.pdf", invoice_no="111",
            screenshots=["/ss/1.png", "/ss/2.png"],
            contracts=["/ct/a.pdf"],
            tags={"企业号": "A"},
            attachments=["/att/x.png"],
        )])
        self.db.migrate_from_json(self.json_path)
        result = self.db.load()[0]
        self.assertEqual(result.screenshots, ["/ss/1.png", "/ss/2.png"])
        self.assertEqual(result.contracts, ["/ct/a.pdf"])
        self.assertEqual(result.tags, {"企业号": "A"})
        self.assertEqual(result.attachments, ["/att/x.png"])

    def test_migrate_renames_json_to_bak(self):
        self._write_json([self._base_record(file="a.pdf", invoice_no="111")])
        self.db.migrate_from_json(self.json_path)
        bak_path = self.json_path + ".bak"
        self.assertTrue(os.path.exists(bak_path))
        self.assertFalse(os.path.exists(self.json_path))


if __name__ == "__main__":
    unittest.main(verbosity=2)
