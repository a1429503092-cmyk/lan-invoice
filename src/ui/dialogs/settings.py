# -*- coding: utf-8 -*-
"""设置对话框：数据目录配置 + 软件另存 + 数据备份恢复"""

import os
import json
import shutil
import zipfile

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit,
    QFileDialog, QMessageBox, QFrame, QListWidget
)
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QDesktopServices

from logger import getLogger
log = getLogger(__name__)

from ui.theme import (TEXT, TEXT_SEC, TEXT_DIM, ACCENT,
                       BG_ALT, BORDER_LIGHT, FS, FS_SM)


class SettingsDialog(QDialog):
    """设置对话框：数据目录配置 + 软件另存 + 数据备份恢复"""

    def __init__(self, app_ref, parent=None):
        super().__init__(parent)
        self._app = app_ref
        self.setWindowTitle("设置")
        self.resize(480, 360)
        self.setMinimumSize(420, 320)
        self._build_ui()

    # ── 辅助组件 ───────────────────────────────

    def _hline(self) -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.HLine)
        f.setStyleSheet(f"color:{BORDER_LIGHT}; border:none;")
        f.setFixedHeight(1)
        return f

    def _stat_label(self, label: str, value: str) -> QLabel:
        return QLabel(f"<span style='color:{TEXT_DIM};font-size:11px;'>{label}</span> "
                      f"<span style='color:{TEXT};font-size:13px;font-weight:bold;'>{value}</span>")

    def _section_title(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"font-size:12px; font-weight:bold; color:{TEXT_SEC};")
        return lbl

    def _calc_data_size(self) -> str:
        data_dir = self._app._data_dir
        total = 0
        if os.path.isdir(data_dir):
            for dirpath, _, filenames in os.walk(data_dir):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    if os.path.isfile(fp):
                        total += os.path.getsize(fp)
        if total < 1024:
            return f"{total} B"
        elif total < 1024 * 1024:
            return f"{total / 1024:.1f} KB"
        else:
            return f"{total / (1024 * 1024):.1f} MB"

    # ── UI 构建 ─────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        title_row = QHBoxLayout()
        lbl_title = QLabel("设置")
        lbl_title.setStyleSheet(f"font-size:15px; font-weight:bold; color:{TEXT};")
        title_row.addWidget(lbl_title)
        title_row.addStretch()
        lbl_ver = QLabel(f"v{getattr(self._app, 'APP_VERSION', '')}")
        lbl_ver.setStyleSheet(f"font-size:11px; color:{TEXT_DIM};")
        title_row.addWidget(lbl_ver)
        layout.addLayout(title_row)

        layout.addWidget(self._hline())

        layout.addWidget(self._section_title("数据存储"))

        invoice_count = len(self._app.records)
        screenshots = sum(len(r.get("screenshots", [])) for r in self._app.records)
        contracts = sum(len(r.get("contracts", [])) for r in self._app.records)
        data_size = self._calc_data_size()

        stats_row = QHBoxLayout()
        stats_row.setSpacing(24)
        stats_row.addWidget(self._stat_label("发票", f"{invoice_count} 条"))
        stats_row.addWidget(self._stat_label("截图", f"{screenshots} 个"))
        stats_row.addWidget(self._stat_label("合同", f"{contracts} 个"))
        stats_row.addWidget(self._stat_label("大小", data_size))
        stats_row.addStretch()
        layout.addLayout(stats_row)

        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        self.edit_data_dir = QLineEdit(self._app._data_dir)
        self.edit_data_dir.setReadOnly(True)
        self.edit_data_dir.setFixedHeight(32)
        self.edit_data_dir.setStyleSheet(
            f"background:{BG_ALT}; border:none; "
            "padding:2px 6px; font-size:11px;")
        btn_browse = QPushButton("浏览…")
        btn_browse.setFixedHeight(32)
        btn_browse.clicked.connect(self._browse_data_dir)
        path_row.addWidget(self.edit_data_dir, 1)
        path_row.addWidget(btn_browse)
        layout.addLayout(path_row)

        btn_apply = QPushButton("应用新目录")
        btn_apply.setFixedHeight(32)
        btn_apply.clicked.connect(self._apply_data_dir)
        layout.addWidget(btn_apply)

        layout.addWidget(self._hline())

        layout.addWidget(self._section_title("软件另存（便携版）"))
        save_hint = QLabel(
            "将软件及全部数据复制到目标文件夹，拷贝后可随身携带直接运行。"
        )
        save_hint.setStyleSheet(f"font-size:11px; color:{TEXT_DIM};")
        save_hint.setWordWrap(True)
        layout.addWidget(save_hint)

        btn_saveas = QPushButton("选择目录另存…")
        btn_saveas.setFixedHeight(32)
        btn_saveas.clicked.connect(self._saveas_software)
        layout.addWidget(btn_saveas)

        layout.addWidget(self._hline())

        layout.addWidget(self._section_title("标签模板"))
        tag_hint = QLabel("定义发票记录的自定义标签字段，将在表格中作为可编辑列显示。")
        tag_hint.setStyleSheet(f"font-size:11px; color:{TEXT_DIM};")
        tag_hint.setWordWrap(True)
        layout.addWidget(tag_hint)

        tag_row = QHBoxLayout()
        tag_row.setSpacing(8)
        self.edit_tag_name = QLineEdit()
        self.edit_tag_name.setPlaceholderText("新标签名（如：项目名称）")
        self.edit_tag_name.setFixedHeight(32)
        btn_add_tag = QPushButton("添加标签")
        btn_add_tag.setFixedHeight(32)
        btn_add_tag.clicked.connect(self._add_tag_template)
        tag_row.addWidget(self.edit_tag_name, 1)
        tag_row.addWidget(btn_add_tag)
        layout.addLayout(tag_row)

        self.tag_list = QListWidget()
        self.tag_list.setMaximumHeight(100)
        self.tag_list.setStyleSheet(f"background:{BG_ALT}; border:none; font-size:12px;")
        self._load_tag_templates()
        layout.addWidget(self.tag_list)

        btn_del_tag = QPushButton("删除选中标签")
        btn_del_tag.setFixedHeight(28)
        btn_del_tag.clicked.connect(self._del_tag_template)
        layout.addWidget(btn_del_tag)

        layout.addWidget(self._hline())

        layout.addWidget(self._section_title("数据备份与恢复"))

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_backup = QPushButton("备份数据…")
        btn_backup.setFixedHeight(32)
        btn_backup.clicked.connect(self._backup_data)
        btn_restore = QPushButton("恢复数据…")
        btn_restore.setFixedHeight(32)
        btn_restore.clicked.connect(self._restore_data)
        btn_row.addWidget(btn_backup)
        btn_row.addWidget(btn_restore)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addStretch()

        btn_close = QPushButton("关闭")
        btn_close.setFixedHeight(32)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignRight)

        from ui.theme import DIALOG_QSS
        self.setStyleSheet(DIALOG_QSS)
        for btn in self.findChildren(QPushButton):
            btn.setCursor(Qt.PointingHandCursor)

    # ── 标签模板管理 ─────────────────────────────

    def _load_tag_templates(self):
        self.tag_list.clear()
        templates = self._get_tag_templates()
        for name in templates:
            self.tag_list.addItem(name)

    def _get_tag_templates(self) -> list[str]:
        try:
            with open(self._app._config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
                return config.get("tag_templates", ["企业号"])
        except (OSError, json.JSONDecodeError):
            return ["企业号"]

    def _save_tag_templates(self, templates: list[str]):
        try:
            config = {}
            if os.path.exists(self._app._config_file):
                with open(self._app._config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
            config["tag_templates"] = templates
            os.makedirs(os.path.dirname(self._app._config_file), exist_ok=True)
            with open(self._app._config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def _add_tag_template(self):
        name = self.edit_tag_name.text().strip()
        if not name:
            return
        templates = self._get_tag_templates()
        if name in templates:
            QMessageBox.information(self, "提示", f"标签「{name}」已存在。")
            return
        templates.append(name)
        self._save_tag_templates(templates)
        self._load_tag_templates()
        self.edit_tag_name.clear()
        self._app._tag_templates = templates
        self._app._rebuild_table()

    def _del_tag_template(self):
        item = self.tag_list.currentItem()
        if not item:
            return
        name = item.text()
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定删除标签「{name}」吗？\n\n所有记录中该标签的值将被保留，但不再显示为列。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        templates = self._get_tag_templates()
        if name in templates:
            templates.remove(name)
        self._save_tag_templates(templates)
        self._load_tag_templates()
        self._app._tag_templates = templates
        self._app._rebuild_table()

    # ── 数据目录操作 ────────────────────────────

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

        old_files_count = 0
        if os.path.exists(self._app._data_file):
            old_files_count += 1
        if os.path.isdir(self._app._screenshot_dir):
            old_files_count += len(os.listdir(self._app._screenshot_dir))
        if os.path.isdir(self._app._contract_dir):
            old_files_count += len(os.listdir(self._app._contract_dir))

        migration_hint = ""
        if old_files_count > 0:
            migration_hint = f"\n\n检测到旧目录有 {old_files_count} 个文件，将自动迁移到新目录。"

        reply = QMessageBox.question(
            self, "确认更改数据目录",
            f"确认将数据目录切换为：\n{new_dir}\n\n"
            f"新目录下的数据文件会自动加载。\n{migration_hint}"
            "软件将立即以新目录重新初始化。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if reply != QMessageBox.Yes:
            return

        self._app._save_data()

        if old_files_count > 0:
            os.makedirs(new_dir, exist_ok=True)
            os.makedirs(os.path.join(new_dir, "screenshots"), exist_ok=True)
            os.makedirs(os.path.join(new_dir, "contracts"), exist_ok=True)
            errors = []
            old_data_file = self._app._data_file
            old_screenshot_dir = self._app._screenshot_dir
            old_contract_dir = self._app._contract_dir
            if os.path.exists(old_data_file):
                try:
                    shutil.copy2(old_data_file, os.path.join(new_dir, "invoices_data.json"))
                except Exception as e:
                    errors.append(f"invoices_data.json: {e}")
            if os.path.isdir(old_screenshot_dir):
                for fname in os.listdir(old_screenshot_dir):
                    src = os.path.join(old_screenshot_dir, fname)
                    dst = os.path.join(new_dir, "screenshots", fname)
                    try:
                        if os.path.isfile(src):
                            shutil.copy2(src, dst)
                    except Exception as e:
                        errors.append(f"screenshots/{fname}: {e}")
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

        self._app._data_dir = new_dir
        self._app._data_file = os.path.join(new_dir, "invoices_data.json")
        self._app._screenshot_dir = os.path.join(new_dir, "screenshots")
        self._app._contract_dir = os.path.join(new_dir, "contracts")
        os.makedirs(self._app._screenshot_dir, exist_ok=True)
        os.makedirs(self._app._contract_dir, exist_ok=True)

        self._app._save_config_dir(new_dir)

        self._app.records.clear()
        self._app.table.setRowCount(0)
        self._app._load_data()

        QMessageBox.information(
            self, "已切换",
            f"数据目录已切换为：\n{new_dir}\n\n"
            f"旧目录的文件已自动迁移到新目录。\n\n"
            f"下次启动软件时将自动使用此目录。"
        )

    # ── 软件另存 ────────────────────────────────

    def _saveas_software(self):
        dst_dir = QFileDialog.getExistingDirectory(self, "选择软件保存目录")
        if not dst_dir:
            return

        src_base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        src_script = os.path.join(src_base, "src", "invoice_tool.py")

        items = []
        if os.path.exists(src_script):
            items.append(("file", src_script, os.path.join(dst_dir, os.path.basename(src_script))))
        req_src = os.path.join(src_base, "requirements.txt")
        if os.path.exists(req_src):
            items.append(("file", req_src, os.path.join(dst_dir, "requirements.txt")))
        bat_src = os.path.join(src_base, "启动.bat")
        if os.path.exists(bat_src):
            items.append(("file", bat_src, os.path.join(dst_dir, "启动.bat")))
        if os.path.exists(self._app._data_file):
            items.append(("file", self._app._data_file, os.path.join(dst_dir, "invoices_data.json")))
        if os.path.isdir(self._app._screenshot_dir):
            items.append(("dir", self._app._screenshot_dir, os.path.join(dst_dir, "screenshots")))
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
                QDesktopServices.openUrl(QUrl.fromLocalFile(dst_dir))
            except Exception:
                pass

    # ── 数据备份与恢复 ──────────────────────────

    def _backup_data(self):
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"invoice_backup_{ts}.zip"
        dst, _ = QFileDialog.getSaveFileName(
            self, "选择备份保存位置", default_name, "ZIP 文件 (*.zip)"
        )
        if not dst:
            return
        try:
            data_dir = self._app._data_dir
            with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as zf:
                for dirpath, _, filenames in os.walk(data_dir):
                    for f in filenames:
                        fp = os.path.join(dirpath, f)
                        arcname = os.path.relpath(fp, data_dir)
                        zf.write(fp, arcname)
            size_mb = os.path.getsize(dst) / (1024 * 1024)
            QMessageBox.information(
                self, "备份成功",
                f"数据已备份到：\n{dst}\n\n备份大小：{size_mb:.1f} MB"
            )
        except Exception as e:
            QMessageBox.critical(self, "备份失败", f"备份时出错：\n{e}")

    def _restore_data(self):
        src, _ = QFileDialog.getOpenFileName(
            self, "选择备份文件", "", "ZIP 文件 (*.zip)"
        )
        if not src:
            return
        reply = QMessageBox.question(
            self, "确认恢复",
            f"此操作将用备份文件内容替换当前所有数据，\n"
            f"现有数据将被覆盖且无法恢复！\n\n"
            f"备份文件：{os.path.basename(src)}\n\n"
            f"确认恢复？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        try:
            data_dir = os.path.abspath(self._app._data_dir)
            with zipfile.ZipFile(src, 'r') as zf:
                for info in zf.infolist():
                    target = os.path.abspath(os.path.join(data_dir, info.filename))
                    if not target.startswith(data_dir + os.sep) and target != data_dir:
                        raise ValueError(f"安全拦截: 路径穿越 {info.filename}")
                zf.extractall(data_dir)
            self._app.records.clear()
            self._app.table.setRowCount(0)
            self._app._load_data()
            QMessageBox.information(
                self, "恢复成功",
                f"数据已从备份恢复。\n当前记录数：{len(self._app.records)} 条"
            )
        except Exception as e:
            QMessageBox.critical(self, "恢复失败", f"恢复时出错：\n{e}")
