# -*- coding: utf-8 -*-
"""Excel 导出服务"""

import os
from datetime import datetime

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

from models import Invoice
from utils import safe_float
from logger import getLogger

log = getLogger(__name__)

# 导出列（不含付款截图、合同）
XL_COLUMNS = ["发票类型", "购买方名称", "纳税人识别号",
              "销售方名称", "金额(元)", "征收率", "税额(元)", "价税合计(元)",
              "发票号码", "开票日期", "企业号", "备注"]


class ExportService:
    """将发票列表导出为 Excel 文件"""

    def export(self, invoices: list[Invoice], save_path: str) -> None:
        log.info("Excel 导出开始: %d 条 → %s", len(invoices), save_path)
        """导出到指定路径的 xlsx 文件"""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "发票归档"

        self._write_header(ws)
        self._write_data(ws, invoices)
        self._write_summary(ws, invoices)
        self._set_column_widths(ws)

        ws.freeze_panes = "A2"
        wb.save(save_path)
        log.info("Excel 导出完成: %s (%d 条)", save_path, len(invoices))

    def _write_header(self, ws):
        header_fill = PatternFill("solid", fgColor="1E6FBF")
        header_font = Font(color="FFFFFF", bold=True, size=12)
        header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
        thin = Side(style="thin", color="AAAAAA")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)

        ws.append(XL_COLUMNS)
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = header_align
            cell.border = border
        ws.row_dimensions[1].height = 28

    def _write_data(self, ws, invoices: list[Invoice]):
        alt_fill = PatternFill("solid", fgColor="EEF4FB")
        normal_align = Alignment(horizontal="left", vertical="center")
        center_align = Alignment(horizontal="center", vertical="center")
        thin = Side(style="thin", color="AAAAAA")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)

        for i, inv in enumerate(invoices, 2):
            row_data = [
                inv.invoice_type,
                inv.buyer_name,
                inv.buyer_tax_id,
                inv.seller_name,
                inv.amount,
                inv.tax_rate,
                inv.tax_amount,
                inv.total,
                inv.invoice_no,
                inv.invoice_date,
                inv.company,
                inv.remark or inv.error or "✓"
            ]
            ws.append(row_data)
            fill = alt_fill if i % 2 == 0 else None
            for j, cell in enumerate(ws[i]):
                if fill:
                    cell.fill = fill
                cell.border = border
                cell.alignment = center_align if j in [5, 6, 7, 8] else normal_align
            ws.row_dimensions[i].height = 20

    def _write_summary(self, ws, invoices: list[Invoice]):
        sum_row = ws.max_row + 2
        ws.append([])  # 空行
        ws.append([])  # 汇总行占位

        total_amt = sum(safe_float(inv.amount) for inv in invoices)
        total_tax = sum(safe_float(inv.tax_amount) for inv in invoices)
        total_all = sum(safe_float(inv.total) for inv in invoices)

        sum_font = Font(bold=True, color="1E6FBF", size=12)
        sum_fill = PatternFill("solid", fgColor="D6E4F5")
        center_align = Alignment(horizontal="center", vertical="center")
        thin = Side(style="thin", color="AAAAAA")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)

        ws.cell(sum_row, 1, "合计")
        ws.cell(sum_row, 5, round(total_amt, 2))
        ws.cell(sum_row, 7, round(total_tax, 2))
        ws.cell(sum_row, 8, round(total_all, 2))
        for cell in ws[sum_row]:
            cell.font = sum_font
            cell.fill = sum_fill
            cell.border = border
            cell.alignment = center_align
        ws.row_dimensions[sum_row].height = 24

    def _set_column_widths(self, ws):
        widths = [16, 20, 22, 20, 12, 8, 12, 14, 20, 14, 15, 14]
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w
