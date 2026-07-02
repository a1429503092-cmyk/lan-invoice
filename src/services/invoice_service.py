# -*- coding: utf-8 -*-
"""业务服务层 — 发票 CRUD、搜索、导出、标签管理，依赖 Repository/Backup/Config"""

import os
import re
import json
import shutil
from datetime import datetime
from models import Invoice
from storage import InvoiceStorage
from logger import getLogger

log = getLogger(__name__)

VALID_SORT_FIELDS = {"amount", "tax_rate", "tax_amount", "total",
                     "invoice_no", "invoice_date", "invoice_type",
                     "buyer_name", "seller_name", "file"}


class InvoiceService:
    """发票业务编排：CRUD、搜索、导出、附件、标签，统一写后备份"""

    def __init__(self, db: InvoiceStorage, backup, config,
                 data_dir: str, invoice_dir: str):
        self._db = db
        self._backup = backup      # BackupService
        self._config = config      # ConfigManager
        self._data_dir = data_dir
        self._invoice_dir = invoice_dir
        self._webdav_enabled = False  # MCP 模式关，GUI 模式开
        os.makedirs(data_dir, exist_ok=True)
        os.makedirs(invoice_dir, exist_ok=True)

    def enable_webdav_sync(self, enabled: bool = True):
        self._webdav_enabled = enabled

    # ── 存取 ──────────────────────────────────

    def load_all(self) -> list[Invoice]:
        return self._db.load()

    def save_all(self, invoices: list[Invoice]) -> None:
        self._db.save(invoices)

    def find_by_invoice_no(self, invoices: list[Invoice], inv_no: str) -> int | None:
        if not inv_no:
            return None
        for i, inv in enumerate(invoices):
            if inv.invoice_no == inv_no:
                return i
        return None

    # ── 写后操作 ──────────────────────────────

    def _post_write(self):
        """每次写操作后：优化 → 备份 → 清理 → 可选 WebDAV 同步"""
        strategy = self._config.get_local_strategy()
        if not strategy["enabled"]:
            return
        self._db.optimize()
        try:
            self._backup.backup(self._db.data_file)
            self._backup.cleanup(keep_days=strategy["retention_days"],
                                 min_keep=strategy["min_keep"],
                                 max_keep=strategy["max_keep"])
        except OSError as e:
            log.warning("备份失败（数据已保存）: %s", e)
        # WebDAV 仅 GUI 模式（避免阻塞 MCP stdio）
        if self._webdav_enabled:
            self._sync_webdav()

    def _sync_webdav(self):
        webdav_s = self._config.get_webdav_strategy()
        if not webdav_s["enabled"] or not webdav_s["url"]:
            return
        from PyQt5.QtCore import QThread
        from webdav_sync import sync_to_webdav
        url = webdav_s["url"]
        user = webdav_s["username"]
        pw = webdav_s["password"]
        data_dir = self._data_dir

        vm = webdav_s["version_mode"]
        mv = webdav_s["max_versions"]

        def run():
            try:
                result = sync_to_webdav(data_dir, url, user, pw,
                                        version_mode=vm, max_versions=mv)
                if result.get("failed", 0) > 0:
                    log.warning("WebDAV 同步部分失败: %s", result)
            except Exception as e:
                log.warning("WebDAV 同步失败: %s", e)

        class _SyncThread(QThread):
            def run(self):
                run()
        _SyncThread().start()

    # ── 搜索 ──────────────────────────────────

    def search(self, **kwargs) -> dict:
        from filters import record_matches_filter
        from utils import safe_float
        invs = self._db.load()
        keyword = (kwargs.get("keyword") or "").lower()

        filtered = []
        for inv in invs:
            if not record_matches_filter(inv, kwargs.get("year"), kwargs.get("month"),
                                         kwargs.get("invoice_type"), kwargs.get("seller"),
                                         kwargs.get("buyer", ""), kwargs.get("tag", "")):
                continue
            if keyword:
                full = json.dumps(self._inv_dict(inv), ensure_ascii=False).lower()
                if keyword not in full:
                    continue
            filtered.append(self._inv_dict(inv))

        sort_by = kwargs.get("sort_by")
        if sort_by:
            if sort_by not in VALID_SORT_FIELDS:
                raise ValueError(f"不支持的排序字段: {sort_by}")
            asc = kwargs.get("sort_asc", True)
            numeric = sort_by in ("amount", "tax_rate", "tax_amount", "total")
            if numeric:
                filtered.sort(key=lambda x: safe_float(str(x.get(sort_by, ""))),
                              reverse=not asc)
            else:
                filtered.sort(key=lambda x: str(x.get(sort_by, "")).lower(),
                              reverse=not asc)

        limit = kwargs.get("limit", 50)
        offset = kwargs.get("offset", 0)
        page = filtered[offset:offset + limit]

        return {
            "count": len(filtered),
            "returned": len(page),
            "total_amount": sum(safe_float(r.get("amount")) for r in filtered),
            "total_tax": sum(safe_float(r.get("tax_amount")) for r in filtered),
            "total_with_tax": sum(safe_float(r.get("total")) for r in filtered),
            "records": page,
        }

    # ── 导入 ──────────────────────────────────

    def import_invoice(self, pdf_path: str, tags: dict | None = None,
                       remark: str | None = None) -> dict:
        from invoice_parser import parse_invoice_pdf
        from utils import copy_file_to_dir

        if not pdf_path or not os.path.exists(pdf_path):
            return {"error": f"文件不存在: {pdf_path}"}
        if not pdf_path.lower().endswith(".pdf"):
            return {"error": "仅支持 PDF 文件"}

        result = parse_invoice_pdf(pdf_path)
        if result.get("error"):
            return {"parsed": result, "status": "parse_error"}

        inv = Invoice.from_dict(result)
        inv.ensure_defaults()

        if tags:
            if not inv.tags:
                inv.tags = {}
            for k, v in tags.items():
                inv.tags[k] = str(v) if v else ""
        if remark is not None:
            inv.remark = str(remark)

        if inv.invoice_no and self._db.find_by_invoice_no(inv.invoice_no):
            return {"status": "duplicate", "invoice_no": inv.invoice_no,
                    "message": f"发票号 {inv.invoice_no} 已存在"}

        dst_dir = os.path.join(self._data_dir, "invoices")
        os.makedirs(dst_dir, exist_ok=True)
        copied = copy_file_to_dir(pdf_path, dst_dir)
        if copied == pdf_path:
            return {"error": "PDF 文件复制失败，磁盘可能已满或无写入权限"}
        inv.pdf_path = copied

        existing = self._db.load()
        existing.append(inv)
        self._db.save(existing)
        self._post_write()
        return {"status": "ok", "invoice": self._inv_dict(inv)}

    # ── 导出 Excel ────────────────────────────

    def export_excel(self, output_path: str = "", **filters) -> dict:
        from services.export_service import ExportService
        from filters import record_matches_filter

        if not output_path:
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            output_path = os.path.join(desktop,
                f"发票导出_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
        out_dir = os.path.dirname(output_path)
        if out_dir and not os.path.isdir(out_dir):
            return {"error": f"目录不存在: {out_dir}"}

        invs = self._db.load()
        year = filters.get("year")
        month = filters.get("month")
        inv_type = filters.get("invoice_type")
        seller = filters.get("seller")
        if any([year, month, inv_type, seller]):
            invs = [i for i in invs if record_matches_filter(
                i, year, month, inv_type, seller, "", "")]
        svc = ExportService()
        svc.export(invs, output_path, tag_columns=self._config.tag_templates)
        return {"status": "ok", "path": output_path}

    # ── 统计摘要 ──────────────────────────────

    def get_summary(self, **filters) -> dict:
        from filters import record_matches_filter
        from utils import safe_float
        invs = self._db.load()
        year = filters.get("year")
        month = filters.get("month")
        if year or month:
            invs = [i for i in invs if record_matches_filter(
                i, year, month, None, None, "", "")]

        types = {}
        for inv in invs:
            t = inv.invoice_type or "未知"
            types[t] = types.get(t, 0) + 1

        return {
            "count": len(invs),
            "total_amount": sum(safe_float(i.amount) for i in invs) or 0.0,
            "total_tax": sum(safe_float(i.tax_amount) for i in invs) or 0.0,
            "total_with_tax": sum(safe_float(i.total) for i in invs) or 0.0,
            "by_type": types,
        }

    # ── 标签管理 ──────────────────────────────

    def manage_tags(self, action: str, tag_name: str = "") -> dict:
        templates = self._config.tag_templates
        if action == "list":
            return {"tags": templates}
        if action not in ("add", "delete"):
            return {"error": f"未知操作: {action}"}
        name = tag_name.strip()
        if not name:
            return {"error": "tag_name 不能为空"}
        if action == "add":
            if name in templates:
                return {"tags": templates, "message": f"标签「{name}」已存在"}
            templates.append(name)
            self._config.tag_templates = templates
            self._config.save()
            return {"tags": templates, "message": f"已添加标签「{name}」"}
        if action == "delete":
            if name not in templates:
                return {"tags": templates, "message": f"标签「{name}」不存在"}
            templates.remove(name)
            self._config.tag_templates = templates
            self._config.save()
            return {"tags": templates, "message": f"已删除标签「{name}」"}
        return {"error": "内部错误"}

    # ── 更新 ──────────────────────────────────

    def update_invoice(self, invoice_no: str, tags: dict | None = None,
                       remark: str | None = None) -> dict:
        if not self._db.find_by_invoice_no(invoice_no):
            return {"error": f"未找到发票号 {invoice_no}"}
        invs = self._db.load()
        target = next((i for i in invs if i.invoice_no == invoice_no), None)
        if not target:
            return {"error": f"未找到发票号 {invoice_no}"}

        changed = []
        if tags:
            if not target.tags:
                target.tags = {}
            for k, v in tags.items():
                target.tags[k] = str(v) if v else ""
            changed.append("tags")
        if remark is not None:
            target.remark = str(remark)
            changed.append("remark")

        if not changed:
            return {"message": "无变更", "invoice": self._inv_dict(target)}
        self._db.save(invs)
        self._post_write()
        return {"status": "ok", "changed": changed, "invoice": self._inv_dict(target)}

    # ── 附件（通用，GUI 使用）──────────────────

    def add_attachments(self, inv: Invoice, src_paths: list[str],
                        field: str, target_dir: str, make_filename) -> int:
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

    # ── 附件（MCP，发票号查找）─────────────────

    def attach_files(self, invoice_no: str, file_paths: list[str]) -> dict:
        """MCP 附件添加：按发票号查找记录并复制文件"""
        if not file_paths:
            return {"error": "缺少必填参数: file_paths"}
        invs = self._db.load()
        target = None
        for inv in invs:
            if inv.invoice_no == invoice_no:
                target = inv
                break
        if not target:
            return {"error": f"未找到发票号 {invoice_no}"}

        valid = [p for p in file_paths if os.path.isfile(p)]
        if not valid:
            return {"error": "没有有效的文件"}

        inv_no_safe = re.sub(r'[\\/:*?"<>|]', '_', invoice_no)
        count = 0
        for src in valid:
            dst = os.path.join(self._data_dir, self._attachment_namer(src, inv_no_safe))
            try:
                shutil.copy2(src, dst)
                if not target.attachments:
                    target.attachments = []
                target.attachments.append(dst)
                count += 1
            except OSError:
                continue

        if count:
            self._db.save(invs)
            self._post_write()
        return {"status": "ok", "added": count,
                "total_attachments": len(target.attachments or [])}

    # ── 删除 ──────────────────────────────────

    def delete_invoice(self, invoice_no: str) -> dict:
        invs = self._db.load()
        target = None
        for inv in invs:
            if inv.invoice_no == invoice_no:
                target = inv
                break
        if not target:
            return {"error": f"未找到发票号 {invoice_no}"}
        invs.remove(target)
        self._db.save(invs)
        del_count, _ = self.delete_invoice_files(target)
        if del_count:
            log.debug("已清理 %d 个关联文件 (发票=%s)", del_count, invoice_no)
        self._post_write()
        return {"status": "ok", "deleted": invoice_no}

    # ── 附件工具 ──────────────────────────────

    @staticmethod
    def _attachment_namer(src: str, safe_name: str) -> str:
        ext = os.path.splitext(src)[1].lower() or ".dat"
        orig_base = os.path.splitext(os.path.basename(src))[0]
        ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
        return f"{safe_name}_{orig_base}_{ts}{ext}"

    namer = _attachment_namer  # backward-compatible alias

    @staticmethod
    def _inv_dict(inv: Invoice) -> dict:
        d = inv.to_dict()
        d.pop("company", None)
        return d

    # ── 文件 ──────────────────────────────────

    def copy_invoice_pdf(self, src: str) -> str:
        from utils import copy_file_to_dir
        return copy_file_to_dir(src, self._invoice_dir)

    @staticmethod
    def delete_invoice_files(inv: Invoice) -> tuple[int, list[str]]:
        """删除发票关联的所有文件：PDF + 附件。返回 (成功数, 失败列表)"""
        deleted = 0
        failed = []
        # 删除 PDF
        for path in ([inv.pdf_path] if inv.pdf_path else []):
            if os.path.isfile(path):
                try:
                    os.remove(path)
                    deleted += 1
                except OSError as e:
                    failed.append(f"pdf:{os.path.basename(path)}：{e}")
        # 删除附件（截图、合同、文档等）
        for path in (inv.attachments or []):
            if os.path.isfile(path):
                try:
                    os.remove(path)
                    deleted += 1
                except OSError as e:
                    failed.append(f"附件:{os.path.basename(path)}：{e}")
        return deleted, failed

    # ── 初始化辅助 ────────────────────────────

    @staticmethod
    def init_record(inv: Invoice, company: str = ""):
        if company:
            inv.company = company
        inv.ensure_defaults()

    @staticmethod
    def make_error_record(pdf_path: str, error_msg: str) -> Invoice:
        return Invoice(pdf_path=pdf_path, error=error_msg)
