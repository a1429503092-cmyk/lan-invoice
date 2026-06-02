# -*- coding: utf-8 -*-
"""filters 模块单元测试 — 纯函数，无需 GUI"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from filters import (record_matches_filter, get_available_years,
                     get_available_inv_types, get_available_sellers)


# ── get_available_years ──────────────────────

class TestGetAvailableYears(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(get_available_years([]), [])

    def test_single_year(self):
        recs = [{"invoice_date": "2024年11月30日"}]
        self.assertEqual(get_available_years(recs), [2024])

    def test_multiple_years_sorted(self):
        recs = [
            {"invoice_date": "2025年01月15日"},
            {"invoice_date": "2023年06月20日"},
            {"invoice_date": "2024年12月01日"},
        ]
        self.assertEqual(get_available_years(recs), [2023, 2024, 2025])

    def test_duplicate_years(self):
        recs = [
            {"invoice_date": "2024年03月01日"},
            {"invoice_date": "2024年11月30日"},
            {"invoice_date": "2025年01月15日"},
        ]
        self.assertEqual(get_available_years(recs), [2024, 2025])

    def test_no_date_field(self):
        recs = [{"amount": "100"}, {}]
        self.assertEqual(get_available_years(recs), [])


# ── get_available_inv_types ──────────────────

class TestGetAvailableInvTypes(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(get_available_inv_types([]), [])

    def test_single_type(self):
        recs = [{"invoice_type": "增值税专用发票"}]
        self.assertEqual(get_available_inv_types(recs), ["增值税专用发票"])

    def test_multiple_sorted(self):
        recs = [
            {"invoice_type": "普通发票"},
            {"invoice_type": "增值税专用发票"},
            {"invoice_type": "票通发票"},
        ]
        self.assertEqual(get_available_inv_types(recs),
                         ["增值税专用发票", "普通发票", "票通发票"])

    def test_skip_empty(self):
        recs = [
            {"invoice_type": "增值税专用发票"},
            {"invoice_type": ""},
            {"invoice_type": "  "},
        ]
        self.assertEqual(get_available_inv_types(recs), ["增值税专用发票"])


# ── get_available_sellers ────────────────────

class TestGetAvailableSellers(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(get_available_sellers([]), [])

    def test_multiple_sorted(self):
        recs = [
            {"seller_name": "京东"},
            {"seller_name": "阿里巴巴"},
            {"seller_name": "华为"},
        ]
        self.assertEqual(get_available_sellers(recs),
                         ["京东", "华为", "阿里巴巴"])

    def test_skip_empty(self):
        recs = [{"seller_name": ""}, {"seller_name": "京东"}]
        self.assertEqual(get_available_sellers(recs), ["京东"])


# ── record_matches_filter ────────────────────

class TestRecordMatchesFilter(unittest.TestCase):

    # ── 无筛选 ────────────────────────────────
    def test_no_filter_passes_any(self):
        self.assertTrue(record_matches_filter({"invoice_date": "2024年11月30日"}))
        self.assertTrue(record_matches_filter({}))

    # ── 年份筛选 ──────────────────────────────
    def test_year_match(self):
        self.assertTrue(record_matches_filter(
            {"invoice_date": "2024年05月15日"}, filter_year=2024))
        self.assertFalse(record_matches_filter(
            {"invoice_date": "2025年01月01日"}, filter_year=2024))

    def test_year_no_date(self):
        self.assertFalse(record_matches_filter(
            {"invoice_date": ""}, filter_year=2024))
        self.assertFalse(record_matches_filter(
            {}, filter_year=2024))

    # ── 月份筛选 ──────────────────────────────
    def test_month_match(self):
        self.assertTrue(record_matches_filter(
            {"invoice_date": "2024年06月01日"}, filter_month=6))
        self.assertFalse(record_matches_filter(
            {"invoice_date": "2024年07月01日"}, filter_month=6))

    def test_year_and_month(self):
        self.assertTrue(record_matches_filter(
            {"invoice_date": "2024年11月30日"}, filter_year=2024, filter_month=11))
        self.assertFalse(record_matches_filter(
            {"invoice_date": "2024年10月01日"}, filter_year=2024, filter_month=11))
        self.assertFalse(record_matches_filter(
            {"invoice_date": "2023年11月01日"}, filter_year=2024, filter_month=11))

    # ── 发票类型筛选 ──────────────────────────
    def test_inv_type_match(self):
        self.assertTrue(record_matches_filter(
            {"invoice_type": "增值税专用发票"}, filter_inv_type="增值税专用发票"))
        self.assertFalse(record_matches_filter(
            {"invoice_type": "普通发票"}, filter_inv_type="增值税专用发票"))

    # ── 销售方筛选 ────────────────────────────
    def test_seller_match(self):
        self.assertTrue(record_matches_filter(
            {"seller_name": "京东世纪"}, filter_seller="京东世纪"))
        self.assertFalse(record_matches_filter(
            {"seller_name": "华为技术"}, filter_seller="京东世纪"))

    # ── 购买方模糊搜索 ────────────────────────
    def test_buyer_name_search(self):
        self.assertTrue(record_matches_filter(
            {"buyer_name": "福建长富乳品有限公司", "buyer_tax_id": ""},
            filter_buyer="长富"))
        self.assertFalse(record_matches_filter(
            {"buyer_name": "其他公司", "buyer_tax_id": ""}, filter_buyer="长富"))

    def test_buyer_tax_id_search(self):
        self.assertTrue(record_matches_filter(
            {"buyer_name": "", "buyer_tax_id": "91350700156534567X"},
            filter_buyer="91350700"))
        self.assertFalse(record_matches_filter(
            {"buyer_name": "", "buyer_tax_id": "12345678"}, filter_buyer="91350700"))

    def test_buyer_case_insensitive(self):
        self.assertTrue(record_matches_filter(
            {"buyer_name": "ABC公司", "buyer_tax_id": ""}, filter_buyer="abc"))

    # ── 企业号模糊搜索 ────────────────────────
    def test_company_search(self):
        self.assertTrue(record_matches_filter(
            {"company": "14786"}, filter_company="14786"))
        self.assertFalse(record_matches_filter(
            {"company": "99999"}, filter_company="14786"))

    def test_company_case_insensitive(self):
        self.assertTrue(record_matches_filter(
            {"company": "ABC Corp"}, filter_company="abc"))

    # ── 组合筛选 ──────────────────────────────
    def test_all_filters_match(self):
        rec = {
            "invoice_date": "2024年11月30日",
            "invoice_type": "增值税专用发票",
            "seller_name": "京东世纪",
            "buyer_name": "长富乳品",
            "company": "14786",
        }
        self.assertTrue(record_matches_filter(
            rec, filter_year=2024, filter_month=11,
            filter_inv_type="增值税专用发票", filter_seller="京东世纪",
            filter_buyer="长富", filter_company="14786"))

    def test_one_filter_fails(self):
        rec = {"invoice_date": "2024年11月30日", "invoice_type": "普通发票"}
        self.assertFalse(record_matches_filter(
            rec, filter_year=2024, filter_inv_type="增值税专用发票"))

    # ── 边界 ──────────────────────────────────
    def test_missing_fields_default_empty(self):
        """缺失字段时使用空字符串兜底，不应崩溃"""
        self.assertTrue(record_matches_filter({}))
        self.assertTrue(record_matches_filter({"invoice_date": "2024年01月01日"}, filter_year=2024))
        self.assertFalse(record_matches_filter({}, filter_year=2024))

    def test_seller_exact_match_only(self):
        """销售方筛选是精确匹配而非模糊"""
        self.assertFalse(record_matches_filter(
            {"seller_name": "北京京东世纪"}, filter_seller="京东"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
