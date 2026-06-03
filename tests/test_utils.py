# -*- coding: utf-8 -*-
"""utils 模块单元测试"""

import sys
import os
import unittest
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from utils import copy_file_to_dir


class TestCopyFileToDir(unittest.TestCase):
    def setUp(self):
        self.tmp_src = tempfile.mkdtemp()
        self.tmp_dst = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_src, ignore_errors=True)
        shutil.rmtree(self.tmp_dst, ignore_errors=True)

    def test_copy_success(self):
        src = os.path.join(self.tmp_src, "test.txt")
        with open(src, "w") as f:
            f.write("hello")
        result = copy_file_to_dir(src, self.tmp_dst)
        expected = os.path.join(self.tmp_dst, "test.txt")
        self.assertEqual(result, expected)
        self.assertTrue(os.path.exists(expected))

    def test_duplicate_rename(self):
        src = os.path.join(self.tmp_src, "test.txt")
        with open(src, "w") as f:
            f.write("hello")
        copy_file_to_dir(src, self.tmp_dst)
        result = copy_file_to_dir(src, self.tmp_dst)
        self.assertNotEqual(result, os.path.join(self.tmp_dst, "test.txt"))
        self.assertTrue(os.path.exists(result))
        self.assertIn("test_", os.path.basename(result))

    def test_nonexistent_src(self):
        result = copy_file_to_dir("/nonexistent/path.txt", self.tmp_dst)
        self.assertEqual(result, "/nonexistent/path.txt")

    def test_empty_src(self):
        result = copy_file_to_dir("", self.tmp_dst)
        self.assertEqual(result, "")

    def test_creates_dst_dir(self):
        dst_sub = os.path.join(self.tmp_dst, "new_subdir")
        src = os.path.join(self.tmp_src, "a.txt")
        with open(src, "w") as f:
            f.write("test")
        result = copy_file_to_dir(src, dst_sub)
        self.assertTrue(os.path.exists(result))
        self.assertTrue(os.path.isdir(dst_sub))

    def test_preserves_content(self):
        src = os.path.join(self.tmp_src, "data.bin")
        with open(src, "wb") as f:
            f.write(b"\x00\x01\x02\x03")
        dst = copy_file_to_dir(src, self.tmp_dst)
        with open(dst, "rb") as f:
            self.assertEqual(f.read(), b"\x00\x01\x02\x03")

    def test_copy_fallback_on_oserror(self):
        """shutil.copy2 失败时回退返回原路径"""
        src = os.path.join(self.tmp_src, "readonly.txt")
        with open(src, "w") as f:
            f.write("data")
        with unittest.mock.patch("shutil.copy2", side_effect=OSError("mock fail")):
            result = copy_file_to_dir(src, self.tmp_dst)
            self.assertEqual(result, src)

    def test_multiple_duplicates_increment(self):
        src = os.path.join(self.tmp_src, "file.txt")
        with open(src, "w") as f:
            f.write("data")
        r1 = copy_file_to_dir(src, self.tmp_dst)
        r2 = copy_file_to_dir(src, self.tmp_dst)
        r3 = copy_file_to_dir(src, self.tmp_dst)
        self.assertTrue(os.path.exists(r1))
        self.assertTrue(os.path.exists(r2))
        self.assertTrue(os.path.exists(r3))
        names = {os.path.basename(r) for r in [r1, r2, r3]}
        self.assertEqual(len(names), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
