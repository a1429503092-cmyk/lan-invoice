# 清理剩余问题 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 清理上一轮重构遗留的 3 个问题：冗余 import、`_base_dir` 未初始化 bug、测试文件过时

**Architecture:** 3 个独立任务，无相互依赖，可任意顺序执行。全部修改集中在现有文件。

**Tech Stack:** Python 3.12, PyQt5（仅 import 清理涉及）

---

### Task 1: 清理 invoice_tool.py 冗余 import

**Files:**
- Modify: `src/invoice_tool.py:12,14,19-28`

- [ ] **Step 1: 删除 invoice_tool.py 中未使用的 import**

当前 L12 `import subprocess` 和 L14 `from pathlib import Path` 全文件无实际使用，删除。

当前 L19-26 的 PyQt5.QtWidgets import 块中，以下符号仅在 import 行出现，删除：
- `QScrollArea`
- `QListWidget`, `QListWidgetItem`
- `QSizePolicy`, `QAction`
- `QSplitter`, `QCheckBox`

当前 L27 的 PyQt5.QtCore import 中，删除：
- `QSize`, `QTimer`

当前 L28 的 PyQt5.QtGui import 中，删除：
- `QPixmap`, `QIcon`

修改后 import 块为：

```python
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QTableWidget, QTableWidgetItem,
    QFileDialog, QMessageBox, QHeaderView, QStatusBar, QFrame,
    QProgressBar, QAbstractItemView, QDialog,
    QComboBox, QMenu, QInputDialog
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QMimeData, QUrl, QEvent
from PyQt5.QtGui import QColor, QDragEnterEvent, QDropEvent
```

同时删除 L12 `import subprocess` 和 L14 `from pathlib import Path`。

- [ ] **Step 2: 运行语法检查确认无错误**

```bash
cd "D:\Code\Python\lan-invoice" && "C:\Users\ewy\AppData\Local\Programs\Python\Python312\python.exe" -c "import py_compile; py_compile.compile('src/invoice_tool.py', doraise=True); print('OK')"
```

期望输出: `OK`

- [ ] **Step 3: 启动程序验证 UI 正常**

```bash
cd "D:\Code\Python\lan-invoice" && uv run python src/invoice_tool.py 2>&1 &
sleep 4
```

期望: 无 Traceback，窗口正常打开

- [ ] **Step 4: 提交**

```bash
git add src/invoice_tool.py
git commit -m "$(cat <<'EOF'
chore: 清理 invoice_tool.py 冗余 import

删除 11 个未使用的 PyQt5 符号 + subprocess + Path，
这些已随对话框代码移到 dialogs.py。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: 修复便携版另存时 src_script 和 src_base 路径错误

**Files:**
- Modify: `src/dialogs.py:660-661`

**问题分析：**
`SettingsDialog._saveas_software` 中 `os.path.abspath(__file__)` 在代码移入 `src/dialogs.py` 后返回的是 dialogs.py 的路径而非 invoice_tool.py。`self._app._base_dir` 从未在 InvoiceApp 中设置，是原始 bug。

**修复：** 用相对路径计算替代 `__file__` 和 `_base_dir`，不依赖调用方。

- [ ] **Step 1: 修改 _saveas_software 中的路径计算**

将 `src/dialogs.py` 第 660-661 行：

```python
        src_script = os.path.abspath(__file__)  # invoice_tool.py 所在绝对路径
        src_base   = self._app._base_dir
```

改为：

```python
        src_base   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        src_script = os.path.join(src_base, "src", "invoice_tool.py")
```

这样 `src_base` = 项目根目录，`src_script` = 项目根目录下的 `src/invoice_tool.py`，不再依赖外部设置。

- [ ] **Step 2: 语法检查**

```bash
cd "D:\Code\Python\lan-invoice" && "C:\Users\ewy\AppData\Local\Programs\Python\Python312\python.exe" -c "import py_compile; py_compile.compile('src/dialogs.py', doraise=True); print('OK')"
```

- [ ] **Step 3: 提交**

```bash
git add src/dialogs.py
git commit -m "$(cat <<'EOF'
fix: 便携版另存路径使用 dialogs.py 路径而非 invoice_tool.py

_settings_saveas 中原 os.path.abspath(__file__) 在代码移入
dialogs.py 后指向了错误的文件。改用相对路径从 dialogs.py
位置推导项目根目录和主脚本路径。

同时修复 _base_dir 从未被设置的原始 bug。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: 更新 tests/test_parse.py 使其复用车牌解析模块

**Files:**
- Modify: `tests/test_parse.py`

- [ ] **Step 1: 重写 tests/test_parse.py**

test_parse.py 当前内嵌了一个简化版 `parse_invoice_pdf`，与新版 `invoice_parser.py` 不同步。
改为从 `invoice_parser` 导入，同时保留命令行独立运行能力。

```python
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.stdout.reconfigure(encoding='utf-8')

from invoice_parser import parse_invoice_pdf

if __name__ == "__main__":
    test_path = os.environ.get('TEST_PDF') or 'C:/Users/dell/Desktop/发票/14786-福建长富乳品有限公司.pdf'
    data = parse_invoice_pdf(test_path)
    for k, v in data.items():
        print(f"  {k:20s}: {v}")
```

- [ ] **Step 2: 语法检查**

```bash
cd "D:\Code\Python\lan-invoice" && "C:\Users\ewy\AppData\Local\Programs\Python\Python312\python.exe" -c "import py_compile; py_compile.compile('tests/test_parse.py', doraise=True); print('OK')"
```

- [ ] **Step 3: 提交**

```bash
git add tests/test_parse.py
git commit -m "$(cat <<'EOF'
refactor: tests/test_parse.py 改为复用 invoice_parser 模块

移除内嵌的 parse_invoice_pdf 副本，改为 import 主模块。
可通过 TEST_PDF 环境变量指定测试文件路径。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

**1. Spec coverage:**
- Import 清理 → Task 1
- _base_dir bug → Task 2
- test_parse.py 过时 → Task 3

全部覆盖。

**2. Placeholder scan:** 无 TBD/TODO/模糊描述。所有步骤含具体代码和命令。

**3. Type consistency:** 无跨任务类型依赖。
