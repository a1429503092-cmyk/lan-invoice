# -*- coding: utf-8 -*-
"""统计面板 — matplotlib 嵌入式图表：月度趋势 + 类型分布 + 年度对比"""

import re
from collections import defaultdict
from datetime import datetime

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QComboBox
)
from PyQt5.QtCore import Qt

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib
matplotlib.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
matplotlib.rcParams['axes.unicode_minus'] = False

from utils import safe_float
from ui.theme import TEXT, TEXT_DIM, ACCENT


class StatsPanel(QDialog):
    """统计面板对话框"""

    def __init__(self, records, parent=None):
        super().__init__(parent)
        self._records = records
        self.setWindowTitle("统计分析")
        self.resize(900, 600)
        self.setMinimumSize(700, 450)
        self._build_ui()
        self._draw_charts()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # 标题栏
        title_row = QHBoxLayout()
        lbl = QLabel("统计分析")
        lbl.setStyleSheet(f"font-size:16px; font-weight:bold; color:{TEXT};")
        title_row.addWidget(lbl)
        title_row.addStretch()

        # 年份切换
        self.cmb_year = QComboBox()
        years = self._available_years()
        self.cmb_year.addItems(["全部"] + [str(y) for y in years])
        self.cmb_year.currentIndexChanged.connect(self._draw_charts)
        title_row.addWidget(QLabel("年份"))
        title_row.addWidget(self.cmb_year)
        layout.addLayout(title_row)

        # Canvas
        self._figure = Figure(figsize=(10, 6), dpi=100)
        self._canvas = FigureCanvas(self._figure)
        layout.addWidget(self._canvas, 1)

        # 关闭
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_close = QPushButton("关闭")
        btn_close.setFixedHeight(32)
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _available_years(self) -> list[int]:
        years = set()
        for r in self._records:
            d = r.get("invoice_date", "")
            try:
                m = re.match(r'(\d{4})年', d)
                if m:
                    years.add(int(m.group(1)))
            except Exception:
                pass
        return sorted(years, reverse=True)

    def _filtered_records(self) -> list[dict]:
        y = self.cmb_year.currentText()
        if y == "全部":
            return list(self._records)
        yr = int(y)
        return [r for r in self._records
                if str(yr) in (r.get("invoice_date", "") or "")]

    def _draw_charts(self):
        self._figure.clear()
        records = self._filtered_records()
        if not records:
            ax = self._figure.add_subplot(111)
            ax.text(0.5, 0.5, "暂无数据", ha='center', va='center',
                    fontsize=16, color='gray')
            ax.axis('off')
            self._canvas.draw()
            return

        # 左图：月度金额趋势
        ax1 = self._figure.add_subplot(2, 2, (1, 2))
        self._draw_monthly_trend(ax1, records)

        # 右图：发票类型分布
        ax2 = self._figure.add_subplot(2, 2, 3)
        self._draw_type_pie(ax2, records)

        # 右下图：年度对比（如果有多年数据）
        ax3 = self._figure.add_subplot(2, 2, 4)
        self._draw_summary(ax3, records)

        self._figure.tight_layout()
        self._canvas.draw()

    def _draw_monthly_trend(self, ax, records):
        monthly = defaultdict(lambda: {"amount": 0.0, "count": 0})
        for r in records:
            d = r.get("invoice_date", "")
            m = re.match(r'(\d{4})年(\d{2})月', d or "")
            if m:
                key = f"{m.group(1)}.{m.group(2)}"
                monthly[key]["amount"] += safe_float(r.get("amount"))
                monthly[key]["count"] += 1

        keys = sorted(monthly.keys())[-12:]  # 最近12个月
        amounts = [monthly[k]["amount"] for k in keys]
        labels = [k.replace(".", "月\n") for k in keys]

        ax.bar(range(len(keys)), amounts, color='#3A8FD4', alpha=0.85)
        ax.set_title("月度金额趋势（近 12 个月）", fontsize=11)
        ax.set_ylabel("金额（元）")
        ax.set_xticks(range(len(keys)))
        ax.set_xticklabels(labels, fontsize=8)
        # 在柱子上标注金额
        for i, v in enumerate(amounts):
            if v > 0:
                ax.text(i, v, f'{v:.0f}', ha='center', va='bottom',
                        fontsize=7, color='#333')

    def _draw_type_pie(self, ax, records):
        types = defaultdict(float)
        for r in records:
            t = r.get("invoice_type", "未知")
            types[t] += abs(safe_float(r.get("amount")))
        labels = list(types.keys())
        sizes = list(types.values())
        if sum(sizes) <= 0:
            ax.text(0.5, 0.5, "暂无金额数据", ha='center', va='center',
                    fontsize=12, color='gray', transform=ax.transAxes)
            ax.axis('off')
            return
        colors = ['#3A8FD4', '#E74C3C', '#27AE60', '#F39C12',
                  '#8E44AD', '#1ABC9C', '#E67E22', '#2C3E50']
        wedges, texts, autotexts = ax.pie(
            sizes, labels=None, autopct='%1.1f%%',
            colors=colors[:len(labels)], startangle=90,
            textprops={'fontsize': 8})
        ax.set_title("发票类型金额分布", fontsize=11)
        ax.legend(wedges, [f"{l} (¥{s:,.0f})" for l, s in zip(labels, sizes)],
                  loc='lower center', fontsize=7, ncol=2)

    def _draw_summary(self, ax, records):
        total_amt = sum(safe_float(r.get("amount")) for r in records)
        total_tax = sum(safe_float(r.get("tax_amount")) for r in records)
        total_all = sum(safe_float(r.get("total")) for r in records)
        count = len(records)

        ax.axis('off')
        lines = [
            f"发票总数：{count} 张",
            f"金额合计：¥{total_amt:,.2f}",
            f"税额合计：¥{total_tax:,.2f}",
            f"价税合计：¥{total_all:,.2f}",
        ]
        for i, line in enumerate(lines):
            ax.text(0.5, 0.8 - i * 0.2, line, ha='center', va='center',
                    fontsize=12, transform=ax.transAxes,
                    fontweight='bold' if i == 0 else 'normal')
