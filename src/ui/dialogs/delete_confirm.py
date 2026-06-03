# -*- coding: utf-8 -*-
"""删除确认对话框（双重保险：勾选后才能删除）"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QCheckBox
)
from PyQt5.QtCore import Qt

from ui.theme import TEXT, TEXT_SEC, RED


class DeleteConfirmDialog(QDialog):
    """带勾选框的删除确认弹窗，必须勾选才可点击「确认删除」"""

    def __init__(self, records: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("确认删除")
        self.setMinimumWidth(560)
        self._build_ui(records)

    def _build_ui(self, records: list):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel("即将永久删除以下发票记录，请仔细核对：")
        title.setStyleSheet(f"font-size:14px; font-weight:bold; color:{RED};")
        layout.addWidget(title)

        detail = QLabel()
        lines = []
        for r in records:
            inv_date = r.get("invoice_date", "—") if isinstance(r, dict) else getattr(r, "invoice_date", "—")
            inv_no   = r.get("invoice_no",   "无发票号") if isinstance(r, dict) else getattr(r, "invoice_no", "无发票号")
            seller   = r.get("seller_name",   "—") if isinstance(r, dict) else getattr(r, "seller_name", "—")
            total    = r.get("total",        "—") if isinstance(r, dict) else getattr(r, "total", "—")
            fname    = r.get("file",          "未知文件") if isinstance(r, dict) else getattr(r, "file", "未知文件")
            lines.append(
                f"  {fname}\n"
                f"   发票号：{inv_no}   日期：{inv_date}\n"
                f"   销售方：{seller}   合计：¥{total}"
            )
        detail.setText("\n\n".join(lines))
        detail.setStyleSheet(
            "background:#FFF3CD; border:1px solid #FFEAA7; "
            "border-radius:6px; padding:10px 12px; "
            f"font-size:12px; color:{TEXT}; line-height:1.6;"
        )
        detail.setWordWrap(True)
        layout.addWidget(detail)

        warn = QLabel("原始 PDF 文件将同步永久删除，无法恢复！")
        warn.setStyleSheet(f"font-size:13px; font-weight:bold; color:{RED};")
        layout.addWidget(warn)

        self.cb = QCheckBox("我已确认上述信息，知晓删除后果，自愿删除")
        self.cb.setStyleSheet(f"font-size:13px; font-weight:bold; color:{TEXT};")
        self.cb.stateChanged.connect(self._on_check)
        layout.addWidget(self.cb)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_ok = QPushButton("确认删除")
        self.btn_ok.setEnabled(False)
        self.btn_ok.setStyleSheet(f"""
            QPushButton {{ background:{RED}; color:white; border-radius:4px;
                          font-size:13px; font-weight:bold; padding:7px 22px; }}
            QPushButton:enabled {{ background:{RED}; }}
            QPushButton:!enabled {{ background:#AAAAAA; color:{TEXT_SEC}; }}
        """)
        self.btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("取消")
        btn_cancel.setStyleSheet(f"""
            QPushButton {{ background:#F0F0F0; color:{TEXT}; border-radius:4px;
                          font-size:13px; padding:7px 18px; }}
        """)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_ok)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)
        for btn in self.findChildren(QPushButton):
            btn.setCursor(Qt.PointingHandCursor)

    def _on_check(self, state):
        self.btn_ok.setEnabled(state == Qt.Checked)
