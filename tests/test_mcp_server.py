# -*- coding: utf-8 -*-
"""MCP Server 全覆盖测试 — 每条用例验证实际行为，不假覆盖"""

import sys
import os
import json
import tempfile
import shutil
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from mcp_server import McpServer, VALID_SORT_FIELDS
from models import Invoice


def _make_real_pdf(tmpdir, filename="test.pdf", text=None):
    """创建 pdfplumber 可解析的真实 PDF"""
    import fitz
    if text is None:
        text = ("发票号码: 12345678\n开票日期: 2025年06月26日\n"
                "名称: 测试公司\n纳税人识别号: 91350700156534567X\n"
                "销售方名称: 销售方测试\n金额: 1000.00\n税率: 13%\n"
                "税额: 130.00\n价税合计: 1130.00")
    p = os.path.join(tmpdir, filename)
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(50, 50, 500, 300), text,
                        fontsize=11, fontname='china-s')
    doc.save(p)
    doc.close()
    return p


class TestMcpProtocol(unittest.TestCase):
    """JSON-RPC 协议正确性"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ['APPDATA'] = self.tmp
        os.makedirs(os.path.join(self.tmp, "lan-invoice", "data"), exist_ok=True)
        self.s = McpServer()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_initialize_returns_correct_structure(self):
        r = self.s._handle({"id": 1, "method": "initialize"})
        result = r["result"]
        self.assertIn("protocolVersion", result)
        self.assertIn("tools", result["capabilities"])
        self.assertIn("resources", result["capabilities"])
        self.assertEqual(result["serverInfo"]["name"], "invoice-tool")

    def test_tools_list_returns_10_tools(self):
        r = self.s._handle({"id": 1, "method": "tools/list"})
        self.assertEqual(len(r["result"]["tools"]), 10)

    def test_tools_call_unknown_returns_isError(self):
        r = self.s._handle({"id": 1, "method": "tools/call",
                           "params": {"name": "nonexist", "arguments": {}}})
        self.assertTrue(r["result"]["isError"])
        c = json.loads(r["result"]["content"][0]["text"])
        self.assertIn("Unknown", c["error"])

    def test_resources_list_has_3_endpoints(self):
        r = self.s._handle({"id": 1, "method": "resources/list"})
        uris = [x["uri"] for x in r["result"]["resources"]]
        self.assertIn("invoices://all", uris)
        self.assertIn("invoices://summary", uris)
        self.assertIn("invoices://tags", uris)

    def test_resources_read_unknown_returns_text(self):
        r = self.s._handle({"id": 1, "method": "resources/read",
                           "params": {"uri": "bad://"}})
        self.assertIn("Unknown", r["result"]["contents"][0]["text"])

    def test_notification_returns_none(self):
        r = self.s._handle({"id": 1, "method": "notifications/initialized"})
        self.assertIsNone(r)

    def test_unknown_method_returns_error(self):
        r = self.s._handle({"id": 1, "method": "bad"})
        self.assertEqual(r["error"]["code"], -32601)


class TestSearchInvoices(unittest.TestCase):
    """search_invoices — 验证筛选、排序、分页逻辑正确性"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ['APPDATA'] = self.tmp
        os.makedirs(os.path.join(self.tmp, "lan-invoice", "data"), exist_ok=True)
        self.s = McpServer()
        self.s._db.save([
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
        ])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _call(self, args):
        r = self.s._handle({"id": 1, "method": "tools/call",
                           "params": {"name": "search_invoices", "arguments": args}})
        return json.loads(r["result"]["content"][0]["text"])

    def test_search_all(self):
        r = self._call({})
        self.assertEqual(r["count"], 3)

    def test_filter_by_year(self):
        r = self._call({"year": 2025})
        self.assertEqual(r["count"], 2)
        for rec in r["records"]:
            self.assertIn("2025", rec["invoice_date"])

    def test_filter_by_year_no_match(self):
        r = self._call({"year": 2020})
        self.assertEqual(r["count"], 0)

    def test_filter_by_month(self):
        r = self._call({"month": 1})
        self.assertEqual(r["count"], 2)
        for rec in r["records"]:
            self.assertIn("01月", rec["invoice_date"])

    def test_filter_by_month_only_matches_exact(self):
        """month=3 应只匹配 03月，不应匹配 01月"""
        r = self._call({"month": 3})
        self.assertEqual(r["count"], 1)
        self.assertIn("03月", r["records"][0]["invoice_date"])

    def test_filter_by_invoice_type(self):
        r = self._call({"invoice_type": "增值税专用发票"})
        self.assertEqual(r["count"], 1)
        self.assertEqual(r["records"][0]["invoice_no"], "111")

    def test_filter_by_seller(self):
        r = self._call({"seller": "销售方X"})
        self.assertEqual(r["count"], 1)

    def test_filter_by_buyer_name(self):
        r = self._call({"buyer": "测试公司A"})
        self.assertEqual(r["count"], 1)

    def test_filter_by_buyer_tax_id(self):
        r = self._call({"buyer": "TAX001"})
        self.assertEqual(r["count"], 1)

    def test_filter_by_tag(self):
        r = self._call({"tag": "A01"})
        self.assertEqual(r["count"], 2)

    def test_filter_by_keyword(self):
        r = self._call({"keyword": "测试公司A"})
        self.assertEqual(r["count"], 1)

    def test_combined_filters(self):
        r = self._call({"year": 2025, "month": 1, "invoice_type": "增值税专用发票"})
        self.assertEqual(r["count"], 1)

    def test_sort_by_amount_desc(self):
        r = self._call({"sort_by": "amount", "sort_asc": False})
        amounts = [rec["amount"] for rec in r["records"]]
        self.assertEqual(amounts, ["500.00", "200.00", "100.00"])

    def test_sort_by_invoice_no_asc(self):
        r = self._call({"sort_by": "invoice_no", "sort_asc": True})
        nos = [rec["invoice_no"] for rec in r["records"]]
        self.assertEqual(nos, ["111", "222", "333"])

    def test_sort_by_invalid_field_returns_error(self):
        r = self.s._handle({"id": 1, "method": "tools/call",
                           "params": {"name": "search_invoices",
                                      "arguments": {"sort_by": "bad_field"}}})
        self.assertTrue(r["result"]["isError"])

    def test_pagination(self):
        r = self._call({"limit": 1, "offset": 0})
        self.assertEqual(r["count"], 3)
        self.assertEqual(r["returned"], 1)
        self.assertEqual(r["records"][0]["invoice_no"], "111")

    def test_pagination_offset(self):
        r = self._call({"limit": 1, "offset": 2})
        self.assertEqual(r["returned"], 1)
        self.assertEqual(r["records"][0]["invoice_no"], "333")

    def test_pagination_totals_are_full_count(self):
        """分页时合计金额为全部匹配记录的和，非仅当前页"""
        r = self._call({"limit": 1, "offset": 0})
        self.assertAlmostEqual(r["total_amount"], 800.00)
        self.assertAlmostEqual(r["total_tax"], 90.00)
        self.assertAlmostEqual(r["total_with_tax"], 890.00)

    def test_empty_database(self):
        self.s._db.save([])
        r = self._call({})
        self.assertEqual(r["count"], 0)
        self.assertEqual(r["total_amount"], 0)

    def test_zero_limit(self):
        r = self._call({"limit": 0})
        self.assertEqual(r["returned"], 0)
        self.assertEqual(r["count"], 3)


class TestImportInvoice(unittest.TestCase):
    """import_invoice — 包含真实 PDF 导入成功路径"""

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

    def test_import_real_pdf(self):
        p = _make_real_pdf(self.tmp)
        r = self._call({"pdf_path": p})
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["invoice"]["invoice_no"], "12345678")
        self.assertEqual(r["invoice"]["buyer_name"], "测试公司")
        self.assertEqual(r["invoice"]["amount"], "1000.00")
        self.assertEqual(len(self.s._db.load()), 1)

    def test_import_with_tags_and_remark(self):
        p = _make_real_pdf(self.tmp, "tagged.pdf")
        r = self._call({"pdf_path": p, "tags": {"企业号": "14786", "项目": "Q1"},
                        "remark": "测试备注"})
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["invoice"]["tags"]["企业号"], "14786")
        self.assertEqual(r["invoice"]["tags"]["项目"], "Q1")
        self.assertEqual(r["invoice"]["remark"], "测试备注")

    def test_import_duplicate(self):
        p = _make_real_pdf(self.tmp)
        self._call({"pdf_path": p})
        r = self._call({"pdf_path": p})
        self.assertEqual(r["status"], "duplicate")
        self.assertEqual(len(self.s._db.load()), 1)

    def test_missing_pdf_path(self):
        r = self._call({})
        self.assertIn("文件不存在", r["error"])

    def test_nonexistent_file(self):
        r = self._call({"pdf_path": os.path.join(self.tmp, "no.pdf")})
        self.assertIn("不存在", r["error"])

    def test_not_pdf_extension(self):
        p = os.path.join(self.tmp, "test.txt")
        with open(p, "w") as f:
            f.write("x")
        r = self._call({"pdf_path": p})
        self.assertIn("仅支持 PDF", r["error"])

    def test_corrupt_pdf(self):
        p = os.path.join(self.tmp, "bad.pdf")
        with open(p, "wb") as f:
            f.write(b"not a valid pdf")
        r = self._call({"pdf_path": p})
        self.assertEqual(r.get("status"), "parse_error")

    def test_null_tags_ok(self):
        r = self._call({"pdf_path": "/x.pdf", "tags": None})
        self.assertIn("不存在", r["error"])


class TestManageTags(unittest.TestCase):
    """manage_tags — 标签模板增删查"""

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

    def test_list_default(self):
        r = self._call({"action": "list"})
        self.assertIn("企业号", r["tags"])

    def test_add_and_list(self):
        self._call({"action": "add", "tag_name": "项目名称"})
        r = self._call({"action": "list"})
        self.assertIn("项目名称", r["tags"])

    def test_add_duplicate(self):
        self._call({"action": "add", "tag_name": "A"})
        r = self._call({"action": "add", "tag_name": "A"})
        self.assertIn("已存在", r["message"])

    def test_delete(self):
        self._call({"action": "add", "tag_name": "临时"})
        r = self._call({"action": "delete", "tag_name": "临时"})
        self.assertNotIn("临时", r["tags"])
        self.assertIn("已删除", r["message"])

    def test_delete_nonexistent(self):
        r = self._call({"action": "delete", "tag_name": "X"})
        self.assertIn("不存在", r["message"])

    def test_missing_action(self):
        r = self.s._handle({"id": 1, "method": "tools/call",
                           "params": {"name": "manage_tags", "arguments": {}}})
        c = json.loads(r["result"]["content"][0]["text"])
        self.assertIn("未知操作", c["error"])

    def test_unknown_action(self):
        r = self._call({"action": "invalid"})
        self.assertIn("未知操作", r["error"])

    def test_add_empty_name(self):
        r = self._call({"action": "add", "tag_name": ""})
        self.assertIn("tag_name", r["error"])

    def test_add_null_name(self):
        r = self._call({"action": "add", "tag_name": None})
        self.assertIn("tag_name", r["error"])


class TestUpdateInvoice(unittest.TestCase):
    """update_invoice — 修改发票标签和备注"""

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
        r = self._call({"invoice_no": "111", "tags": {"企业号": "A01"}})
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["invoice"]["tags"]["企业号"], "A01")
        # 确认持久化
        invs = self.s._db.load()
        self.assertEqual(invs[0].tags["企业号"], "A01")

    def test_set_remark(self):
        r = self._call({"invoice_no": "111", "remark": "已对账"})
        self.assertEqual(r["status"], "ok")
        invs = self.s._db.load()
        self.assertEqual(invs[0].remark, "已对账")

    def test_set_both(self):
        r = self._call({"invoice_no": "111", "tags": {"企业号": "B02"}, "remark": "done"})
        self.assertIn("tags", r["changed"])
        self.assertIn("remark", r["changed"])

    def test_nonexistent(self):
        r = self._call({"invoice_no": "99999"})
        self.assertIn("未找到", r["error"])

    def test_missing_invoice_no(self):
        r = self.s._handle({"id": 1, "method": "tools/call",
                           "params": {"name": "update_invoice", "arguments": {}}})
        c = json.loads(r["result"]["content"][0]["text"])
        self.assertIn("未找到发票号", c["error"])

    def test_null_tags_noop(self):
        r = self._call({"invoice_no": "111", "tags": None})
        self.assertEqual(r["message"], "无变更")

    def test_no_params_noop(self):
        r = self._call({"invoice_no": "111"})
        self.assertEqual(r["message"], "无变更")


class TestAddAttachment(unittest.TestCase):
    """add_attachment — 给发票添加附件文件"""

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
        r = self._call({"file_paths": ["/a.png"]})
        self.assertIn("未找到发票号", r["error"])

    def test_missing_file_paths(self):
        r = self._call({"invoice_no": "111"})
        self.assertIn("file_paths", r.get("error", ""))

    def test_nonexistent_invoice(self):
        r = self._call({"invoice_no": "999", "file_paths": ["/a.png"]})
        self.assertIn("未找到", r["error"])

    def test_no_valid_files(self):
        r = self._call({"invoice_no": "111", "file_paths": ["/no.png"]})
        self.assertIn("没有有效的文件", r.get("error", ""))

    def test_add_one_file(self):
        p = os.path.join(self.tmp, "s.png")
        with open(p, "w") as f:
            f.write("img")
        r = self._call({"invoice_no": "111", "file_paths": [p]})
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["added"], 1)
        self.assertEqual(r["total_attachments"], 1)
        # 确认文件被复制到数据目录
        invs = self.s._db.load()
        self.assertEqual(len(invs[0].attachments), 1)
        self.assertTrue(os.path.exists(invs[0].attachments[0]))

    def test_add_multiple_files(self):
        p1 = os.path.join(self.tmp, "a.png")
        p2 = os.path.join(self.tmp, "b.png")
        for p in (p1, p2):
            with open(p, "w") as f:
                f.write("x")
        r = self._call({"invoice_no": "111", "file_paths": [p1, p2]})
        self.assertEqual(r["added"], 2)


class TestDeleteInvoice(unittest.TestCase):
    """delete_invoice — 删除记录"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ['APPDATA'] = self.tmp
        os.makedirs(os.path.join(self.tmp, "lan-invoice", "data"), exist_ok=True)
        self.s = McpServer()
        self.s._db.save([Invoice(file="a.pdf", invoice_no="111"),
                          Invoice(file="b.pdf", invoice_no="222")])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _call(self, args):
        r = self.s._handle({"id": 1, "method": "tools/call",
                           "params": {"name": "delete_invoice", "arguments": args}})
        return json.loads(r["result"]["content"][0]["text"])

    def test_delete_existing(self):
        r = self._call({"invoice_no": "111"})
        self.assertEqual(r["status"], "ok")
        self.assertEqual(len(self.s._db.load()), 1)

    def test_delete_nonexistent(self):
        r = self._call({"invoice_no": "999"})
        self.assertIn("未找到", r["error"])

    def test_delete_twice(self):
        self._call({"invoice_no": "111"})
        r = self._call({"invoice_no": "111"})
        self.assertIn("未找到", r["error"])

    def test_missing_invoice_no(self):
        r = self.s._handle({"id": 1, "method": "tools/call",
                           "params": {"name": "delete_invoice", "arguments": {}}})
        c = json.loads(r["result"]["content"][0]["text"])
        self.assertIn("未找到发票号", c["error"])


class TestGetSummary(unittest.TestCase):
    """get_summary — 统计摘要"""

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
        r = self._call({})
        self.assertEqual(r["count"], 0)
        self.assertIsInstance(r["total_amount"], float)

    def test_with_invoices(self):
        self.s._db.save([
            Invoice(invoice_no="111", invoice_date="2025年01月01日",
                    amount="100.00", tax_amount="13.00", total="113.00",
                    invoice_type="增值税专用发票"),
            Invoice(invoice_no="222", invoice_date="2025年01月02日",
                    amount="200.00", tax_amount="26.00", total="226.00",
                    invoice_type="增值税专用发票"),
        ])
        r = self._call({})
        self.assertEqual(r["count"], 2)
        self.assertAlmostEqual(r["total_amount"], 300.0)
        self.assertAlmostEqual(r["total_tax"], 39.0)
        self.assertAlmostEqual(r["total_with_tax"], 339.0)
        self.assertEqual(r["by_type"]["增值税专用发票"], 2)

    def test_filtered_by_year(self):
        self.s._db.save([
            Invoice(invoice_no="111", invoice_date="2025年01月01日",
                    amount="100.00", tax_amount="0", total="100.00"),
            Invoice(invoice_no="222", invoice_date="2026年06月01日",
                    amount="200.00", tax_amount="0", total="200.00"),
        ])
        r = self._call({"year": 2025})
        self.assertEqual(r["count"], 1)

    def test_filtered_by_month(self):
        self.s._db.save([
            Invoice(invoice_no="111", invoice_date="2025年01月01日",
                    amount="100.00", tax_amount="0", total="100.00"),
            Invoice(invoice_no="222", invoice_date="2025年03月01日",
                    amount="200.00", tax_amount="0", total="200.00"),
        ])
        r = self._call({"month": 1})
        self.assertEqual(r["count"], 1)


class TestExportExcel(unittest.TestCase):
    """export_excel — 导出 Excel 文件"""

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

    def test_export_success(self):
        self.s._db.save([Invoice(invoice_no="111")])
        out = os.path.join(self.tmp, "test.xlsx")
        r = self._call({"output_path": out})
        self.assertEqual(r["status"], "ok")
        self.assertTrue(os.path.exists(out))
        self.assertGreater(os.path.getsize(out), 0)

    def test_export_with_filter(self):
        self.s._db.save([
            Invoice(invoice_no="111", invoice_date="2025年01月01日"),
            Invoice(invoice_no="222", invoice_date="2026年06月01日"),
        ])
        out = os.path.join(self.tmp, "f.xlsx")
        r = self._call({"output_path": out, "year": 2025})
        self.assertEqual(r["status"], "ok")

    def test_export_invalid_dir(self):
        r = self._call({"output_path": "Z:\\_no_\\file.xlsx"})
        self.assertIn("目录", r.get("error", ""))


class TestCheckUpdate(unittest.TestCase):
    """check_update — 版本检查"""

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

    def test_returns_required_fields(self):
        r = self._call()
        self.assertIn("current", r)
        self.assertIn("latest", r)
        self.assertIn("has_newer", r)
        from version import APP_VERSION
        self.assertEqual(r["current"], APP_VERSION)


class TestResourcesRead(unittest.TestCase):
    """resources/read — 资源读取"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ['APPDATA'] = self.tmp
        os.makedirs(os.path.join(self.tmp, "lan-invoice", "data"), exist_ok=True)
        self.s = McpServer()
        self.s._db.save([Invoice(invoice_no="111", file="a.pdf")])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _read(self, uri):
        r = self.s._handle({"id": 1, "method": "resources/read",
                           "params": {"uri": uri}})
        return json.loads(r["result"]["contents"][0]["text"])

    def test_read_all(self):
        data = self._read("invoices://all")
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["invoice_no"], "111")

    def test_read_summary(self):
        data = self._read("invoices://summary")
        self.assertEqual(data["count"], 1)

    def test_read_tags(self):
        data = self._read("invoices://tags")
        self.assertIn("企业号", data)

    def test_read_unknown(self):
        r = self.s._handle({"id": 1, "method": "resources/read",
                           "params": {"uri": "bad://"}})
        self.assertIn("Unknown", r["result"]["contents"][0]["text"])


class TestEdgeCases(unittest.TestCase):
    """边界及异常值"""

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

    def test_empty_args_safe_for_readonly_tools(self):
        for tool in ["search_invoices", "get_summary", "check_update"]:
            r = self._call(tool, {})
            self.assertNotIn("error", r, f"{tool} should handle empty args")

    def test_none_args_treated_as_empty(self):
        r = self._call("search_invoices", None)
        self.assertIn("count", r)  # 不报错，正常返回

    def test_special_chars_in_data(self):
        self.s._db.save([Invoice(invoice_no="111",
                                  seller_name="公司<>&\"'",
                                  buyer_name="买方\x00中文")])
        r = self._call("search_invoices", {})
        self.assertEqual(r["count"], 1)

    def test_unicode_tags_roundtrip(self):
        self.s._db.save([Invoice(invoice_no="111", tags={})])
        self.s._handle({"id": 1, "method": "tools/call",
                       "params": {"name": "update_invoice",
                                  "arguments": {"invoice_no": "111",
                                                "tags": {"标签": "中文内容中文内容"}}}})
        invs = self.s._db.load()
        self.assertEqual(invs[0].tags["标签"], "中文内容中文内容")

    def test_large_offset_no_crash(self):
        self.s._db.save([Invoice(invoice_no="111")])
        r = self._call("search_invoices", {"limit": 10, "offset": 9999})
        self.assertEqual(r["returned"], 0)

    def test_request_without_id_still_works(self):
        r = self.s._handle({"method": "initialize"})
        self.assertIn("result", r)

    def test_valid_sort_fields_constant(self):
        self.assertIn("amount", VALID_SORT_FIELDS)
        self.assertIn("invoice_no", VALID_SORT_FIELDS)
        self.assertNotIn("__class__", VALID_SORT_FIELDS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
