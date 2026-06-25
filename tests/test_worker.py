# -*- coding: utf-8 -*-
"""worker 模块单元测试 — mock pdfplumber 测试 ParseWorker"""

import sys
import os
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from PyQt5.QtWidgets import QApplication
from worker import ParseWorker

# 确保有 QApplication 实例
_app = QApplication.instance()
if _app is None:
    _app = QApplication(sys.argv)


class TestParseWorker(unittest.TestCase):

    def setUp(self):
        self.results = []
        self.progress = []
        self.errors = []
        self.finished = False

    def _connect(self, worker):
        worker.result_ready.connect(lambda d: self.results.append(d))
        worker.progress.connect(lambda p: self.progress.append(p))
        worker.error_occurred.connect(lambda e: self.errors.append(e))
        worker.finished.connect(lambda: setattr(self, 'finished', True))

    def test_worker_processes_all_files(self):
        with patch('worker.parse_invoice_pdf') as mock_parse:
            mock_parse.return_value = {
                "file": "test.pdf", "invoice_no": "123",
                "pdf_path": "/tmp/test.pdf", "company": "",
                "invoice_type": "", "buyer_name": "", "buyer_tax_id": "",
                "seller_name": "", "amount": "", "tax_rate": "",
                "tax_amount": "", "total": "", "invoice_date": "",
                "screenshots": [], "contracts": [], "remark": "", "is_red": False,
                "error": "",
            }
            worker = ParseWorker(["a.pdf", "b.pdf", "c.pdf"])
            self._connect(worker)
            worker.run()

        self.assertEqual(len(self.results), 3)
        self.assertTrue(self.finished)
        self.assertGreater(len(self.progress), 0)
        self.assertEqual(self.progress[-1], 100)

    def test_worker_abort(self):
        with patch('worker.parse_invoice_pdf') as mock_parse:
            mock_parse.return_value = {"file": "test.pdf", "invoice_no": "1"}
            worker = ParseWorker(["a.pdf", "b.pdf", "c.pdf", "d.pdf"])
            self._connect(worker)
            # Abort after first file
            worker.result_ready.connect(lambda d: worker.abort())
            worker.run()

        # Should have processed at most 1-2 files before abort took effect
        self.assertLessEqual(len(self.results), 3)
        # finished should still emit
        self.assertTrue(self.finished)

    def test_worker_error_handling(self):
        with patch('worker.parse_invoice_pdf') as mock_parse:
            mock_parse.side_effect = Exception("PDF 解析失败")
            worker = ParseWorker(["bad.pdf"])
            self._connect(worker)
            worker.run()

        self.assertEqual(len(self.results), 1)
        self.assertEqual(len(self.errors), 1)
        self.assertIn("PDF 解析失败", self.errors[0])
        self.assertIn("error", self.results[0])
        self.assertTrue(self.finished)

    def test_worker_with_data_dir(self):
        import tempfile
        import shutil
        tmp = tempfile.mkdtemp()
        try:
            with patch('worker.parse_invoice_pdf') as mock_parse:
                mock_parse.return_value = {
                    "file": "test.pdf", "invoice_no": "111",
                    "pdf_path": os.path.join(tmp, "src.pdf"),
                }
                # Create source file to copy
                with open(os.path.join(tmp, "src.pdf"), "w") as f:
                    f.write("pdf content")

                worker = ParseWorker(
                    [os.path.join(tmp, "src.pdf")],
                    data_dir=tmp
                )
                self._connect(worker)
                worker.run()

            self.assertEqual(len(self.results), 1)
            result = self.results[0]
            # Should have copied to data_dir/invoices/
            self.assertIn("invoices", result.get("pdf_path", ""))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_worker_empty_file_list(self):
        with patch('worker.parse_invoice_pdf') as mock_parse:
            worker = ParseWorker([])
            self._connect(worker)
            worker.run()

        self.assertEqual(len(self.results), 0)
        self.assertTrue(self.finished)

    def test_worker_result_has_pdf_path(self):
        with patch('worker.parse_invoice_pdf') as mock_parse:
            mock_parse.return_value = {"pdf_path": "/input/orig.pdf", "file": "orig.pdf"}
            worker = ParseWorker(["/input/orig.pdf"])
            self._connect(worker)
            worker.run()

        self.assertEqual(len(self.results), 1)
        self.assertEqual(self.results[0].get("pdf_path"), "/input/orig.pdf")

    def test_progress_reaches_100(self):
        with patch('worker.parse_invoice_pdf') as mock_parse:
            mock_parse.return_value = {"file": "x.pdf"}
            worker = ParseWorker(["f1.pdf", "f2.pdf"])
            self._connect(worker)
            worker.run()

        self.assertTrue(self.finished)
        self.assertEqual(self.progress[-1], 100)


if __name__ == "__main__":
    unittest.main(verbosity=2)
