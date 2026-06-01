# 设置窗口综合优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development

**Goal:** 设置对话框增加信息展示、布局优化、新增备份恢复功能

**Architecture:** 重构 `dialogs.py` 中 `SettingsDialog` 类，保持对外接口不变

**Tech Stack:** PyQt5, Python stdlib (zipfile, os, datetime)

---

### Task 1: 重写 SettingsDialog

**Files:**
- Modify: `src/dialogs.py` — 重写 `SettingsDialog` 类的 `__init__` 和 `_build_ui`，新增备份/恢复方法

- [ ] **Step 1: 添加 import**

在 `src/dialogs.py` 顶部加入：
```python
import zipfile
```

- [ ] **Step 2: 重写 SettingsDialog._build_ui**

新的 UI 布局（三张卡片 + 统计信息）：

```python
class SettingsDialog(QDialog):
    """设置对话框：数据目录配置 + 软件另存 + 数据备份恢复"""

    def __init__(self, app_ref, parent=None):
        super().__init__(parent)
        self._app = app_ref
        self.setWindowTitle("⚙️ 设置")
        self.resize(580, 440)
        self.setMinimumSize(520, 380)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        # ── 标题 + 版本 ──────────────────────────
        title_row = QHBoxLayout()
        lbl_title = QLabel("⚙️ 软件设置")
        lbl_title.setStyleSheet("font-size:16px; font-weight:bold; color:#1E6FBF;")
        title_row.addWidget(lbl_title)
        title_row.addStretch()
        lbl_ver = QLabel("v5.1")
        lbl_ver.setStyleSheet("font-size:11px; color:#999; background:transparent;")
        title_row.addWidget(lbl_ver)
        layout.addLayout(title_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#D0DCF0;")
        layout.addWidget(sep)

        # ── 1. 数据存储 ──────────────────────────
        data_card = self._make_card("#F0F7FF", "#B8D4F0")
        card_layout = QVBoxLayout(data_card)
        card_layout.setContentsMargins(14, 10, 14, 10)
        card_layout.setSpacing(6)

        card_layout.addWidget(self._card_title("📁  数据存储"))

        # 统计信息
        stats = []
        invoice_count = len(self._app.records)
        screenshots = sum(len(r.get("screenshots", [])) for r in self._app.records)
        contracts = sum(len(r.get("contracts", [])) for r in self._app.records)
        data_size = self._calc_data_size()

        info_grid = QHBoxLayout()
        info_grid.setSpacing(20)
        info_grid.addWidget(self._stat_widget("发票记录", f"{invoice_count} 条"))
        info_grid.addWidget(self._stat_widget("截图文件", f"{screenshots} 个"))
        info_grid.addWidget(self._stat_widget("合同文件", f"{contracts} 个"))
        info_grid.addWidget(self._stat_widget("数据大小", data_size))
        info_grid.addStretch()
        card_layout.addLayout(info_grid)

        # 路径
        path_row = QHBoxLayout()
        path_row.setSpacing(6)
        self.edit_data_dir = QLineEdit(self._app._data_dir)
        self.edit_data_dir.setReadOnly(True)
        self.edit_data_dir.setFixedHeight(30)
        self.edit_data_dir.setStyleSheet(
            "background:#fff; border:1px solid #B0C4DE; border-radius:4px; padding:2px 6px;"
            "font-family:Consolas,monospace; font-size:12px;")
        btn_browse = QPushButton("浏览…")
        btn_browse.setFixedHeight(30)
        btn_browse.clicked.connect(self._browse_data_dir)
        path_row.addWidget(self.edit_data_dir, 1)
        path_row.addWidget(btn_browse)
        card_layout.addLayout(path_row)

        btn_apply = QPushButton("✅ 应用新目录")
        btn_apply.setFixedHeight(32)
        btn_apply.setStyleSheet(
            "background:#1E6FBF; color:white; font-weight:bold; border-radius:4px;")
        btn_apply.clicked.connect(self._apply_data_dir)
        card_layout.addWidget(btn_apply)

        layout.addWidget(data_card)

        # ── 2. 软件另存 ──────────────────────────
        save_card = self._make_card("#F0FFF4", "#A8D8B0")
        save_layout = QVBoxLayout(save_card)
        save_layout.setContentsMargins(14, 10, 14, 10)
        save_layout.setSpacing(6)

        save_layout.addWidget(self._card_title("💾  软件另存（制作便携版）"))
        save_hint = QLabel(
            "将主程序及全部数据（JSON、截图、合同、发票PDF）复制到目标文件夹，\n"
            "复制后可直接运行，无需重新安装。"
        )
        save_hint.setStyleSheet("font-size:11px; color:#777;")
        save_hint.setWordWrap(True)
        save_layout.addWidget(save_hint)

        btn_saveas = QPushButton("📂 选择目标位置并另存软件")
        btn_saveas.setFixedHeight(32)
        btn_saveas.setStyleSheet(
            "background:#2E7D32; color:white; font-weight:bold; border-radius:4px;")
        btn_saveas.clicked.connect(self._saveas_software)
        save_layout.addWidget(btn_saveas)

        layout.addWidget(save_card)

        # ── 3. 数据备份与恢复 ────────────────────
        backup_card = self._make_card("#FFF5F0", "#E8C8B0")
        backup_layout = QVBoxLayout(backup_card)
        backup_layout.setContentsMargins(14, 10, 14, 10)
        backup_layout.setSpacing(6)

        backup_layout.addWidget(self._card_title("📦  数据备份与恢复"))

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_backup = QPushButton("📤 备份当前数据")
        btn_backup.setFixedHeight(32)
        btn_backup.setStyleSheet(
            "background:#E06020; color:white; font-weight:bold; border-radius:4px;")
        btn_backup.clicked.connect(self._backup_data)
        btn_restore = QPushButton("📥 恢复数据…")
        btn_restore.setFixedHeight(32)
        btn_restore.setStyleSheet(
            "background:#E06020; color:white; font-weight:bold; border-radius:4px;")
        btn_restore.clicked.connect(self._restore_data)
        btn_row.addWidget(btn_backup)
        btn_row.addWidget(btn_restore)
        backup_layout.addLayout(btn_row)

        layout.addWidget(backup_card)

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
```

- [ ] **Step 3: 添加辅助方法**

```python
    def _make_card(self, bg: str, border: str) -> QFrame:
        f = QFrame()
        f.setStyleSheet(
            f"QFrame {{ background:{bg}; border:1px solid {border}; border-radius:6px; }}")
        return f

    def _card_title(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("font-size:13px; font-weight:bold; color:#333;")
        return lbl

    def _stat_widget(self, label: str, value: str) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(1)
        lt = QLabel(label)
        lt.setStyleSheet("color:#666; font-size:10px;")
        lv = QLabel(value)
        lv.setStyleSheet("color:#1E6FBF; font-size:13px; font-weight:bold;")
        v.addWidget(lt)
        v.addWidget(lv)
        return w

    def _calc_data_size(self) -> str:
        data_dir = self._app._data_dir
        total = 0
        for dirpath, _, filenames in os.walk(data_dir):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if os.path.isfile(fp):
                    total += os.path.getsize(fp)
        if total < 1024:
            return f"{total} B"
        elif total < 1024 * 1024:
            return f"{total/1024:.1f} KB"
        else:
            return f"{total/(1024*1024):.1f} MB"

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
            import zipfile
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
        # 双重确认
        reply = QMessageBox.question(
            self, "⚠️ 确认恢复",
            f"此操作将用备份文件内容替换当前所有数据，\n"
            f"现有数据将被覆盖且无法恢复！\n\n"
            f"备份文件：{os.path.basename(src)}\n\n"
            f"确认恢复？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        try:
            import zipfile
            data_dir = self._app._data_dir
            with zipfile.ZipFile(src, 'r') as zf:
                zf.extractall(data_dir)
            # 重新加载数据
            self._app.records.clear()
            self._app.table.setRowCount(0)
            self._app._load_data()
            QMessageBox.information(
                self, "恢复成功",
                f"数据已从备份恢复。\n当前记录数：{len(self._app.records)} 条"
            )
        except Exception as e:
            QMessageBox.critical(self, "恢复失败", f"恢复时出错：\n{e}")
```

- [ ] **Step 4: 语法检查 + 启动验证**

```bash
cd "D:\Code\Python\lan-invoice" && "C:\Users\ewy\AppData\Local\Programs\Python\Python312\python.exe" -c "import py_compile; py_compile.compile('src/dialogs.py', doraise=True); print('OK')"
uv run python src/invoice_tool.py 2>&1 &
sleep 4
```

- [ ] **Step 5: 运行测试**

```bash
uv run python -m unittest tests.test_invoice_parser -v 2>&1 | tail -5
```

Expected: 87 tests OK

- [ ] **Step 6: 提交**

```bash
git add src/dialogs.py
git commit -m "$(cat <<'EOF'
feat: 设置窗口综合优化——统计信息+备份恢复+视觉升级

- 新增数据统计展示（记录数/截图/合同/数据大小）
- 新增数据备份与恢复功能（ZIP 打包/解压）
- 三张卡片风格统一（蓝/绿/橙三色区分）
- 窗口尺寸优化 580x440
- 添加版本号显示

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

## Self-Review

- 单一任务，单文件修改
- 保持 SettingsDialog 对外接口 (`__init__(self, app_ref, parent=None)`) 不变
- 所有新功能使用 stdlib，无新增依赖
