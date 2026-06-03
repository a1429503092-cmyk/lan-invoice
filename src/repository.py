# -*- coding: utf-8 -*-
"""发票数据仓库 — JSON 文件持久化，与 UI 完全解耦"""

import json
import os
from models import Invoice


class InvoiceRepository:
    """管理发票数据的 JSON 存储"""

    def __init__(self, data_file: str):
        self._data_file = data_file

    @property
    def data_file(self) -> str:
        return self._data_file

    def load(self) -> list[Invoice]:
        """加载全部发票记录；文件不存在或损坏时返回空列表"""
        if not os.path.exists(self._data_file):
            return []
        try:
            with open(self._data_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if not isinstance(raw, list):
                return []
            return [Invoice.from_dict(d) for d in raw]
        except (OSError, json.JSONDecodeError):
            return []

    def save(self, invoices: list[Invoice]) -> None:
        """保存全部发票记录"""
        os.makedirs(os.path.dirname(self._data_file), exist_ok=True)
        with open(self._data_file, "w", encoding="utf-8") as f:
            json.dump([inv.to_dict() for inv in invoices], f,
                      ensure_ascii=False, indent=2)
