# -*- coding: utf-8 -*-
"""invoice_tool 模块非 GUI 逻辑单元测试"""

import sys
import os
import unittest
import tempfile
import shutil
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from utils import copy_file_to_dir as _copy_file_to_dir, safe_float
from invoice_tool import InvoiceApp, COL_IDX
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
            Qt.ScrollBarAlwaysOn,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
