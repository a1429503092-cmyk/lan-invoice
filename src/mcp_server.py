# -*- coding: utf-8 -*-
"""MCP Server — stdio JSON-RPC，委托 InvoiceService 处理业务"""

import sys
import os
import json

from database import Database
from backup import BackupService
from config_manager import ConfigManager
from services.invoice_service import InvoiceService
from version import APP_VERSION

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")


class McpServer:
    """MCP stdio server: 读 stdin JSON-RPC → 委托 InvoiceService → 写 stdout"""

    def __init__(self):
        appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
        config_dir = os.path.join(appdata, "lan-invoice")
        self._config = ConfigManager(os.path.join(config_dir, "config.json"))
        self._data_dir = self._init_data_dir(config_dir)
        self._db = Database(os.path.join(self._data_dir, "invoices.db"))
        self._backup = BackupService()
        self._svc = InvoiceService(
            self._db, self._backup, self._config,
            self._data_dir, os.path.join(self._data_dir, "invoices"),
        )

        self._routes = {
            "search_invoices": self._search,
            "import_invoice": self._import,
            "export_excel": self._export,
            "get_summary": self._summary,
            "manage_tags": self._tags,
            "update_invoice": self._update,
            "add_attachment": self._attach,
            "delete_invoice": self._delete,
            "check_update": self._check_update,
        }

    def _init_data_dir(self, config_dir: str) -> str:
        cfg_file = os.path.join(config_dir, "config.json")
        try:
            with open(cfg_file, encoding="utf-8") as f:
                d = json.load(f).get("data_dir", "")
                if d and os.path.isdir(d):
                    return d
        except (OSError, json.JSONDecodeError):
            pass
        return os.path.join(config_dir, "data")

    # ── MCP 协议 ──────────────────────────────

    def run(self):
        for line in sys.stdin:
            try:
                req = json.loads(line.strip())
            except json.JSONDecodeError:
                self._write({"jsonrpc": "2.0", "id": None,
                             "error": {"code": -32700, "message": "Parse error"}})
                continue
            resp = self._handle(req)
            if resp is not None:
                self._write(resp)

    def _write(self, data: dict):
        sys.stdout.write(json.dumps(data, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    def _handle(self, req: dict) -> dict | None:
        method = req.get("method", "")
        rid = req.get("id")

        if method == "initialize":
            return self._ok(rid, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}, "resources": {}},
                "serverInfo": {"name": "invoice-tool", "version": APP_VERSION},
            })
        if method == "notifications/initialized":
            return None
        if method == "tools/list":
            return self._ok(rid, {"tools": self._tool_defs()})
        if method == "tools/call":
            return self._ok(rid, self._call_tool(req.get("params", {})))
        if method == "resources/list":
            return self._ok(rid, {"resources": self._resource_defs()})
        if method == "resources/read":
            return self._ok(rid, self._read_resource(req.get("params", {})))
        return self._err(rid, -32601, f"Unknown method: {method}")

    def _ok(self, rid, result):
        return {"jsonrpc": "2.0", "id": rid, "result": result}

    def _err(self, rid, code, message):
        return {"jsonrpc": "2.0", "id": rid,
                "error": {"code": code, "message": message}}

    # ── 工具定义 ──────────────────────────────

    def _tool_defs(self):
        return [
            {"name": "search_invoices",
             "description": "搜索/筛选发票记录。可按年份、月份、发票类型、销售方、购买方、标签、关键词筛选，支持排序和分页。",
             "inputSchema": {"type": "object", "properties": {
                 "year": {"type": "integer"}, "month": {"type": "integer"},
                 "invoice_type": {"type": "string"}, "seller": {"type": "string"},
                 "buyer": {"type": "string"}, "tag": {"type": "string"},
                 "keyword": {"type": "string"},
                 "sort_by": {"type": "string"}, "sort_asc": {"type": "boolean"},
                 "limit": {"type": "integer"}, "offset": {"type": "integer"},
             }}},
            {"name": "import_invoice",
             "description": "导入 PDF 发票，解析并存入数据库。可附带标签和备注。",
             "inputSchema": {"type": "object", "properties": {
                 "pdf_path": {"type": "string"},
                 "tags": {"type": "object"},
                 "remark": {"type": "string"},
             }, "required": ["pdf_path"]}},
            {"name": "export_excel",
             "description": "导出当前筛选结果为 Excel 文件。",
             "inputSchema": {"type": "object", "properties": {
                 "output_path": {"type": "string"},
                 "year": {"type": "integer"}, "month": {"type": "integer"},
                 "invoice_type": {"type": "string"}, "seller": {"type": "string"},
             }}},
            {"name": "get_summary",
             "description": "获取数据库统计摘要：总记录数、金额/税额/价税合计、类型分布。",
             "inputSchema": {"type": "object", "properties": {
                 "year": {"type": "integer"}, "month": {"type": "integer"},
             }}},
            {"name": "manage_tags",
             "description": "管理标签模板：列出所有、添加、删除。",
             "inputSchema": {"type": "object", "properties": {
                 "action": {"type": "string", "enum": ["list", "add", "delete"]},
                 "tag_name": {"type": "string"},
             }, "required": ["action"]}},
            {"name": "update_invoice",
             "description": "修改发票记录的标签值和备注。",
             "inputSchema": {"type": "object", "properties": {
                 "invoice_no": {"type": "string"},
                 "tags": {"type": "object"},
                 "remark": {"type": "string"},
             }, "required": ["invoice_no"]}},
            {"name": "add_attachment",
             "description": "给指定发票添加附件（截图、文档等）。",
             "inputSchema": {"type": "object", "properties": {
                 "invoice_no": {"type": "string"},
                 "file_paths": {"type": "array", "items": {"type": "string"}},
             }, "required": ["invoice_no", "file_paths"]}},
            {"name": "delete_invoice",
             "description": "删除一条发票记录及其关联 PDF 文件。",
             "inputSchema": {"type": "object", "properties": {
                 "invoice_no": {"type": "string"},
             }, "required": ["invoice_no"]}},
            {"name": "check_update",
             "description": "检查 Gitee 是否有新版本发布。",
             "inputSchema": {"type": "object", "properties": {}}},
        ]

    # ── 资源定义 ──────────────────────────────

    def _resource_defs(self):
        return [
            {"uri": "invoices://all", "name": "全部发票"},
            {"uri": "invoices://summary", "name": "统计摘要"},
            {"uri": "invoices://tags", "name": "标签模板"},
        ]

    def _read_resource(self, params: dict):
        params = params or {}
        uri = params.get("uri", "")
        if uri == "invoices://all":
            data = [self._svc._inv_dict(inv) for inv in self._svc.load_all()]
            return {"contents": [{"uri": uri, "mimeType": "application/json",
                    "text": json.dumps(data, ensure_ascii=False)}]}
        if uri == "invoices://summary":
            return {"contents": [{"uri": uri, "mimeType": "application/json",
                    "text": json.dumps(self._svc.get_summary(), ensure_ascii=False)}]}
        if uri == "invoices://tags":
            return {"contents": [{"uri": uri, "mimeType": "application/json",
                    "text": json.dumps(self._config.tag_templates, ensure_ascii=False)}]}
        return {"contents": [{"uri": uri, "mimeType": "text/plain",
                "text": f"Unknown resource: {uri}"}]}

    # ── 工具调度 ──────────────────────────────

    def _call_tool(self, params: dict):
        name = params.get("name", "")
        args = params.get("arguments") or {}
        fn = self._routes.get(name)
        if not fn:
            return {"content": [{"type": "text",
                    "text": json.dumps({"error": f"Unknown tool: {name}"},
                                       ensure_ascii=False)}], "isError": True}
        try:
            result = fn(args)
            return {"content": [{"type": "text",
                    "text": json.dumps(result, ensure_ascii=False)}]}
        except Exception as e:
            return {"content": [{"type": "text",
                    "text": json.dumps({"error": str(e)}, ensure_ascii=False)}],
                    "isError": True}

    def _search(self, a):
        return self._svc.search(**a)

    def _import(self, a):
        return self._svc.import_invoice(
            a.get("pdf_path", ""), a.get("tags"), a.get("remark"))

    def _export(self, a):
        return self._svc.export_excel(a.pop("output_path", ""), **a)

    def _summary(self, a):
        return self._svc.get_summary(**a)

    def _tags(self, a):
        return self._svc.manage_tags(a.get("action", ""), a.get("tag_name", ""))

    def _update(self, a):
        return self._svc.update_invoice(
            a.get("invoice_no", ""), a.get("tags"), a.get("remark"))

    def _attach(self, a):
        return self._svc.attach_files(
            a.get("invoice_no", ""), a.get("file_paths") or [])

    def _delete(self, a):
        return self._svc.delete_invoice(a.get("invoice_no", ""))

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
                newer = (tuple(int(x) for x in tag.split("."))
                         > tuple(int(x) for x in APP_VERSION.split(".")))
            except ValueError:
                pass
        return {"current": APP_VERSION, "latest": latest, "has_newer": newer}
