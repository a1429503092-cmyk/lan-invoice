# -*- coding: utf-8 -*-
"""invoice_parser 模块单元测试"""

import sys
import os
import unittest
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from invoice_parser import (
    _norm_date, _signed_amount,
    _detect_invoice_type, _extract_invoice_no, _extract_invoice_date,
    _extract_buyer_info, _extract_seller_name, _extract_sections,
    _set_financial, _extract_financials,
)
from utils import copy_file_to_dir as _copy_file_to_dir


# ── 测试用的发票文本片段 ──────────────────────

SAMPLE_INVOICE_COMMON = """
电子发票（增值税专用发票）
发票号码：24113000000012345678
开票日期：2024年11月30日
购买方信息
名称：福建长富乳品有限公司
统一社会信用代码/纳税人识别号：91350700156534567X
销售方信息
销售方名称：北京京东世纪信息技术有限公司
销售方纳税人识别号：91110302563334444Y
*商品名称*数量*单价
*牛奶*100*5.50
合计  ¥550.00  ¥71.50
价税合计  ¥621.50
备注：订单号 JD20241130001
"""

SAMPLE_INVOICE_VARIANT = """
电子发票（普通发票）
发票号码：25011500000000000999
开票日期：2025-01-15
购买方
名称：深圳市腾讯计算机系统有限公司
统一社会信用代码/纳税人识别号：91440300708461136T
销售方
名称：华为技术有限公司
合计  1,200.00  36.00
价税合计  1,236.00
"""

SAMPLE_INVOICE_RED = """
电子发票（增值税专用发票）
发票号码：24120100000000000001
开票日期：2024年12月01日
购买方
名称：福建长富乳品有限公司
统一社会信用代码/纳税人识别号：91350700156534567X
销售方
名称：北京京东世纪信息技术有限公司
合计  -550.00  -71.50
价税合计  -621.50
红字发票
"""

SAMPLE_SIMPLIFIED = """
增值税普通发票
号码：24113000000012345678
日期：2024年11月30日
名称：福建长富乳品有限公司
纳税人识别号：91350700156534567X
销货方：北京京东世纪信息技术有限公司
金额：550.00
税：71.50
"""


# ── _norm_date 测试 ──────────────────────────

class TestNormDate(unittest.TestCase):
    def test_full_date(self):
        self.assertEqual(_norm_date("2024", "11", "30"), "2024年11月30日")

    def test_single_digit_month_day(self):
        self.assertEqual(_norm_date("2024", "1", "5"), "2024年01月05日")

    def test_no_day_returns_none(self):
        self.assertIsNone(_norm_date("2024", "11"))

    def test_month_zero_fill(self):
        self.assertEqual(_norm_date("2025", "3", "12"), "2025年03月12日")


# ── _signed_amount 测试 ────────────────────

class TestSignedAmount(unittest.TestCase):
    def test_positive(self):
        val, neg = _signed_amount("550.00")
        self.assertEqual(val, "550.00")
        self.assertFalse(neg)

    def test_negative_dash(self):
        val, neg = _signed_amount("-550.00")
        self.assertEqual(val, "550.00")
        self.assertTrue(neg)

    def test_negative_parens(self):
        val, neg = _signed_amount("(550.00)")
        self.assertEqual(val, "550.00")
        self.assertTrue(neg)

    def test_with_comma(self):
        val, neg = _signed_amount("1,200.00")
        self.assertEqual(val, "1200.00")
        self.assertFalse(neg)

    def test_negative_with_comma(self):
        val, neg = _signed_amount("-1,200.00")
        self.assertEqual(val, "1200.00")
        self.assertTrue(neg)


# ── 发票类型识别测试 ──────────────────────────

class TestDetectInvoiceType(unittest.TestCase):
    def test_special_invoice(self):
        text = "电子发票（增值税专用发票）\n发票号码：123"
        self.assertEqual(_detect_invoice_type(text), "增值税专用发票")

    def test_normal_invoice(self):
        text = "电子发票（普通发票）\n发票号码：123"
        self.assertEqual(_detect_invoice_type(text), "普通发票")

    def test_keyword_match_in_500_chars(self):
        text = "增值税专用发票\n" * 10
        self.assertEqual(_detect_invoice_type(text), "增值税专用发票")

    def test_keyword_fallback_full_text(self):
        prefix = "X" * 600  # push keyword past 500 chars
        text = prefix + "\n增值税普通发票\n"
        self.assertEqual(_detect_invoice_type(text), "增值税普通发票")

    def test_tongpiao_keyword(self):
        text = "票通电子发票\n发票号码：123"
        self.assertEqual(_detect_invoice_type(text), "票通发票")

    def test_no_match(self):
        self.assertEqual(_detect_invoice_type("无发票类型标识"), "")


# ── 发票号码提取测试 ──────────────────────────

class TestExtractInvoiceNo(unittest.TestCase):
    def test_standard_format(self):
        self.assertEqual(_extract_invoice_no("发票号码：24113000000012345678"), "24113000000012345678")

    def test_colon_format(self):
        self.assertEqual(_extract_invoice_no("发票号码:24113000000012345678"), "24113000000012345678")

    def test_number_prefix(self):
        self.assertEqual(_extract_invoice_no("号码：24113000000012345678"), "24113000000012345678")

    def test_long_number_fallback(self):
        # Fallback: find any 10-20 digit number in text
        self.assertEqual(_extract_invoice_no("文本内容 24113000000012345678 其他内容"), "24113000000012345678")

    def test_no_number(self):
        self.assertEqual(_extract_invoice_no("没有任何号码"), "")


# ── 开票日期提取测试 ──────────────────────────

class TestExtractInvoiceDate(unittest.TestCase):
    def test_standard_chinese_format(self):
        text = "开票日期：2024年11月30日"
        self.assertEqual(_extract_invoice_date(text), "2024年11月30日")

    def test_standard_chinese_space_format(self):
        text = "开票日期：2024年 11月 30日"
        self.assertEqual(_extract_invoice_date(text), "2024年11月30日")

    def test_dash_format(self):
        text = "开票日期：2024-11-30"
        self.assertEqual(_extract_invoice_date(text), "2024年11月30日")

    def test_compact_format(self):
        text = "开票日期：20241130"
        self.assertEqual(_extract_invoice_date(text), "2024年11月30日")

    def test_date_keyword_fallback(self):
        text = "日期：2024年11月30日"
        self.assertEqual(_extract_invoice_date(text), "2024年11月30日")

    def test_no_date_keyword(self):
        text = "前言不搭后语 2025年03月15日 更多内容"
        self.assertEqual(_extract_invoice_date(text), "2025年03月15日")

    def test_slash_format(self):
        """含开票日期关键字的斜杠格式"""
        text = "开票日期：2024/11/30"
        self.assertEqual(_extract_invoice_date(text), "2024年11月30日")

    def test_dot_format(self):
        """含开票日期关键字的点号格式"""
        text = "开票日期：2024.11.30"
        self.assertEqual(_extract_invoice_date(text), "2024年11月30日")

    def test_date_keyword_dash(self):
        """含日期关键字的横线格式"""
        text = "日期：2024-11-30"
        self.assertEqual(_extract_invoice_date(text), "2024年11月30日")

    def test_fallback_dash(self):
        """兜底：全文第一个横线日期"""
        text = "内容 2025-06-15 其他"
        self.assertEqual(_extract_invoice_date(text), "2025年06月15日")

    def test_no_date(self):
        self.assertEqual(_extract_invoice_date("无日期"), "")


# ── 购买方信息提取测试 ────────────────────────

class TestExtractBuyerInfo(unittest.TestCase):
    def test_standard_name_and_tax_id(self):
        text = (
            "名称：福建长富乳品有限公司\n"
            "统一社会信用代码/纳税人识别号：91350700156534567X"
        )
        name, tax_id = _extract_buyer_info(text, "")
        self.assertEqual(name, "福建长富乳品有限公司")
        self.assertEqual(tax_id, "91350700156534567X")

    def test_from_buyer_section(self):
        text = "其他文本"
        section = "名称：测试公司有限公司\n识别号：12345678901234567"
        name, tax_id = _extract_buyer_info(text, section)
        self.assertEqual(name, "测试公司有限公司")

    def test_buyer_prefix_company_name(self):
        text = "购买方 福建长富乳品有限公司"
        name, _ = _extract_buyer_info(text, "")
        self.assertEqual(name, "福建长富乳品有限公司")

    def test_fallback_first_company(self):
        text = "福建长富乳品有限公司 北京京东世纪信息技术有限公司"
        name, _ = _extract_buyer_info(text, "")
        self.assertEqual(name, "福建长富乳品有限公司")

    def test_tax_id_short_format(self):
        text = "纳税人识别号：91350700156534567X"
        _, tax_id = _extract_buyer_info(text, "")
        self.assertEqual(tax_id, "91350700156534567X")

    def test_buyer_section_company_name(self):
        """模式3：buyer_section 中提取公司名"""
        section = "福建长富乳品有限公司"
        name, _ = _extract_buyer_info("", section)
        self.assertEqual(name, "福建长富乳品有限公司")

    def test_buyer_prefix_second_pattern(self):
        """模式4：购买方后面跟公司名"""
        text = "购买方：福建长富乳品有限公司"
        name, _ = _extract_buyer_info(text, "")
        self.assertEqual(name, "福建长富乳品有限公司")

    def test_tax_id_from_buyer_section(self):
        """模式3：从购买方区域提取税号"""
        section = "税号 91350700156534567X 其他"
        _, tax_id = _extract_buyer_info("其他文字", section)
        self.assertEqual(tax_id, "91350700156534567X")

    def test_tax_id_buyer_prefix(self):
        """模式4：购买方附近提取税号"""
        text = "购买方信息 91350700156534567X 其他"
        _, tax_id = _extract_buyer_info(text, "")
        self.assertEqual(tax_id, "91350700156534567X")

    def test_no_data(self):
        name, tax_id = _extract_buyer_info("无数据", "")
        self.assertEqual(name, "")
        self.assertEqual(tax_id, "")


# ── 销售方名称提取测试 ────────────────────────

class TestExtractSellerName(unittest.TestCase):
    def test_seller_name_prefix(self):
        text = "销售方名称：北京京东世纪信息技术有限公司"
        result = _extract_seller_name(text, "", "")
        self.assertEqual(result, "北京京东世纪信息技术有限公司")

    def test_two_names_second_is_seller(self):
        text = (
            "名称：福建长富乳品有限公司\n"
            "名称：北京京东世纪信息技术有限公司"
        )
        result = _extract_seller_name(text, "", "")
        self.assertEqual(result, "北京京东世纪信息技术有限公司")

    def test_from_seller_section(self):
        section = "名称：华为技术有限公司\n税号：123"
        result = _extract_seller_name("", section, "")
        self.assertEqual(result, "华为技术有限公司")

    def test_seller_with_special_chars(self):
        # The function strips leading/trailing special characters
        text = "销售方名称：*北京京东世纪信息技术有限公司*"
        result = _extract_seller_name(text, "", "")
        self.assertIn("北京京东世纪信息技术有限公司", result)

    def test_fallback_last_company(self):
        text = "福建长富乳品有限公司 北京京东世纪信息技术有限公司"
        result = _extract_seller_name(text, "", "福建长富乳品有限公司")
        self.assertEqual(result, "北京京东世纪信息技术有限公司")

    def test_xiaofang_name_format(self):
        """模式2：销方名称：格式（带空格变体）"""
        text = "销 方 名称：北京京东世纪信息技术有限公司"
        result = _extract_seller_name(text, "", "")
        self.assertEqual(result, "北京京东世纪信息技术有限公司")

    def test_xiao_mingcheng_format(self):
        """模式3：销 名 称：分散字符格式"""
        text = "销 名 称：北京京东世纪信息技术有限公司"
        result = _extract_seller_name(text, "", "")
        self.assertEqual(result, "北京京东世纪信息技术有限公司")

    def test_xiaohuofang_format(self):
        """模式4：销货方：格式"""
        text = "销货方：北京京东世纪信息技术有限公司"
        result = _extract_seller_name(text, "", "")
        self.assertEqual(result, "北京京东世纪信息技术有限公司")

    def test_seller_parens_name_format(self):
        """模式6：销售方（名称）：格式"""
        text = "销售方（名称）：北京京东世纪信息技术有限公司"
        result = _extract_seller_name(text, "", "")
        self.assertEqual(result, "北京京东世纪信息技术有限公司")

    def test_from_seller_section_company_pattern(self):
        """模式8：销售方区域提取公司名"""
        section = "某某信息\n福建长富乳品有限公司\n税号：123"
        result = _extract_seller_name("", section, "")
        self.assertEqual(result, "福建长富乳品有限公司")

    def test_xiao_keyword_company_name(self):
        """模式9：销售关键字后面的公司名"""
        text = "销 售某某 北京京东世纪信息技术有限公司 备注"
        result = _extract_seller_name(text, "", "")
        self.assertEqual(result, "北京京东世纪信息技术有限公司")

    def test_xiaofang_prefix_company_name(self):
        """模式10：销售方后面直接跟公司名"""
        text = "销售方 北京京东世纪信息技术有限公司"
        result = _extract_seller_name(text, "", "")
        self.assertEqual(result, "北京京东世纪信息技术有限公司")

    def test_single_company_as_seller(self):
        """模式11兜底：只有一个公司名且无购买方时当作销售方"""
        text = "北京京东世纪信息技术有限公司"
        result = _extract_seller_name(text, "", "")
        self.assertEqual(result, "北京京东世纪信息技术有限公司")


# ── 区域分割测试 ────────────────────────────

class TestExtractSections(unittest.TestCase):
    def test_buyer_and_seller_sections(self):
        text = "购买方信息\n名称：测试A公司\n销售方信息\n名称：测试B公司"
        buyer, seller = _extract_sections(text)
        self.assertIn("测试A公司", buyer)
        self.assertIn("测试B公司", seller)

    def test_no_sections(self):
        buyer, seller = _extract_sections("无区域信息")
        self.assertEqual(buyer, "")
        self.assertEqual(seller, "")


# ── 金额/财务字段测试 ──────────────────────────

class TestSetFinancial(unittest.TestCase):
    def test_set_amount(self):
        result = {"amount": "", "is_red": False}
        _set_financial(result, "amount", "550.00", False)
        self.assertEqual(result["amount"], "550.00")
        self.assertFalse(result["is_red"])

    def test_set_negative_marks_red(self):
        result = {"amount": "", "is_red": False}
        _set_financial(result, "amount", "-550.00", True)
        self.assertEqual(result["amount"], "550.00")
        self.assertTrue(result["is_red"])

    def test_no_overwrite(self):
        result = {"amount": "existing", "is_red": False}
        _set_financial(result, "amount", "999.99", False)
        self.assertEqual(result["amount"], "existing")

    def test_empty_raw_does_nothing(self):
        result = {"amount": "", "is_red": False}
        _set_financial(result, "amount", "", False)
        self.assertEqual(result["amount"], "")


class TestExtractFinancials(unittest.TestCase):
    def test_heji_line(self):
        result = {"amount": "", "tax_rate": "", "tax_amount": "", "total": "", "is_red": False}
        text = "合计  ¥550.00  ¥71.50"
        _extract_financials(text, result)
        self.assertEqual(result["amount"], "550.00")
        self.assertEqual(result["tax_amount"], "71.50")

    def test_tax_rate_extraction(self):
        result = {"amount": "", "tax_rate": "", "tax_amount": "", "total": "", "is_red": False}
        text = "*牛奶*100*5.50 13% 71.50"
        _extract_financials(text, result)
        self.assertEqual(result["tax_rate"], "13%")

    def test_xiaoxie_total(self):
        result = {"amount": "", "tax_rate": "", "tax_amount": "", "total": "", "is_red": False}
        text = "（小写）¥621.50"
        _extract_financials(text, result)
        self.assertEqual(result["total"], "621.50")

    def test_jiashui_total(self):
        result = {"amount": "", "tax_rate": "", "tax_amount": "", "total": "", "is_red": False}
        text = "价税合计  ¥621.50"
        _extract_financials(text, result)
        self.assertEqual(result["total"], "621.50")

    def test_negative_amount(self):
        result = {"amount": "", "tax_rate": "", "tax_amount": "", "total": "", "is_red": False}
        text = "合计  -550.00  -71.50"
        _extract_financials(text, result)
        self.assertEqual(result["amount"], "550.00")
        self.assertTrue(result["is_red"])

    def test_auto_calculate_tax(self):
        result = {"amount": "550.00", "tax_rate": "13%", "tax_amount": "", "total": "", "is_red": False}
        _extract_financials("无额外金额信息", result)
        self.assertEqual(result["tax_amount"], "71.5")

    def test_auto_calculate_total(self):
        result = {"amount": "550.00", "tax_rate": "", "tax_amount": "71.50", "total": "", "is_red": False}
        _extract_financials("无额外金额信息", result)
        self.assertEqual(result["total"], "621.5")

    def test_quantity_price_line(self):
        """模式4：数量×单价行"""
        result = {"amount": "", "tax_rate": "", "tax_amount": "", "total": "", "is_red": False}
        text = "*牛奶*100*5.50 100.00 13% 13.00"
        _extract_financials(text, result)
        self.assertEqual(result["amount"], "100.00")
        self.assertEqual(result["tax_rate"], "13%")
        self.assertEqual(result["tax_amount"], "13.00")

    def test_amount_after_tax_rate(self):
        """模式6：税率后面取金额"""
        result = {"amount": "", "tax_rate": "13%", "tax_amount": "", "total": "", "is_red": False}
        text = "550.00  13%"
        _extract_financials(text, result)
        self.assertEqual(result["amount"], "550.00")

    def test_amount_keyword(self):
        """模式7：金额关键字"""
        result = {"amount": "", "tax_rate": "", "tax_amount": "", "total": "", "is_red": False}
        text = "金额：¥550.00"
        _extract_financials(text, result)
        self.assertEqual(result["amount"], "550.00")

    def test_tax_keyword(self):
        """模式8：税关键字"""
        result = {"amount": "", "tax_rate": "", "tax_amount": "", "total": "", "is_red": False}
        text = "税：¥71.50"
        _extract_financials(text, result)
        self.assertEqual(result["tax_amount"], "71.50")

    def test_no_auto_calc_when_rate_missing(self):
        """税率缺失时不自动计算税额"""
        result = {"amount": "550.00", "tax_rate": "", "tax_amount": "", "total": "", "is_red": False}
        _extract_financials("", result)
        self.assertEqual(result["tax_amount"], "")


# ── 销售方提取补充 ────────────────────────────

class TestExtractSellerExtended(unittest.TestCase):
    """覆盖 invoice_parser line 224: 兜底销售方模式"""

    def test_seller_secondary_pattern_with_co_ltd(self):
        """(?:销售方|销方) 匹配含有限公司的销售方名称"""
        text = "销售方：北京京东世纪信息技术有限公司"
        result = _extract_seller_name(text, "", "")
        self.assertEqual(result, "北京京东世纪信息技术有限公司")

    def test_seller_xiaofang_pattern(self):
        """销方 前缀匹配"""
        text = "销方：神州数码集团股份有限公司"
        result = _extract_seller_name(text, "", "")
        self.assertEqual(result, "神州数码集团股份有限公司")

    def test_seller_xiaofang_prefix_cooperative(self):
        """销方 + 合作社模式（line 222 专用前缀，不被 line 218 拦截）"""
        text = "销方：东台市富农蔬菜专业合作社"
        result = _extract_seller_name(text, "", "")
        self.assertEqual(result, "东台市富农蔬菜专业合作社")


# ── 金额计算边界补充 ──────────────────────────

class TestExtractFinancialsCalcEdgeCases(unittest.TestCase):
    """覆盖 invoice_parser lines 327-328, 334-335: ValueError/TypeError 异常"""

    def test_auto_calc_tax_with_invalid_rate_handles_valueerror(self):
        """税率非数字时自动计算税额不崩溃（line 327-328）"""
        result = {"amount": "550.00", "tax_rate": "abc%", "tax_amount": "",
                  "total": "", "is_red": False}
        _extract_financials("", result)
        # 税率无效，税额保持空（不抛出异常）
        self.assertEqual(result["tax_amount"], "")

    def test_auto_calc_total_with_invalid_amount_handles_valueerror(self):
        """金额非数字时自动计算总价不崩溃（line 334-335）"""
        result = {"amount": "not_a_number", "tax_rate": "",
                  "tax_amount": "71.50", "total": "", "is_red": False}
        _extract_financials("", result)
        # 金额无效，总价保持空
        self.assertEqual(result["total"], "")

    def test_combined_pattern_extracts_tax_rate(self):
        """line 294: 组合金额模式中提取征收率"""
        result = {"amount": "", "tax_rate": "", "tax_amount": "", "total": "",
                  "is_red": False}
        # 模拟模式4：数量×单价 金额 征收率 税额
        text = "*牛奶*100*5.50 550.00 3% 16.50"
        _extract_financials(text, result)
        self.assertEqual(result["amount"], "550.00")
        self.assertEqual(result["tax_rate"], "3%")
        self.assertEqual(result["tax_amount"], "16.50")


# ── _copy_file_to_dir 测试 ──────────────────

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

    def test_md5_dedup_reuses_existing(self):
        src = os.path.join(self.tmp_src, "test.txt")
        with open(src, "w") as f:
            f.write("hello")
        r1 = _copy_file_to_dir(src, self.tmp_dst)
        r2 = _copy_file_to_dir(src, self.tmp_dst)
        self.assertEqual(r1, r2)  # MD5 相同，复用同一个文件

    def test_nonexistent_src(self):
        result = _copy_file_to_dir("/nonexistent/path.txt", self.tmp_dst)
        self.assertEqual(result, "/nonexistent/path.txt")

    def test_empty_src(self):
        result = _copy_file_to_dir("", self.tmp_dst)
        self.assertEqual(result, "")


# ── 集成测试：parse_invoice_pdf（mock pdfplumber）─

class TestParseInvoicePdfIntegration(unittest.TestCase):
    """使用 mock 测试 parse_invoice_pdf 的主流程"""

    def test_parse_with_mock(self):
        from unittest.mock import patch, MagicMock
        from invoice_parser import parse_invoice_pdf

        mock_pdf = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = (
            "电子发票（增值税专用发票）\n"
            "发票号码：24113000000012345678\n"
            "开票日期：2024年11月30日\n"
            "购买方\n"
            "名称：福建长富乳品有限公司\n"
            "统一社会信用代码/纳税人识别号：91350700156534567X\n"
            "销售方\n"
            "名称：北京京东世纪信息技术有限公司\n"
            "合计  ¥550.00  ¥71.50\n"
            "价税合计  ¥621.50\n"
        )
        mock_page.extract_tables.return_value = []
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=None)

        with patch('invoice_parser.pdfplumber.open', return_value=mock_pdf):
            result = parse_invoice_pdf('/fake/path.pdf')

        self.assertEqual(result["invoice_type"], "增值税专用发票")
        self.assertEqual(result["invoice_no"], "24113000000012345678")
        self.assertEqual(result["invoice_date"], "2024年11月30日")
        self.assertEqual(result["buyer_name"], "福建长富乳品有限公司")
        self.assertEqual(result["buyer_tax_id"], "91350700156534567X")
        self.assertEqual(result["seller_name"], "北京京东世纪信息技术有限公司")
        self.assertEqual(result["amount"], "550.00")
        self.assertEqual(result["tax_amount"], "71.50")
        self.assertEqual(result["total"], "621.50")
        self.assertEqual(result["file"], "path.pdf")
        self.assertFalse(result["is_red"])

    def test_red_invoice_detection(self):
        from unittest.mock import patch, MagicMock
        from invoice_parser import parse_invoice_pdf

        mock_pdf = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = (
            "电子发票（增值税专用发票）\n"
            "发票号码：24120100000000000001\n"
            "开票日期：2024年12月01日\n"
            "红字发票\n"
            "合计  -550.00  -71.50\n"
        )
        mock_page.extract_tables.return_value = []
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=None)

        with patch('invoice_parser.pdfplumber.open', return_value=mock_pdf):
            result = parse_invoice_pdf('/fake/red.pdf')

        self.assertTrue(result["is_red"])

    def test_error_on_exception(self):
        from unittest.mock import patch
        from invoice_parser import parse_invoice_pdf

        with patch('invoice_parser.pdfplumber.open', side_effect=Exception("PDF损坏")):
            result = parse_invoice_pdf('/bad.pdf')

        self.assertIn("PDF损坏", result["error"])

    def test_simplified_invoice_format(self):
        """简化发票格式：无'电子发票'前缀，用号码/日期/销货方等简化字段"""
        from unittest.mock import patch, MagicMock
        from invoice_parser import parse_invoice_pdf

        mock_pdf = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = (
            "增值税普通发票\n"
            "号码：25011500000000000999\n"
            "日期：2025年01月15日\n"
            "名称：深圳市腾讯计算机系统有限公司\n"
            "纳税人识别号：91440300708461136T\n"
            "销货方：华为技术有限公司\n"
            "金额：1,200.00\n"
            "税率：6%\n"
            "税：36.00\n"
        )
        mock_page.extract_tables.return_value = []
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=None)

        with patch('invoice_parser.pdfplumber.open', return_value=mock_pdf):
            result = parse_invoice_pdf('/fake/simple.pdf')

        self.assertEqual(result["invoice_type"], "增值税普通发票")
        self.assertEqual(result["invoice_no"], "25011500000000000999")
        self.assertEqual(result["buyer_name"], "深圳市腾讯计算机系统有限公司")
        self.assertEqual(result["seller_name"], "华为技术有限公司")
        self.assertEqual(result["amount"], "1200.00")

    def test_tongpiao_invoice(self):
        """票通电子发票格式"""
        from unittest.mock import patch, MagicMock
        from invoice_parser import parse_invoice_pdf

        mock_pdf = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = (
            "票通电子发票\n"
            "发票号码：24113000000012345678\n"
            "开票日期：2024年11月30日\n"
            "名称：测试购方有限公司\n"
            "统一社会信用代码/纳税人识别号：91350700156534567X\n"
            "销售方名称：测试销方有限公司\n"
            "合计  ¥880.00  ¥114.40\n"
        )
        mock_page.extract_tables.return_value = []
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=None)

        with patch('invoice_parser.pdfplumber.open', return_value=mock_pdf):
            result = parse_invoice_pdf('/fake/tongpiao.pdf')

        self.assertEqual(result["invoice_type"], "票通发票")

    def test_empty_pdf(self):
        """扫描件/空白 PDF：无法提取文字"""
        from unittest.mock import patch, MagicMock
        from invoice_parser import parse_invoice_pdf

        mock_pdf = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = ""
        mock_page.extract_tables.return_value = []
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=None)

        with patch('invoice_parser.pdfplumber.open', return_value=mock_pdf):
            result = parse_invoice_pdf('/fake/empty.pdf')

        self.assertIn("无法提取文字内容", result["error"])

    def test_red_keyword_detection(self):
        """红票关键字识别（红冲/作废等）"""
        from unittest.mock import patch, MagicMock
        from invoice_parser import parse_invoice_pdf

        mock_pdf = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = (
            "电子发票（增值税专用发票）\n"
            "发票号码：24120100000000000002\n"
            "开票日期：2024年12月01日\n"
            "（红字冲红发票）\n"
        )
        mock_page.extract_tables.return_value = []
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=None)

        with patch('invoice_parser.pdfplumber.open', return_value=mock_pdf):
            result = parse_invoice_pdf('/fake/red_keyword.pdf')

        self.assertTrue(result["is_red"])

    def test_company_from_filename(self):
        """文件名自动提取企业号"""
        from unittest.mock import patch, MagicMock
        from invoice_parser import parse_invoice_pdf

        mock_pdf = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "电子发票（普通发票）\n发票号码：12345678901234\n"
        mock_page.extract_tables.return_value = []
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=None)

        with patch('invoice_parser.pdfplumber.open', return_value=mock_pdf):
            result = parse_invoice_pdf('/fake/14786-福建长富乳品有限公司.pdf')

        self.assertEqual(result["file"], "14786-福建长富乳品有限公司.pdf")
        self.assertEqual(result["company"], "14786")


# ── _extract_pdf_text 测试 ────────────────────

class TestExtractPdfText(unittest.TestCase):
    def test_extract_text_only(self):
        from unittest.mock import patch, MagicMock
        from invoice_parser import _extract_pdf_text

        mock_pdf = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "发票号码：12345678"
        mock_page.extract_tables.return_value = []
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=None)

        with patch('invoice_parser.pdfplumber.open', return_value=mock_pdf):
            text = _extract_pdf_text('/fake.pdf')

        self.assertIn("发票号码：12345678", text)

    def test_extract_with_tables(self):
        from unittest.mock import patch, MagicMock
        from invoice_parser import _extract_pdf_text

        mock_pdf = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "文字内容"
        mock_page.extract_tables.return_value = [
            [["项目", "金额"], ["牛奶", "100.00"]]
        ]
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=None)

        with patch('invoice_parser.pdfplumber.open', return_value=mock_pdf):
            text = _extract_pdf_text('/fake_tables.pdf')

        self.assertIn("牛奶", text)
        self.assertIn("100.00", text)

    def test_extract_tables_error_graceful(self):
        """表格提取异常时不应影响文字提取"""
        from unittest.mock import patch, MagicMock
        from invoice_parser import _extract_pdf_text

        mock_pdf = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "文字内容"
        mock_page.extract_tables.side_effect = Exception("表格解析失败")
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=None)

        with patch('invoice_parser.pdfplumber.open', return_value=mock_pdf):
            text = _extract_pdf_text('/fake_bad_table.pdf')

        self.assertIn("文字内容", text)


# ── _extract_sections 补充 ──────────────────

class TestExtractSectionsExtra(unittest.TestCase):
    def test_buyer_only(self):
        text = "购买方信息\n名称：测试公司"
        buyer, seller = _extract_sections(text)
        self.assertIn("测试公司", buyer)
        self.assertEqual(seller, "")

    def test_seller_only(self):
        text = "销售方信息\n名称：销方公司"
        buyer, seller = _extract_sections(text)
        self.assertEqual(buyer, "")
        self.assertIn("销方公司", seller)

    def test_alternative_keywords(self):
        text = "买方信息\n名称：买方公司\n销方信息\n名称：销方公司"
        buyer, seller = _extract_sections(text)
        self.assertIn("买方公司", buyer)
        self.assertIn("销方公司", seller)


# ── _extract_buyer_info 补充 ────────────────

class TestExtractBuyerInfoExtra(unittest.TestCase):
    def test_tax_id_18_chars(self):
        text = "纳税人识别号：123456789012345678"
        _, tax_id = _extract_buyer_info(text, "")
        self.assertEqual(tax_id, "123456789012345678")

    def test_buyer_name_with_limited_company(self):
        text = "购买方：北京测试有限责任公司"
        name, _ = _extract_buyer_info(text, "")
        self.assertEqual(name, "北京测试有限责任公司")

    def test_buyer_name_from_section_only(self):
        section = "名称：福建测试有限公司\n识别号：91110000123456789X"
        name, tax_id = _extract_buyer_info("其他文本", section)
        self.assertEqual(name, "福建测试有限公司")
        self.assertEqual(tax_id, "91110000123456789X")


# ── parse_invoice_pdf 集成补充 ──────────────

class TestParseInvoicePdfExtra(unittest.TestCase):
    def test_invoice_with_tables(self):
        from unittest.mock import patch, MagicMock
        from invoice_parser import parse_invoice_pdf
        mock_pdf = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "电子发票（增值税专用发票）\n发票号码：12345678901234"
        mock_page.extract_tables.return_value = [
            [["项目", "数量", "金额"], ["牛奶", "10", "550.00"]]
        ]
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=None)

        with patch('invoice_parser.pdfplumber.open', return_value=mock_pdf):
            result = parse_invoice_pdf('/fake_with_table.pdf')

        self.assertEqual(result["invoice_no"], "12345678901234")

    def test_multi_page_pdf(self):
        from unittest.mock import patch, MagicMock
        from invoice_parser import parse_invoice_pdf
        mock_pdf = MagicMock()
        page1 = MagicMock()
        page1.extract_text.return_value = "电子发票（普通发票）"
        page1.extract_tables.return_value = []
        page2 = MagicMock()
        page2.extract_text.return_value = "发票号码：99999999999999\n开票日期：2025年06月01日"
        page2.extract_tables.return_value = []
        mock_pdf.pages = [page1, page2]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=None)

        with patch('invoice_parser.pdfplumber.open', return_value=mock_pdf):
            result = parse_invoice_pdf('/multi.pdf')

        self.assertEqual(result["invoice_type"], "普通发票")
        self.assertEqual(result["invoice_no"], "99999999999999")

    def test_all_electronic_invoice(self):
        """全电发票类型"""
        from unittest.mock import patch, MagicMock
        from invoice_parser import parse_invoice_pdf
        mock_pdf = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "全电发票\n发票号码：12345678901234"
        mock_page.extract_tables.return_value = []
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=None)

        with patch('invoice_parser.pdfplumber.open', return_value=mock_pdf):
            result = parse_invoice_pdf('/quandian.pdf')

        self.assertEqual(result["invoice_type"], "全电发票")


if __name__ == "__main__":
    unittest.main(verbosity=2)
