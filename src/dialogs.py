# -*- coding: utf-8 -*-
"""对话框组件 — 截图预览、发票管理、合同管理、设置、删除确认"""

import os
import shutil
from datetime import datetime

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit,
    QFileDialog, QMessageBox, QScrollArea, QFrame, QListWidget,
    QListWidgetItem, QCheckBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QColor

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
        layout.setSpacing(6)

        self.scroll = QScrollArea()
        self.scroll.setAlignment(Qt.AlignCenter)
        self.scroll.setStyleSheet("QScrollArea { background:#2b2b2b; border:none; }")
        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignCenter)
        self.img_label.setStyleSheet("background:#2b2b2b;")
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
        self.lbl_index.setStyleSheet("color:#eee; font-size:13px; background:transparent;")

        self.btn_next = QPushButton("下一张 ▶")
        self.btn_next.setFixedHeight(32)
        self.btn_next.clicked.connect(self._next)

        self.btn_save = QPushButton("💾 下载当前截图")
        self.btn_save.setFixedHeight(32)
        self.btn_save.setStyleSheet(
            "background:#1E6FBF; color:white; font-weight:bold; border-radius:4px; padding:0 12px;")
        self.btn_save.clicked.connect(self._save_current)

        self.btn_save_all = QPushButton("📦 下载全部截图")
        self.btn_save_all.setFixedHeight(32)
        self.btn_save_all.setStyleSheet(
            "background:#2E8B57; color:white; font-weight:bold; border-radius:4px; padding:0 12px;")
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

        self.setStyleSheet("""
            QDialog { background:#1e1e1e; }
            QPushButton {
                border:1px solid #555; border-radius:4px;
                padding:4px 14px; background:#3a3a3a; color:#eee; font-size:13px;
            }
            QPushButton:hover { background:#4a4a4a; }
        """)

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


# ─────────────────────────────────────────────
#  发票 PDF 查看/下载对话框
# ─────────────────────────────────────────────

class InvoiceManagerDialog(QDialog):
    """发票 PDF 查看与下载对话框（仿合同管理）"""

    def __init__(self, pdf_path: str, rec_name: str = "", parent=None):
        super().__init__(parent)
        self.pdf_path = pdf_path
        self.rec_name = rec_name
        title = f"发票PDF — {rec_name}" if rec_name else "发票PDF"
        self.setWindowTitle(title)
        self.resize(520, 200)
        self.setMinimumSize(380, 160)
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        lbl_title = QLabel("📄 发票原始 PDF 文件")
        lbl_title.setStyleSheet("font-size:13px; font-weight:bold; color:#333;")
        layout.addWidget(lbl_title)

        # 文件信息展示
        self.lbl_path = QLabel()
        self.lbl_path.setWordWrap(True)
        self.lbl_path.setStyleSheet(
            "font-size:12px; color:#555; background:#F5F8FC; "
            "border:1px solid #D0DCF0; border-radius:4px; padding:6px 8px;"
        )
        layout.addWidget(self.lbl_path)

        # 按钮行
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(8)

        self.btn_open = QPushButton("📂 打开")
        self.btn_open.setFixedHeight(32)
        self.btn_open.clicked.connect(self._open_pdf)

        self.btn_download = QPushButton("💾 下载另存")
        self.btn_download.setFixedHeight(32)
        self.btn_download.clicked.connect(self._download_pdf)

        self.btn_close = QPushButton("关闭")
        self.btn_close.setFixedHeight(32)
        self.btn_close.clicked.connect(self.accept)

        btn_bar.addWidget(self.btn_open)
        btn_bar.addWidget(self.btn_download)
        btn_bar.addStretch()
        btn_bar.addWidget(self.btn_close)
        layout.addLayout(btn_bar)

        self.setStyleSheet("""
            QDialog { background:#F5F8FC; }
            QPushButton {
                border:1px solid #B0C4DE; border-radius:4px;
                padding:4px 14px; background:#FFFFFF; font-size:13px;
            }
            QPushButton:hover { background:#E8F0FE; border-color:#1E6FBF; }
        """)

    def _refresh(self):
        if self.pdf_path and os.path.exists(self.pdf_path):
            size_kb = os.path.getsize(self.pdf_path) / 1024
            size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.2f} MB"
            self.lbl_path.setText(
                f"<b>{os.path.basename(self.pdf_path)}</b><br>"
                f"<span style='color:#888;'>{self.pdf_path}</span><br>"
                f"<span style='color:#1E6FBF;'>文件大小：{size_str}</span>"
            )
            self.btn_open.setEnabled(True)
            self.btn_download.setEnabled(True)
        else:
            self.lbl_path.setText(
                f"<span style='color:#CC0000;'>⚠️ 文件不存在或路径未记录</span><br>"
                f"<span style='color:#aaa;'>{self.pdf_path or '（无路径信息）'}</span>"
            )
            self.btn_open.setEnabled(False)
            self.btn_download.setEnabled(False)

    def _open_pdf(self):
        if not os.path.exists(self.pdf_path):
            QMessageBox.warning(self, "文件不存在", f"找不到文件：\n{self.pdf_path}")
            return
        try:
            os.startfile(self.pdf_path)
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


# ─────────────────────────────────────────────
#  合同管理对话框
# ─────────────────────────────────────────────

class ContractManagerDialog(QDialog):
    """合同列表管理对话框：查看、下载、打开合同"""

    def __init__(self, contract_paths, rec_name="", parent=None):
        super().__init__(parent)
        self.contract_paths = list(contract_paths)  # 副本，不直接改原列表
        self.rec_name = rec_name
        self.setWindowTitle(f"合同管理 — {rec_name}" if rec_name else "合同管理")
        self.resize(600, 420)
        self.setMinimumSize(400, 300)
        self._build_ui()
        self._refresh_list()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        lbl = QLabel("📄 合同文件列表（双击打开）")
        lbl.setStyleSheet("font-size:13px; font-weight:bold; color:#333;")
        layout.addWidget(lbl)

        self.list_widget = QListWidget()
        self.list_widget.setAlternatingRowColors(True)
        self.list_widget.setStyleSheet("""
            QListWidget { font-size:13px; border:1px solid #ccc; border-radius:4px; }
            QListWidget::item { padding:6px 8px; }
            QListWidget::item:selected { background:#BDD7EE; color:#000; }
            QListWidget::item:alternate { background:#F5F8FC; }
        """)
        self.list_widget.itemDoubleClicked.connect(self._open_selected)
        # 选中项变化时同步更新按钮可用状态
        self.list_widget.currentItemChanged.connect(lambda *_: self._update_btn_state())
        layout.addWidget(self.list_widget)

        # 底部按钮行
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(8)

        self.btn_open = QPushButton("📂 打开")
        self.btn_open.setFixedHeight(32)
        self.btn_open.clicked.connect(self._open_selected)

        self.btn_download = QPushButton("💾 下载另存")
        self.btn_download.setFixedHeight(32)
        self.btn_download.clicked.connect(self._download_selected)

        self.btn_del = QPushButton("🗑 移除")
        self.btn_del.setFixedHeight(32)
        self.btn_del.setStyleSheet("color:#CC0000;")
        self.btn_del.clicked.connect(self._remove_selected)

        self.btn_close = QPushButton("关闭")
        self.btn_close.setFixedHeight(32)
        self.btn_close.clicked.connect(self.accept)

        btn_bar.addWidget(self.btn_open)
        btn_bar.addWidget(self.btn_download)
        btn_bar.addWidget(self.btn_del)
        btn_bar.addStretch()
        btn_bar.addWidget(self.btn_close)
        layout.addLayout(btn_bar)

        hint = QLabel("提示：支持 PDF 和 Word（.docx/.doc）格式，用系统默认程序打开")
        hint.setStyleSheet("color:#888; font-size:11px;")
        layout.addWidget(hint)

        self.setStyleSheet("""
            QDialog { background:#F5F8FC; }
            QPushButton {
                border:1px solid #B0C4DE; border-radius:4px;
                padding:4px 14px; background:#FFFFFF; font-size:13px;
            }
            QPushButton:hover { background:#E8F0FE; border-color:#1E6FBF; }
        """)

    def _refresh_list(self):
        self.list_widget.clear()
        for path in self.contract_paths:
            fname = os.path.basename(path)
            exists = os.path.exists(path)
            item = QListWidgetItem()
            ext = os.path.splitext(fname)[1].lower()
            if ext == ".pdf":
                icon_txt = "📄"
            elif ext in (".docx", ".doc"):
                icon_txt = "📝"
            else:
                icon_txt = "📎"
            status = "" if exists else "  ⚠️ 文件已移动"
            item.setText(f"  {icon_txt}  {fname}{status}")
            item.setData(Qt.UserRole, path)
            if not exists:
                item.setForeground(QColor("#CC0000"))
            self.list_widget.addItem(item)
        # 有条目时自动选中第一项，确保按钮默认可用
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)
        self._update_btn_state()

    def _update_btn_state(self):
        has_sel = self.list_widget.currentRow() >= 0
        self.btn_open.setEnabled(has_sel)
        self.btn_download.setEnabled(has_sel)
        self.btn_del.setEnabled(has_sel)

    def _get_selected_path(self):
        item = self.list_widget.currentItem()
        if item:
            return item.data(Qt.UserRole)
        return None

    def _open_selected(self):
        path = self._get_selected_path()
        if not path:
            return
        if not os.path.exists(path):
            QMessageBox.warning(self, "文件不存在", f"找不到文件：\n{path}")
            return
        try:
            os.startfile(path)
        except Exception as e:
            QMessageBox.warning(self, "打开失败", f"无法打开文件：\n{e}")

    def _download_selected(self):
        path = self._get_selected_path()
        if not path:
            return
        if not os.path.exists(path):
            QMessageBox.warning(self, "文件不存在", f"找不到文件：\n{path}")
            return
        ext = os.path.splitext(path)[1]
        dst, _ = QFileDialog.getSaveFileName(
            self, "另存合同文件", os.path.basename(path),
            f"文件 (*{ext});;所有文件 (*)"
        )
        if dst:
            shutil.copy2(path, dst)
            QMessageBox.information(self, "下载成功", f"合同已保存到：\n{dst}")

    def _remove_selected(self):
        row = self.list_widget.currentRow()
        if row < 0:
            return
        fname = os.path.basename(self.contract_paths[row])
        reply = QMessageBox.question(
            self, "确认移除",
            f"确认从列表中移除「{fname}」？\n（文件本身不会被删除）",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.contract_paths.pop(row)
            self._refresh_list()


# ─────────────────────────────────────────────
#  设置对话框
# ─────────────────────────────────────────────

class SettingsDialog(QDialog):
    """设置对话框：数据目录配置 + 软件另存"""

    def __init__(self, app_ref, parent=None):
        super().__init__(parent)
        self._app = app_ref  # InvoiceApp 实例
        self.setWindowTitle("⚙️ 设置")
        self.resize(560, 320)
        self.setMinimumSize(480, 280)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        # ── 标题 ──────────────────────────────────
        lbl_title = QLabel("⚙️ 软件设置")
        lbl_title.setStyleSheet("font-size:15px; font-weight:bold; color:#1E6FBF;")
        layout.addWidget(lbl_title)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#D0DCF0;")
        layout.addWidget(sep)

        # ── 1. 数据目录设置 ───────────────────────
        grp_data = QFrame()
        grp_data.setStyleSheet(
            "QFrame { background:#F0F7FF; border:1px solid #B8D4F0; border-radius:6px; }")
        data_layout = QVBoxLayout(grp_data)
        data_layout.setContentsMargins(14, 10, 14, 10)
        data_layout.setSpacing(8)

        lbl_data_title = QLabel("📁  数据存储位置")
        lbl_data_title.setStyleSheet("font-size:13px; font-weight:bold; color:#333;")
        data_layout.addWidget(lbl_data_title)

        lbl_hint = QLabel("软件的数据文件（JSON）、截图、合同将保存在此目录下。\n"
                          "⚠️ 更改目录后，旧目录中的文件不会自动迁移，请手动复制。")
        lbl_hint.setStyleSheet("font-size:11px; color:#777;")
        lbl_hint.setWordWrap(True)
        data_layout.addWidget(lbl_hint)

        row_dir = QHBoxLayout()
        row_dir.setSpacing(6)
        self.edit_data_dir = QLineEdit(self._app._data_dir)
        self.edit_data_dir.setReadOnly(True)
        self.edit_data_dir.setFixedHeight(30)
        self.edit_data_dir.setStyleSheet(
            "background:#fff; border:1px solid #B0C4DE; border-radius:4px; padding:2px 6px;")
        btn_browse = QPushButton("浏览…")
        btn_browse.setFixedHeight(30)
        btn_browse.setFixedWidth(70)
        btn_browse.clicked.connect(self._browse_data_dir)
        row_dir.addWidget(self.edit_data_dir, 1)
        row_dir.addWidget(btn_browse)
        data_layout.addLayout(row_dir)

        btn_apply_dir = QPushButton("✅ 应用新目录")
        btn_apply_dir.setFixedHeight(32)
        btn_apply_dir.setStyleSheet(
            "background:#1E6FBF; color:white; font-weight:bold; border-radius:4px;")
        btn_apply_dir.clicked.connect(self._apply_data_dir)
        data_layout.addWidget(btn_apply_dir)

        layout.addWidget(grp_data)

        # ── 2. 软件另存 ───────────────────────────
        grp_save = QFrame()
        grp_save.setStyleSheet(
            "QFrame { background:#F0FFF4; border:1px solid #A8D8B0; border-radius:6px; }")
        save_layout = QVBoxLayout(grp_save)
        save_layout.setContentsMargins(14, 10, 14, 10)
        save_layout.setSpacing(6)

        lbl_save_title = QLabel("💾  软件另存（制作便携版）")
        lbl_save_title.setStyleSheet("font-size:13px; font-weight:bold; color:#2E7D32;")
        save_layout.addWidget(lbl_save_title)

        lbl_save_hint = QLabel(
            "将软件主程序（invoice_tool.py）及当前所有数据（JSON、截图、合同）\n"
            "复制到您选择的目标文件夹，复制后直接运行即可，无需重新安装。"
        )
        lbl_save_hint.setStyleSheet("font-size:11px; color:#777;")
        lbl_save_hint.setWordWrap(True)
        save_layout.addWidget(lbl_save_hint)

        btn_saveas = QPushButton("📂 选择目标位置并另存软件")
        btn_saveas.setFixedHeight(32)
        btn_saveas.setStyleSheet(
            "background:#2E7D32; color:white; font-weight:bold; border-radius:4px;")
        btn_saveas.clicked.connect(self._saveas_software)
        save_layout.addWidget(btn_saveas)

        layout.addWidget(grp_save)
        layout.addStretch()

        # ── 底部关闭 ──────────────────────────────
        btn_close = QPushButton("关闭")
        btn_close.setFixedHeight(32)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignRight)

        self.setStyleSheet("""
            QDialog { background:#F5F8FC; }
            QPushButton {
                border:1px solid #B0C4DE; border-radius:4px;
                padding:4px 14px; background:#FFFFFF; font-size:13px;
            }
            QPushButton:hover { background:#E8F0FE; border-color:#1E6FBF; }
        """)

    def _browse_data_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择数据存储目录", self._app._data_dir)
        if d:
            self.edit_data_dir.setText(d)

    def _apply_data_dir(self):
        new_dir = self.edit_data_dir.text().strip()
        if not new_dir or not os.path.isdir(new_dir):
            QMessageBox.warning(self, "目录无效", "请先选择一个有效的目录。")
            return
        if os.path.abspath(new_dir) == os.path.abspath(self._app._data_dir):
            QMessageBox.information(self, "无需更改", "目标目录与当前目录相同。")
            return

        # 统计旧目录中的文件数量
        old_files_count = 0
        if os.path.exists(self._app._data_file):
            old_files_count += 1
        if os.path.isdir(self._app._screenshot_dir):
            old_files_count += len(os.listdir(self._app._screenshot_dir))
        if os.path.isdir(self._app._contract_dir):
            old_files_count += len(os.listdir(self._app._contract_dir))

        migration_hint = ""
        if old_files_count > 0:
            migration_hint = f"\n\n📦 检测到旧目录有 {old_files_count} 个文件，将自动迁移到新目录。"

        reply = QMessageBox.question(
            self, "确认更改数据目录",
            f"确认将数据目录切换为：\n{new_dir}\n\n"
            f"✅ 新目录下的数据文件会自动加载。\n{migration_hint}"
            "软件将立即以新目录重新初始化。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if reply != QMessageBox.Yes:
            return

        # 先保存当前数据到旧路径
        self._app._save_data()

        # 自动迁移旧目录文件
        if old_files_count > 0:
            old_data_file = self._app._data_file
            old_screenshot_dir = self._app._screenshot_dir
            old_contract_dir = self._app._contract_dir
            
            # 确保新目录结构存在
            os.makedirs(new_dir, exist_ok=True)
            os.makedirs(os.path.join(new_dir, "screenshots"), exist_ok=True)
            os.makedirs(os.path.join(new_dir, "contracts"), exist_ok=True)
            
            errors = []
            
            # 迁移数据 JSON
            if os.path.exists(old_data_file):
                try:
                    dst = os.path.join(new_dir, "invoices_data.json")
                    shutil.copy2(old_data_file, dst)
                except Exception as e:
                    errors.append(f"invoices_data.json: {e}")
            
            # 迁移截图目录
            if os.path.isdir(old_screenshot_dir):
                for fname in os.listdir(old_screenshot_dir):
                    src = os.path.join(old_screenshot_dir, fname)
                    dst = os.path.join(new_dir, "screenshots", fname)
                    try:
                        if os.path.isfile(src):
                            shutil.copy2(src, dst)
                    except Exception as e:
                        errors.append(f"screenshots/{fname}: {e}")
            
            # 迁移合同目录
            if os.path.isdir(old_contract_dir):
                for fname in os.listdir(old_contract_dir):
                    src = os.path.join(old_contract_dir, fname)
                    dst = os.path.join(new_dir, "contracts", fname)
                    try:
                        if os.path.isfile(src):
                            shutil.copy2(src, dst)
                    except Exception as e:
                        errors.append(f"contracts/{fname}: {e}")
            
            if errors:
                QMessageBox.warning(
                    self, "部分文件迁移失败",
                    "以下文件迁移失败：\n\n" + "\n".join(errors) +
                    "\n\n请手动将旧目录文件复制到新目录。"
                )

        # 切换目录
        self._app._data_dir       = new_dir
        self._app._data_file      = os.path.join(new_dir, "invoices_data.json")
        self._app._screenshot_dir = os.path.join(new_dir, "screenshots")
        self._app._contract_dir   = os.path.join(new_dir, "contracts")
        os.makedirs(self._app._screenshot_dir, exist_ok=True)
        os.makedirs(self._app._contract_dir,   exist_ok=True)

        # 保存配置（下次启动时自动使用此目录）
        self._app._save_config_dir(new_dir)

        # 重新加载（新目录可能有历史数据）
        self._app.records.clear()
        self._app.table.setRowCount(0)
        self._app._load_data()

        QMessageBox.information(
            self, "已切换",
            f"数据目录已切换为：\n{new_dir}\n\n"
            f"旧目录的文件已自动迁移到新目录。\n\n"
            f"下次启动软件时将自动使用此目录。"
        )

    def _saveas_software(self):
        """将软件及数据整体复制到目标文件夹（便携版）"""
        dst_dir = QFileDialog.getExistingDirectory(self, "选择软件保存目录")
        if not dst_dir:
            return

        src_script = os.path.abspath(__file__)  # invoice_tool.py 所在绝对路径
        src_base   = self._app._base_dir

        # 计算要复制的内容
        items = []
        # 主程序脚本
        if os.path.exists(src_script):
            items.append(("file", src_script, os.path.join(dst_dir, os.path.basename(src_script))))
        # requirements.txt（如果存在）
        req_src = os.path.join(src_base, "requirements.txt")
        if os.path.exists(req_src):
            items.append(("file", req_src, os.path.join(dst_dir, "requirements.txt")))
        # 启动批处理（如果存在）
        bat_src = os.path.join(src_base, "启动.bat")
        if os.path.exists(bat_src):
            items.append(("file", bat_src, os.path.join(dst_dir, "启动.bat")))
        # 数据 JSON
        if os.path.exists(self._app._data_file):
            items.append(("file", self._app._data_file, os.path.join(dst_dir, "invoices_data.json")))
        # screenshots 目录
        if os.path.isdir(self._app._screenshot_dir):
            items.append(("dir", self._app._screenshot_dir, os.path.join(dst_dir, "screenshots")))
        # contracts 目录
        if os.path.isdir(self._app._contract_dir):
            items.append(("dir", self._app._contract_dir, os.path.join(dst_dir, "contracts")))

        if not items:
            QMessageBox.warning(self, "无内容", "未找到可复制的软件文件。")
            return

        reply = QMessageBox.question(
            self, "确认另存",
            f"确认将软件及数据复制到：\n{dst_dir}\n\n"
            f"包含：主程序、数据文件、截图目录、合同目录",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if reply != QMessageBox.Yes:
            return

        errors = []
        for kind, src, dst in items:
            try:
                if kind == "file":
                    shutil.copy2(src, dst)
                elif kind == "dir":
                    if os.path.exists(dst):
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst)
            except Exception as e:
                errors.append(f"{os.path.basename(src)}：{e}")

        if errors:
            QMessageBox.warning(self, "部分文件复制失败",
                "以下文件复制失败：\n\n" + "\n".join(errors))
        else:
            QMessageBox.information(
                self, "另存成功",
                f"软件已成功复制到：\n{dst_dir}\n\n"
                "将此文件夹拷贝到任意位置（含U盘）均可直接运行。\n"
                "运行方式：双击 启动.bat 或直接执行 invoice_tool.py"
            )
            try:
                os.startfile(dst_dir)
            except Exception:
                pass


# ─────────────────────────────────────────────
#  删除确认对话框（双重保险：勾选后才能删除）
# ─────────────────────────────────────────────
# ─────────────────────────────────────────────
#  删除确认对话框（双重保险：勾选后才能删除）
# ─────────────────────────────────────────────

class DeleteConfirmDialog(QDialog):
    """带勾选框的删除确认弹窗，必须勾选才可点击「确认删除」"""

    def __init__(self, records: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚠️ 确认删除")
        self.setMinimumWidth(560)
        self._build_ui(records)

    def _build_ui(self, records: list):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # 警告图标 + 标题
        title = QLabel("⚠️ 即将永久删除以下发票记录，请仔细核对：")
        title.setStyleSheet("font-size:14px; font-weight:bold; color:#CC0000;")
        layout.addWidget(title)

        # 发票列表
        detail = QLabel()
        lines = []
        for r in records:
            inv_date = r.get("invoice_date", "—")
            inv_no   = r.get("invoice_no",   "无发票号")
            seller   = r.get("seller_name",   "—")
            total    = r.get("total",        "—")
            fname    = r.get("file",          "未知文件")
            lines.append(
                f"📄 {fname}\n"
                f"   发票号：{inv_no}   日期：{inv_date}\n"
                f"   销售方：{seller}   合计：¥{total}"
            )
        detail.setText("\n\n".join(lines))
        detail.setStyleSheet(
            "background:#FFF3CD; border:1px solid #FFEAA7; "
            "border-radius:6px; padding:10px 12px; "
            "font-size:12px; color:#333; line-height:1.6;"
        )
        detail.setWordWrap(True)
        layout.addWidget(detail)

        # 危险提示
        warn = QLabel("⚠️ 原始 PDF 文件将同步永久删除，无法恢复！")
        warn.setStyleSheet("font-size:13px; font-weight:bold; color:#CC0000;")
        layout.addWidget(warn)

        # 勾选框（必须勾选）
        self.cb = QCheckBox("我已确认上述信息，知晓删除后果，自愿删除")
        self.cb.setStyleSheet("font-size:13px; font-weight:bold; color:#1A1A1A;")
        self.cb.stateChanged.connect(self._on_check)
        layout.addWidget(self.cb)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_ok = QPushButton("✅ 确认删除")
        self.btn_ok.setEnabled(False)   # 默认禁用，必须勾选
        self.btn_ok.setStyleSheet("""
            QPushButton { background:#CC0000; color:white; border-radius:4px;
                          font-size:13px; font-weight:bold; padding:7px 22px; }
            QPushButton:enabled { background:#CC0000; }
            QPushButton:!enabled { background:#AAAAAA; color:#666; }
        """)
        self.btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("取消")
        btn_cancel.setStyleSheet(
            "QPushButton { background:#F0F0F0; color:#333; border-radius:4px; "
            "font-size:13px; padding:7px 18px; }"
        )
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_ok)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

    def _on_check(self, state):
        self.btn_ok.setEnabled(state == Qt.Checked)

