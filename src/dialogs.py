# -*- coding: utf-8 -*-
"""对话框组件 — 向后兼容重导出，实际实现在 ui/dialogs/ 子包中"""

from ui.dialogs.image_viewer import ImageViewerDialog
from ui.dialogs.invoice_manager import InvoiceManagerDialog
from ui.dialogs.settings import SettingsDialog
from ui.dialogs.delete_confirm import DeleteConfirmDialog

__all__ = [
    "ImageViewerDialog",
    "InvoiceManagerDialog",
    "SettingsDialog",
    "DeleteConfirmDialog",
]
