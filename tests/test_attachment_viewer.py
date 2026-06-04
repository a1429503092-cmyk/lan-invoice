# -*- coding: utf-8 -*-
"""统一附件预览对话框测试"""
import sys, os, unittest, tempfile, shutil
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from PyQt5.QtWidgets import QApplication, QMessageBox

_app = QApplication.instance()
if _app is None:
    _app = QApplication(sys.argv)


def _patch_qmessagebox():
    p = patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes)
    p.start()
    patch.object(QMessageBox, 'warning', return_value=None).start()
    patch.object(QMessageBox, 'information', return_value=None).start()
    patch.object(QMessageBox, 'critical', return_value=None).start()
    return p


class TestAttachmentViewerInit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._msg = _patch_qmessagebox()
    @classmethod
    def tearDownClass(cls):
        cls._msg.stop()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_file(self, name, content=b"data"):
        p = os.path.join(self.tmp, name)
        with open(p, "wb") as f:
            f.write(content)
        return p

    def test_init_with_empty(self):
        from ui.dialogs.attachment_viewer import AttachmentViewerDialog
        dlg = AttachmentViewerDialog([])
        self.assertEqual(dlg.list_widget.count(), 0)
        dlg.close()

    def test_init_with_images(self):
        from ui.dialogs.attachment_viewer import AttachmentViewerDialog
        p1 = self._make_file("img1.png")
        p2 = self._make_file("img2.jpg")
        dlg = AttachmentViewerDialog([p1, p2])
        self.assertEqual(dlg.list_widget.count(), 2)
        dlg.close()

    def test_init_with_pdf(self):
        from ui.dialogs.attachment_viewer import AttachmentViewerDialog
        p1 = self._make_file("doc.pdf")
        dlg = AttachmentViewerDialog([p1])
        self.assertEqual(dlg.list_widget.count(), 1)
        dlg.close()

    def test_init_with_mixed(self):
        from ui.dialogs.attachment_viewer import AttachmentViewerDialog
        p1 = self._make_file("a.png")
        p2 = self._make_file("b.pdf")
        p3 = self._make_file("c.docx")
        dlg = AttachmentViewerDialog([p1, p2, p3])
        self.assertEqual(dlg.list_widget.count(), 3)
        dlg.close()

    def test_init_with_nonexistent_files(self):
        from ui.dialogs.attachment_viewer import AttachmentViewerDialog
        dlg = AttachmentViewerDialog(["/nonexistent/a.png", "/nonexistent/b.pdf"])
        self.assertEqual(dlg.list_widget.count(), 2)
        dlg.close()

    def test_remove_attachment(self):
        from ui.dialogs.attachment_viewer import AttachmentViewerDialog
        p1 = self._make_file("keep.png")
        p2 = self._make_file("remove.pdf")
        dlg = AttachmentViewerDialog([p1, p2])
        self.assertEqual(len(dlg.attachment_paths), 2)
        dlg.list_widget.setCurrentRow(1)
        dlg._remove_selected()
        self.assertEqual(len(dlg.attachment_paths), 1)
        dlg.close()

    def test_no_select_disables_preview(self):
        from ui.dialogs.attachment_viewer import AttachmentViewerDialog
        dlg = AttachmentViewerDialog([])
        self.assertFalse(dlg.btn_preview.isEnabled())
        dlg.close()

    def test_select_enables_buttons(self):
        from ui.dialogs.attachment_viewer import AttachmentViewerDialog
        p1 = self._make_file("a.png")
        dlg = AttachmentViewerDialog([p1])
        # First item should be auto-selected (well, currentRowChanged will fire)
        # We just check that preview is enabled since first item is selected
        dlg.list_widget.setCurrentRow(0)
        self.assertTrue(dlg.btn_preview.isEnabled())
        dlg.close()


class TestAttachmentViewerPreview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._msg = _patch_qmessagebox()
    @classmethod
    def tearDownClass(cls):
        cls._msg.stop()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_image_preview_opens_viewer(self):
        from ui.dialogs.attachment_viewer import AttachmentViewerDialog
        p1 = os.path.join(self.tmp, "img.png")
        with open(p1, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        dlg = AttachmentViewerDialog([p1])
        dlg.list_widget.setCurrentRow(0)
        with patch("ui.dialogs.attachment_viewer.ImageViewerDialog") as mock_img:
            dlg._preview_selected()
            mock_img.assert_called_once()
        dlg.close()

    def test_pdf_preview_opens_viewer(self):
        from ui.dialogs.attachment_viewer import AttachmentViewerDialog
        f = os.path.join(self.tmp, "doc.pdf")
        from pypdf import PdfWriter
        w = PdfWriter(); w.add_blank_page(595, 842)
        with open(f, "wb") as fh:
            w.write(fh)
        dlg = AttachmentViewerDialog([f])
        dlg.list_widget.setCurrentRow(0)
        with patch("ui.dialogs.attachment_viewer.PdfViewerDialog") as mock_pdf:
            dlg._preview_selected()
            mock_pdf.assert_called_once()
        dlg.close()

    def test_doc_opens_system(self):
        from ui.dialogs.attachment_viewer import AttachmentViewerDialog
        f = os.path.join(self.tmp, "contract.docx")
        with open(f, "wb") as fh:
            fh.write(b"docx data")
        dlg = AttachmentViewerDialog([f])
        dlg.list_widget.setCurrentRow(0)
        with patch("ui.dialogs.attachment_viewer.QDesktopServices.openUrl") as mock_open:
            dlg._preview_selected()
            mock_open.assert_called_once()
        dlg.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
