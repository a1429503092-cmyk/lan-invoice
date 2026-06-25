# -*- coding: utf-8 -*-
"""发票数据模型 — dataclass 替代裸 dict，提供类型安全和序列化"""

from dataclasses import dataclass, field


@dataclass
class Invoice:
    """单张发票的完整数据"""
    file: str = ""
    pdf_path: str = ""
    company: str = ""
    invoice_type: str = ""
    buyer_name: str = ""
    buyer_tax_id: str = ""
    seller_name: str = ""
    amount: str = ""
    tax_rate: str = ""
    tax_amount: str = ""
    total: str = ""
    invoice_no: str = ""
    invoice_date: str = ""
    is_red: bool = False
    tags: dict[str, str] = field(default_factory=dict)
    attachments: list[str] = field(default_factory=list)
    remark: str = ""
    error: str = ""

    # ── 序列化 ────────────────────────────────

    def to_dict(self) -> dict:
        """转为可 JSON 序列化的 dict"""
        return {
            "file": self.file,
            "pdf_path": self.pdf_path,
            "company": self.company,
            "invoice_type": self.invoice_type,
            "buyer_name": self.buyer_name,
            "buyer_tax_id": self.buyer_tax_id,
            "seller_name": self.seller_name,
            "amount": self.amount,
            "tax_rate": self.tax_rate,
            "tax_amount": self.tax_amount,
            "total": self.total,
            "invoice_no": self.invoice_no,
            "invoice_date": self.invoice_date,
            "is_red": self.is_red,
            "tags": dict(self.tags),
            "attachments": list(self.attachments),
            "remark": self.remark,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Invoice":
        """从 dict 创建实例，兼容旧数据缺失字段"""
        # 兼容旧数据：screenshots/contracts 合并到 attachments
        atts = list(d.get("attachments", []))
        for old_field in ("screenshots", "contracts"):
            for p in d.get(old_field, []):
                if p and p not in atts:
                    atts.append(p)
        return cls(
            file=d.get("file", ""),
            pdf_path=d.get("pdf_path", ""),
            company=d.get("company", ""),
            invoice_type=d.get("invoice_type", ""),
            buyer_name=d.get("buyer_name", ""),
            buyer_tax_id=d.get("buyer_tax_id", ""),
            seller_name=d.get("seller_name", ""),
            amount=str(d.get("amount", "")),
            tax_rate=str(d.get("tax_rate", "")),
            tax_amount=str(d.get("tax_amount", "")),
            total=str(d.get("total", "")),
            invoice_no=d.get("invoice_no", ""),
            invoice_date=d.get("invoice_date", ""),
            is_red=bool(d.get("is_red", False)),
            tags=dict(d.get("tags", {})),
            attachments=atts,
            remark=d.get("remark", ""),
            error=d.get("error", ""),
        )

    def ensure_defaults(self):
        """初始化缺失字段的默认值；红票金额转负数"""
        if self.is_red:
            for attr in ("amount", "tax_amount", "total"):
                v = getattr(self, attr)
                if v and not str(v).startswith('-'):
                    setattr(self, attr, '-' + str(v))

    # ── 字典兼容（允许旧代码渐进迁移）──────────

    def get(self, key: str, default=None):
        """dict-style get，兼容旧代码"""
        return getattr(self, key, default)

    def setdefault(self, key: str, default=None):
        """dict-style setdefault：键不存在时设默认值"""
        if not hasattr(self, key) or getattr(self, key) in (None, "", []):
            setattr(self, key, default)
        return getattr(self, key)

    def __getitem__(self, key: str):
        return getattr(self, key)

    def __setitem__(self, key: str, value):
        setattr(self, key, value)

    def __contains__(self, key: str) -> bool:
        return hasattr(self, key)
