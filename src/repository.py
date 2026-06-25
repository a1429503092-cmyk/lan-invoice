# -*- coding: utf-8 -*-
"""发票数据仓库 — JSON 文件持久化，与 UI 完全解耦"""

import json
import os
from models import Invoice
from logger import getLogger

log = getLogger(__name__)


class InvoiceRepository:
    """管理发票数据的 JSON 存储"""

    def __init__(self, data_file: str):
        self._data_file = data_file

    @property
    def data_file(self) -> str:
        return self._data_file

    def load(self) -> list[Invoice]:
        """加载全部发票记录；文件不存在或损坏时返回空列表。自动迁移旧格式。"""
        if not os.path.exists(self._data_file):
            log.debug("数据文件不存在，返回空列表: %s", self._data_file)
            return []
        try:
            with open(self._data_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if not isinstance(raw, list):
                log.warning("数据文件格式异常(非列表): %s", self._data_file)
                return []
            invoices = [Invoice.from_dict(d) for d in raw]
            # 旧格式迁移
            if self._needs_migration(invoices):
                invoices = self._migrate(invoices)
                self.save(invoices)
            log.info("数据加载完成: %s | %d 条记录", self._data_file, len(invoices))
            return invoices
        except (OSError, json.JSONDecodeError) as e:
            log.error("数据文件加载失败: %s | %s", self._data_file, e)
            return []

    def _needs_migration(self, invoices: list[Invoice]) -> bool:
        """检测是否有旧格式数据需要迁移（company→tags）"""
        for inv in invoices:
            if inv.company and "企业号" not in (inv.tags or {}):
                return True
        return False

    def _migrate(self, invoices: list[Invoice]) -> list[Invoice]:
        """执行旧格式到新格式的迁移：company→tags"""
        for inv in invoices:
            if inv.company and "企业号" not in (inv.tags or {}):
                if not inv.tags:
                    inv.tags = {}
                inv.tags["企业号"] = inv.company
        log.info("旧数据迁移完成: %d 条记录", len(invoices))
        return invoices

    def save(self, invoices: list[Invoice]) -> None:
        """保存全部发票记录"""
        os.makedirs(os.path.dirname(self._data_file), exist_ok=True)
        with open(self._data_file, "w", encoding="utf-8") as f:
            json.dump([inv.to_dict() for inv in invoices], f,
                      ensure_ascii=False, indent=2)
        log.debug("数据已保存: %d 条 → %s", len(invoices), self._data_file)
