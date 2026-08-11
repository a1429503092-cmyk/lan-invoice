# -*- coding: utf-8 -*-
"""MCP Server — stdio JSON-RPC，委托 InvoiceService 处理业务
协议版本: 2026-07-28（向后兼容 2024-11-05 旧客户端）
"""

import sys
import os
import json

from database import Database
from backup import BackupService
from config_manager import ConfigManager
from services.invoice_service import InvoiceService, VALID_SORT_FIELDS
from version import APP_VERSION

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# ── 协议常量 ────────────────────────────────

PROTOCOL_VERSION = "2026-07-28"
SUPPORTED_VERSIONS = ["2026-07-28", "2025-11-25", "2024-11-05"]

# _meta 键名（2026-07-28 规范）
META_PROTOCOL_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CLIENT_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"
META_CLIENT_INFO = "io.modelcontextprotocol/clientInfo"
META_SERVER_INFO = "io.modelcontextprotocol/serverInfo"
META_LOG_LEVEL = "io.modelcontextprotocol/logLevel"

# 默认缓存 TTL（毫秒）
_DEFAULT_TTL_MS = 300000  # 5 分钟
_TOOL_LIST_TTL_MS = 600000  # 工具列表 10 分钟（变化极少）


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
            "import_invoices_batch": self._import_batch,
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

        # ── 2026-07-28: _meta 协议版本检查 ──
        meta = req.get("_meta", {})
        client_ver = meta.get(META_PROTOCOL_VERSION, "")
        if client_ver and client_ver not in SUPPORTED_VERSIONS:
            return self._err(rid, -32022,
                f"Unsupported protocol version: {client_ver}. "
                f"Supported: {', '.join(SUPPORTED_VERSIONS)}")

        # ── server/discover（2026-07-28 新握手）──
        if method == "server/discover":
            return self._discover(rid)

        # ── 向后兼容：initialize（2024-11-05 旧握手）──
        if method == "initialize":
            return self._legacy_initialize(rid, req.get("params", {}))

        # ── 2026-07-28 无状态：不再需要 initialized 通知 ──
        if method == "notifications/initialized":
            return None

        # ── 工具/资源 ──
        if method == "tools/list":
            return self._ok(rid, {"tools": self._tool_defs()},
                           ttl_ms=_TOOL_LIST_TTL_MS)
        if method == "tools/call":
            return self._ok(rid, self._call_tool(req.get("params", {})))
        if method == "resources/list":
            return self._ok(rid, {"resources": self._resource_defs()},
                           ttl_ms=_DEFAULT_TTL_MS)
        if method == "resources/read":
            return self._ok(rid, self._read_resource(req.get("params", {})),
                           ttl_ms=_DEFAULT_TTL_MS)

        # ── 已废弃方法（向后兼容） ──
        if method == "ping":
            return self._ok(rid, {})

        return self._err(rid, -32601, f"Unknown method: {method}")

    # ── server/discover ────────────────────────

    def _discover(self, rid):
        """2026-07-28 协议发现端点"""
        return {
            "jsonrpc": "2.0",
            "id": rid,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "supportedProtocolVersions": SUPPORTED_VERSIONS,
                "capabilities": {
                    "tools": {},
                    "resources": {},
                    "extensions": {
                        "io.modelcontextprotocol/tasks": {
                            "supportedMethods": ["tasks/get"],
                        },
                    },
                },
                "serverInfo": {
                    "name": "invoice-tool",
                    "version": APP_VERSION,
                },
            },
        }

    def _legacy_initialize(self, rid, params: dict):
        """向后兼容 2024-11-05 旧客户端 initialize"""
        client_ver = params.get("protocolVersion", "")
        if client_ver and client_ver not in SUPPORTED_VERSIONS:
            return self._err(rid, -32022,
                f"Unsupported protocol version: {client_ver}")
        # 旧客户端未指定版本时使用 2024-11-05
        effective_ver = client_ver or "2024-11-05"
        return {
            "jsonrpc": "2.0",
            "id": rid,
            "result": {
                "protocolVersion": effective_ver,
                "capabilities": {"tools": {}, "resources": {}},
                "serverInfo": {
                    "name": "invoice-tool",
                    "version": APP_VERSION,
                },
            },
        }

    # ── 响应构造 ──────────────────────────────

    def _ok(self, rid, result, ttl_ms: int | None = None):
        """构造成功响应。2026-07-28 要求 resultType + _meta"""
        resp = {
            "jsonrpc": "2.0",
            "id": rid,
            "result": result,
        }
        # resultType（2026-07-28 必填）
        if isinstance(result, dict):
            result["resultType"] = "complete"

        # _meta（2026-07-28 新规范：每次响应带 serverInfo）
        meta = {
            META_SERVER_INFO: {
                "name": "invoice-tool",
                "version": APP_VERSION,
            },
        }
        if ttl_ms is not None:
            meta["ttlMs"] = ttl_ms
            meta["cacheScope"] = "private"
        resp["_meta"] = meta
        return resp

    def _err(self, rid, code, message):
        resp = {
            "jsonrpc": "2.0",
            "id": rid,
            "error": {"code": code, "message": message},
        }
        resp["_meta"] = {
            META_SERVER_INFO: {
                "name": "invoice-tool",
                "version": APP_VERSION,
            },
        }
        return resp

    # ── 工具定义 ──────────────────────────────

    def _tool_defs(self):
        return [
            {"name": "search_invoices",
             "description": "搜索/筛选发票记录。可按年份、月份、发票类型、销售方、购买方、标签、关键词筛选，支持排序和分页。",
             "inputSchema": {
                 "$schema": "https://json-schema.org/draft/2020-12/schema",
                 "type": "object",
                 "properties": {
                     "year": {"type": "integer"},
                     "month": {"type": "integer"},
                     "invoice_type": {"type": "string"},
                     "seller": {"type": "string"},
                     "buyer": {"type": "string"},
                     "tag": {"type": "string"},
                     "keyword": {"type": "string"},
                     "sort_by": {"type": "string"},
                     "sort_asc": {"type": "boolean"},
                     "limit": {"type": "integer"},
                     "offset": {"type": "integer"},
                 },
             }},
            {"name": "import_invoice",
             "description": "导入单个 PDF 发票，解析并存入数据库。批量导入请用 import_invoices_batch。",
             "inputSchema": {
                 "$schema": "https://json-schema.org/draft/2020-12/schema",
                 "type": "object",
                 "properties": {
                     "pdf_path": {"type": "string"},
                     "tags": {"type": "object"},
                     "remark": {"type": "string"},
                 },
                 "required": ["pdf_path"],
             }},
            {"name": "import_invoices_batch",
             "description": "批量导入多个 PDF 发票——并行解析 + 单事务写入，比逐条导入快 10-100 倍。传入 PDF 文件路径列表或目录路径（自动扫描目录下所有 PDF）。",
             "inputSchema": {
                 "$schema": "https://json-schema.org/draft/2020-12/schema",
                 "type": "object",
                 "properties": {
                     "pdf_paths": {
                         "type": "array", "items": {"type": "string"},
                         "description": "PDF 文件路径列表",
                     },
                     "directory": {
                         "type": "string",
                         "description": "目录路径，自动扫描该目录下所有 .pdf 文件",
                     },
                     "tags": {"type": "object",
                              "description": "统一标签，应用到所有导入的发票"},
                     "remark": {"type": "string", "description": "统一备注"},
                     "parallel": {"type": "integer", "default": 4,
                                  "description": "并行解析线程数（默认 4）"},
                 },
             }},
            {"name": "export_excel",
             "description": "导出当前筛选结果为 Excel 文件。",
             "inputSchema": {
                 "$schema": "https://json-schema.org/draft/2020-12/schema",
                 "type": "object",
                 "properties": {
                     "output_path": {"type": "string"},
                     "year": {"type": "integer"},
                     "month": {"type": "integer"},
                     "invoice_type": {"type": "string"},
                     "seller": {"type": "string"},
                 },
             }},
            {"name": "get_summary",
             "description": "获取数据库统计摘要：总记录数、金额/税额/价税合计、类型分布。",
             "inputSchema": {
                 "$schema": "https://json-schema.org/draft/2020-12/schema",
                 "type": "object",
                 "properties": {
                     "year": {"type": "integer"},
                     "month": {"type": "integer"},
                 },
             }},
            {"name": "manage_tags",
             "description": "管理标签模板：列出所有、添加、删除。",
             "inputSchema": {
                 "$schema": "https://json-schema.org/draft/2020-12/schema",
                 "type": "object",
                 "properties": {
                     "action": {"type": "string",
                                "enum": ["list", "add", "delete"]},
                     "tag_name": {"type": "string"},
                 },
                 "required": ["action"],
             }},
            {"name": "update_invoice",
             "description": "修改发票记录的标签值和备注。",
             "inputSchema": {
                 "$schema": "https://json-schema.org/draft/2020-12/schema",
                 "type": "object",
                 "properties": {
                     "invoice_no": {"type": "string"},
                     "tags": {"type": "object"},
                     "remark": {"type": "string"},
                 },
                 "required": ["invoice_no"],
             }},
            {"name": "add_attachment",
             "description": "给指定发票添加附件（截图、文档等）。",
             "inputSchema": {
                 "$schema": "https://json-schema.org/draft/2020-12/schema",
                 "type": "object",
                 "properties": {
                     "invoice_no": {"type": "string"},
                     "file_paths": {"type": "array",
                                    "items": {"type": "string"}},
                 },
                 "required": ["invoice_no", "file_paths"],
             }},
            {"name": "delete_invoice",
             "description": "删除一条发票记录及其关联 PDF 文件。",
             "inputSchema": {
                 "$schema": "https://json-schema.org/draft/2020-12/schema",
                 "type": "object",
                 "properties": {
                     "invoice_no": {"type": "string"},
                 },
                 "required": ["invoice_no"],
             }},
            {"name": "check_update",
             "description": "检查 Gitee 是否有新版本发布。",
             "inputSchema": {
                 "$schema": "https://json-schema.org/draft/2020-12/schema",
                 "type": "object",
                 "properties": {},
             }},
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
        # 2026-07-28: 资源未找到用 -32602（与原 JSON-RPC 一致）
        return {"isError": True,
                "contents": [{"uri": uri, "mimeType": "text/plain",
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

    def _import_batch(self, a):
        paths = list(a.get("pdf_paths") or [])
        directory = a.get("directory", "")
        if directory:
            import glob as _glob
            scanned = sorted(_glob.glob(os.path.join(directory, "*.pdf")))
            paths.extend(scanned)
        if not paths:
            return {"error": "pdf_paths 和 directory 均为空，至少提供其一"}
        return self._svc.import_invoices_batch(
            paths,
            tags=a.get("tags"),
            remark=a.get("remark"),
            parallel=a.get("parallel", 4),
        )

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
