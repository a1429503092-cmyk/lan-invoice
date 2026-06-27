# -*- coding: utf-8 -*-
"""WebDAV 增量同步全覆盖测试"""

import sys
import os
import json
import unittest
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from webdav_sync import SyncManifest, _md5, test_connection


class TestSyncManifest(unittest.TestCase):
    """SyncManifest 增量扫描测试"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.data = os.path.join(self.tmp, "data")
        os.makedirs(self.data)
        self.sync = SyncManifest(self.data)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, relpath, content="test"):
        p = os.path.join(self.data, relpath)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(content)

    # ── 空目录 ──────────────────────────────────

    def test_empty_scan(self):
        diff = self.sync.scan(self.data)
        self.assertEqual(diff["added"], [])
        self.assertEqual(diff["deleted"], [])

    def test_empty_load(self):
        self.sync.load()
        self.assertEqual(self.sync._files, {})

    # ── 新增 ────────────────────────────────────

    def test_new_file_detected_as_added(self):
        self._write("a.txt")
        diff = self.sync.scan(self.data)
        self.assertIn("a.txt", diff["added"])
        self.assertEqual(diff["deleted"], [])
        self.assertEqual(diff["modified"], [])

    def test_multiple_new_files(self):
        self._write("a.txt")
        self._write("sub/b.txt")
        diff = self.sync.scan(self.data)
        self.assertEqual(len(diff["added"]), 2)

    # ── 修改 ────────────────────────────────────

    def test_modified_file_detected(self):
        self._write("a.txt", "v1")
        self.sync.scan(self.data)
        self.sync.commit()
        self._write("a.txt", "v2")
        diff = self.sync.scan(self.data)
        self.assertIn("a.txt", diff["modified"])
        self.assertNotIn("a.txt", diff["added"])

    # ── 删除 ────────────────────────────────────

    def test_deleted_file_detected(self):
        self._write("a.txt")
        self.sync.scan(self.data)
        self.sync.commit()
        p = os.path.join(self.data, "a.txt")
        os.remove(p)
        diff = self.sync.scan(self.data)
        self.assertIn("a.txt", diff["deleted"])

    # ── 无变更 ──────────────────────────────────

    def test_no_change_no_diff(self):
        self._write("a.txt")
        self.sync.scan(self.data)
        self.sync.commit()
        diff = self.sync.scan(self.data)
        self.assertEqual(diff["added"], [])
        self.assertEqual(diff["modified"], [])
        self.assertEqual(diff["deleted"], [])

    # ── 混合 ────────────────────────────────────

    def test_add_modify_delete_together(self):
        self._write("old.txt", "v1")
        self._write("mod.txt", "v1")
        self.sync.scan(self.data)
        self.sync.commit()

        os.remove(os.path.join(self.data, "old.txt"))
        self._write("mod.txt", "v2")
        self._write("new.txt", "v1")

        diff = self.sync.scan(self.data)
        self.assertIn("old.txt", diff["deleted"])
        self.assertIn("mod.txt", diff["modified"])
        self.assertIn("new.txt", diff["added"])
        self.assertEqual(len(diff["added"]), 1)
        self.assertEqual(len(diff["modified"]), 1)
        self.assertEqual(len(diff["deleted"]), 1)

    # ── manifest 持久化 ──────────────────────────

    def test_save_and_load_manifest(self):
        self._write("a.txt", "hello")
        self.sync.scan(self.data)
        self.sync.commit()

        s2 = SyncManifest(self.data)
        s2.load()
        self.assertEqual(s2._files, self.sync._files)

    def test_load_corrupt_manifest(self):
        with open(os.path.join(self.data, "sync_manifest.json"), "w") as f:
            f.write("not json")
        self.sync.load()
        self.assertEqual(self.sync._files, {})

    def test_load_missing_manifest(self):
        self.sync.load()
        self.assertEqual(self.sync._files, {})

    # ── 排除自身 ───────────────────────────────

    def test_manifest_excluded_from_scan(self):
        self._write("sync_manifest.json", "{}")
        diff = self.sync.scan(self.data)
        self.assertNotIn("sync_manifest.json", diff["added"])

    # ── 子目录 ──────────────────────────────────

    def test_nested_directories(self):
        self._write("a/b/c/d.txt", "deep")
        diff = self.sync.scan(self.data)
        self.assertIn("a/b/c/d.txt", diff["added"])

    def test_empty_subdir_ignored(self):
        os.makedirs(os.path.join(self.data, "empty_dir"))
        diff = self.sync.scan(self.data)
        self.assertEqual(diff["added"], [])

    # ── 二进制文件 ──────────────────────────────

    def test_binary_file_md5(self):
        p = os.path.join(self.data, "img.png")
        with open(p, "wb") as f:
            f.write(b"\x00\x01\x02\x03\x04" * 100)
        diff = self.sync.scan(self.data)
        self.assertEqual(len(diff["added"]), 1)


class TestMd5(unittest.TestCase):
    """MD5 计算测试"""

    def test_same_content_same_hash(self):
        tmp = tempfile.mkdtemp()
        try:
            a = os.path.join(tmp, "a.txt")
            b = os.path.join(tmp, "b.txt")
            with open(a, "w") as f:
                f.write("same")
            with open(b, "w") as f:
                f.write("same")
            self.assertEqual(_md5(a), _md5(b))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_different_content_different_hash(self):
        tmp = tempfile.mkdtemp()
        try:
            a = os.path.join(tmp, "a.txt")
            b = os.path.join(tmp, "b.txt")
            with open(a, "w") as f:
                f.write("aaa")
            with open(b, "w") as f:
                f.write("bbb")
            self.assertNotEqual(_md5(a), _md5(b))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestConnection(unittest.TestCase):
    """连接测试（无效 URL 应取 false）"""

    def test_invalid_url_returns_false(self):
        ok = test_connection("http://127.0.0.1:19999/nonexist")
        self.assertFalse(ok)

    def test_empty_url_returns_false(self):
        ok = test_connection("")
        self.assertFalse(ok)


class TestSyncIntegration(unittest.TestCase):
    """模拟 WebDAV 同步的端到端流程（mock client）"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.data = os.path.join(self.tmp, "data")
        os.makedirs(self.data)
        self.remote = os.path.join(self.tmp, "remote")
        os.makedirs(self.remote)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, d, path, content="test"):
        p = os.path.join(d, path)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(content)

    def test_full_incremental_cycle(self):
        """模拟：第一次全量同步 → 修改一个 → 第二次只有修改"""
        from unittest.mock import patch, MagicMock
        from webdav_sync import sync_to_webdav

        # Mock webdav client
        mock_client = MagicMock()
        mock_client.check.return_value = True

        with patch("webdav_sync._make_client", return_value=mock_client):
            # 第一次：新增 3 个文件
            self._write(self.data, "a.txt", "hello")
            self._write(self.data, "b.txt", "world")
            self._write(self.data, "sub/c.txt", "nested")

            result = sync_to_webdav(self.data, "http://mock.local/")
            self.assertEqual(result["added"], 3)
            self.assertEqual(result["modified"], 0)
            self.assertEqual(result["deleted"], 0)

            # 第二次：修改 b.txt，删除 a.txt
            self._write(self.data, "b.txt", "world-modified")
            os.remove(os.path.join(self.data, "a.txt"))

            result = sync_to_webdav(self.data, "http://mock.local/")
            self.assertEqual(result["added"], 0)
            self.assertEqual(result["modified"], 1)
            self.assertEqual(result["deleted"], 1)

    def test_no_change_skips(self):
        from unittest.mock import patch, MagicMock
        from webdav_sync import sync_to_webdav

        mock_client = MagicMock()
        mock_client.check.return_value = True

        with patch("webdav_sync._make_client", return_value=mock_client):
            self._write(self.data, "a.txt", "hello")
            sync_to_webdav(self.data, "http://mock.local/")
            result = sync_to_webdav(self.data, "http://mock.local/")
            self.assertEqual(result["added"], 0)
            self.assertEqual(result["modified"], 0)
            self.assertEqual(result["deleted"], 0)

    def test_empty_url_returns_error(self):
        from webdav_sync import sync_to_webdav
        result = sync_to_webdav(self.data, "")
        self.assertIn("error", result)


class TestRestore(unittest.TestCase):
    """恢复功能测试"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.data = os.path.join(self.tmp, "data")
        os.makedirs(self.data)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_restore_invalid_url(self):
        from webdav_sync import restore_from_webdav
        ok = restore_from_webdav(self.data, "http://127.0.0.1:1/")
        self.assertFalse(ok)

    def test_restore_empty_url(self):
        from webdav_sync import restore_from_webdav
        ok = restore_from_webdav(self.data, "")
        self.assertFalse(ok)

    def test_restore_mock_downloads_all(self):
        from unittest.mock import patch, MagicMock
        from webdav_sync import restore_from_webdav

        mock_client = MagicMock()
        mock_client.list.return_value = ["a.txt", "sub/b.txt"]

        with patch("webdav_sync._make_client", return_value=mock_client):
            ok = restore_from_webdav(self.data, "http://mock.local/")
            self.assertTrue(ok)
            self.assertEqual(mock_client.download_sync.call_count, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
