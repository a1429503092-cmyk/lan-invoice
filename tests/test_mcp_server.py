# -*- coding: utf-8 -*-
"""MCP Server 全覆盖测试 — 9 工具 + 协议 + 资源 + 边界 + 异常"""

import sys
import os
import json
import tempfile
import shutil
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from mcp_server import McpServer, VALID_SORT_FIELDS
from models import Invoice
from database import Database


class TestMcpSetup(unittest.TestCase):
    """MCP Server 基础设施测试"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ['APPDATA'] = self.tmp
        os.makedirs(os.path.join(self.tmp, "lan-invoice", "data"), exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_server_starts_without_crash(self):
        s = McpServer()
        self.assertIsNotNone(s._db)
        self.assertTrue(os.path.isdir(s._data_dir))

    def test_server_creates_default_config_when_missing(self):
        s = McpServer()
        tags = s._config.tag_templates
        self.assertIn("企业号", tags)


class TestMcpProtocol(unittest.TestCase):
    """JSON-RPC 协议正确性测试"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ['APPDATA'] = self.tmp
        os.makedirs(os.path.join(self.tmp, "lan-invoice", "data"), exist_ok=True)
        self.s = McpServer()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ── initialize ───────────────────────────────

    def test_initialize_returns_correct_fields(self):
        r = self.s._handle({"id": 1, "method": "initialize"})
        result = r["result"]
        self.assertEqual(r["id"], 1)
        self.assertIn("protocolVersion", result)
        self.assertIn("capabilities", result)
        self.assertIn("tools", result["capabilities"])
        self.assertIn("resources", result["capabilities"])
        self.assertIn("serverInfo", result)
        self.assertTrue(result["serverInfo"]["version"])

    # ── tools/list ───────────────────────────────

    def test_tools_list_returns_9_tools(self):
        r = self.s._handle({"id": 1, "method": "tools/list"})
        tools = r["result"]["tools"]
        self.assertEqual(len(tools), 9)

    def test_tools_list_each_has_required_fields(self):
        r = self.s._handle({"id": 1, "method": "tools/list"})
        for t in r["result"]["tools"]:
            self.assertIn("name", t)
            self.assertIn("description", t)
            self.assertIn("inputSchema", t)

    # ── tools/call ───────────────────────────────

    def test_tools_call_unknown_tool_returns_error(self):
        r = self.s._handle({"id": 1, "method": "tools/call",
                           "params": {"name": "nonexist", "arguments": {}}})
        c = r["result"]["content"][0]
        self.assertTrue(r["result"].get("isError"))
        self.assertIn("Unknown tool", c["text"])

    def test_tools_call_missing_name(self):
        r = self.s._handle({"id": 1, "method": "tools/call",
                           "params": {}})
        c = r["result"]["content"][0]
        self.assertTrue(r["result"].get("isError"))

    # ── resources ────────────────────────────────

    def test_resources_list(self):
        r = self.s._handle({"id": 1, "method": "resources/list"})
        resources = r["result"]["resources"]
        self.assertEqual(len(resources), 3)

    def test_resources_read_unknown_uri(self):
        r = self.s._handle({"id": 1, "method": "resources/read",
                           "params": {"uri": "bad://"}})
        contents = r["result"]["contents"]
        self.assertTrue(len(contents) > 0)
        self.assertIn("Unknown", contents[0]["text"])

    # ── notifications ────────────────────────────

    def test_notification_returns_none(self):
        r = self.s._handle({"id": 1, "method": "notifications/initialized"})
        self.assertIsNone(r)

    # ── unknown method ───────────────────────────

    def test_unknown_method_returns_error(self):
        r = self.s._handle({"id": 1, "method": "bad_method"})
        self.assertIn("error", r)
        self.assertEqual(r["error"]["code"], -32601)


class TestSearchInvoices(unittest.TestCase):
    """search_invoices 全覆盖"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ['APPDATA'] = self.tmp
        os.makedirs(os.path.join(self.tmp, "lan-invoice", "data"), exist_ok=True)
        self.s = McpServer()
        self._seed_data()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _seed_data(self):
        invs = [
            Invoice(file="a.pdf", invoice_no="111", invoice_date="2025年01月15日",
                    invoice_type="增值税专用发票", buyer_name="测试公司A",
                    buyer_tax_id="TAX001", seller_name="销售方X",
                    amount="100.00", tax_rate="13%", tax_amount="13.00",
                    total="113.00", tags={"企业号": "A01"}, remark="ok"),
            Invoice(file="b.pdf", invoice_no="222", invoice_date="2025年03月20日",
                    invoice_type="增值税普通发票", buyer_name="测试公司B",
                    buyer_tax_id="TAX002", seller_name="销售方Y",
                    amount="200.00", tax_rate="6%", tax_amount="12.00",
                    total="212.00", tags={"企业号": "B02"}, remark=""),
            Invoice(file="c.pdf", invoice_no="333", invoice_date="2026年01月10日",
                    invoice_type="全电发票", buyer_name="测试公司C",
                    buyer_tax_id="TAX003", seller_name="销售方Z",
                    amount="500.00", tax_rate="13%", tax_amount="65.00",
                    total="565.00", tags={"企业号": "A01", "项目": "Q1"}, remark="急"),
        ]
        self.s._db.save(invs)

    def _call(self, tool, args):
        r = self.s._handle({"id": 1, "method": "tools/call",
                           "params": {"name": tool, "arguments": args}})
        return json.loads(r["result"]["content"][0]["text"])

    # ── 基础查询 ─────────────────────────────────

    def test_search_all_returns_all(self):
        result = self._call("search_invoices", {})
        self.assertEqual(result["count"], 3)
        self.assertEqual(result["returned"], 3)

    # ── 年份筛选 ─────────────────────────────────

    def test_filter_by_year(self):
        result = self._call("search_invoices", {"year": 2025})
        self.assertEqual(result["count"], 2)

    def test_filter_by_year_no_match(self):
        result = self._call("search_invoices", {"year": 2020})
        self.assertEqual(result["count"], 0)

    # ── 月份筛选 ─────────────────────────────────

    def test_filter_by_month(self):
        result = self._call("search_invoices", {"month": 1})
        self.assertEqual(result["count"], 2)  # 01月 ×2

    def test_filter_by_month_not_01(self):
        """确认月份筛选精确：month=3 不应匹配 01月"""
        result = self._call("search_invoices", {"month": 3})
        self.assertEqual(result["count"], 1)  # 只有 03月20日 一条

    # ── 发票类型 ─────────────────────────────────

    def test_filter_by_invoice_type(self):
        result = self._call("search_invoices", {"invoice_type": "增值税专用发票"})
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["records"][0]["invoice_no"], "111")

    # ── 销售方 ───────────────────────────────────

    def test_filter_by_seller(self):
        result = self._call("search_invoices", {"seller": "销售方X"})
        self.assertEqual(result["count"], 1)

    # ── 购买方 ───────────────────────────────────

    def test_filter_by_buyer_name(self):
        result = self._call("search_invoices", {"buyer": "测试公司A"})
        self.assertEqual(result["count"], 1)

    def test_filter_by_buyer_tax_id(self):
        result = self._call("search_invoices", {"buyer": "TAX001"})
        self.assertEqual(result["count"], 1)

    # ── 标签 ─────────────────────────────────────

    def test_filter_by_tag(self):
        result = self._call("search_invoices", {"tag": "A01"})
        self.assertEqual(result["count"], 2)

    def test_filter_by_tag_project(self):
        result = self._call("search_invoices", {"tag": "Q1"})
        self.assertEqual(result["count"], 1)

    # ── 关键字 ───────────────────────────────────

    def test_filter_by_keyword(self):
        result = self._call("search_invoices", {"keyword": "测试公司A"})
        self.assertEqual(result["count"], 1)

    # ── 组合筛选 ─────────────────────────────────

    def test_combined_filters(self):
        result = self._call("search_invoices", {"year": 2025, "month": 1, "invoice_type": "增值税专用发票"})
        self.assertEqual(result["count"], 1)

    # ── 排序 ─────────────────────────────────────

    def test_sort_by_amount_desc(self):
        result = self._call("search_invoices", {"sort_by": "amount", "sort_asc": False})
        self.assertEqual(result["records"][0]["amount"], "500.00")
        self.assertEqual(result["records"][-1]["amount"], "100.00")

    def test_sort_by_invoice_no_asc(self):
        result = self._call("search_invoices", {"sort_by": "invoice_no", "sort_asc": True})
        self.assertEqual(result["records"][0]["invoice_no"], "111")
        self.assertEqual(result["records"][2]["invoice_no"], "333")

    def test_sort_by_invalid_field_raises(self):
        r = self.s._handle({"id": 1, "method": "tools/call",
                           "params": {"name": "search_invoices",
                                      "arguments": {"sort_by": "bad_field"}}})
        self.assertTrue(r["result"].get("isError"))

    # ── 分页 ─────────────────────────────────────

    def test_pagination_limit(self):
        result = self._call("search_invoices", {"limit": 1})
        self.assertEqual(result["count"], 3)
        self.assertEqual(result["returned"], 1)

    def test_pagination_offset(self):
        result = self._call("search_invoices", {"limit": 1, "offset": 2})
        self.assertEqual(result["returned"], 1)
        self.assertEqual(result["records"][0]["invoice_no"], "333")

    # ── 分页合计为全量 ───────────────────────────

    def test_pagination_totals_are_full_count(self):
        result = self._call("search_invoices", {"limit": 1, "offset": 0})
        self.assertEqual(result["count"], 3)
        # 合计应为全部3条的和
        self.assertAlmostEqual(result["total_amount"], 800.00, places=2)

    # ── 边界值 ───────────────────────────────────

    def test_null_keyword_does_not_crash(self):
        result = self._call("search_invoices", {"keyword": None})
        self.assertEqual(result["count"], 3)

    def test_zero_limit(self):
        result = self._call("search_invoices", {"limit": 0})
        self.assertEqual(result["returned"], 0)

    def test_large_offset_returns_empty(self):
        result = self._call("search_invoices", {"offset": 999})
        self.assertEqual(result["returned"], 0)
        self.assertEqual(result["count"], 3)

    # ── 空数据库 ─────────────────────────────────

    def test_empty_database(self):
        self.s._db.save([])
        result = self._call("search_invoices", {})
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["total_amount"], 0)


class TestImportInvoice(unittest.TestCase):
    """import_invoice 全覆盖"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ['APPDATA'] = self.tmp
        os.makedirs(os.path.join(self.tmp, "lan-invoice", "data"), exist_ok=True)
        self.s = McpServer()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _call(self, args):
        r = self.s._handle({"id": 1, "method": "tools/call",
                           "params": {"name": "import_invoice", "arguments": args}})
        return json.loads(r["result"]["content"][0]["text"])

    # ── 必填参数 ─────────────────────────────────

    def test_missing_pdf_path(self):
        result = self._call({})
        self.assertIn("pdf_path", result.get("error", ""))

    def test_empty_pdf_path(self):
        result = self._call({"pdf_path": ""})
        self.assertIn("pdf_path", result.get("error", ""))

    # ── 文件不存在 ───────────────────────────────

    def test_nonexistent_pdf(self):
        result = self._call({"pdf_path": "/nonexistent/file.pdf"})
        self.assertIn("不存在", result["error"])

    # ── 非 PDF 文件 ──────────────────────────────

    def test_not_pdf_extension(self):
        p = os.path.join(self.tmp, "test.txt")
        with open(p, "w") as f:
            f.write("not a pdf")
        result = self._call({"pdf_path": p})
        self.assertIn("仅支持 PDF", result["error"])

    # ── 解析失败 ─────────────────────────────────

    def test_invalid_pdf_content(self):
        p = os.path.join(self.tmp, "bad.pdf")
        with open(p, "wb") as f:
            f.write(b"not a valid pdf")
        result = self._call({"pdf_path": p})
        self.assertEqual(result.get("status"), "parse_error")
        self.assertIn("parsed", result)

    # ── 带标签导入 ───────────────────────────────

    def test_import_with_tags(self):
        """需要有效 PDF 才能完整测试，此处测参数传递"""
        result = self._call({"pdf_path": "/nonexistent.pdf", "tags": {"企业号": "A01"}})
        # 文件不存在先报错，但不崩溃
        self.assertIn("不存在", result["error"])

    # ── null 参数 ────────────────────────────────

    def test_null_tags_does_not_crash(self):
        result = self._call({"pdf_path": "/nonexistent.pdf", "tags": None})
        self.assertIn("不存在", result["error"])


class TestManageTags(unittest.TestCase):
    """manage_tags 全覆盖"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ['APPDATA'] = self.tmp
        os.makedirs(os.path.join(self.tmp, "lan-invoice", "data"), exist_ok=True)
        self.s = McpServer()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _call(self, args):
        r = self.s._handle({"id": 1, "method": "tools/call",
                           "params": {"name": "manage_tags", "arguments": args}})
        return json.loads(r["result"]["content"][0]["text"])

    def test_list_tags(self):
        result = self._call({"action": "list"})
        self.assertIn("企业号", result["tags"])

    def test_add_tag(self):
        result = self._call({"action": "add", "tag_name": "项目名称"})
        self.assertIn("项目名称", result["tags"])
        self.assertIn("已添加", result["message"])

    def test_add_duplicate_tag(self):
        self._call({"action": "add", "tag_name": "项目A"})
        result = self._call({"action": "add", "tag_name": "项目A"})
        self.assertIn("已存在", result["message"])

    def test_delete_tag(self):
        self._call({"action": "add", "tag_name": "临时标签"})
        result = self._call({"action": "delete", "tag_name": "临时标签"})
        self.assertNotIn("临时标签", result["tags"])
        self.assertIn("已删除", result["message"])

    def test_delete_nonexistent_tag(self):
        result = self._call({"action": "delete", "tag_name": "不存在"})
        self.assertIn("不存在", result["message"])

    def test_missing_action(self):
        r = self.s._handle({"id": 1, "method": "tools/call",
                           "params": {"name": "manage_tags", "arguments": {}}})
        c = json.loads(r["result"]["content"][0]["text"])
        self.assertIn("action", c.get("error", ""))

    def test_unknown_action(self):
        result = self._call({"action": "invalid"})
        self.assertIn("未知操作", result["error"])

    def test_add_empty_tag_name(self):
        result = self._call({"action": "add", "tag_name": ""})
        self.assertIn("tag_name", result["error"])

    def test_null_tag_name(self):
        result = self._call({"action": "add", "tag_name": None})
        self.assertIn("tag_name", result["error"])

    def test_delete_empty_tag_name(self):
        result = self._call({"action": "delete", "tag_name": ""})
        self.assertIn("tag_name", result["error"])


class TestUpdateInvoice(unittest.TestCase):
    """update_invoice 全覆盖"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ['APPDATA'] = self.tmp
        os.makedirs(os.path.join(self.tmp, "lan-invoice", "data"), exist_ok=True)
        self.s = McpServer()
        self.s._db.save([Invoice(file="a.pdf", invoice_no="111", tags={}, remark="")])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _call(self, args):
        r = self.s._handle({"id": 1, "method": "tools/call",
                           "params": {"name": "update_invoice", "arguments": args}})
        return json.loads(r["result"]["content"][0]["text"])

    def test_set_tags(self):
        result = self._call({"invoice_no": "111", "tags": {"企业号": "A01"}})
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["invoice"]["tags"]["企业号"], "A01")

    def test_set_remark(self):
        result = self._call({"invoice_no": "111", "remark": "已对账"})
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["invoice"]["remark"], "已对账")

    def test_set_both_tags_and_remark(self):
        result = self._call({"invoice_no": "111", "tags": {"企业号": "B02", "项目": "Q2"}, "remark": "完成"})
        self.assertEqual(result["status"], "ok")
        self.assertIn("tags", result["changed"])
        self.assertIn("remark", result["changed"])

    def test_nonexistent_invoice(self):
        result = self._call({"invoice_no": "99999"})
        self.assertIn("未找到", result["error"])

    def test_missing_invoice_no(self):
        r = self.s._handle({"id": 1, "method": "tools/call",
                           "params": {"name": "update_invoice", "arguments": {}}})
        c = json.loads(r["result"]["content"][0]["text"])
        self.assertIn("invoice_no", c.get("error", ""))

    def test_empty_invoice_no(self):
        result = self._call({"invoice_no": ""})
        self.assertIn("invoice_no", result["error"])

    def test_null_tags(self):
        result = self._call({"invoice_no": "111", "tags": None})
        self.assertEqual(result.get("message", ""), "无变更")

    def test_no_changes(self):
        result = self._call({"invoice_no": "111"})
        self.assertEqual(result["message"], "无变更")

    def test_override_existing_tags(self):
        self._call({"invoice_no": "111", "tags": {"企业号": "A01"}})
        result = self._call({"invoice_no": "111", "tags": {"企业号": "ZZZ"}})
        self.assertEqual(result["invoice"]["tags"]["企业号"], "ZZZ")


class TestAddAttachment(unittest.TestCase):
    """add_attachment 全覆盖"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ['APPDATA'] = self.tmp
        os.makedirs(os.path.join(self.tmp, "lan-invoice", "data"), exist_ok=True)
        self.s = McpServer()
        self.s._db.save([Invoice(file="a.pdf", invoice_no="111")])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _call(self, args):
        r = self.s._handle({"id": 1, "method": "tools/call",
                           "params": {"name": "add_attachment", "arguments": args}})
        return json.loads(r["result"]["content"][0]["text"])

    def test_missing_invoice_no(self):
        result = self._call({"file_paths": ["/a.png"]})
        self.assertIn("invoice_no", result.get("error", ""))

    def test_empty_invoice_no(self):
        result = self._call({"invoice_no": "", "file_paths": ["/a.png"]})
        self.assertIn("invoice_no", result["error"])

    def test_missing_file_paths(self):
        result = self._call({"invoice_no": "111"})
        self.assertIn("file_paths", result.get("error", ""))

    def test_empty_file_paths(self):
        result = self._call({"invoice_no": "111", "file_paths": []})
        self.assertIn("file_paths", result["error"])

    def test_nonexistent_invoice(self):
        result = self._call({"invoice_no": "99999", "file_paths": ["/a.png"]})
        self.assertIn("未找到", result["error"])

    def test_files_not_exist(self):
        result = self._call({"invoice_no": "111", "file_paths": ["/nonexistent.png"]})
        self.assertIn("没有有效的文件", result.get("error", ""))

    def test_add_valid_file(self):
        p = os.path.join(self.tmp, "screenshot.png")
        with open(p, "w") as f:
            f.write("fake image")
        result = self._call({"invoice_no": "111", "file_paths": [p]})
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["added"], 1)
        self.assertEqual(result["total_attachments"], 1)

    def test_add_multiple_files(self):
        p1 = os.path.join(self.tmp, "a.png")
        p2 = os.path.join(self.tmp, "b.png")
        with open(p1, "w") as f:
            f.write("a")
        with open(p2, "w") as f:
            f.write("b")
        result = self._call({"invoice_no": "111", "file_paths": [p1, p2]})
        self.assertEqual(result["added"], 2)


class TestDeleteInvoice(unittest.TestCase):
    """delete_invoice 全覆盖"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ['APPDATA'] = self.tmp
        os.makedirs(os.path.join(self.tmp, "lan-invoice", "data"), exist_ok=True)
        self.s = McpServer()
        self.s._db.save([
            Invoice(file="a.pdf", invoice_no="111"),
            Invoice(file="b.pdf", invoice_no="222"),
        ])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _call(self, args):
        r = self.s._handle({"id": 1, "method": "tools/call",
                           "params": {"name": "delete_invoice", "arguments": args}})
        return json.loads(r["result"]["content"][0]["text"])

    def test_delete_existing(self):
        result = self._call({"invoice_no": "111"})
        self.assertEqual(result["status"], "ok")
        # 确认已删除
        invs = self.s._db.load()
        self.assertEqual(len(invs), 1)

    def test_delete_nonexistent(self):
        result = self._call({"invoice_no": "99999"})
        self.assertIn("未找到", result["error"])

    def test_missing_invoice_no(self):
        r = self.s._handle({"id": 1, "method": "tools/call",
                           "params": {"name": "delete_invoice", "arguments": {}}})
        c = json.loads(r["result"]["content"][0]["text"])
        self.assertIn("invoice_no", c.get("error", ""))

    def test_empty_invoice_no(self):
        result = self._call({"invoice_no": ""})
        self.assertIn("invoice_no", result["error"])

    def test_delete_twice(self):
        self._call({"invoice_no": "111"})
        result = self._call({"invoice_no": "111"})
        self.assertIn("未找到", result["error"])


class TestGetSummary(unittest.TestCase):
    """get_summary 全覆盖"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ['APPDATA'] = self.tmp
        os.makedirs(os.path.join(self.tmp, "lan-invoice", "data"), exist_ok=True)
        self.s = McpServer()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _call(self, args):
        r = self.s._handle({"id": 1, "method": "tools/call",
                           "params": {"name": "get_summary", "arguments": args}})
        return json.loads(r["result"]["content"][0]["text"])

    def test_empty_database(self):
        result = self._call({})
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["total_amount"], 0.0)
        self.assertEqual(result["total_tax"], 0.0)
        self.assertEqual(result["total_with_tax"], 0.0)
        self.assertEqual(result["by_type"], {})

    def test_with_data(self):
        self.s._db.save([Invoice(invoice_no="111", invoice_date="2025年01月01日",
                                  amount="100.00", tax_amount="13.00", total="113.00",
                                  invoice_type="增值税专用发票")])
        result = self._call({})
        self.assertEqual(result["count"], 1)
        self.assertAlmostEqual(result["total_amount"], 100.0)
        self.assertAlmostEqual(result["total_with_tax"], 113.0)

    def test_filtered_by_year(self):
        self.s._db.save([
            Invoice(invoice_no="111", invoice_date="2025年01月01日", amount="100.00", tax_amount="13.00", total="113.00"),
            Invoice(invoice_no="222", invoice_date="2026年06月01日", amount="200.00", tax_amount="26.00", total="226.00"),
        ])
        result = self._call({"year": 2025})
        self.assertEqual(result["count"], 1)
        self.assertAlmostEqual(result["total_amount"], 100.0)

    def test_filtered_by_month(self):
        self.s._db.save([
            Invoice(invoice_no="111", invoice_date="2025年01月01日", amount="100.00", tax_amount="0", total="100.00"),
            Invoice(invoice_no="222", invoice_date="2025年03月01日", amount="200.00", tax_amount="0", total="200.00"),
        ])
        result = self._call({"month": 1})
        self.assertEqual(result["count"], 1)

    def test_null_params(self):
        self.s._db.save([Invoice(invoice_no="111", invoice_date="2025年01月01日",
                                  amount="100.00", tax_amount="13.00", total="113.00")])
        result = self._call({"year": None, "month": None})
        self.assertEqual(result["count"], 1)

    def test_by_type_distribution(self):
        self.s._db.save([
            Invoice(invoice_no="111", invoice_type="增值税专用发票",
                    amount="100.00", tax_amount="13.00", total="113.00"),
            Invoice(invoice_no="222", invoice_type="增值税专用发票",
                    amount="200.00", tax_amount="26.00", total="226.00"),
            Invoice(invoice_no="333", invoice_type="全电发票",
                    amount="300.00", tax_amount="39.00", total="339.00"),
        ])
        result = self._call({})
        self.assertEqual(result["by_type"]["增值税专用发票"], 2)
        self.assertEqual(result["by_type"]["全电发票"], 1)


class TestExportExcel(unittest.TestCase):
    """export_excel 全覆盖"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ['APPDATA'] = self.tmp
        os.makedirs(os.path.join(self.tmp, "lan-invoice", "data"), exist_ok=True)
        self.s = McpServer()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _call(self, args):
        r = self.s._handle({"id": 1, "method": "tools/call",
                           "params": {"name": "export_excel", "arguments": args}})
        return json.loads(r["result"]["content"][0]["text"])

    def test_export_with_custom_path(self):
        self.s._db.save([Invoice(invoice_no="111")])
        out = os.path.join(self.tmp, "test.xlsx")
        result = self._call({"output_path": out})
        self.assertEqual(result["status"], "ok")
        self.assertTrue(os.path.exists(out))

    def test_export_invalid_directory(self):
        result = self._call({"output_path": "Z:\\_no_such_drive_\\file.xlsx"})
        self.assertIn("目录", result.get("error", ""))

    def test_export_with_filters(self):
        self.s._db.save([
            Invoice(invoice_no="111", invoice_date="2025年01月01日"),
            Invoice(invoice_no="222", invoice_date="2026年06月01日"),
        ])
        out = os.path.join(self.tmp, "filtered.xlsx")
        result = self._call({"output_path": out, "year": 2025})
        self.assertEqual(result["status"], "ok")


class TestCheckUpdate(unittest.TestCase):
    """check_update 全覆盖"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ['APPDATA'] = self.tmp
        os.makedirs(os.path.join(self.tmp, "lan-invoice", "data"), exist_ok=True)
        self.s = McpServer()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _call(self):
        r = self.s._handle({"id": 1, "method": "tools/call",
                           "params": {"name": "check_update", "arguments": {}}})
        return json.loads(r["result"]["content"][0]["text"])

    def test_check_update_returns_fields(self):
        result = self._call()
        self.assertIn("current", result)
        self.assertIn("latest", result)
        self.assertIn("has_newer", result)

    def test_check_update_current_is_version(self):
        from version import APP_VERSION
        result = self._call()
        self.assertEqual(result["current"], APP_VERSION)


class TestResourcesRead(unittest.TestCase):
    """resources/read 全覆盖"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ['APPDATA'] = self.tmp
        os.makedirs(os.path.join(self.tmp, "lan-invoice", "data"), exist_ok=True)
        self.s = McpServer()
        self.s._db.save([Invoice(invoice_no="111", file="a.pdf")])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_read_all(self):
        r = self.s._handle({"id": 1, "method": "resources/read",
                           "params": {"uri": "invoices://all"}})
        self.assertIn("contents", r["result"])
        data = json.loads(r["result"]["contents"][0]["text"])
        self.assertEqual(len(data), 1)

    def test_read_summary(self):
        r = self.s._handle({"id": 1, "method": "resources/read",
                           "params": {"uri": "invoices://summary"}})
        data = json.loads(r["result"]["contents"][0]["text"])
        self.assertEqual(data["count"], 1)

    def test_read_tags(self):
        r = self.s._handle({"id": 1, "method": "resources/read",
                           "params": {"uri": "invoices://tags"}})
        data = json.loads(r["result"]["contents"][0]["text"])
        self.assertIn("企业号", data)

    def test_read_unknown(self):
        r = self.s._handle({"id": 1, "method": "resources/read",
                           "params": {"uri": "bad://"}})
        self.assertIn("contents", r["result"])


class TestMcpEdgeCases(unittest.TestCase):
    """边界及异常值测试"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ['APPDATA'] = self.tmp
        os.makedirs(os.path.join(self.tmp, "lan-invoice", "data"), exist_ok=True)
        self.s = McpServer()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _call(self, tool, args):
        r = self.s._handle({"id": 1, "method": "tools/call",
                           "params": {"name": tool, "arguments": args}})
        return json.loads(r["result"]["content"][0]["text"])

    # ── 空参数 ────────────────────────────────────

    def test_empty_arguments_not_crash(self):
        for tool in ["search_invoices", "get_summary", "check_update"]:
            r = self.s._handle({"id": 1, "method": "tools/call",
                               "params": {"name": tool, "arguments": {}}})
            self.assertNotIn("error", r.get("result", {}),
                            f"Tool {tool} should not error with empty args")

    # ── None 参数 ─────────────────────────────────

    def test_none_arguments(self):
        c = self._call("search_invoices", None)
        self.assertEqual(c["count"], 0)

    # ── 特殊字符 ──────────────────────────────────

    def test_special_chars_in_search(self):
        self.s._db.save([Invoice(invoice_no="111", seller_name="公司<>&\"'")])
        result = self._call("search_invoices", {"keyword": "公司"})
        self.assertEqual(result["count"], 1)

    # ── Unicode ───────────────────────────────────

    def test_unicode_in_tags(self):
        from models import Invoice
        self.s._db.save([Invoice(invoice_no="111", tags={"测试": "值"})])
        r = self.s._handle({"id": 1, "method": "tools/call",
                           "params": {"name": "update_invoice",
                                      "arguments": {"invoice_no": "111",
                                                    "tags": {"标签名": "中文内容"}}}})
        c = json.loads(r["result"]["content"][0]["text"])
        self.assertEqual(c["status"], "ok")

    # ── 大批量参数 ────────────────────────────────

    def test_large_offset_handled(self):
        result = self._call("search_invoices", {"limit": 1000, "offset": 10000})
        self.assertEqual(result["returned"], 0)

    # ── request with no id ────────────────────────

    def test_request_without_id(self):
        r = self.s._handle({"method": "initialize"})
        self.assertIn("result", r)

    # ── VALID_SORT_FIELDS ─────────────────────────

    def test_valid_sort_fields(self):
        self.assertIn("amount", VALID_SORT_FIELDS)
        self.assertIn("invoice_date", VALID_SORT_FIELDS)
        self.assertNotIn("bad", VALID_SORT_FIELDS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
