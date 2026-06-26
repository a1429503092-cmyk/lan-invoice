# -*- coding: utf-8 -*-
"""backup 模块单元测试"""
import sys
import os
import unittest
import tempfile
import shutil
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from backup import BackupService


class TestGetBackupDirs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_creates_dirs_in_given_roots(self):
        svc = BackupService(roots=[self.tmp])
        dirs = svc.get_backup_dirs()
        self.assertEqual(len(dirs), 1)
        self.assertTrue(os.path.isdir(dirs[0]))
        self.assertTrue(dirs[0].endswith(".lan-invoice-backup"))

    def test_filters_nonexistent_roots(self):
        svc = BackupService(roots=["Z:\\nonexistent\\path\\xyz", self.tmp])
        dirs = svc.get_backup_dirs()
        self.assertEqual(len(dirs), 1)

    def test_idempotent(self):
        svc = BackupService(roots=[self.tmp])
        svc.get_backup_dirs()
        svc.get_backup_dirs()
        dirs = svc.get_backup_dirs()
        self.assertEqual(len(dirs), 1)


class TestBackup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.src_dir = os.path.join(self.tmp, "src")
        self.backup_root = os.path.join(self.tmp, "backup")
        os.makedirs(self.src_dir, exist_ok=True)
        os.makedirs(self.backup_root, exist_ok=True)
        self.db_path = os.path.join(self.src_dir, "invoices.db")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_db(self, path):
        import sqlite3
        os.makedirs(os.path.dirname(path), exist_ok=True)
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE IF NOT EXISTS invoices (id INTEGER, name TEXT)")
        conn.execute("INSERT INTO invoices VALUES (1, 'test')")
        conn.commit()
        conn.close()

    def test_backup_creates_directory_backup(self):
        self._make_db(self.db_path)
        svc = BackupService(roots=[self.backup_root])
        count = svc.backup(self.db_path)
        self.assertGreaterEqual(count, 1)
        backup_dir = os.path.join(self.backup_root, ".lan-invoice-backup")
        entries = os.listdir(backup_dir)
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0].startswith("data_"))
        self.assertTrue(os.path.isdir(os.path.join(backup_dir, entries[0])))

    def test_backup_contains_db_and_files(self):
        import sqlite3
        self._make_db(self.db_path)
        svc = BackupService(roots=[self.backup_root])
        svc.backup(self.db_path)
        backup_dir = os.path.join(self.backup_root, ".lan-invoice-backup")
        sub = os.path.join(backup_dir, os.listdir(backup_dir)[0])
        db_in_backup = os.path.join(sub, "invoices.db")
        self.assertTrue(os.path.exists(db_in_backup), f"Expected {db_in_backup}")
        conn = sqlite3.connect(db_in_backup)
        row = conn.execute("SELECT name FROM invoices WHERE id=1").fetchone()
        conn.close()
        self.assertEqual(row[0], "test")

    def test_backup_skips_when_source_missing(self):
        svc = BackupService(roots=[self.backup_root])
        count = svc.backup("/nonexistent/path.db")
        self.assertEqual(count, 0)

    def test_backup_multiple_roots(self):
        self._make_db(self.db_path)
        root2 = os.path.join(self.tmp, "backup2")
        os.makedirs(root2, exist_ok=True)
        svc = BackupService(roots=[self.backup_root, root2])
        count = svc.backup(self.db_path)
        self.assertEqual(count, 2)

    def test_backup_accumulates_files(self):
        self._make_db(self.db_path)
        svc = BackupService(roots=[self.backup_root])
        svc.backup(self.db_path)
        backup_dir = os.path.join(self.backup_root, ".lan-invoice-backup")
        self.assertEqual(len(os.listdir(backup_dir)), 1)
        # 第二次备份（新实例重置防抖计时器，模拟不同会话的写入）
        svc2 = BackupService(roots=[self.backup_root])
        time.sleep(1.1)
        svc2.backup(self.db_path)
        files = os.listdir(backup_dir)
        self.assertGreaterEqual(len(files), 2)


class TestRestore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.src_dir = os.path.join(self.tmp, "src")
        self.backup_root = os.path.join(self.tmp, "backup")
        os.makedirs(self.src_dir, exist_ok=True)
        os.makedirs(self.backup_root, exist_ok=True)
        self.db_path = os.path.join(self.src_dir, "invoices.db")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_db(self, path):
        import sqlite3
        os.makedirs(os.path.dirname(path), exist_ok=True)
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE IF NOT EXISTS invoices (id INTEGER, name TEXT)")
        conn.execute("INSERT INTO invoices VALUES (1, 'test')")
        conn.commit()
        conn.close()

    def test_restore_from_backup(self):
        import sqlite3
        self._make_db(self.db_path)
        svc = BackupService(roots=[self.backup_root])
        svc.backup(self.db_path)
        os.remove(self.db_path)
        restored = svc.restore(self.db_path)
        self.assertTrue(restored)
        self.assertTrue(os.path.exists(self.db_path))
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT name FROM invoices WHERE id=1").fetchone()
        conn.close()
        self.assertEqual(row[0], "test")

    def test_restore_no_backups_available(self):
        svc = BackupService(roots=["/nonexistent"])
        restored = svc.restore(self.db_path)
        self.assertFalse(restored)


class TestCleanup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_cleanup_removes_old_backups(self):
        backup_dir = os.path.join(self.tmp, ".lan-invoice-backup")
        os.makedirs(backup_dir, exist_ok=True)
        for i in range(5):
            p = os.path.join(backup_dir, f"invoices_2025010{i+1}_120000.db")
            with open(p, "w") as f:
                f.write("")
        svc = BackupService(roots=[self.tmp])
        removed = svc.cleanup(keep_days=0)
        # _MIN_KEEP=3 保留最近 3 个，删除 2 个
        self.assertEqual(removed, 2)
        self.assertEqual(len(os.listdir(backup_dir)), 3)

    def test_cleanup_keeps_recent_backups(self):
        backup_dir = os.path.join(self.tmp, ".lan-invoice-backup")
        os.makedirs(backup_dir, exist_ok=True)
        # 新文件
        recent = os.path.join(backup_dir, "invoices_20250105_120000.db")
        with open(recent, "w") as f:
            f.write("")
        svc = BackupService(roots=[self.tmp])
        removed = svc.cleanup(keep_days=365)
        self.assertEqual(removed, 0)
        self.assertEqual(len(os.listdir(backup_dir)), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
