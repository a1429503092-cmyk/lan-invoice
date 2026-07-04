# -*- coding: utf-8 -*-
"""设置对话框：数据目录配置 + 数据备份恢复"""

import os
import sys
import shutil
import zipfile
from datetime import datetime

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit,
    QFileDialog, QMessageBox, QFrame, QListWidget, QCheckBox, QComboBox,
    QSpinBox, QTabWidget, QWidget
)
from PyQt5.QtCore import Qt
from logger import getLogger
from version import APP_VERSION
log = getLogger(__name__)

from ui.theme import (TEXT, TEXT_SEC, TEXT_DIM, BG_ALT, BORDER_LIGHT)


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    else:
        return f"{size / (1024 * 1024):.1f} MB"


class SettingsDialog(QDialog):
    """设置对话框：数据目录配置 + 数据备份恢复"""

    def __init__(self, app_ref, parent=None):
        super().__init__(parent)
        self._app = app_ref
        self.setWindowTitle("设置")
        self.setMinimumSize(420, 400)
        self._build_ui()
        self.layout().activate()
        self.resize(self.sizeHint())

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
        return _format_size(total)

    # ── UI 构建 ─────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        # 标题栏
        title_row = QHBoxLayout()
        lbl_title = QLabel("设置")
        lbl_title.setStyleSheet(f"font-size:15px; font-weight:bold; color:{TEXT};")
        title_row.addWidget(lbl_title)
        title_row.addStretch()
        lbl_ver = QLabel(f"v{APP_VERSION}")
        lbl_ver.setStyleSheet(f"font-size:11px; color:{TEXT_DIM};")
        title_row.addWidget(lbl_ver)
        btn_check = QPushButton("检查更新")
        btn_check.setFlat(True)
        btn_check.clicked.connect(self._check_update)
        title_row.addWidget(btn_check)
        layout.addLayout(title_row)

        # 页签
        tabs = QTabWidget()
        tabs.addTab(self._build_general_tab(), "通用")
        tabs.addTab(self._build_backup_tab(), "备份策略")
        tabs.addTab(self._build_mcp_tab(), "MCP 服务")
        layout.addWidget(tabs)

        # WebDAV 配置加载（在构建完 widget 后）
        self._load_webdav_config()

        # 关闭
        btn_close = QPushButton("关闭")
        btn_close.setFixedHeight(32)
        btn_close.clicked.connect(self._save_and_close)
        layout.addWidget(btn_close, alignment=Qt.AlignRight)

        from ui.theme import DIALOG_QSS
        self.setStyleSheet(DIALOG_QSS)
        for btn in self.findChildren(QPushButton):
            btn.setCursor(Qt.PointingHandCursor)

    def _save_and_close(self):
        self._save_webdav_config()
        self.accept()

    def _check_update(self):
        self._app.check_update()

    def _on_theme_changed(self):
        theme = self.cmb_theme.currentData()
        if theme:
            self._app._config.theme = theme
            self._app._config.save()
            from qt_material import apply_stylesheet
            apply_stylesheet(QApplication.instance(), theme=theme)

    # ── 页签构建 ─────────────────────────────

    def _build_general_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        lay.addWidget(self._section_title("数据存储"))
        invoice_count = len(self._app.records)
        attachments = sum(len(r.get("attachments", [])) for r in self._app.records)
        stats_row = QHBoxLayout()
        stats_row.setSpacing(24)
        stats_row.addWidget(self._stat_label("发票", f"{invoice_count} 条"))
        stats_row.addWidget(self._stat_label("附件", f"{attachments} 个"))
        stats_row.addWidget(self._stat_label("大小", self._calc_data_size()))
        stats_row.addStretch()
        lay.addLayout(stats_row)

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
        lay.addLayout(path_row)
        btn_apply = QPushButton("应用新目录")
        btn_apply.setFixedHeight(32)
        btn_apply.clicked.connect(self._apply_data_dir)
        lay.addWidget(btn_apply)

        # 主题选择
        theme_row = QHBoxLayout()
        theme_row.setSpacing(8)
        theme_row.addWidget(QLabel("主题"))
        self.cmb_theme = QComboBox()
        from qt_material import list_themes
        for t in sorted(list_themes()):
            self.cmb_theme.addItem(t.replace(".xml", "").replace("_", " ").title(), t)
        current = self._app._config.theme
        idx = self.cmb_theme.findData(current)
        if idx >= 0:
            self.cmb_theme.setCurrentIndex(idx)
        self.cmb_theme.currentIndexChanged.connect(self._on_theme_changed)
        theme_row.addWidget(self.cmb_theme, 1)
        lay.addLayout(theme_row)

        lay.addWidget(self._hline())
        lay.addWidget(self._section_title("标签模板"))
        tag_hint = QLabel("定义发票记录的自定义标签字段，将在表格中作为可编辑列显示。")
        tag_hint.setStyleSheet(f"font-size:11px; color:{TEXT_DIM};")
        tag_hint.setWordWrap(True)
        lay.addWidget(tag_hint)
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
        lay.addLayout(tag_row)
        self.tag_list = QListWidget()
        self.tag_list.setMaximumHeight(100)
        self.tag_list.setStyleSheet(f"background:{BG_ALT}; border:none; font-size:12px;")
        self._load_tag_templates()
        lay.addWidget(self.tag_list)
        btn_del_tag = QPushButton("删除选中标签")
        btn_del_tag.setFixedHeight(28)
        btn_del_tag.clicked.connect(self._del_tag_template)
        lay.addWidget(btn_del_tag)

        lay.addWidget(self._hline())
        lay.addWidget(self._section_title("手动操作"))
        manual_row = QHBoxLayout()
        manual_row.setSpacing(8)
        btn_backup = QPushButton("导出 ZIP 备份…")
        btn_backup.setFixedHeight(32)
        btn_backup.clicked.connect(self._backup_data)
        btn_restore = QPushButton("从 ZIP 恢复…")
        btn_restore.setFixedHeight(32)
        btn_restore.clicked.connect(self._restore_data)
        manual_row.addWidget(btn_backup)
        manual_row.addWidget(btn_restore)
        manual_row.addStretch()
        lay.addLayout(manual_row)

        lay.addStretch()
        return w

    def _build_backup_tab(self):
        from ui.widgets.strategy_card import StrategyCard
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        # 本地策略
        lay.addWidget(self._section_title("本地多盘备份"))
        self._local_card = StrategyCard("local", self._app._config.get_local_strategy())
        self._local_card.strategy_changed.connect(self._on_local_strategy_changed)
        lay.addWidget(self._local_card)
        self.lbl_local_stats = QLabel()
        self.lbl_local_stats.setStyleSheet(f"font-size:11px; color:{TEXT_DIM};")
        self.lbl_local_stats.setWordWrap(True)
        lay.addWidget(self.lbl_local_stats)
        self._refresh_local_stats()

        lay.addWidget(self._hline())

        # WebDAV 策略
        lay.addWidget(self._section_title("远程备份（WebDAV）"))
        self._webdav_card = StrategyCard("webdav", self._app._config.get_webdav_strategy())
        self._webdav_card.strategy_changed.connect(self._on_webdav_strategy_changed)
        lay.addWidget(self._webdav_card)

        wd_hint = QLabel("支持群晖、Nextcloud 等 WebDAV 服务器，增量同步仅上传变更文件。")
        wd_hint.setStyleSheet(f"font-size:11px; color:{TEXT_DIM};")
        wd_hint.setWordWrap(True)
        lay.addWidget(wd_hint)
        url_row = QHBoxLayout()
        url_row.setSpacing(8)
        url_row.addWidget(QLabel("地址"))
        self.edit_wd_url = QLineEdit()
        self.edit_wd_url.setPlaceholderText("https://nas.local:5006/invoice-backup/")
        self.edit_wd_url.setFixedHeight(32)
        url_row.addWidget(self.edit_wd_url, 1)
        lay.addLayout(url_row)
        auth_row = QHBoxLayout()
        auth_row.setSpacing(8)
        auth_row.addWidget(QLabel("账号"))
        self.edit_wd_user = QLineEdit()
        self.edit_wd_user.setPlaceholderText("用户名")
        self.edit_wd_user.setFixedHeight(32)
        auth_row.addWidget(self.edit_wd_user, 1)
        auth_row.addWidget(QLabel("密码"))
        self.edit_wd_pass = QLineEdit()
        self.edit_wd_pass.setPlaceholderText("密码")
        self.edit_wd_pass.setEchoMode(QLineEdit.Password)
        self.edit_wd_pass.setFixedHeight(32)
        auth_row.addWidget(self.edit_wd_pass, 1)
        lay.addLayout(auth_row)
        wd_btn_row = QHBoxLayout()
        wd_btn_row.setSpacing(8)
        btn_test = QPushButton("测试连接")
        btn_test.setFixedHeight(32)
        btn_test.clicked.connect(self._test_webdav)
        btn_sync = QPushButton("立即同步")
        btn_sync.setFixedHeight(32)
        btn_sync.clicked.connect(self._sync_webdav_now)
        btn_restore = QPushButton("从远程恢复…")
        btn_restore.setFixedHeight(32)
        btn_restore.clicked.connect(self._restore_webdav)
        wd_btn_row.addWidget(btn_test)
        wd_btn_row.addWidget(btn_sync)
        wd_btn_row.addWidget(btn_restore)
        wd_btn_row.addStretch()
        lay.addLayout(wd_btn_row)

        lay.addStretch()
        return w

    def _build_mcp_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        lay.addWidget(self._section_title("MCP 服务"))
        mcp_hint = QLabel(
            "MCP（Model Context Protocol）允许 AI 客户端直接操作发票数据库。\n"
            "支持 Claude Code、CodeBuddy（腾讯）、WorkBuddy（阿里）。\n"
            "通过 stdio 协议通信，不绑端口、无冲突。"
        )
        mcp_hint.setStyleSheet(f"font-size:11px; color:{TEXT_DIM};")
        mcp_hint.setWordWrap(True)
        lay.addWidget(mcp_hint)

        if getattr(sys, 'frozen', False):
            self._mcp_cmd_text = f'"{sys.executable}" --mcp'
        else:
            self._mcp_cmd_text = "uv run python src/invoice_tool.py --mcp"
        mcp_cmd_row = QHBoxLayout()
        mcp_cmd_row.setSpacing(8)
        self.edit_mcp_cmd = QLineEdit()
        self.edit_mcp_cmd.setReadOnly(True)
        self.edit_mcp_cmd.setFixedHeight(32)
        self.edit_mcp_cmd.setStyleSheet(
            f"background:{BG_ALT}; border:none; "
            "font-family:Consolas,monospace; padding:2px 6px; font-size:11px;")
        self.edit_mcp_cmd.setText(self._mcp_cmd_text)
        mcp_cmd_row.addWidget(self.edit_mcp_cmd, 1)
        lay.addLayout(mcp_cmd_row)

        mcp_btn_row = QHBoxLayout()
        mcp_btn_row.setSpacing(8)
        btn_copy = QPushButton("复制命令")
        btn_copy.setFixedHeight(32)
        btn_copy.clicked.connect(self._copy_mcp_cmd)
        btn_claude = QPushButton("配置 Claude")
        btn_claude.setFixedHeight(32)
        btn_claude.clicked.connect(self._install_mcp_claude)
        btn_codebuddy = QPushButton("配置 CodeBuddy")
        btn_codebuddy.setFixedHeight(32)
        btn_codebuddy.clicked.connect(self._install_mcp_codebuddy)
        btn_wb = QPushButton("配置 WorkBuddy")
        btn_wb.setFixedHeight(32)
        btn_wb.clicked.connect(self._install_mcp_workbuddy)
        mcp_btn_row.addWidget(btn_copy)
        mcp_btn_row.addWidget(btn_claude)
        mcp_btn_row.addWidget(btn_codebuddy)
        mcp_btn_row.addWidget(btn_wb)
        mcp_btn_row.addStretch()
        lay.addLayout(mcp_btn_row)

        lay.addStretch()
        return w

    # ── 策略卡片事件 ─────────────────────────────

    def _on_local_strategy_changed(self):
        s = self._local_card.get_strategy()
        self._app._config.set_local_strategy(s)
        self._app._config.save()
        self._refresh_local_stats()

    def _on_webdav_strategy_changed(self):
        s = self._webdav_card.get_strategy()
        self._app._config.set_webdav_strategy(s)
        self._app._config.save()

    def _refresh_local_stats(self):
        stats = self._app._backup.get_stats()
        if stats["count"] == 0:
            self.lbl_local_stats.setText("暂无自动备份")
            return
        size_str = _format_size(stats["size"])
        self.lbl_local_stats.setText(
            f"自动备份：{stats['count']} 份（{stats['partitions']} 个分区）"
            f"  |  最近：{stats['latest']}"
            f"  |  总计：{size_str}"
        )

    # ── WebDAV ──────────────────────────────────

    def _load_webdav_config(self):
        s = self._app._config.get_webdav_strategy()
        self.edit_wd_url.setText(s["url"])
        self.edit_wd_user.setText(s["username"])
        self.edit_wd_pass.setText(s["password"])

    def _save_webdav_config(self):
        self._app._config.set_webdav_strategy({
            "url": self.edit_wd_url.text().strip(),
            "username": self.edit_wd_user.text().strip(),
            "password": self.edit_wd_pass.text(),
        })
        self._app._config.save()

    def _test_webdav(self):
        self._save_webdav_config()
        from webdav_sync import test_connection
        s = self._app._config.get_webdav_strategy()
        if test_connection(s["url"], s["username"], s["password"]):
            QMessageBox.information(self, "测试成功", "WebDAV 连接正常")
        else:
            QMessageBox.warning(self, "测试失败",
                                f"无法连接到 {s['url']}\n请检查地址和账号密码。")

    def _sync_webdav_now(self):
        self._save_webdav_config()
        s = self._app._config.get_webdav_strategy()
        if not s["url"]:
            QMessageBox.warning(self, "提示", "请先填写 WebDAV 地址")
            return
        self._app._do_webdav_sync(silent=False)

    def _restore_webdav(self):
        self._save_webdav_config()
        s = self._app._config.get_webdav_strategy()
        if not s["url"]:
            QMessageBox.warning(self, "提示", "请先填写 WebDAV 地址")
            return
        reply = QMessageBox.warning(
            self, "确认恢复",
            "将从 WebDAV 下载备份文件，覆盖本地所有数据。\n确定要恢复吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            from webdav_sync import restore_from_webdav
            self._app._save_data()
            ok = restore_from_webdav(self._app._data_dir, s["url"],
                                     s["username"], s["password"])
            if ok:
                QMessageBox.information(self, "恢复完成", "数据已从 WebDAV 恢复，请重新打开软件。")
                self._app.close()
            else:
                QMessageBox.warning(self, "恢复失败", "从 WebDAV 下载数据失败，请检查网络和配置。")

    # ── 标签模板管理 ─────────────────────────────

    def _load_tag_templates(self):
        self.tag_list.clear()
        templates = self._get_tag_templates()
        for name in templates:
            self.tag_list.addItem(name)

    def _get_tag_templates(self) -> list[str]:
        return self._app._config.tag_templates

    def _save_tag_templates(self, templates: list[str]):
        self._app._config.tag_templates = templates
        self._app._config.save()

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

    def _data_dir_has_content(self, dirpath: str) -> bool:
        """检查目录是否已有数据内容"""
        db_file = os.path.join(dirpath, "invoices.db")
        json_file = os.path.join(dirpath, "invoices_data.json")
        if os.path.exists(db_file) and os.path.getsize(db_file) > 0:
            return True
        if os.path.exists(json_file) and os.path.getsize(json_file) > 0:
            return True
        invoices_dir = os.path.join(dirpath, "invoices")
        if os.path.isdir(invoices_dir) and os.listdir(invoices_dir):
            return True
        return False

    def _snapshot_before_switch(self):
        """创建目录切换前的 ZIP 快照备份"""
        import tempfile
        from PyQt5.QtWidgets import QApplication
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_path = os.path.join(tempfile.gettempdir(), f"lan_invoice_snapshot_{ts}.zip")
        try:
            data_dir = self._app._data_dir
            if not os.path.isdir(data_dir):
                return
            self._app.status.showMessage("正在创建切换前快照备份…")
            QApplication.processEvents()
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                file_count = 0
                for dirpath, _, filenames in os.walk(data_dir):
                    for f in filenames:
                        fp = os.path.join(dirpath, f)
                        zf.write(fp, os.path.relpath(fp, data_dir))
                        file_count += 1
                        if file_count % 20 == 0:
                            QApplication.processEvents()
            size_mb = os.path.getsize(zip_path) / (1024 * 1024)
            log.info("目录切换前快照: %s (%.1f MB)", zip_path, size_mb)
            self._app.status.showMessage(f"快照备份完成 ({size_mb:.1f} MB)", 3000)
        except Exception as e:
            log.warning("快照备份失败（仍继续切换）: %s", e)
            self._app.status.showMessage("", 0)

    def _switch_to_dir(self, new_dir: str, migrate_old: bool):
        """执行目录切换"""
        self._app._save_data()

        # 切换前自动创建 ZIP 快照备份
        self._snapshot_before_switch()

        if migrate_old:
            os.makedirs(new_dir, exist_ok=True)
            os.makedirs(os.path.join(new_dir, "invoices"), exist_ok=True)
            errors = []

            old_data_file = self._app._data_file
            old_inv_dir = os.path.join(self._app._data_dir, "invoices")

            if os.path.exists(old_data_file):
                try:
                    shutil.copy2(old_data_file, os.path.join(new_dir, "invoices.db"))
                except Exception as e:
                    errors.append(f"invoices.db: {e}")

            if old_inv_dir and os.path.isdir(old_inv_dir):
                dst_dir = os.path.join(new_dir, "invoices")
                for fname in os.listdir(old_inv_dir):
                    src = os.path.join(old_inv_dir, fname)
                    dst = os.path.join(dst_dir, fname)
                    try:
                        if os.path.isfile(src) and not os.path.exists(dst):
                            shutil.copy2(src, dst)
                    except Exception as e:
                        errors.append(f"invoices/{fname}: {e}")

            if errors:
                QMessageBox.warning(self, "部分文件迁移失败",
                                    "以下文件迁移失败：\n\n" + "\n".join(errors))

        # 更新路径
        self._app._data_dir = new_dir
        self._app._data_file = os.path.join(new_dir, "invoices.db")
        self._app._attachment_dir = new_dir
        os.makedirs(os.path.join(new_dir, "invoices"), exist_ok=True)

        # 更新 Service
        from services.invoice_service import InvoiceService
        from database import Database
        self._app._db = Database(self._app._data_file)
        # 迁移新目录下的旧 JSON（如果有）
        json_path = os.path.join(new_dir, "invoices_data.json")
        if os.path.exists(json_path):
            self._app._db.migrate_from_json(json_path)
        self._app._svc = InvoiceService(self._app._db, self._app._backup,
                                         self._app._config, self._app._data_dir,
                                         os.path.join(new_dir, "invoices"))
        self._app._svc.enable_webdav_sync(True)

        self._app._config.data_dir = new_dir
        self._app._config.save()

        # 重新加载
        self._app.records.clear()
        self._app.table.setRowCount(0)
        self._app._load_data()
        self.edit_data_dir.setText(new_dir)

        QMessageBox.information(self, "已切换", f"数据目录已切换为：\n{new_dir}")

    def _apply_data_dir(self):
        new_dir = self.edit_data_dir.text().strip()
        if not new_dir or not os.path.isdir(new_dir):
            QMessageBox.warning(self, "目录无效", "请先选择一个有效的目录。")
            return
        if os.path.abspath(new_dir) == os.path.abspath(self._app._data_dir):
            QMessageBox.information(self, "无需更改", "目标目录与当前目录相同。")
            return

        has_content = self._data_dir_has_content(new_dir)
        old_has_content = self._data_dir_has_content(self._app._data_dir)

        if has_content:
            # 新目录已有数据 → 三选一
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("确认数据目录")
            msg_box.setText(f"目标目录已有数据：\n{new_dir}\n\n请选择处理方式：")
            btn_keep = msg_box.addButton("保留新目录数据", QMessageBox.AcceptRole)
            btn_overwrite = msg_box.addButton("用旧数据覆盖", QMessageBox.DestructiveRole)
            btn_cancel = msg_box.addButton("取消", QMessageBox.RejectRole)
            msg_box.exec_()

            clicked = msg_box.clickedButton()
            if clicked == btn_keep:
                self._switch_to_dir(new_dir, migrate_old=False)
            elif clicked == btn_overwrite:
                self._switch_to_dir(new_dir, migrate_old=True)
            # else: cancel — do nothing
        else:
            # 新目录为空
            if old_has_content:
                reply = QMessageBox.question(
                    self, "确认数据目录",
                    f"目标目录为空：\n{new_dir}\n\n是否将旧数据迁移到新目录？",
                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                    QMessageBox.Yes
                )
                if reply == QMessageBox.Cancel:
                    return
                self._switch_to_dir(new_dir, migrate_old=(reply == QMessageBox.Yes))
            else:
                self._switch_to_dir(new_dir, migrate_old=False)

    # ── MCP 配置 ──────────────────────────────

    def _copy_mcp_cmd(self):
        from PyQt5.QtWidgets import QApplication
        QApplication.clipboard().setText(self.edit_mcp_cmd.text())
        QMessageBox.information(self, "已复制",
                                "MCP 命令已复制到剪贴板。\n\n在 AI 客户端中粘贴此命令即可。")

    def _install_mcp_claude(self):
        cfg_dir = os.path.join(
            os.environ.get("APPDATA", os.path.expanduser("~")), "Claude")
        self._write_mcp_config(cfg_dir, os.path.join(cfg_dir, "settings.json"),
                               self._make_mcp_entry(), "Claude Code")

    def _install_mcp_codebuddy(self):
        cfg_dir = os.path.join(os.path.expanduser("~"), ".codebuddy")
        self._write_mcp_config(cfg_dir, os.path.join(cfg_dir, "mcp.json"),
                               self._make_mcp_entry(), "CodeBuddy")

    def _install_mcp_workbuddy(self):
        cfg_dir = os.path.join(os.path.expanduser("~"), ".workbuddy")
        entry = self._make_mcp_entry()
        entry["type"] = "stdio"
        self._write_mcp_config(cfg_dir, os.path.join(cfg_dir, "mcp.json"),
                               entry, "WorkBuddy")

    @staticmethod
    def _make_mcp_entry() -> dict:
        if getattr(sys, 'frozen', False):
            return {"command": sys.executable, "args": ["--mcp"]}
        proj = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))))
        return {
            "command": "uv",
            "args": ["run", "python", "src/invoice_tool.py", "--mcp"],
            "cwd": proj,
        }

    def _write_mcp_config(self, cfg_dir: str, cfg_file: str, entry: dict, name: str):
        import json
        os.makedirs(cfg_dir, exist_ok=True)
        cfg = {}
        if os.path.exists(cfg_file):
            try:
                with open(cfg_file, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            except (OSError, json.JSONDecodeError):
                pass
        servers = cfg.setdefault("mcpServers", {})
        servers["invoice"] = entry
        try:
            with open(cfg_file, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            QMessageBox.information(
                self, "配置完成",
                f"已写入 {name} 配置：\n{cfg_file}\n\n"
                f"重启 {name} 后即可使用 MCP 工具。"
            )
        except OSError as e:
            QMessageBox.warning(self, "配置失败",
                                f"写入配置文件失败：\n{e}")

    # ── 手动 ZIP 备份恢复 ────────────────────────

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
            self._refresh_local_stats()
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
