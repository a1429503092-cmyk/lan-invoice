# -*- coding: utf-8 -*-
"""发票筛选逻辑 — 纯函数，可脱离 GUI 独立测试"""

import re


def get_available_years(records: list) -> list[int]:
    """从记录列表中提取所有不重复年份，排序返回"""
    years = set()
    for r in records:
        m = re.match(r'(\d{4})年', r.get("invoice_date", ""))
        if m:
            years.add(int(m.group(1)))
    return sorted(years)


def get_available_inv_types(records: list) -> list[str]:
    """从记录列表中提取所有不重复发票类型，排序返回"""
    types = set()
    for r in records:
        t = r.get("invoice_type", "").strip()
        if t:
            types.add(t)
    return sorted(types)


def get_available_sellers(records: list) -> list[str]:
    """从记录列表中提取所有不重复销售方名称，排序返回"""
    sellers = set()
    for r in records:
        s = r.get("seller_name", "").strip()
        if s:
            sellers.add(s)
    return sorted(sellers)


def record_matches_filter(rec: dict,
                          filter_year=None,
                          filter_month=None,
                          filter_inv_type=None,
                          filter_seller=None,
                          filter_buyer="",
                          filter_company="") -> bool:
    """判断单条记录是否满足所有筛选条件"""
    # 年月筛选
    if filter_year is not None or filter_month is not None:
        m = re.match(r'(\d{4})年(\d{2})月', rec.get("invoice_date", ""))
        if not m:
            return False
        y, mo = int(m.group(1)), int(m.group(2))
        if filter_year is not None and y != filter_year:
            return False
        if filter_month is not None and mo != filter_month:
            return False
    # 发票类型筛选
    if filter_inv_type is not None:
        if rec.get("invoice_type", "").strip() != filter_inv_type:
            return False
    # 销售方筛选
    if filter_seller is not None:
        if rec.get("seller_name", "").strip() != filter_seller:
            return False
    # 购买方名称/税号模糊搜索
    if filter_buyer:
        buyer_name = rec.get("buyer_name", "").lower()
        buyer_tax_id = rec.get("buyer_tax_id", "").lower()
        search_text = filter_buyer.lower()
        if search_text not in buyer_name and search_text not in buyer_tax_id:
            return False
    # 企业号模糊搜索
    if filter_company:
        company = rec.get("company", "")
        if filter_company.lower() not in company.lower():
            return False
    return True
