# -*- coding: utf-8 -*-
"""付款截图预览对话框"""

import os
import shutil
from datetime import datetime

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QMessageBox, QScrollArea
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap

from ui.theme import ACCENT, GREEN, DARK_SURFACE, DARK_TEXT


class ImageViewerDialog(QDialog):
    def __init__(self, image_paths, current_index=0, parent=None):
        super().__init__(parent)
        self.image_paths = image_paths
        self.current_index = current_index
        self.setWindowTitle("付款截图预览")
        self.resize(900, 700)
        self.setMinimumSize(400, 300)
        self._build_ui()
        self._show_image()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.scroll = QScrollArea()
        self.scroll.setAlignment(Qt.AlignCenter)
        self.scroll.setStyleSheet(f"QScrollArea {{ background:{DARK_SURFACE}; border:none; }}")
        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignCenter)
        self.img_label.setStyleSheet(f"background:{DARK_SURFACE};")
        self.scroll.setWidget(self.img_label)
        self.scroll.setWidgetResizable(True)
        layout.addWidget(self.scroll)

        nav = QHBoxLayout()
        nav.setSpacing(8)

        self.btn_prev = QPushButton("◀ 上一张")
        self.btn_prev.setFixedHeight(32)
        self.btn_prev.clicked.connect(self._prev)

        self.lbl_index = QLabel()
        self.lbl_index.setAlignment(Qt.AlignCenter)
        self.lbl_index.setStyleSheet(f"color:{DARK_TEXT}; font-size:13px; background:transparent;")

        self.btn_next = QPushButton("下一张 ▶")
        self.btn_next.setFixedHeight(32)
        self.btn_next.clicked.connect(self._next)

        self.btn_save = QPushButton("下载当前截图")
        self.btn_save.setFixedHeight(32)
        self.btn_save.setStyleSheet(
            f"background:{ACCENT}; color:white; font-weight:bold; border-radius:4px; padding:0 12px;")
        self.btn_save.clicked.connect(self._save_current)

        self.btn_save_all = QPushButton("下载全部截图")
        self.btn_save_all.setFixedHeight(32)
        self.btn_save_all.setStyleSheet(
            f"background:{GREEN}; color:white; font-weight:bold; border-radius:4px; padding:0 12px;")
        self.btn_save_all.clicked.connect(self._save_all)

        nav.addWidget(self.btn_prev)
        nav.addStretch()
        nav.addWidget(self.lbl_index)
        nav.addStretch()
        nav.addWidget(self.btn_next)
        nav.addSpacing(20)
        nav.addWidget(self.btn_save)
        nav.addWidget(self.btn_save_all)
        layout.addLayout(nav)

        from ui.theme import DIALOG_QSS_DARK
        self.setStyleSheet(DIALOG_QSS_DARK)
        for btn in self.findChildren(QPushButton):
            btn.setCursor(Qt.PointingHandCursor)

    def _show_image(self):
        if not self.image_paths:
            self.img_label.setText("暂无截图")
            return
        path = self.image_paths[self.current_index]
        if os.path.exists(path):
            pix = QPixmap(path)
            max_w = max(self.scroll.width() - 20, 100)
            max_h = max(self.scroll.height() - 20, 100)
            if pix.width() > max_w or pix.height() > max_h:
                pix = pix.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.img_label.setPixmap(pix)
        else:
            self.img_label.setText(f"图片文件不存在：\n{path}")

        n = len(self.image_paths)
        self.lbl_index.setText(f"{self.current_index + 1} / {n}")
        self.btn_prev.setEnabled(self.current_index > 0)
        self.btn_next.setEnabled(self.current_index < n - 1)
        self.btn_save_all.setVisible(n > 1)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._show_image()

    def _prev(self):
        if self.current_index > 0:
            self.current_index -= 1
            self._show_image()

    def _next(self):
        if self.current_index < len(self.image_paths) - 1:
            self.current_index += 1
            self._show_image()

    def _save_current(self):
        if not self.image_paths:
            return
        src = self.image_paths[self.current_index]
        if not os.path.exists(src):
            QMessageBox.warning(self, "错误", f"文件不存在：{src}")
            return
        ext = os.path.splitext(src)[1] or ".png"
        dst, _ = QFileDialog.getSaveFileName(
            self, "保存截图", os.path.basename(src),
            f"图片文件 (*{ext});;所有文件 (*)"
        )
        if dst:
            shutil.copy2(src, dst)
            QMessageBox.information(self, "保存成功", f"截图已保存到：\n{dst}")

    def _save_all(self):
        if not self.image_paths:
            return
        dst_dir = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if not dst_dir:
            return
        saved = 0
        for src in self.image_paths:
            if os.path.exists(src):
                dst = os.path.join(dst_dir, os.path.basename(src))
                if os.path.exists(dst):
                    base, ext = os.path.splitext(os.path.basename(src))
                    dst = os.path.join(dst_dir, f"{base}_{datetime.now().strftime('%H%M%S%f')}{ext}")
                shutil.copy2(src, dst)
                saved += 1
        QMessageBox.information(self, "保存成功", f"已保存 {saved} 张截图到：\n{dst_dir}")
