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
from mcp_tasks import TaskManager, get_task_manager
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
            "download_update": self._download_update,
        }

        # 异步任务管理（io.modelcontextprotocol/tasks 扩展）
        self._tasks = get_task_manager()
        # 支持异步执行的方法名集合（tools/call 检测到后返回 CreateTaskResult）
        self._async_methods: set[str] = {"import_invoices_batch", "download_update"}

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
            return self._handle_tools_call(rid, req)
        if method == "resources/list":
            return self._ok(rid, {"resources": self._resource_defs()},
                           ttl_ms=_DEFAULT_TTL_MS)
        if method == "resources/read":
            return self._ok(rid, self._read_resource(req.get("params", {})),
                           ttl_ms=_DEFAULT_TTL_MS)

        # ── Tasks 扩展（2026-07-28） ──
        if method == "tasks/get":
            return self._handle_tasks_get(rid, req.get("params", {}))
        if method == "tasks/cancel":
            return self._handle_tasks_cancel(rid, req.get("params", {}))

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

    # ── Tasks 扩展 ──────────────────────────

    def _client_supports_tasks(self, meta: dict) -> bool:
        """检查请求 _meta 中是否声明了 Tasks 扩展能力。"""
        caps = meta.get(META_CLIENT_CAPABILITIES, {})
        extensions = caps.get("extensions", {})
        return "io.modelcontextprotocol/tasks" in extensions

    def _handle_tools_call(self, rid, req: dict):
        """处理 tools/call，对支持异步的方法检查客户端能力并返回 Task。"""
        params = req.get("params", {})
        name = params.get("name", "")
        meta = req.get("_meta", {})

        # 异步方法 + 客户端支持 Tasks → 返回 CreateTaskResult
        if name in self._async_methods and self._client_supports_tasks(meta):
            task_id = self._tasks.submit(
                name=name,
                fn=self._run_tool_async,
                tool_name=name,
                args=params.get("arguments") or {},
            )
            return {
                "jsonrpc": "2.0",
                "id": rid,
                "result": {
                    "resultType": "task",
                    "taskId": task_id,
                    "status": "working",
                    "ttlMs": 3_600_000,
                    "pollIntervalMs": 2000,
                },
                "_meta": {
                    META_SERVER_INFO: {
                        "name": "invoice-tool",
                        "version": APP_VERSION,
                    },
                },
            }

        # 同步执行（兼容不支持 Tasks 的客户端）
        result = self._call_tool(params)
        return self._ok(rid, result)

    def _run_tool_async(self, task, tool_name: str, args: dict):
        """在线程池中执行工具调用，通过 task 汇报进度。"""
        task.set_progress(0, f"启动 {tool_name}...")
        fn = self._routes.get(tool_name)
        if not fn:
            return {"error": f"Unknown tool: {tool_name}"}
        # import_invoices_batch 接受 progress_cb 参数，其他方法忽略
        if tool_name == "import_invoices_batch":
            return fn(args, progress_cb=task.set_progress)
        return fn(args)

    def _handle_tasks_get(self, rid, params: dict):
        """tasks/get — 轮询任务状态。"""
        task_id = params.get("taskId", "")
        if not task_id:
            return self._err(rid, -32602, "缺少必填参数: taskId")
        task_dict = self._tasks.get(task_id)
        if task_dict is None:
            return self._err(rid, -32602, f"任务不存在: {task_id}")
        resp = {
            "jsonrpc": "2.0",
            "id": rid,
            "result": task_dict,
            "_meta": {
                META_SERVER_INFO: {
                    "name": "invoice-tool",
                    "version": APP_VERSION,
                },
            },
        }
        return resp

    def _handle_tasks_cancel(self, rid, params: dict):
        """tasks/cancel — 请求取消任务。"""
        task_id = params.get("taskId", "")
        if not task_id:
            return self._err(rid, -32602, "缺少必填参数: taskId")
        cancelled = self._tasks.cancel(task_id)
        resp = {
            "jsonrpc": "2.0",
            "id": rid,
            "result": {"cancelled": cancelled},
            "_meta": {
                META_SERVER_INFO: {
                    "name": "invoice-tool",
                    "version": APP_VERSION,
                },
            },
        }
        return resp

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
             "description": "检查 Gitee 是否有新版本发布，返回最新版本号和全部资产（便携版/安装包）的直接下载链接。",
             "inputSchema": {
                 "$schema": "https://json-schema.org/draft/2020-12/schema",
                 "type": "object",
                 "properties": {},
             }},
            {"name": "download_update",
             "description": "下载新版本安装包到指定目录（支持进度，走异步任务）。先用 check_update 获取下载链接。",
             "inputSchema": {
                 "$schema": "https://json-schema.org/draft/2020-12/schema",
                 "type": "object",
                 "properties": {
                     "url": {"type": "string",
                             "description": "文件直接下载链接（来自 check_update 的 assets[].url）"},
                     "output_dir": {"type": "string",
                                    "description": "保存目录（默认桌面 Downloads 文件夹）"},
                     "filename": {"type": "string",
                                  "description": "可选：自定义保存文件名（默认用 URL 的文件名）"},
                 },
                 "required": ["url"],
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

    def _import_batch(self, a, progress_cb=None):
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
            progress_cb=progress_cb,
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

    def _download_update(self, a, progress_cb=None):
        """下载新版本文件。支持进度回调（MCP Tasks 异步）。

        流式下载到临时文件后原子重命名，避免下载中断留下半个文件。
        """
        import urllib.request
        url = (a.get("url") or "").strip()
        if not url:
            return {"error": "缺少必填参数: url"}

        # 默认保存到下载目录
        output_dir = a.get("output_dir") or os.path.join(
            os.path.expanduser("~"), "Downloads")
        os.makedirs(output_dir, exist_ok=True)
        filename = a.get("filename") or os.path.basename(url.split("?")[0])
        if not filename:
            return {"error": "无法从 URL 推断文件名，请指定 filename"}

        dest = os.path.join(output_dir, filename)
        tmp = dest + ".part"

        def _progress(pct, msg=""):
            if progress_cb:
                try:
                    progress_cb(pct, msg)
                except Exception:
                    pass

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "lan-invoice-updater"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                total = int(resp.headers.get("Content-Length") or 0)
                _progress(1, f"连接成功，文件大小 {total/1024/1024:.1f} MB")
                downloaded = 0
                with open(tmp, "wb") as f:
                    while True:
                        chunk = resp.read(1024 * 256)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            pct = int(downloaded * 100 / total)
                            _progress(pct, f"下载中 {downloaded/1024/1024:.1f}/{total/1024/1024:.1f} MB")
            os.replace(tmp, dest)
            _progress(100, f"下载完成")
            return {"status": "ok", "path": dest,
                    "size_mb": round(downloaded / 1024 / 1024, 1)}
        except Exception as e:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            return {"error": f"下载失败: {e}"}

    @staticmethod
    def _version_tuple(v: str) -> tuple:
        """版本号转元组，用于比较，非法返回 (0,)"""
        try:
            return tuple(int(x) for x in v.split("."))
        except ValueError:
            return (0,)

    def _check_update(self, _args):
        """检查更新：返回最新版本 + 全部资产的直接下载链接。

        注意：不用 Gitee 的 /releases/latest——该接口按创建顺序返回列表第一个
        release，删除旧版本后会导致检测错误。改用列表接口自行取版本号最大的。
        """
        try:
            import http.client
            conn = http.client.HTTPSConnection("gitee.com", timeout=10)
            conn.request("GET",
                         "/api/v5/repos/GUYI33/lan-invoice/releases?per_page=50")
            resp = conn.getresponse()
            data = json.loads(resp.read().decode())
            conn.close()
        except Exception:
            return {"status": "offline", "message": "无法连接网络"}

        # 列表接口 → 取版本号最大的 release
        if isinstance(data, list):
            best = None
            for r in data:
                t = (r.get("tag_name") or "").lstrip("v")
                if t and (best is None
                          or self._version_tuple(t) > self._version_tuple(best[0])):
                    best = (t, r)
            if best is None:
                return {"status": "ok", "current": APP_VERSION,
                        "latest": "", "has_newer": False, "assets": []}
            tag, latest = best
        else:  # 兼容单个对象
            tag = data.get("tag_name", "").lstrip("v")
            latest = data

        newer = (self._version_tuple(tag)
                 > self._version_tuple(APP_VERSION)) if tag else False

        # 解析全部资产（下载文件）
        assets = []
        for a in latest.get("assets") or []:
            name = a.get("name", "")
            url = a.get("browser_download_url", "")
            size = a.get("size", 0)
            if name and url:
                assets.append({
                    "name": name,
                    "size_mb": round(size / 1024 / 1024, 1),
                    "url": url,
                })

        result = {
            "status": "ok",
            "current": APP_VERSION,
            "latest": tag,
            "has_newer": newer,
            "release_page": f"https://gitee.com/GUYI33/lan-invoice/releases/tag/v{tag}" if tag else "",
            "assets": assets,
        }
        # 便捷字段：便携版/安装包直达
        for a in assets:
            if a["name"].endswith(".exe") and "setup" not in a["name"]:
                result["portable_download"] = a
            elif "setup" in a["name"]:
                result["installer_download"] = a
        return result
