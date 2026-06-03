# -*- coding: utf-8 -*-
"""ui.icons 模块单元测试"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from PyQt5.QtWidgets import QApplication

_app = QApplication.instance()
if _app is None:
    _app = QApplication(sys.argv)


# 导入前清理缓存，确保测试隔离
import ui.icons as _icons_mod


class TestIconLoading(unittest.TestCase):

    def setUp(self):
        self._saved_cache = dict(_icons_mod._cache)
        _icons_mod._cache.clear()

    def tearDown(self):
        _icons_mod._cache.clear()
        _icons_mod._cache.update(self._saved_cache)

    def test_load_existing_icon_returns_qicon(self):
        """加载存在的图标返回有效 QIcon"""
        from PyQt5.QtGui import QIcon
        icon = _icons_mod._load('folder')
        self.assertIsInstance(icon, QIcon)
        self.assertFalse(icon.isNull())

    def test_load_nonexistent_icon_returns_empty_qicon(self):
        """加载不存在的图标返回空 QIcon（不崩溃）"""
        from PyQt5.QtGui import QIcon
        icon = _icons_mod._load('__nonexistent_icon_name__')
        self.assertIsInstance(icon, QIcon)
        self.assertTrue(icon.isNull())

    def test_load_caches_result(self):
        """第二次请求同一图标走缓存"""
        icon1 = _icons_mod._load('folder')
        icon2 = _icons_mod._load('folder')
        self.assertIs(icon1, icon2)

    def test_get_returns_same_as_load(self):
        """get() 和 _load() 返回相同结果"""
        self.assertIs(
            _icons_mod.get('folder'),
            _icons_mod._load('folder'),
        )

    def test_load_nonexistent_also_cached(self):
        """缺失图标的结果也会被缓存（不会重复检查文件）"""
        _icons_mod._load('__nonexistent__')
        self.assertIn('__nonexistent__', _icons_mod._cache)


class TestIconProperties(unittest.TestCase):

    def setUp(self):
        self._saved_cache = dict(_icons_mod._cache)
        _icons_mod._cache.clear()

    def tearDown(self):
        _icons_mod._cache.clear()
        _icons_mod._cache.update(self._saved_cache)

    def test_all_predefined_icon_names_load(self):
        """所有预定义快捷属性都对应有效图标文件"""
        names = ['folder', 'delete', 'settings', 'export', 'search',
                 'camera', 'document', 'save', 'package', 'warning',
                 'check', 'add', 'clipboard', 'arrow_left', 'arrow_right',
                 'dot_red', 'dot_blue', 'note', 'paperclip', 'clear']
        from PyQt5.QtGui import QIcon
        for name in names:
            icon = _icons_mod.get(name)
            self.assertIsInstance(icon, QIcon, f"get('{name}') should return QIcon")
            self.assertFalse(icon.isNull(), f"get('{name}') should not be null")


if __name__ == "__main__":
    unittest.main(verbosity=2)
