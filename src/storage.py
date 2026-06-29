# -*- coding: utf-8 -*-
"""存储抽象 — Protocol 定义 load/save 接口，InvoiceRepository 和 Database 均实现"""

from typing import Protocol
from models import Invoice


class InvoiceStorage(Protocol):
    """发票存储接口：任何实现 load/save/data_file 的类型均可作为存储后端"""

    def load(self) -> list[Invoice]:
        """加载全部发票记录"""
        ...

    def save(self, invoices: list[Invoice]) -> None:
        """保存全部发票记录"""
        ...

    @property
    def data_file(self) -> str:
        """返回存储文件路径（供备份等模块使用）"""
        ...
