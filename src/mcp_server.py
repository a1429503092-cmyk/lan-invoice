# -*- coding: utf-8 -*-
"""MCP Server — stdio JSON-RPC 模式，将发票工具所有功能暴露给 AI 客户端"""

import sys
import os
import re
import json
import shutil
from datetime import datetime

from models import Invoice
from invoice_parser import parse_invoice_pdf
from filters import record_matches_filter
from database import Database
from backup import BackupService
from config_manager import ConfigManager
from utils import safe_float, copy_file_to_dir
from version import APP_VERSION

# Windows 下 stdout 默认非 UTF-8，包含中文内容时会崩溃
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

VALID_SORT_FIELDS = {"amount", "tax_rate", "tax_amount", "total",
                     "invoice_no", "invoice_date", "invoice_type",
                     "buyer_name", "seller_name", "file"}


class McpServer:
    """MCP stdio server: 读取 stdin JSON-RPC，写入 stdout"""

    def __init__(self):
        self._data_dir = self._init_data_dir()
        self._db = Database(os.path.join(self._data_dir, "invoices.db"))
        self._backup = BackupService()
        self._config = ConfigManager(os.path.join(
            os.environ.get("APPDATA", os.path.expanduser("~")),
            "lan-invoice", "config.json"
        ))
        self._tools = {
            "search_invoices": self._search_invoices,
            "import_invoice": self._import_invoice,
            "export_excel": self._export_excel,
            "get_summary": self._get_summary,
            "manage_tags": self._manage_tags,
            "update_invoice": self._update_invoice,
            "add_attachment": self._add_attachment,
            "delete_invoice": self._delete_invoice,
            "check_update": self._check_update,
        }

    # ── 初始化 ────────────────────────────────────

    def _init_data_dir(self):
        appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
        cfg_file = os.path.join(appdata, "lan-invoice", "config.json")
        try:
            with open(cfg_file, encoding="utf-8") as f:
                d = json.load(f).get("data_dir", "")
                if d and os.path.isdir(d):
                    return d
        except (OSError, json.JSONDecodeError):
            pass
        return os.path.join(appdata, "lan-invoice", "data")

    # ── MCP 协议 ──────────────────────────────────

    def run(self):
        for line in sys.stdin:
            try:
                req = json.loads(line.strip())
            except json.JSONDecodeError:
                sys.stdout.write(json.dumps({
                    "jsonrpc": "2.0", "id": None,
                    "error": {"code": -32700, "message": "Parse error"}
                }) + "\n")
                sys.stdout.flush()
                continue
            resp = self._handle(req)
            if resp is not None:
                sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
                sys.stdout.flush()

    def _handle(self, req: dict) -> dict | None:
        method = req.get("method", "")
        rid = req.get("id")

        if method == "initialize":
            return self._response(rid, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}, "resources": {}},
                "serverInfo": {"name": "invoice-tool", "version": APP_VERSION},
            })
        if method == "notifications/initialized":
            return None
        if method == "tools/list":
            return self._response(rid, {"tools": self._tool_defs()})
        if method == "tools/call":
            return self._response(rid, self._call_tool(req.get("params", {})))
        if method == "resources/list":
            return self._response(rid, {"resources": self._resource_defs()})
        if method == "resources/read":
            return self._response(rid, self._read_resource(req.get("params", {})))
        return self._error(rid, -32601, f"Unknown method: {method}")

    def _response(self, rid, result):
        return {"jsonrpc": "2.0", "id": rid, "result": result}

    def _error(self, rid, code, message):
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}

    # ── 工具定义 ──────────────────────────────────

    def _tool_defs(self):
        return [
            {
                "name": "search_invoices",
                "description": "搜索/筛选发票记录。可按年份、月份、发票类型、销售方、购买方、标签、关键词筛选，支持排序和分页。返回匹配记录列表及合计金额/税额。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "year": {"type": "integer", "description": "年份，如 2025"},
                        "month": {"type": "integer", "description": "月份 1-12"},
                        "invoice_type": {"type": "string", "description": "发票类型，如「增值税专用发票」"},
                        "seller": {"type": "string", "description": "销售方名称模糊搜索"},
                        "buyer": {"type": "string", "description": "购买方名称或税号模糊搜索"},
                        "tag": {"type": "string", "description": "标签值模糊搜索"},
                        "keyword": {"type": "string", "description": "全文字段搜索"},
                        "sort_by": {"type": "string", "description": "排序字段"},
                        "sort_asc": {"type": "boolean", "description": "升序排列，默认 true"},
                        "limit": {"type": "integer", "description": "返回条数，默认 50"},
                        "offset": {"type": "integer", "description": "偏移量，默认 0"},
                    }
                }
            },
            {
                "name": "import_invoice",
                "description": "导入一个 PDF 发票文件。解析发票号、日期、购买方、销售方、金额/税额等字段并存入数据库。导入时可附带设置标签值（如企业号）和备注。如发票号重复则跳过。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "pdf_path": {"type": "string", "description": "PDF 文件的绝对路径"},
                        "tags": {"type": "object", "description": "导入时附带的标签键值对，如 {\"企业号\": \"14786\"}"},
                        "remark": {"type": "string", "description": "导入时附带的备注"},
                    },
                    "required": ["pdf_path"]
                }
            },
            {
                "name": "export_excel",
                "description": "导出当前筛选结果为 Excel 文件，返回保存路径。支持可选筛选条件。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "output_path": {"type": "string", "description": "输出 .xlsx 文件路径，默认保存到桌面"},
                        "year": {"type": "integer"},
                        "month": {"type": "integer"},
                        "invoice_type": {"type": "string"},
                        "seller": {"type": "string"},
                    }
                }
            },
            {
                "name": "get_summary",
                "description": "获取数据库统计摘要：总记录数、金额合计、税额合计、价税合计，以及可选的时间范围和发票类型分布。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "year": {"type": "integer"},
                        "month": {"type": "integer"},
                    }
                }
            },
            {
                "name": "manage_tags",
                "description": "管理标签模板：列出所有、添加新标签、删除标签。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["list", "add", "delete"]},
                        "tag_name": {"type": "string", "description": "add/delete 时使用"},
                    },
                    "required": ["action"]
                }
            },
            {
                "name": "update_invoice",
                "description": "修改发票记录的字段：标签值（如企业号、项目名称）和备注。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "invoice_no": {"type": "string", "description": "发票号码"},
                        "tags": {"type": "object", "description": "要设置的标签键值对，如 {\"企业号\": \"14786\", \"项目名称\": \"Q1\"}"},
                        "remark": {"type": "string", "description": "备注内容"},
                    },
                    "required": ["invoice_no"]
                }
            },
            {
                "name": "add_attachment",
                "description": "给指定发票添加附件（截图、文档等文件）。文件会被复制到数据目录。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "invoice_no": {"type": "string", "description": "发票号码"},
                        "file_paths": {"type": "array", "items": {"type": "string"}, "description": "要添加为附件的文件路径列表"},
                    },
                    "required": ["invoice_no", "file_paths"]
                }
            },
            {
                "name": "delete_invoice",
                "description": "删除一条发票记录及其关联的 PDF 文件。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "invoice_no": {"type": "string", "description": "发票号码"},
                    },
                    "required": ["invoice_no"]
                }
            },
            {
                "name": "check_update",
                "description": "检查 Gitee 是否有新版本发布。",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            },
        ]

    # ── 资源定义 ──────────────────────────────────

    def _resource_defs(self):
        return [
            {"uri": "invoices://all", "name": "全部发票", "description": "数据库中的所有发票记录"},
            {"uri": "invoices://summary", "name": "统计摘要", "description": "总记录数、金额/税额/价税合计"},
            {"uri": "invoices://tags", "name": "标签模板", "description": "当前配置的标签模板列表"},
        ]

    def _read_resource(self, params: dict):
        params = params or {}
        uri = params.get("uri", "")
        if uri == "invoices://all":
            data = [self._inv_to_dict(inv) for inv in self._db.load()]
            return {"contents": [{"uri": uri, "mimeType": "application/json", "text": json.dumps(data, ensure_ascii=False)}]}
        if uri == "invoices://summary":
            return {"contents": [{"uri": uri, "mimeType": "application/json", "text": json.dumps(
                self._get_summary({}), ensure_ascii=False)}]}
        if uri == "invoices://tags":
            return {"contents": [{"uri": uri, "mimeType": "application/json", "text": json.dumps(self._config.tag_templates, ensure_ascii=False)}]}
        return {"contents": [{"uri": uri, "mimeType": "text/plain", "text": f"Unknown resource: {uri}"}]}

    # ── 工具实现 ──────────────────────────────────

    def _call_tool(self, params: dict):
        name = params.get("name", "")
        args = params.get("arguments") or {}
        fn = self._tools.get(name)
        if not fn:
            return {"content": [{"type": "text", "text": json.dumps({"error": f"Unknown tool: {name}"}, ensure_ascii=False)}], "isError": True}
        try:
            result = fn(args)
            return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}
        except Exception as e:
            return {"content": [{"type": "text", "text": json.dumps({"error": str(e)}, ensure_ascii=False)}], "isError": True}

    def _search_invoices(self, args):
        invs = self._db.load()
        keyword = (args.get("keyword") or "").lower()

        filtered = []
        for inv in invs:
            if not record_matches_filter(inv, args.get("year"), args.get("month"),
                                         args.get("invoice_type"), args.get("seller"),
                                         args.get("buyer", ""), args.get("tag", "")):
                continue
            if keyword:
                full = json.dumps(self._inv_to_dict(inv), ensure_ascii=False).lower()
                if keyword not in full:
                    continue
            filtered.append(self._inv_to_dict(inv))

        sort_by = args.get("sort_by")
        if sort_by:
            if sort_by not in VALID_SORT_FIELDS:
                raise ValueError(f"不支持的排序字段: {sort_by}")
            asc = args.get("sort_asc", True)
            numeric = sort_by in ("amount", "tax_rate", "tax_amount", "total")
            if numeric:
                filtered.sort(key=lambda x: safe_float(str(x.get(sort_by, ""))), reverse=not asc)
            else:
                filtered.sort(key=lambda x: str(x.get(sort_by, "")).lower(), reverse=not asc)

        limit = args.get("limit", 50)
        offset = args.get("offset", 0)
        page = filtered[offset:offset + limit]

        return {
            "count": len(filtered),
            "returned": len(page),
            "total_amount": sum(safe_float(r.get("amount")) for r in filtered),
            "total_tax": sum(safe_float(r.get("tax_amount")) for r in filtered),
            "total_with_tax": sum(safe_float(r.get("total")) for r in filtered),
            "records": page,
        }

    def _import_invoice(self, args):
        pdf_path = args.get("pdf_path", "")
        if not pdf_path:
            return {"error": "缺少必填参数: pdf_path"}
        if not os.path.exists(pdf_path):
            return {"error": f"文件不存在: {pdf_path}"}
        if not pdf_path.lower().endswith(".pdf"):
            return {"error": "仅支持 PDF 文件"}

        result = parse_invoice_pdf(pdf_path)
        if result.get("error"):
            return {"parsed": result, "status": "parse_error"}

        inv = Invoice.from_dict(result)
        inv.ensure_defaults()

        tags = args.get("tags")
        if tags and isinstance(tags, dict):
            if not inv.tags:
                inv.tags = {}
            for k, v in tags.items():
                inv.tags[k] = str(v) if v else ""
        remark = args.get("remark")
        if remark is not None:
            inv.remark = str(remark)

        existing = self._db.load()
        if inv.invoice_no and any(i.invoice_no == inv.invoice_no for i in existing):
            return {"status": "duplicate", "invoice_no": inv.invoice_no, "message": f"发票号 {inv.invoice_no} 已存在"}

        # 复制 PDF 到 data/invoices/（处理重名）
        dst_dir = os.path.join(self._data_dir, "invoices")
        os.makedirs(dst_dir, exist_ok=True)
        copied = copy_file_to_dir(pdf_path, dst_dir)
        if copied == pdf_path:
            return {"error": f"PDF 文件复制失败，磁盘可能已满或无写入权限"}
        inv.pdf_path = copied

        existing.append(inv)
        self._db.save(existing)
        self._backup.backup(self._db.data_file)
        return {"status": "ok", "invoice": self._inv_to_dict(inv)}

    def _export_excel(self, args):
        output = args.get("output_path", "")
        if not output:
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            output = os.path.join(desktop, f"发票导出_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
        out_dir = os.path.dirname(output)
        if out_dir and not os.path.isdir(out_dir):
            return {"error": f"目录不存在: {out_dir}"}

        from services.export_service import ExportService
        invs = self._db.load()
        year = args.get("year")
        month = args.get("month")
        inv_type = args.get("invoice_type")
        seller = args.get("seller")
        if any([year, month, inv_type, seller]):
            invs = [i for i in invs if record_matches_filter(i, year, month, inv_type, seller, "", "")]
        svc = ExportService()
        svc.export(invs, output, tag_columns=self._config.tag_templates)
        return {"status": "ok", "path": output}

    def _get_summary(self, args):
        invs = self._db.load()
        year = args.get("year")
        month = args.get("month")
        if year or month:
            invs = [i for i in invs if record_matches_filter(i, year, month, None, None, "", "")]

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

    def _manage_tags(self, args):
        action = args.get("action", "")
        if not action:
            return {"error": "缺少必填参数: action"}
        if action not in ("list", "add", "delete"):
            return {"error": f"未知操作: {action}"}
        templates = self._config.tag_templates
        if action == "list":
            return {"tags": templates}
        name = (args.get("tag_name") or "").strip()
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
        return {"error": "内部错误"}  # unreachable

    def _update_invoice(self, args):
        inv_no = (args.get("invoice_no") or "").strip()
        if not inv_no:
            return {"error": "缺少必填参数: invoice_no"}
        invs = self._db.load()
        target = None
        for inv in invs:
            if inv.invoice_no == inv_no:
                target = inv
                break
        if not target:
            return {"error": f"未找到发票号 {inv_no}"}

        changed = []
        tags = args.get("tags")
        if tags and isinstance(tags, dict):
            if not target.tags:
                target.tags = {}
            for k, v in tags.items():
                target.tags[k] = str(v) if v else ""
            changed.append("tags")
        remark = args.get("remark")
        if remark is not None:
            target.remark = str(remark)
            changed.append("remark")

        if not changed:
            return {"message": "无变更", "invoice": self._inv_to_dict(target)}
        self._db.save(invs)
        self._backup.backup(self._db.data_file)
        return {"status": "ok", "changed": changed, "invoice": self._inv_to_dict(target)}

    def _add_attachment(self, args):
        inv_no = (args.get("invoice_no") or "").strip()
        paths = args.get("file_paths") or []
        if not inv_no:
            return {"error": "缺少必填参数: invoice_no"}
        if not paths:
            return {"error": "缺少必填参数: file_paths"}

        invs = self._db.load()
        target = None
        for inv in invs:
            if inv.invoice_no == inv_no:
                target = inv
                break
        if not target:
            return {"error": f"未找到发票号 {inv_no}"}

        valid = [p for p in paths if os.path.isfile(p)]
        if not valid:
            return {"error": "没有有效的文件"}

        from services.invoice_service import InvoiceService
        added = InvoiceService._attachment_namer
        inv_no_safe = re.sub(r'[\\/:*?"<>|]', '_', inv_no)
        count = 0
        for src in valid:
            dst = os.path.join(self._data_dir, added(src, inv_no_safe))
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
            self._backup.backup(self._db.data_file)
        return {"status": "ok", "added": count, "total_attachments": len(target.attachments or [])}

    def _delete_invoice(self, args):
        inv_no = args.get("invoice_no", "")
        if not inv_no:
            return {"error": "缺少必填参数: invoice_no"}
        invs = self._db.load()
        target = None
        for inv in invs:
            if inv.invoice_no == inv_no:
                target = inv
                break
        if not target:
            return {"error": f"未找到发票号 {inv_no}"}

        invs.remove(target)
        self._db.save(invs)
        if target.pdf_path and os.path.exists(target.pdf_path):
            try:
                os.remove(target.pdf_path)
            except OSError:
                pass
        self._backup.backup(self._db.data_file)
        return {"status": "ok", "deleted": inv_no}

    def _check_update(self, _args):
        try:
            import http.client
            conn = http.client.HTTPSConnection("gitee.com", timeout=10)
            conn.request("GET", "/api/v5/repos/GUYI33/lan-invoice/releases/latest")
            resp = conn.getresponse()
            data = json.loads(resp.read().decode())
            conn.close()
        except Exception:
            return {"status": "offline", "message": "无法连接网络"}

        tag = data.get("tag_name", "").lstrip("v")
        latest = tag or "未知"
        newer = False
        if tag:
            try:
                newer = tuple(int(x) for x in tag.split(".")) > tuple(int(x) for x in APP_VERSION.split("."))
            except ValueError:
                pass
        return {"current": APP_VERSION, "latest": latest, "has_newer": newer}

    @staticmethod
    def _inv_to_dict(inv: Invoice) -> dict:
        d = inv.to_dict()
        d.pop("company", None)
        return d
