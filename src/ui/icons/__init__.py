# -*- coding: utf-8 -*-
"""统一图标资源 — 加载 PNG 图标为 QIcon"""

import os
from PyQt5.QtGui import QIcon

_ICON_DIR = os.path.dirname(__file__)
_cache = {}


def _load(name: str) -> QIcon:
    if name not in _cache:
        path = os.path.join(_ICON_DIR, f"{name}.png")
        if os.path.exists(path):
            _cache[name] = QIcon(path)
        else:
            _cache[name] = QIcon()
    return _cache[name]


def get(name: str) -> QIcon:
    """按名称获取图标: folder, delete, settings, export, search,
       camera, document, save, package, warning, check, add,
       clipboard, arrow_left, arrow_right, dot_red, dot_blue,
       note, paperclip, clear"""
    return _load(name)


# 常用图标快捷访问
ICON_OPEN      = property(lambda s: _load('folder'))
ICON_DELETE    = property(lambda s: _load('delete'))
ICON_SETTINGS  = property(lambda s: _load('settings'))
ICON_EXPORT    = property(lambda s: _load('export'))
ICON_SEARCH    = property(lambda s: _load('search'))
ICON_CAMERA    = property(lambda s: _load('camera'))
ICON_DOCUMENT  = property(lambda s: _load('document'))
ICON_SAVE      = property(lambda s: _load('save'))
ICON_PACKAGE   = property(lambda s: _load('package'))
ICON_WARNING   = property(lambda s: _load('warning'))
ICON_CHECK     = property(lambda s: _load('check'))
ICON_ADD       = property(lambda s: _load('add'))
ICON_CLIPBOARD = property(lambda s: _load('clipboard'))
ICON_PREV      = property(lambda s: _load('arrow_left'))
ICON_NEXT      = property(lambda s: _load('arrow_right'))
ICON_RED       = property(lambda s: _load('dot_red'))
ICON_BLUE      = property(lambda s: _load('dot_blue'))
ICON_NOTE      = property(lambda s: _load('note'))
ICON_ATTACH    = property(lambda s: _load('paperclip'))
ICON_CLEAR     = property(lambda s: _load('clear'))
