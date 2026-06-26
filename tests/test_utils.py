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

    def test_md5_dedup_reuses_existing(self):
        """相同内容文件 → MD5 去重，复用已有文件"""
        src = os.path.join(self.tmp_src, "a.txt")
        with open(src, "w") as f:
            f.write("hello")
        r1 = copy_file_to_dir(src, self.tmp_dst)
        r2 = copy_file_to_dir(src, self.tmp_dst)
        self.assertEqual(r1, r2)

    def test_different_content_same_name_renames(self):
        """同名不同内容 → 重命名避免覆盖"""
        src = os.path.join(self.tmp_src, "dup.txt")
        with open(src, "w") as f:
            f.write("content_a")
        r1 = copy_file_to_dir(src, self.tmp_dst)
        # 手动放一个同名不同内容的文件
        with open(os.path.join(self.tmp_dst, "dup.txt"), "w") as f:
            f.write("content_b_different")
        # 现在 src 的 MD5 ≠ dst/dup.txt 的 MD5，且名字冲突 → 重命名
        r2 = copy_file_to_dir(src, self.tmp_dst)
        self.assertNotEqual(r2, os.path.join(self.tmp_dst, "dup.txt"))
        self.assertIn("dup_", os.path.basename(r2))

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

    def test_md5_dedup_three_identical_copies(self):
        """三个相同内容 → MD5 去重，全部返回同一文件"""
        src = os.path.join(self.tmp_src, "file.txt")
        with open(src, "w") as f:
            f.write("same_data")
        r1 = copy_file_to_dir(src, self.tmp_dst)
        r2 = copy_file_to_dir(src, self.tmp_dst)
        r3 = copy_file_to_dir(src, self.tmp_dst)
        self.assertEqual(r1, r2)
        self.assertEqual(r2, r3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
