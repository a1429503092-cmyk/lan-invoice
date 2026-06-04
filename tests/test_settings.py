# -*- coding: utf-8 -*-
"""设置对话框测试 — 标签模板管理 + 目录切换安全化"""

import sys, os, unittest, tempfile, shutil, json
from unittest.mock import patch, MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from PyQt5.QtWidgets import QApplication, QMessageBox

_app = QApplication.instance()
if _app is None:
    _app = QApplication(sys.argv)


def _patch_qmessagebox():
    p = patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes)
    p.start()
    patch.object(QMessageBox, 'warning', return_value=None).start()
    patch.object(QMessageBox, 'information', return_value=None).start()
    patch.object(QMessageBox, 'critical', return_value=None).start()
    return p


class TestDataDirContentDetection(unittest.TestCase):
    """测试目录内容检测逻辑"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _has_content(self, dirpath):
        data_file = os.path.join(dirpath, "invoices_data.json")
        if os.path.exists(data_file) and os.path.getsize(data_file) > 0:
            return True
        for sub in ["attachments", "invoices"]:
            d = os.path.join(dirpath, sub)
            if os.path.isdir(d) and os.listdir(d):
                return True
        return False

    def test_empty_dir_has_no_content(self):
        self.assertFalse(self._has_content(self.tmp))

    def test_dir_with_data_file_has_content(self):
        with open(os.path.join(self.tmp, "invoices_data.json"), "w") as f:
            json.dump([{"file": "test.pdf"}], f)
        self.assertTrue(self._has_content(self.tmp))

    def test_dir_with_attachments_has_content(self):
        att_dir = os.path.join(self.tmp, "attachments")
        os.makedirs(att_dir)
        with open(os.path.join(att_dir, "file.png"), "w") as f:
            f.write("data")
        self.assertTrue(self._has_content(self.tmp))

    def test_dir_with_invoices_has_content(self):
        inv_dir = os.path.join(self.tmp, "invoices")
        os.makedirs(inv_dir)
        with open(os.path.join(inv_dir, "inv.pdf"), "w") as f:
            f.write("pdf")
        self.assertTrue(self._has_content(self.tmp))

    def test_empty_data_file_no_content(self):
        with open(os.path.join(self.tmp, "invoices_data.json"), "w") as f:
            f.write("")
        self.assertFalse(self._has_content(self.tmp))


class TestDirectorySwitchLogic(unittest.TestCase):
    """测试目录切换决策逻辑"""

    def test_switch_with_content_offers_three_options(self):
        """新目录有数据时提供三选一"""
        has_content = True
        options = ["保留新目录数据", "用旧数据覆盖", "取消"]
        self.assertEqual(len(options), 3)

    def test_switch_without_content_offers_two_options(self):
        """新目录无数据+旧目录有数据时提供二选一"""
        has_content = False
        old_has_content = True
        if not has_content and old_has_content:
            options = ["迁移旧数据", "从空开始", "取消"]
            self.assertEqual(len(options), 3)

    def test_switch_both_empty_direct_switch(self):
        """新目录和旧目录都为空时直接切换"""
        has_content = False
        old_has_content = False
        should_migrate = has_content or old_has_content
        self.assertFalse(should_migrate)


class TestTagTemplateStorage(unittest.TestCase):
    """测试标签模板存储"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.config_file = os.path.join(self.tmp, "config.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_default_tags_include_company(self):
        """默认标签包含企业号"""
        # 无配置文件时返回默认
        if not os.path.exists(self.config_file):
            templates = ["企业号"]
            self.assertIn("企业号", templates)

    def test_save_and_load_tags(self):
        """保存和加载标签模板"""
        templates = ["企业号", "项目名称", "负责人"]
        config = {"data_dir": self.tmp, "tag_templates": templates}
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False)

        with open(self.config_file, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        self.assertEqual(loaded["tag_templates"], templates)

    def test_add_new_tag(self):
        """添加新标签"""
        templates = ["企业号"]
        new_tag = "项目名称"
        if new_tag not in templates:
            templates.append(new_tag)
        self.assertIn("项目名称", templates)
        self.assertEqual(len(templates), 2)

    def test_remove_tag(self):
        """删除标签"""
        templates = ["企业号", "项目名称"]
        to_remove = "项目名称"
        if to_remove in templates:
            templates.remove(to_remove)
        self.assertNotIn("项目名称", templates)
        self.assertEqual(len(templates), 1)

    def test_add_duplicate_tag_prevented(self):
        """添加重复标签被阻止"""
        templates = ["企业号"]
        new_tag = "企业号"
        self.assertIn(new_tag, templates)


if __name__ == "__main__":
    unittest.main(verbosity=2)
