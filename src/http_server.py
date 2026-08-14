# -*- coding: utf-8 -*-
"""HTTP API Server — 标准库 http.server，零额外依赖，委托 InvoiceService"""

import sys
import os
import json
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from io import BytesIO

from database import Database
from backup import BackupService
from config_manager import ConfigManager
from services.invoice_service import InvoiceService
from version import APP_VERSION

_PREFIX = "/api/v1"


def _init_service():
    appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
    config_dir = os.path.join(appdata, "lan-invoice")
    config = ConfigManager(os.path.join(config_dir, "config.json"))
    data_dir = config.data_dir or os.path.join(config_dir, "data")
    db = Database(os.path.join(data_dir, "invoices.db"))
    backup = BackupService()
    inv_dir = os.path.join(data_dir, "invoices")
    svc = InvoiceService(db, backup, config, data_dir, inv_dir)
    return svc, config, data_dir


class AppHandler(BaseHTTPRequestHandler):
    """REST 路由：GET/POST/PUT/DELETE → InvoiceService"""
    _svc: InvoiceService = None
    _config: ConfigManager = None
    _data_dir: str = ""
    _backup: BackupService = None

    def log_message(self, fmt, *args):
        if len(args) >= 2 and isinstance(args[1], int) and args[1] >= 400:
            print(f"[HTTP] {fmt % args}", file=sys.stderr)

    # ── 工具方法 ──────────────────────────────

    def _send(self, code: int, data):
        try:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        except UnicodeEncodeError:
            # 与 MCP _write 相同的兜底：孤立代理字符改用 ASCII 转义
            body = json.dumps(data, ensure_ascii=True).encode("ascii")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json_body(self) -> dict | None:
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            self._send(400, {"error": "JSON 格式错误"})
            return None

    def _qs(self) -> dict:
        parsed = urlparse(self.path)
        return {k: v[0] for k, v in parse_qs(parsed.query).items()}

    def _path_parts(self) -> list[str]:
        return urlparse(self.path).path.rstrip("/").split("/")

    # ── CORS ──────────────────────────────────

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods",
                         "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # ── GET ───────────────────────────────────

    def do_GET(self):
        parts = self._path_parts()

        if parts[-2:] == ["api", "v1"] or parts[-1:] == ["api"]:
            return self._send(200, {
                "name": "lan-invoice",
                "version": APP_VERSION,
                "endpoints": [
                    "GET  /api/v1/invoices?year=&month=&type=&seller=&keyword=&sort_by=&limit=",
                    "GET  /api/v1/invoices/{invoice_no}",
                    "POST /api/v1/invoices/import",
                    "PUT  /api/v1/invoices/{invoice_no}",
                    "DELETE /api/v1/invoices/{invoice_no}",
                    "GET  /api/v1/summary?year=&month=",
                    "GET  /api/v1/tags",
                    "POST /api/v1/tags",
                    "DELETE /api/v1/tags/{tag_name}",
                    "GET  /api/v1/export?year=&month=&type=&seller=",
                    "GET  /api/v1/backup/status",
                ]
            })

        # /api/v1/invoices/export
        if len(parts) >= 4 and parts[2] == "v1" and parts[3] == "invoices" \
                and parts[-1] == "export":
            return self._send(200, self._svc.export_excel(**self._qs()))

        # /api/v1/invoices/{invoice_no}
        if len(parts) >= 5 and parts[2] == "v1" and parts[3] == "invoices":
            return self._handle_get_one(parts[4])

        # /api/v1/invoices
        if len(parts) >= 4 and parts[2] == "v1" and parts[3] == "invoices":
            return self._handle_search()

        # /api/v1/summary
        if len(parts) >= 4 and parts[2] == "v1" and parts[3] == "summary":
            return self._send(200, self._svc.get_summary(**self._qs()))

        # /api/v1/tags
        if len(parts) >= 4 and parts[2] == "v1" and parts[3] == "tags":
            return self._send(200, self._svc.manage_tags("list"))

        # /api/v1/backup/status
        if len(parts) >= 4 and parts[2] == "v1" and parts[3] == "backup":
            return self._send(200, self._backup.get_stats())

        self._send(404, {"error": "Not found"})

    # ── POST ──────────────────────────────────

    def do_POST(self):
        parts = self._path_parts()

        # /api/v1/invoices/import
        if len(parts) >= 5 and parts[2] == "v1" and parts[3] == "invoices" \
                and parts[4] == "import":
            ctype = self.headers.get("Content-Type", "")
            if "multipart" in ctype:
                return self._handle_upload()
            body = self._json_body()
            if body is None:
                return
            return self._send(200, self._svc.import_invoice(
                body.get("pdf_path", ""), body.get("tags"), body.get("remark")))

        # /api/v1/tags
        if len(parts) >= 4 and parts[2] == "v1" and parts[3] == "tags":
            body = self._json_body()
            if body is None:
                return
            return self._send(200, self._svc.manage_tags(
                "add", body.get("tag_name", "")))

        self._send(404, {"error": "Not found"})

    # ── PUT ───────────────────────────────────

    def do_PUT(self):
        parts = self._path_parts()

        # /api/v1/invoices/{invoice_no}
        if len(parts) >= 5 and parts[2] == "v1" and parts[3] == "invoices":
            body = self._json_body()
            if body is None:
                return
            return self._send(200, self._svc.update_invoice(
                parts[4], body.get("tags"), body.get("remark")))

        self._send(404, {"error": "Not found"})

    # ── DELETE ────────────────────────────────

    def do_DELETE(self):
        parts = self._path_parts()

        # /api/v1/invoices/{invoice_no}
        if len(parts) >= 5 and parts[2] == "v1" and parts[3] == "invoices":
            return self._send(200, self._svc.delete_invoice(parts[4]))

        # /api/v1/tags/{tag_name}
        if len(parts) >= 5 and parts[2] == "v1" and parts[3] == "tags":
            return self._send(200, self._svc.manage_tags("delete", parts[4]))

        self._send(404, {"error": "Not found"})

    # ── 帮助方法 ──────────────────────────────

    def _handle_search(self):
        qs = self._qs()
        return self._send(200, self._svc.search(
            year=_parse_int(qs.get("year")),
            month=_parse_int(qs.get("month")),
            invoice_type=qs.get("type"),
            seller=qs.get("seller"),
            buyer=qs.get("buyer"),
            keyword=qs.get("keyword"),
            sort_by=qs.get("sort_by"),
            sort_asc=qs.get("sort_asc", "1") == "1",
            limit=_parse_int(qs.get("limit"), 50),
            offset=_parse_int(qs.get("offset"), 0),
        ))

    def _handle_get_one(self, inv_no: str):
        invs = self._svc.load_all()
        for inv in invs:
            if inv.invoice_no == inv_no:
                d = inv.to_dict()
                d.pop("company", None)
                return self._send(200, d)
        return self._send(404, {"error": f"未找到发票号 {inv_no}"})

    def _handle_upload(self):
        """multipart 文件上传（标准库方式）"""
        ctype = self.headers.get("Content-Type", "")
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        # 简单 multipart 解析（仅支持单个 PDF 文件）
        boundary = ctype.split("boundary=")[-1].encode()
        parts = body.split(b"--" + boundary)
        for part in parts:
            if b"filename=" in part:
                header_end = part.find(b"\r\n\r\n")
                if header_end == -1:
                    continue
                header = part[:header_end].decode("utf-8", errors="ignore")
                file_data = part[header_end + 4:]
                # 精确去掉末尾的 boundary 尾部标记
                file_data = file_data.rstrip(b"\r\n")
                if file_data.endswith(b"--"):
                    file_data = file_data[:-2]

                import tempfile
                fname_match = re.search(r'filename="([^"]*)"', header)
                fname = fname_match.group(1) if fname_match else "upload.pdf"
                tmp = os.path.join(tempfile.gettempdir(), fname)
                with open(tmp, "wb") as f:
                    f.write(file_data)
                result = self._svc.import_invoice(tmp)
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                return self._send(200, result)

        return self._send(400, {"error": "未找到上传文件"})

    @classmethod
    def configure(cls, svc, config, data_dir, backup):
        cls._svc = svc
        cls._config = config
        cls._data_dir = data_dir
        cls._backup = backup


def _parse_int(v, default=None):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def run_server(port: int = 8080):
    svc, config, data_dir = _init_service()
    backup = BackupService()
    AppHandler.configure(svc, config, data_dir, backup)
    server = HTTPServer(("127.0.0.1", port), AppHandler)
    print(f"HTTP API 已启动: http://127.0.0.1:{port}/api/v1")
    print(f"文档: http://127.0.0.1:{port}/api/v1")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
    print("服务器已关闭")
