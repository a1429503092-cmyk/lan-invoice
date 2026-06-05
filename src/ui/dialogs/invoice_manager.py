# -*- coding: utf-8 -*-
"""发票 PDF 查看与下载对话框"""

import os
import shutil

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QMessageBox
)
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QDesktopServices

from ui.theme import TEXT, TEXT_SEC, TEXT_DIM, ACCENT, RED, BG_ALT


class InvoiceManagerDialog(QDialog):
    """发票 PDF 查看与下载对话框"""

    def __init__(self, pdf_path: str, rec_name: str = "", rec_no: str = "", parent=None):
        super().__init__(parent)
        self.pdf_path = pdf_path
        self.rec_name = rec_name
        self.rec_no = rec_no
        # 标题格式：发票PDF — 购买方名称 — № 发票号码
        parts = ["发票PDF"]
        if rec_name:
            parts.append(rec_name)
        if rec_no:
            parts.append(f"№ {rec_no}")
        self.setWindowTitle(" — ".join(parts))
        self.resize(520, 220)
        self.setMinimumSize(420, 180)
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        lbl_title = QLabel("发票原始 PDF 文件")
        lbl_title.setStyleSheet(f"font-size:13px; font-weight:bold; color:{TEXT};")
        layout.addWidget(lbl_title)

        self.lbl_path = QLabel()
        self.lbl_path.setWordWrap(True)
        self.lbl_path.setStyleSheet(
            f"font-size:12px; color:{TEXT_SEC}; background:{BG_ALT}; "
            "border:none; padding:6px 8px;"
        )
        layout.addWidget(self.lbl_path)

        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(8)

        self.btn_preview = QPushButton("预览")
        self.btn_preview.setFixedHeight(32)
        self.btn_preview.setToolTip("在软件内预览PDF")
        self.btn_preview.clicked.connect(self._preview_pdf)

        self.btn_sys_open = QPushButton("系统打开")
        self.btn_sys_open.setFixedHeight(32)
        self.btn_sys_open.setToolTip("在系统默认程序中打开")
        self.btn_sys_open.clicked.connect(self._open_system)

        self.btn_download = QPushButton("下载另存")
        self.btn_download.setFixedHeight(32)
        self.btn_download.clicked.connect(self._download_pdf)

        self.btn_close = QPushButton("关闭")
        self.btn_close.setFixedHeight(32)
        self.btn_close.clicked.connect(self.accept)

        btn_bar.addWidget(self.btn_preview)
        btn_bar.addWidget(self.btn_sys_open)
        btn_bar.addWidget(self.btn_download)
        btn_bar.addStretch()
        btn_bar.addWidget(self.btn_close)
        layout.addLayout(btn_bar)

        from ui.theme import DIALOG_QSS
        self.setStyleSheet(DIALOG_QSS)
        for btn in self.findChildren(QPushButton):
            btn.setCursor(Qt.PointingHandCursor)

    def _refresh(self):
        if self.pdf_path and os.path.exists(self.pdf_path):
            size_kb = os.path.getsize(self.pdf_path) / 1024
            size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.2f} MB"
            self.lbl_path.setText(
                f"<b>{os.path.basename(self.pdf_path)}</b><br>"
                f"<span style='color:{TEXT_SEC};'>{self.pdf_path}</span><br>"
                f"<span style='color:{ACCENT};'>文件大小：{size_str}</span>"
            )
            self.btn_preview.setEnabled(True)
            self.btn_sys_open.setEnabled(True)
            self.btn_download.setEnabled(True)
        else:
            self.lbl_path.setText(
                f"<span style='color:{RED};'>文件不存在或路径未记录</span><br>"
                f"<span style='color:{TEXT_DIM};'>{self.pdf_path or '（无路径信息）'}</span>"
            )
            self.btn_preview.setEnabled(False)
            self.btn_sys_open.setEnabled(False)
            self.btn_download.setEnabled(False)

    def _preview_pdf(self):
        if not self.pdf_path or not os.path.exists(self.pdf_path):
            QMessageBox.warning(self, "文件不存在", f"找不到文件：\n{self.pdf_path or '（无路径信息）'}")
            return
        from ui.dialogs.pdf_viewer import PdfViewerDialog
        dlg = PdfViewerDialog(self.pdf_path, parent=self)
        dlg.exec_()

    def _open_system(self):
        if not self.pdf_path or not os.path.exists(self.pdf_path):
            QMessageBox.warning(self, "文件不存在", f"找不到文件：\n{self.pdf_path or '（无路径信息）'}")
            return
        try:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.pdf_path))
        except Exception as e:
            QMessageBox.warning(self, "打开失败", f"无法打开文件：\n{e}")

    def _download_pdf(self):
        if not os.path.exists(self.pdf_path):
            QMessageBox.warning(self, "文件不存在", f"找不到文件：\n{self.pdf_path}")
            return
        dst, _ = QFileDialog.getSaveFileName(
            self, "另存发票PDF", os.path.basename(self.pdf_path),
            "PDF 文件 (*.pdf);;所有文件 (*)"
        )
        if dst:
            shutil.copy2(self.pdf_path, dst)
            QMessageBox.information(self, "下载成功", f"发票PDF已保存到：\n{dst}")
