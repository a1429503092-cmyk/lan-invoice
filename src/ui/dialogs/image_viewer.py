# -*- coding: utf-8 -*-
"""付款截图预览对话框 — 左侧缩略图列表 + 右侧大图预览 + 批量删除"""

import os
import shutil
from datetime import datetime

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QMessageBox, QScrollArea, QListWidget,
    QListWidgetItem, QAbstractItemView
)
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QPixmap, QIcon

from logger import getLogger
log = getLogger(__name__)

from ui.theme import ACCENT, RED, GREEN, DARK_SURFACE, DARK_BG, DARK_TEXT, DARK_TEXT_DIM


THUMB_SIZE = 120


class ImageViewerDialog(QDialog):
    def __init__(self, image_paths, current_index=0, parent=None):
        super().__init__(parent)
        self.image_paths = list(image_paths)
        self.current_index = current_index
        self.deleted_indices = set()  # 记录被删除的索引

        self.setWindowTitle("付款截图预览")
        self.resize(1100, 700)
        self.setMinimumSize(700, 400)
        self._build_ui()
        self._populate_thumbnails()
        if self.image_paths:
            self._show_image(current_index)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ── 左侧缩略图列表面板 ─────────────────────
        left_header = QHBoxLayout()
        lbl_title = QLabel("截图列表")
        lbl_title.setStyleSheet(f"color:{DARK_TEXT}; font-size:13px; font-weight:bold; background:transparent;")

        self.btn_select_all = QPushButton("全选")
        self.btn_select_all.setFixedHeight(24)
        self.btn_select_all.setFixedWidth(50)
        self.btn_select_all.setStyleSheet(
            f"font-size:11px; padding:1px 4px; color:{ACCENT}; border:1px solid {ACCENT}; background:transparent; border-radius:2px;")
        self.btn_select_all.clicked.connect(self._toggle_select_all)
        self._all_selected = False

        left_header.addWidget(lbl_title)
        left_header.addStretch()
        left_header.addWidget(self.btn_select_all)

        self.thumb_list = QListWidget()
        self.thumb_list.setIconSize(QSize(THUMB_SIZE, int(THUMB_SIZE * 0.75)))
        self.thumb_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.thumb_list.setFixedWidth(THUMB_SIZE + 40)
        self.thumb_list.setStyleSheet(
            f"QListWidget {{ background:{DARK_BG}; border: 1px solid #444; }}"
            f"QListWidget::item {{ padding: 4px; }}"
            f"QListWidget::item:selected {{ background: #3A5A8C; }}"
        )
        self.thumb_list.currentRowChanged.connect(self._on_thumb_selected)

        # 左侧删除按钮
        self.btn_delete_selected = QPushButton("删除选中")
        self.btn_delete_selected.setFixedHeight(30)
        self.btn_delete_selected.setStyleSheet(
            f"background:{RED}; color:white; font-weight:bold; border-radius:4px; padding:0 12px;")
        self.btn_delete_selected.clicked.connect(self._delete_selected)

        # ── 右侧大图预览 ───────────────────────────
        self.scroll = QScrollArea()
        self.scroll.setAlignment(Qt.AlignCenter)
        self.scroll.setStyleSheet(f"QScrollArea {{ background:{DARK_SURFACE}; border:none; }}")
        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignCenter)
        self.img_label.setStyleSheet(f"background:{DARK_SURFACE};")
        self.scroll.setWidget(self.img_label)
        self.scroll.setWidgetResizable(True)

        # ── 左右分栏 ──────────────────────────────
        body = QHBoxLayout()
        body.setSpacing(8)
        left_section = QVBoxLayout()
        left_section.setContentsMargins(0, 0, 8, 0)
        left_section.setSpacing(6)
        left_section.addLayout(left_header)
        left_section.addWidget(self.thumb_list, 1)
        left_section.addWidget(self.btn_delete_selected)
        body.addLayout(left_section)
        body.addWidget(self.scroll, 1)
        layout.addLayout(body)

        # ── 底部导航栏 ─────────────────────────────
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

    def _populate_thumbnails(self):
        self.thumb_list.blockSignals(True)
        self.thumb_list.clear()
        for i, path in enumerate(self.image_paths):
            if i in self.deleted_indices:
                continue
            name = os.path.basename(path)
            pix = QPixmap(path)
            if not pix.isNull():
                thumb = pix.scaled(THUMB_SIZE, int(THUMB_SIZE * 0.75),
                                   Qt.KeepAspectRatio, Qt.SmoothTransformation)
            else:
                thumb = QPixmap(THUMB_SIZE, int(THUMB_SIZE * 0.75))
                thumb.fill(Qt.gray)
            item = QListWidgetItem(QIcon(thumb), name)
            item.setData(Qt.UserRole, i)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.thumb_list.addItem(item)
        self.thumb_list.blockSignals(False)
        self._update_delete_button()

    def _on_thumb_selected(self, row):
        if row < 0:
            return
        item = self.thumb_list.item(row)
        if item is None:
            return
        idx = item.data(Qt.UserRole)
        if idx is not None:
            self.current_index = idx
            self._show_image(idx)

    def _show_image(self, index=None):
        if index is not None:
            self.current_index = index
        if not self.image_paths:
            self.img_label.setText("暂无截图")
            self.lbl_index.setText("0 / 0")
            return

        effective_paths = [p for i, p in enumerate(self.image_paths) if i not in self.deleted_indices]
        if not effective_paths:
            self.img_label.setText("所有截图已删除")
            self.lbl_index.setText("0 / 0")
            self.btn_prev.setEnabled(False)
            self.btn_next.setEnabled(False)
            self.btn_save_all.setVisible(False)
            return

        # Ensure current_index points to a valid non-deleted image
        if self.current_index in self.deleted_indices or self.current_index >= len(self.image_paths):
            # Find first non-deleted
            for i in range(len(self.image_paths)):
                if i not in self.deleted_indices:
                    self.current_index = i
                    break

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

        n_total = len(effective_paths)
        # Find position of current_index among effective paths
        pos = 0
        for i in range(self.current_index + 1):
            if i not in self.deleted_indices:
                pos += 1
        self.lbl_index.setText(f"{pos} / {n_total}")
        self.btn_prev.setEnabled(pos > 1)
        self.btn_next.setEnabled(pos < n_total)
        self.btn_save_all.setVisible(n_total > 1)

        # Update thumbnail selection to match current image
        for row in range(self.thumb_list.count()):
            item = self.thumb_list.item(row)
            if item and item.data(Qt.UserRole) == self.current_index:
                self.thumb_list.blockSignals(True)
                self.thumb_list.setCurrentRow(row)
                self.thumb_list.blockSignals(False)
                break

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, 'img_label'):
            self._show_image()

    def _prev(self):
        # Find previous non-deleted image
        for i in range(self.current_index - 1, -1, -1):
            if i not in self.deleted_indices:
                self.current_index = i
                self._show_image()
                return

    def _next(self):
        # Find next non-deleted image
        for i in range(self.current_index + 1, len(self.image_paths)):
            if i not in self.deleted_indices:
                self.current_index = i
                self._show_image()
                return

    def _toggle_select_all(self):
        self._all_selected = not self._all_selected
        state = Qt.Checked if self._all_selected else Qt.Unchecked
        self.btn_select_all.setText("取消" if self._all_selected else "全选")
        for row in range(self.thumb_list.count()):
            self.thumb_list.item(row).setCheckState(state)
        self._update_delete_button()

    def _update_delete_button(self):
        checked = 0
        for row in range(self.thumb_list.count()):
            item = self.thumb_list.item(row)
            if item and item.checkState() == Qt.Checked:
                checked += 1
        self.btn_delete_selected.setEnabled(checked > 0)
        self.btn_delete_selected.setText(f"删除选中 ({checked})" if checked > 0 else "删除选中")

    def _delete_selected(self):
        indices_to_delete = []
        for row in range(self.thumb_list.count()):
            item = self.thumb_list.item(row)
            if item and item.checkState() == Qt.Checked:
                idx = item.data(Qt.UserRole)
                if idx is not None:
                    indices_to_delete.append(idx)

        if not indices_to_delete:
            return

        n = len(indices_to_delete)
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除选中的 {n} 张截图吗？\n\n此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        for idx in indices_to_delete:
            self.deleted_indices.add(idx)
            # Also delete the actual file
            if idx < len(self.image_paths):
                try:
                    if os.path.exists(self.image_paths[idx]):
                        os.remove(self.image_paths[idx])
                        log.info("截图文件已删除: %s", self.image_paths[idx])
                except OSError as e:
                    log.warning("截图文件删除失败: %s → %s", self.image_paths[idx], e)

        self._all_selected = False
        self.btn_select_all.setText("全选")

        # Refresh thumbnail list
        self._populate_thumbnails()

        # Update preview
        remaining = [p for i, p in enumerate(self.image_paths) if i not in self.deleted_indices]
        if remaining:
            # Select first available
            for i in range(len(self.image_paths)):
                if i not in self.deleted_indices:
                    self.current_index = i
                    break
            self._show_image()
        else:
            self.img_label.setText("所有截图已删除")
            self.lbl_index.setText("0 / 0")

    def get_remaining_paths(self):
        """返回未被删除的截图路径列表"""
        return [p for i, p in enumerate(self.image_paths) if i not in self.deleted_indices]

    def _save_current(self):
        effective = self.get_remaining_paths()
        if not effective:
            return
        # Find current in effective list
        if self.current_index in self.deleted_indices:
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
        effective = self.get_remaining_paths()
        if not effective:
            return
        dst_dir = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if not dst_dir:
            return
        saved = 0
        for src in effective:
            if os.path.exists(src):
                dst = os.path.join(dst_dir, os.path.basename(src))
                if os.path.exists(dst):
                    base, ext = os.path.splitext(os.path.basename(src))
                    dst = os.path.join(dst_dir, f"{base}_{datetime.now().strftime('%H%M%S%f')}{ext}")
                shutil.copy2(src, dst)
                saved += 1
        QMessageBox.information(self, "保存成功", f"已保存 {saved} 张截图到：\n{dst_dir}")
