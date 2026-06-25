# -*- coding: utf-8 -*-
"""配置管理 — 数据目录、标签模板等持久化配置"""

import json
import os

from logger import getLogger

log = getLogger(__name__)


class ConfigManager:
    """读写 config.json，管理数据目录和标签模板等持久化设置"""

    def __init__(self, config_path: str):
        self._path = config_path
        self._data: dict = {}
        self._load()

    # ── 读取 ──────────────────────────────────

    def _load(self):
        if not os.path.exists(self._path):
            self._data = {}
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        except (OSError, json.JSONDecodeError):
            log.warning("配置文件损坏，使用默认值: %s", self._path)
            self._data = {}

    # ── 保存 ──────────────────────────────────

    def save(self):
        try:
            os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            log.error("配置保存失败: %s | %s", self._path, e)

    # ── 属性 ──────────────────────────────────

    @property
    def data_dir(self) -> str:
        return self._data.get("data_dir", "")

    @data_dir.setter
    def data_dir(self, value: str):
        self._data["data_dir"] = value

    @property
    def tag_templates(self) -> list[str]:
        return self._data.get("tag_templates", ["企业号"])

    @tag_templates.setter
    def tag_templates(self, value: list[str]):
        self._data["tag_templates"] = list(value)

    @property
    def path(self) -> str:
        return self._path
