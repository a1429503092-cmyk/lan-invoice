# -*- coding: utf-8 -*-
"""业务服务层 — 封装业务逻辑，依赖 Repository 而非 UI"""

import os
import re
import shutil
from datetime import datetime
from models import Invoice
from repository import InvoiceRepository


class InvoiceService:
    """发票业务编排：导入、删除、附件管理"""

    def __init__(self, repository: InvoiceRepository,
                 screenshot_dir: str, contract_dir: str, invoice_dir: str):
        self._repo = repository
        self._screenshot_dir = screenshot_dir
        self._contract_dir = contract_dir
        self._invoice_dir = invoice_dir
        os.makedirs(screenshot_dir, exist_ok=True)
        os.makedirs(contract_dir, exist_ok=True)
        os.makedirs(invoice_dir, exist_ok=True)

    # ── 数据存取 ────────────────────────────────

    def load_all(self) -> list[Invoice]:
        return self._repo.load()

    def save_all(self, invoices: list[Invoice]) -> None:
        self._repo.save(invoices)

    def find_by_invoice_no(self, invoices: list[Invoice], inv_no: str) -> int | None:
        """按发票号码查索引，返回 int 或 None"""
        if not inv_no:
            return None
        for i, inv in enumerate(invoices):
            if inv.invoice_no == inv_no:
                return i
        return None

    # ── 初始化 ──────────────────────────────────

    @staticmethod
    def init_record(inv: Invoice, company: str = ""):
        """初始化记录默认值；红票金额转负数"""
        if company:
            inv.company = company
        inv.ensure_defaults()

    @staticmethod
    def make_error_record(pdf_path: str, error_msg: str) -> Invoice:
        """构造解析失败的占位记录"""
        return Invoice(
            pdf_path=pdf_path,
            error=error_msg,
        )

    # ── 附件管理 ────────────────────────────────

    def add_attachments(self, inv: Invoice, src_paths: list[str],
                         field: str, target_dir: str,
                         make_filename) -> int:
        """通用附件添加，返回成功添加数"""
        inv_no = inv.invoice_no or inv.file or "unnamed"
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', inv_no)
        added = 0
        for src in src_paths:
            if not os.path.isfile(src):
                continue
            dst = os.path.join(target_dir, make_filename(src, safe_name))
            try:
                shutil.copy2(src, dst)
                getattr(inv, field).append(dst)
                added += 1
            except OSError:
                continue
        return added

    @staticmethod
    def screenshot_namer(src: str, safe_name: str) -> str:
        ext = os.path.splitext(src)[1].lower() or ".png"
        ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
        return f"{safe_name}_{ts}{ext}"

    @staticmethod
    def contract_namer(src: str, safe_name: str) -> str:
        ext = os.path.splitext(src)[1].lower()
        orig_base = os.path.splitext(os.path.basename(src))[0]
        ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
        return f"{safe_name}_{orig_base}_{ts}{ext}"

    def copy_invoice_pdf(self, src: str) -> str:
        """复制发票 PDF 到 data/invoices/"""
        from utils import copy_file_to_dir
        return copy_file_to_dir(src, self._invoice_dir)

    # ── 删除 ────────────────────────────────────

    @staticmethod
    def delete_invoice_files(inv: Invoice) -> tuple[int, list[str]]:
        """删除发票关联的 PDF 文件；返回 (成功数, 失败列表)"""
        deleted = 0
        failed = []
        path = inv.pdf_path
        if path and os.path.isfile(path):
            try:
                os.remove(path)
                deleted += 1
            except OSError as e:
                failed.append(f"{os.path.basename(path)}：{e}")
        return deleted, failed
