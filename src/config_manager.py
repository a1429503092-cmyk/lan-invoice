# -*- coding: utf-8 -*-
"""配置管理 — 数据目录、备份策略、标签模板等持久化配置"""

import json
import os

from logger import getLogger

log = getLogger(__name__)

# ── 策略默认值 ─────────────────────────────────────

DEFAULT_LOCAL_STRATEGY = {
    "enabled": True,
    "trigger": "on_save",
    "interval_minutes": 30,
    "max_keep": 30,
    "retention_days": 30,
    "min_keep": 3,
}

DEFAULT_WEBDAV_STRATEGY = {
    "enabled": False,
    "trigger": "on_save",
    "interval_minutes": 60,
    "version_mode": "incremental",
    "max_versions": 10,
    "url": "",
    "username": "",
    "password": "",
}

class ConfigManager:
    """读写 config.json，管理数据目录、备份策略和标签模板等持久化设置"""

    def __init__(self, config_path: str):
        self._path = config_path
        self._data: dict = {}
        self._load()
        self._migrate()

    # ── 读写 ──────────────────────────────────

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

    def save(self):
        try:
            os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            log.error("配置保存失败: %s | %s", self._path, e)

    # ── 迁移 ──────────────────────────────────

    _CONFIG_VERSION = 1  # 当前配置格式版本

    def _migrate(self):
        """旧配置迁移 → 新策略结构，按版本号跳过已完成迁移"""
        version = self._data.get("config_version", 0)
        if version >= self._CONFIG_VERSION:
            return
        # v0 → v1: backup_enabled / webdav_* → backup_strategies
        if "backup_strategies" not in self._data:
            strategies = {}
            old_enabled = self._data.pop("backup_enabled", True)
            strategies["local"] = dict(DEFAULT_LOCAL_STRATEGY, enabled=old_enabled)
            wd_url = self._data.pop("webdav_url", "") or ""
            wd_enabled = bool(self._data.pop("webdav_enabled", False) or wd_url)
            strategies["webdav"] = dict(
                DEFAULT_WEBDAV_STRATEGY,
                enabled=wd_enabled,
                url=wd_url,
                username=self._data.pop("webdav_username", "") or "",
                password=self._data.pop("webdav_password", "") or "",
            )
            self._data["backup_strategies"] = strategies
            log.info("配置已迁移到策略结构: local=%s webdav=%s",
                     strategies["local"]["enabled"], strategies["webdav"]["enabled"])
        # 清理可能残留的旧字段
        for key in ("webdav_url", "webdav_username", "webdav_password",
                     "webdav_enabled", "backup_enabled"):
            self._data.pop(key, None)
        self._data["config_version"] = self._CONFIG_VERSION
        self.save()

    # ── 备份策略 ─────────────────────────────

    @property
    def backup_strategies(self) -> dict:
        return self._data.setdefault("backup_strategies", {
            "local": dict(DEFAULT_LOCAL_STRATEGY),
            "webdav": dict(DEFAULT_WEBDAV_STRATEGY),
        })

    def get_local_strategy(self) -> dict:
        s = self.backup_strategies.get("local", {})
        return dict(DEFAULT_LOCAL_STRATEGY, **s) if s else dict(DEFAULT_LOCAL_STRATEGY)

    def get_webdav_strategy(self) -> dict:
        s = self.backup_strategies.get("webdav", {})
        return dict(DEFAULT_WEBDAV_STRATEGY, **s) if s else dict(DEFAULT_WEBDAV_STRATEGY)

    def set_local_strategy(self, updates: dict):
        current = self.backup_strategies.setdefault("local", dict(DEFAULT_LOCAL_STRATEGY))
        current.update(updates)

    def set_webdav_strategy(self, updates: dict):
        current = self.backup_strategies.setdefault("webdav", dict(DEFAULT_WEBDAV_STRATEGY))
        current.update(updates)

    # ── 向后兼容只读属性 ─────────────────────

    @property
    def backup_enabled(self) -> bool:
        return self.get_local_strategy()["enabled"]

    @property
    def webdav_enabled(self) -> bool:
        s = self.get_webdav_strategy()
        return s["enabled"] and bool(s["url"])

    @property
    def webdav_url(self) -> str:
        return self.get_webdav_strategy()["url"]

    @property
    def webdav_username(self) -> str:
        return self.get_webdav_strategy()["username"]

    @property
    def webdav_password(self) -> str:
        return self.get_webdav_strategy()["password"]

    # ── 数据目录 ─────────────────────────────

    @property
    def skipped_version(self) -> str:
        return self._data.get("skipped_version", "")

    @skipped_version.setter
    def skipped_version(self, v: str):
        self._data["skipped_version"] = v

    @property
    def data_dir(self) -> str:
        return self._data.get("data_dir", "")

    @data_dir.setter
    def data_dir(self, value: str):
        self._data["data_dir"] = value

    # ── 标签模板 ─────────────────────────────

    @property
    def tag_templates(self) -> list[str]:
        return self._data.get("tag_templates", ["企业号"])

    @tag_templates.setter
    def tag_templates(self, value: list[str]):
        self._data["tag_templates"] = list(value)

    @property
    def path(self) -> str:
        return self._path
