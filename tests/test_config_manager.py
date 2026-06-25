# -*- coding: utf-8 -*-
"""config_manager 模块单元测试"""
import sys, os, json, unittest, tempfile, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from config_manager import ConfigManager


class TestConfigManager(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.config_path = os.path.join(self.tmp, "config.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_load_defaults_when_no_file(self):
        mgr = ConfigManager(self.config_path)
        self.assertEqual(mgr.data_dir, "")
        self.assertEqual(mgr.tag_templates, ["企业号"])

    def test_load_data_dir(self):
        mgr = ConfigManager(self.config_path)
        mgr.data_dir = os.path.join(self.tmp, "mydata")
        mgr.save()
        mgr2 = ConfigManager(self.config_path)
        self.assertEqual(mgr2.data_dir, os.path.join(self.tmp, "mydata"))

    def test_load_tag_templates(self):
        mgr = ConfigManager(self.config_path)
        mgr.tag_templates = ["企业号", "项目名称", "部门"]
        mgr.save()
        mgr2 = ConfigManager(self.config_path)
        self.assertEqual(mgr2.tag_templates, ["企业号", "项目名称", "部门"])

    def test_save_and_load_roundtrip(self):
        mgr = ConfigManager(self.config_path)
        mgr.data_dir = "/test/dir"
        mgr.tag_templates = ["A", "B"]
        mgr.save()
        with open(self.config_path) as f:
            raw = json.load(f)
        self.assertEqual(raw["data_dir"], "/test/dir")
        self.assertEqual(raw["tag_templates"], ["A", "B"])

    def test_save_preserves_unknown_keys(self):
        with open(self.config_path, "w") as f:
            json.dump({"data_dir": "/old", "tag_templates": ["X"],
                       "custom_key": "keep_me"}, f)
        mgr = ConfigManager(self.config_path)
        mgr.save()
        with open(self.config_path) as f:
            raw = json.load(f)
        self.assertEqual(raw["custom_key"], "keep_me")

    def test_creates_parent_dir(self):
        p = os.path.join(self.tmp, "subdir", "cfg.json")
        mgr = ConfigManager(p)
        mgr.save()
        self.assertTrue(os.path.exists(p))

    def test_corrupted_config_falls_back_to_defaults(self):
        with open(self.config_path, "w") as f:
            f.write("not json")
        mgr = ConfigManager(self.config_path)
        self.assertEqual(mgr.tag_templates, ["企业号"])
        self.assertEqual(mgr.data_dir, "")

    def test_path_property(self):
        mgr = ConfigManager(self.config_path)
        self.assertEqual(mgr.path, self.config_path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
