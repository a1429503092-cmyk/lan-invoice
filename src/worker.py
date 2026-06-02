# -*- coding: utf-8 -*-
"""后台解析线程 — 批量解析发票 PDF"""

import os

from PyQt5.QtCore import QThread, pyqtSignal

from invoice_parser import parse_invoice_pdf
from utils import copy_file_to_dir


class ParseWorker(QThread):
    progress = pyqtSignal(int)
    result_ready = pyqtSignal(dict)
    finished = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self, files, data_dir: str = ""):
        super().__init__()
        self.files    = files
        self.data_dir = data_dir
        self._abort   = False

    def abort(self):
        self._abort = True

    def _copy_pdf(self, src: str) -> str:
        if not self.data_dir:
            return src
        return copy_file_to_dir(src, os.path.join(self.data_dir, "invoices"))

    def run(self):
        total = len(self.files)
        for i, f in enumerate(self.files, 1):
            if self._abort:
                break
            try:
                data = parse_invoice_pdf(f)
                data["pdf_path"] = self._copy_pdf(data.get("pdf_path", "") or f)
            except Exception as e:
                self.error_occurred.emit(f"解析 {os.path.basename(f)} 时出错: {str(e)}")
                data = {
                    "pdf_path": f,
                    "error": str(e),
                    "invoice_type": "", "buyer_name": "", "buyer_tax_id": "",
                    "seller_name": "", "amount": "", "tax_rate": "",
                    "tax_amount": "", "total": "", "invoice_no": "",
                    "invoice_date": "", "company": "",
                    "screenshots": [], "contracts": [], "remark": "", "is_red": False
                }
            self.result_ready.emit(data)
            self.progress.emit(int(i / total * 100))
        self.finished.emit()
