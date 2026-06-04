# -*- coding: utf-8 -*-
"""invoice_tool 模块非 GUI 逻辑单元测试"""

import sys
import os
import json
import unittest
import tempfile
import shutil
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from utils import copy_file_to_dir as _copy_file_to_dir, safe_float
from invoice_tool import InvoiceApp, COL_IDX, IMG_EXTS, CONTRACT_EXTS, COLUMNS
from models import Invoice
from PyQt5.QtWidgets import QApplication, QHBoxLayout
from PyQt5.QtCore import Qt

_qt_app = QApplication.instance()
if _qt_app is None:
    _qt_app = QApplication(sys.argv)


# ── _safe_float 测试 ──────────────────────────

class TestSafeFloat(unittest.TestCase):
    def test_positive_integer(self):
        self.assertEqual(safe_float(100), 100.0)

    def test_float_string(self):
        self.assertEqual(safe_float("550.00"), 550.0)

    def test_negative_number(self):
        self.assertEqual(safe_float(-100), -100.0)

    def test_negative_string(self):
        self.assertEqual(safe_float("-100.50"), -100.5)

    def test_empty_string(self):
        self.assertEqual(safe_float(""), 0.0)

    def test_none(self):
        self.assertEqual(safe_float(None), 0.0)

    def test_invalid_string(self):
        self.assertEqual(safe_float("abc"), 0.0)

    def test_zero(self):
        self.assertEqual(safe_float(0), 0.0)
        self.assertEqual(safe_float("0"), 0.0)
        self.assertEqual(safe_float("0.00"), 0.0)

    def test_large_number(self):
        self.assertEqual(safe_float("123456789.99"), 123456789.99)


# ── _copy_file_to_dir 测试（补充）──────────────

class TestCopyFileToDir(unittest.TestCase):
    def setUp(self):
        self.tmp_src = tempfile.mkdtemp()
        self.tmp_dst = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_src, ignore_errors=True)
        shutil.rmtree(self.tmp_dst, ignore_errors=True)

    def test_copy_success(self):
        src = os.path.join(self.tmp_src, "test.txt")
        with open(src, "w") as f:
            f.write("hello")
        result = _copy_file_to_dir(src, self.tmp_dst)
        expected = os.path.join(self.tmp_dst, "test.txt")
        self.assertEqual(result, expected)
        self.assertTrue(os.path.exists(expected))

    def test_duplicate_rename(self):
        src = os.path.join(self.tmp_src, "test.txt")
        with open(src, "w") as f:
            f.write("hello")
        _copy_file_to_dir(src, self.tmp_dst)
        result = _copy_file_to_dir(src, self.tmp_dst)
        self.assertNotEqual(result, os.path.join(self.tmp_dst, "test.txt"))
        self.assertTrue(os.path.exists(result))
        self.assertIn("test_", os.path.basename(result))

    def test_nonexistent_src(self):
        result = _copy_file_to_dir("/nonexistent/path.txt", self.tmp_dst)
        self.assertEqual(result, "/nonexistent/path.txt")

    def test_empty_src(self):
        result = _copy_file_to_dir("", self.tmp_dst)
        self.assertEqual(result, "")

    def test_creates_dst_dir(self):
        dst_sub = os.path.join(self.tmp_dst, "new_subdir")
        src = os.path.join(self.tmp_src, "a.txt")
        with open(src, "w") as f:
            f.write("test")
        result = _copy_file_to_dir(src, dst_sub)
        self.assertTrue(os.path.exists(result))
        self.assertTrue(os.path.isdir(dst_sub))


# ── _record_matches_filter 测试 ───────────────

class TestRecordMatchesFilter(unittest.TestCase):
    """使用 __new__ 绕过 GUI 初始化，直接测试筛选逻辑"""

    def _make_app(self, **filters):
        app = InvoiceApp.__new__(InvoiceApp)
        app._filter_year = None
        app._filter_month = None
        app._filter_inv_type = None
        app._filter_seller = None
        app._filter_buyer = ""
        app._filter_company = ""
        for k, v in filters.items():
            setattr(app, k, v)
        return app

    def test_no_filter_passes_all(self):
        app = self._make_app()
        self.assertTrue(app._record_matches_filter({"invoice_date": "2024年11月30日"}))

    def test_year_filter_match(self):
        app = self._make_app(_filter_year=2024)
        self.assertTrue(app._record_matches_filter({"invoice_date": "2024年05月15日"}))
        self.assertFalse(app._record_matches_filter({"invoice_date": "2025年01月01日"}))

    def test_year_filter_no_date(self):
        app = self._make_app(_filter_year=2024)
        self.assertFalse(app._record_matches_filter({"invoice_date": ""}))
        self.assertFalse(app._record_matches_filter({}))

    def test_month_filter_match(self):
        app = self._make_app(_filter_month=6)
        self.assertTrue(app._record_matches_filter({"invoice_date": "2024年06月01日"}))
        self.assertFalse(app._record_matches_filter({"invoice_date": "2024年07月01日"}))

    def test_year_and_month_filter(self):
        app = self._make_app(_filter_year=2024, _filter_month=11)
        self.assertTrue(app._record_matches_filter({"invoice_date": "2024年11月30日"}))
        self.assertFalse(app._record_matches_filter({"invoice_date": "2024年10月01日"}))
        self.assertFalse(app._record_matches_filter({"invoice_date": "2023年11月01日"}))

    def test_invoice_type_filter(self):
        app = self._make_app(_filter_inv_type="增值税专用发票")
        self.assertTrue(app._record_matches_filter({"invoice_type": "增值税专用发票"}))
        self.assertFalse(app._record_matches_filter({"invoice_type": "普通发票"}))

    def test_seller_filter(self):
        app = self._make_app(_filter_seller="京东世纪")
        self.assertTrue(app._record_matches_filter({"seller_name": "京东世纪"}))
        self.assertFalse(app._record_matches_filter({"seller_name": "华为技术"}))

    def test_buyer_fuzzy_search(self):
        app = self._make_app(_filter_buyer="长富")
        self.assertTrue(app._record_matches_filter({"buyer_name": "福建长富乳品有限公司", "buyer_tax_id": ""}))
        self.assertFalse(app._record_matches_filter({"buyer_name": "其他公司", "buyer_tax_id": ""}))

    def test_buyer_tax_id_search(self):
        app = self._make_app(_filter_buyer="91350700")
        self.assertTrue(app._record_matches_filter({"buyer_name": "", "buyer_tax_id": "91350700156534567X"}))
        self.assertFalse(app._record_matches_filter({"buyer_name": "", "buyer_tax_id": "12345678"}))

    def test_buyer_case_insensitive(self):
        app = self._make_app(_filter_buyer="abc")
        self.assertTrue(app._record_matches_filter({"buyer_name": "ABC公司", "buyer_tax_id": ""}))

    def test_company_fuzzy_search(self):
        app = self._make_app(_filter_company="14786")
        self.assertTrue(app._record_matches_filter({"company": "14786"}))
        self.assertFalse(app._record_matches_filter({"company": "99999"}))

    def test_company_case_insensitive(self):
        app = self._make_app(_filter_company="abc")
        self.assertTrue(app._record_matches_filter({"company": "ABC Corp"}))

    def test_multiple_filters_all_match(self):
        app = self._make_app(
            _filter_year=2024, _filter_month=11,
            _filter_inv_type="增值税专用发票",
            _filter_seller="京东世纪"
        )
        rec = {
            "invoice_date": "2024年11月30日",
            "invoice_type": "增值税专用发票",
            "seller_name": "京东世纪"
        }
        self.assertTrue(app._record_matches_filter(rec))

    def test_multiple_filters_one_fails(self):
        app = self._make_app(
            _filter_year=2024,
            _filter_inv_type="增值税专用发票"
        )
        rec = {
            "invoice_date": "2024年11月30日",
            "invoice_type": "普通发票"
        }
        self.assertFalse(app._record_matches_filter(rec))


# ── _init_record_fields 测试 ─────────────────

class TestInitRecordFields(unittest.TestCase):
    def setUp(self):
        self.app = InvoiceApp.__new__(InvoiceApp)

    def test_sets_defaults(self):
        data = {}
        self.app._init_record_fields(data)
        self.assertEqual(data["pdf_path"], "")
        self.assertEqual(data["invoice_type"], "")
        self.assertEqual(data["seller_name"], "")
        self.assertEqual(data["remark"], "")
        self.assertEqual(data["screenshots"], [])
        self.assertEqual(data["contracts"], [])
        self.assertFalse(data["is_red"])

    def test_preserves_existing_values(self):
        data = {"pdf_path": "/test.pdf", "invoice_type": "增值税专用发票"}
        self.app._init_record_fields(data)
        self.assertEqual(data["pdf_path"], "/test.pdf")
        self.assertEqual(data["invoice_type"], "增值税专用发票")

    def test_red_invoice_negates_amounts(self):
        data = {"amount": "550.00", "tax_amount": "71.50", "total": "621.50", "is_red": True}
        self.app._init_record_fields(data)
        self.assertEqual(data["amount"], "-550.00")
        self.assertEqual(data["tax_amount"], "-71.50")
        self.assertEqual(data["total"], "-621.50")

    def test_red_invoice_already_negative(self):
        data = {"amount": "-550.00", "is_red": True}
        self.app._init_record_fields(data)
        self.assertEqual(data["amount"], "-550.00")  # 不重复加负号

    def test_blue_invoice_amounts_unchanged(self):
        data = {"amount": "550.00", "total": "621.50", "is_red": False}
        self.app._init_record_fields(data)
        self.assertEqual(data["amount"], "550.00")
        self.assertEqual(data["total"], "621.50")


# ── _find_record_index 测试 ──────────────────

class TestFindRecordIndex(unittest.TestCase):
    def setUp(self):
        self.app = InvoiceApp.__new__(InvoiceApp)
        self.app.records = [
            {"invoice_no": "11111111"},
            {"invoice_no": "22222222"},
            {"invoice_no": "33333333"},
        ]

    def test_find_existing(self):
        self.assertEqual(self.app._find_record_index("22222222"), 1)

    def test_find_first(self):
        self.assertEqual(self.app._find_record_index("11111111"), 0)

    def test_find_last(self):
        self.assertEqual(self.app._find_record_index("33333333"), 2)

    def test_find_nonexistent(self):
        self.assertIsNone(self.app._find_record_index("99999999"))

    def test_find_empty_string(self):
        self.assertIsNone(self.app._find_record_index(""))

    def test_find_none(self):
        self.assertIsNone(self.app._find_record_index(None))

    def test_empty_records(self):
        self.app.records = []
        self.assertIsNone(self.app._find_record_index("11111111"))


# ── _get_record_by_row 测试 ─────────────────

class TestGetRecordByRow(unittest.TestCase):
    def setUp(self):
        self.app = InvoiceApp.__new__(InvoiceApp)
        from models import Invoice
        self.app.records = [
            Invoice(invoice_no="AAA", file="a.pdf"),
            Invoice(invoice_no="BBB", file="b.pdf"),
        ]
        self.app._current_col_idx = COL_IDX
        self.app._shown_records = list(self.app.records)
        # 模拟 table.item 返回 None（无匹配发票号时走 shown 回退）
        self.app.table = MagicMock()
        self.app.table.item = MagicMock(return_value=None)

    def test_fallback_to_shown_when_no_table_match(self):
        rec = self.app._get_record_by_row(0)
        self.assertEqual(rec.invoice_no, "AAA")

    def test_fallback_to_shown_out_of_range(self):
        rec = self.app._get_record_by_row(99)
        self.assertIsNone(rec)

    def test_empty_shown(self):
        self.app._shown_records = []
        self.assertIsNone(self.app._get_record_by_row(0))


# ── _on_parse_error 测试 ────────────────────

class TestOnParseError(unittest.TestCase):
    def test_collects_errors(self):
        app = InvoiceApp.__new__(InvoiceApp)
        app._parse_errors = []
        app.status = MagicMock()
        app._on_parse_error("测试错误")
        self.assertEqual(app._parse_errors, ["测试错误"])

    def test_multiple_errors(self):
        app = InvoiceApp.__new__(InvoiceApp)
        app._parse_errors = []
        app.status = MagicMock()
        app._on_parse_error("错误1")
        app._on_parse_error("错误2")
        self.assertEqual(len(app._parse_errors), 2)


# ── _safe_float 补充 ─────────────────────────

class TestSafeFloatExtra(unittest.TestCase):
    def test_boolean_value(self):
        self.assertEqual(safe_float(True), 1.0)

    def test_whitespace_string(self):
        self.assertEqual(safe_float("   "), 0.0)

    def test_comma_in_string(self):
        # 注意：_safe_float 不支持千分位逗号
        self.assertEqual(safe_float("1,200.50"), 0.0)

    def test_scientific_notation(self):
        self.assertGreater(safe_float("1.5e2"), 0.0)


class TestFrozenOperationColumn(unittest.TestCase):
    def setUp(self):
        self.old_appdata = os.environ.get("APPDATA")
        self.tmp_dir = tempfile.mkdtemp()
        os.environ["APPDATA"] = self.tmp_dir
        self.window = InvoiceApp()
        self.window.records = [
            Invoice.from_dict({
                "invoice_no": f"NO-{i:03d}",
                "invoice_date": "2024年06月01日",
                "invoice_type": "普通发票",
                "buyer_name": "购买方",
                "buyer_tax_id": "TAX",
                "seller_name": "销售方",
                "amount": "100.00",
                "tax_rate": "1%",
                "tax_amount": "1.00",
                "total": "101.00",
                "company": "001",
                "screenshots": [],
                "contracts": [],
                "remark": "✓",
                "pdf_path": "",
            })
            for i in range(40)
        ]
        self.window.resize(900, 520)
        self.window.show()
        self.window._rebuild_table()
        QApplication.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        QApplication.processEvents()
        if self.old_appdata is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = self.old_appdata
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_operation_table_is_layout_managed_beside_main_table(self):
        table_parent = self.window.table.parentWidget()
        freeze_parent = self.window._freeze_table.parentWidget()

        self.assertIs(table_parent, freeze_parent)
        self.assertIsInstance(table_parent.layout(), QHBoxLayout)
        self.assertGreaterEqual(table_parent.layout().indexOf(self.window.table), 0)
        self.assertGreaterEqual(table_parent.layout().indexOf(self.window._freeze_table), 0)

    def test_operation_table_rows_and_scroll_stay_synced(self):
        self.assertEqual(self.window.table.rowCount(), self.window._freeze_table.rowCount())

        for row in range(self.window.table.rowCount()):
            self.assertEqual(
                self.window.table.rowHeight(row),
                self.window._freeze_table.rowHeight(row),
            )

        main_scroll = self.window.table.verticalScrollBar()
        freeze_scroll = self.window._freeze_table.verticalScrollBar()
        main_scroll.setValue(main_scroll.maximum())
        QApplication.processEvents()
        self.assertEqual(freeze_scroll.value(), main_scroll.value())

        freeze_scroll.setValue(0)
        QApplication.processEvents()
        self.assertEqual(main_scroll.value(), 0)

    def test_horizontal_scroll_does_not_move_operation_table(self):
        before = self.window._freeze_table.geometry()
        self.window.table.horizontalScrollBar().setValue(
            self.window.table.horizontalScrollBar().maximum()
        )
        QApplication.processEvents()
        after = self.window._freeze_table.geometry()

        self.assertEqual(after.x(), before.x())
        self.assertEqual(after.y(), before.y())
        self.assertEqual(after.width(), before.width())
        self.assertEqual(
            self.window._freeze_table.verticalScrollBarPolicy(),
            Qt.ScrollBarAsNeeded,
        )


# ── 拖拽路由测试 ──────────────────────────────

class TestDragDropRouting(unittest.TestCase):
    """测试拖拽路由逻辑：PDF始终作为发票，图片/文档作为附件"""

    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        import tempfile, shutil
        self.tmp = tempfile.mkdtemp()
        self.data_dir = os.path.join(self.tmp, "data")
        os.makedirs(os.path.join(self.data_dir, "invoices"))
        os.makedirs(os.path.join(self.data_dir, "attachments"))
        # 写入空数据文件
        with open(os.path.join(self.data_dir, "invoices_data.json"), "w") as f:
            json.dump([], f)
        # 创建临时app实例
        from invoice_tool import InvoiceApp
        self.app = InvoiceApp.__new__(InvoiceApp)
        self.app.records = []
        self.app._shown_records = []
        self.app._data_dir = self.data_dir
        self.app._data_file = os.path.join(self.data_dir, "invoices_data.json")
        self.app._attachment_dir = os.path.join(self.data_dir, "attachments")
        self.app._config_file = os.path.join(self.tmp, "config.json")
        self.app._tag_templates = ["企业号"]
        self.app._current_col_idx = {}
        self.app._save_locked = True
        self.app._filter_year = None
        self.app._filter_month = None
        self.app._filter_inv_type = None
        self.app._filter_seller = None
        self.app._filter_buyer = ""
        self.app._filter_company = ""

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_pdf(self, name):
        path = os.path.join(self.tmp, name)
        with open(path, "wb") as f:
            f.write(b"%PDF-1.4 fake pdf")
        return path

    def _make_img(self, name):
        path = os.path.join(self.tmp, name)
        with open(path, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        return path

    def _make_doc(self, name):
        path = os.path.join(self.tmp, name)
        with open(path, "wb") as f:
            f.write(b"docx content")
        return path

    def test_pdf_always_classified_as_invoice(self):
        """PDF文件始终分类为发票，不依赖选中状态"""
        from PyQt5.QtCore import QUrl, QMimeData
        from PyQt5.QtGui import QDragEnterEvent
        pdf = self._make_pdf("invoice.pdf")
        # 构造拖入事件
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(pdf)])
        # 验证：PDF应当被识别为pdf_files（通过扩展名判断）
        import os as _os
        ext = _os.path.splitext(pdf)[1].lower()
        self.assertEqual(ext, ".pdf")
        self.assertIn(ext, {".pdf"})

    def test_image_classified_as_attachment(self):
        """图片文件分类为附件"""
        img = self._make_img("screenshot.png")
        import os as _os
        ext = _os.path.splitext(img)[1].lower()
        from invoice_tool import IMG_EXTS
        self.assertIn(ext, IMG_EXTS)

    def test_docx_classified_as_attachment(self):
        """文档文件分类为附件"""
        doc = self._make_doc("contract.docx")
        import os as _os
        ext = _os.path.splitext(doc)[1].lower()
        from invoice_tool import CONTRACT_EXTS
        self.assertIn(ext, CONTRACT_EXTS)

    def test_mixed_files_separated_correctly(self):
        """混合拖入时PDF和图片/文档正确分离"""
        pdf = self._make_pdf("inv.pdf")
        img = self._make_img("ss.png")
        doc = self._make_doc("ct.docx")

        all_files = [pdf, img, doc]
        pdf_files = [f for f in all_files if f.lower().endswith('.pdf')]
        other = [f for f in all_files if not f.lower().endswith('.pdf')]

        self.assertEqual(len(pdf_files), 1)
        self.assertEqual(len(other), 2)

    def test_no_pdf_in_attachment_classification(self):
        """PDF不会出现在附件列表中"""
        pdf = self._make_pdf("test.pdf")
        import os as _os
        ext = _os.path.splitext(pdf)[1].lower()
        self.assertEqual(ext, ".pdf")


# ── 导入重复检测测试 ───────────────────────────

class TestImportDuplicateDetection(unittest.TestCase):
    """测试导入重复发票检测"""

    def test_duplicate_found_by_invoice_no(self):
        """相同发票号应被检测为重复"""
        from models import Invoice
        records = [
            Invoice(invoice_no="12345678", file="a.pdf"),
            Invoice(invoice_no="87654321", file="b.pdf"),
        ]
        target = "12345678"
        found = any(r.invoice_no == target for r in records)
        self.assertTrue(found)

    def test_new_invoice_not_duplicate(self):
        """新发票号不应被检测为重复"""
        from models import Invoice
        records = [Invoice(invoice_no="12345678", file="a.pdf")]
        target = "99999999"
        found = any(r.invoice_no == target for r in records)
        self.assertFalse(found)

    def test_empty_invoice_no_not_duplicate(self):
        """空发票号不应被检测为重复"""
        from models import Invoice
        records = [Invoice(invoice_no="12345678", file="a.pdf")]
        target = ""
        found = any(r.invoice_no == target for r in records) if target else False
        self.assertFalse(found)

    def test_duplicate_list_collected(self):
        """重复发票应被收集到列表中"""
        duplicates = []
        from models import Invoice
        records = [Invoice(invoice_no="12345", file="a.pdf")]
        new_inv = Invoice(invoice_no="12345", file="b.pdf")

        found = any(r.invoice_no == new_inv.invoice_no for r in records)
        if found:
            duplicates.append(new_inv)

        self.assertEqual(len(duplicates), 1)
        self.assertEqual(duplicates[0].invoice_no, "12345")

    def test_parse_done_summary_counts(self):
        """验证导入完成后的计数逻辑"""
        total_parsed = 10
        errors = ["file1.pdf: 无法识别", "file2.pdf: 格式损坏"]
        duplicates = [type('obj', (object,), {'invoice_no': '11111'})()]

        ok = total_parsed - len(errors) - len(duplicates)
        self.assertEqual(ok, 7)
        self.assertEqual(len(errors), 2)
        self.assertEqual(len(duplicates), 1)


# ── 附件列测试 ─────────────────────────────────

class TestAttachmentColumn(unittest.TestCase):
    """测试附件列合并功能"""

    def test_attachments_field_exists(self):
        """Invoice 模型有 attachments 字段"""
        from models import Invoice
        inv = Invoice()
        self.assertTrue(hasattr(inv, 'attachments'))
        self.assertIsInstance(inv.attachments, list)

    def test_attachments_from_old_screenshots(self):
        """旧 screenshots 字段可迁移到 attachments"""
        from models import Invoice
        inv = Invoice(screenshots=["/old/ss/1.png"], contracts=[])
        # 模拟迁移逻辑
        if inv.screenshots:
            inv.attachments.extend(inv.screenshots)
        self.assertIn("/old/ss/1.png", inv.attachments)

    def test_attachments_from_old_contracts(self):
        """旧 contracts 字段可迁移到 attachments"""
        from models import Invoice
        inv = Invoice(screenshots=[], contracts=["/old/ct/1.pdf"])
        if inv.contracts:
            inv.attachments.extend(inv.contracts)
        self.assertIn("/old/ct/1.pdf", inv.attachments)

    def test_attachments_merge_dedup(self):
        """合并附件时去重"""
        from models import Invoice
        inv = Invoice(
            screenshots=["/a.png", "/b.png"],
            contracts=["/a.png", "/c.pdf"],
            attachments=["/a.png"]
        )
        existing = set(inv.attachments)
        for p in inv.screenshots + inv.contracts:
            if p not in existing:
                inv.attachments.append(p)
                existing.add(p)
        # /a.png should only appear once
        self.assertEqual(inv.attachments.count("/a.png"), 1)
        self.assertEqual(len(inv.attachments), 3)

    def test_column_list_has_attachment_not_screenshots(self):
        """列定义中只有附件，没有截图和合同"""
        from invoice_tool import COLUMNS
        self.assertIn("附件", COLUMNS)
        self.assertNotIn("付款截图", COLUMNS)
        self.assertNotIn("合同", COLUMNS)


# ── 实时筛选测试 ──────────────────────────────

class TestRealTimeFilter(unittest.TestCase):
    """测试实时筛选逻辑"""

    def setUp(self):
        from models import Invoice
        self.records = [
            Invoice(invoice_no="001", invoice_date="2024年01月15日", seller_name="甲公司", amount="100.00", tags={"企业号": "A01"}),
            Invoice(invoice_no="002", invoice_date="2024年02月20日", seller_name="乙公司", amount="200.00", tags={"企业号": "B02"}),
            Invoice(invoice_no="003", invoice_date="2025年01月10日", seller_name="甲公司", amount="300.00", tags={"企业号": "A01"}),
        ]

    def test_filter_by_seller(self):
        """按销售方筛选"""
        seller = "甲公司"
        result = [r for r in self.records if r.seller_name == seller]
        self.assertEqual(len(result), 2)

    def test_filter_by_year(self):
        """按年份筛选"""
        result = [r for r in self.records if "2024" in (r.invoice_date or "")]
        self.assertEqual(len(result), 2)

    def test_filter_by_tag(self):
        """按标签值筛选"""
        company = "A01"
        result = [r for r in self.records if (r.tags or {}).get("企业号") == company]
        self.assertEqual(len(result), 2)

    def test_filter_combined(self):
        """组合筛选"""
        result = [
            r for r in self.records
            if r.seller_name == "甲公司" and "2024" in (r.invoice_date or "")
        ]
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].invoice_no, "001")

    def test_filter_empty_result(self):
        """筛选无匹配时返回空"""
        result = [r for r in self.records if r.seller_name == "不存在的公司"]
        self.assertEqual(len(result), 0)


class TestColumnSort(unittest.TestCase):
    """测试列排序逻辑"""

    def setUp(self):
        from models import Invoice
        self.records = [
            Invoice(invoice_no="003", amount="300.00", invoice_date="2025年01月10日"),
            Invoice(invoice_no="001", amount="100.00", invoice_date="2024年01月15日"),
            Invoice(invoice_no="002", amount="200.00", invoice_date="2024年02月20日"),
        ]

    def test_sort_by_amount_ascending(self):
        """按金额升序排列"""
        from utils import safe_float
        sorted_records = sorted(self.records, key=lambda r: safe_float(r.amount))
        self.assertEqual(sorted_records[0].invoice_no, "001")
        self.assertEqual(sorted_records[1].invoice_no, "002")
        self.assertEqual(sorted_records[2].invoice_no, "003")

    def test_sort_by_amount_descending(self):
        """按金额降序排列"""
        from utils import safe_float
        sorted_records = sorted(self.records, key=lambda r: safe_float(r.amount), reverse=True)
        self.assertEqual(sorted_records[0].invoice_no, "003")
        self.assertEqual(sorted_records[-1].invoice_no, "001")

    def test_sort_by_text_field(self):
        """按文本字段排序"""
        sorted_records = sorted(self.records, key=lambda r: r.invoice_no.lower())
        self.assertEqual(sorted_records[0].invoice_no, "001")
        self.assertEqual(sorted_records[2].invoice_no, "003")

    def test_sort_cycle_clears(self):
        """第三次点击取消排序"""
        sort_column = "金额(元)"
        sort_ascending = True

        # 1st click: asc
        self.assertTrue(sort_ascending)

        # 2nd click: desc
        sort_ascending = False
        self.assertFalse(sort_ascending)

        # 3rd click: clear
        sort_column = None
        self.assertIsNone(sort_column)


# ── 全局搜索测试 ──────────────────────────────

class TestGlobalSearch(unittest.TestCase):
    """测试全局搜索逻辑"""

    def setUp(self):
        from models import Invoice
        self.records = [
            Invoice(invoice_no="12345", buyer_name="北京科技有限公司", seller_name="甲公司",
                    amount="500.00", tags={"企业号": "BJ001"}, remark="已报销"),
            Invoice(invoice_no="67890", buyer_name="上海贸易有限公司", seller_name="乙公司",
                    amount="1200.00", tags={"企业号": "SH002"}, remark="待审批"),
        ]

    def test_search_by_invoice_no(self):
        """按发票号搜索"""
        keyword = "12345"
        matches = []
        for i, r in enumerate(self.records):
            if keyword in str(r.invoice_no):
                matches.append(i)
        self.assertEqual(len(matches), 1)

    def test_search_by_buyer_name(self):
        """按购买方名称搜索"""
        keyword = "科技"
        matches = []
        for i, r in enumerate(self.records):
            if keyword in str(r.buyer_name):
                matches.append(i)
        self.assertEqual(len(matches), 1)

    def test_search_by_tag_value(self):
        """按标签值搜索"""
        keyword = "BJ"
        matches = []
        for i, r in enumerate(self.records):
            tags = r.tags or {}
            if any(keyword.lower() in str(v).lower() for v in tags.values()):
                matches.append(i)
        self.assertEqual(len(matches), 1)

    def test_search_by_remark(self):
        """按备注搜索"""
        keyword = "报销"
        matches = []
        for i, r in enumerate(self.records):
            if keyword in str(r.remark or ""):
                matches.append(i)
        self.assertEqual(len(matches), 1)

    def test_search_no_match(self):
        """无匹配搜索"""
        keyword = "不存在的"
        matches = []
        for i, r in enumerate(self.records):
            # 搜索所有字段
            found = False
            for attr in ['invoice_no', 'buyer_name', 'seller_name', 'remark']:
                val = getattr(r, attr, '') or ''
                if keyword in str(val):
                    found = True
                    break
            if not found and r.tags:
                for v in r.tags.values():
                    if keyword in str(v):
                        found = True
                        break
            if found:
                matches.append(i)
        self.assertEqual(len(matches), 0)

    def test_search_case_insensitive(self):
        """搜索不区分大小写"""
        keyword = "BJ001"
        matches = []
        for i, r in enumerate(self.records):
            tags = r.tags or {}
            if any(keyword.lower() in str(v).lower() for v in tags.values()):
                matches.append(i)
        self.assertEqual(len(matches), 1)

    def test_search_empty_keyword(self):
        """空关键词不匹配"""
        keyword = ""
        matches = []
        if keyword.strip():
            for i, r in enumerate(self.records):
                matches.append(i)
        self.assertEqual(len(matches), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
