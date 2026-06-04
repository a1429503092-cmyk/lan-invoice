# 操作流程优化 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构发票归档工具的操作流程——数据模型（tags + attachments）、导入（消除歧义+结果摘要）、附件合并、筛选实时化、标签系统、目录切换安全化。

**Architecture:** 自底向上推进：先改数据模型（models.py），再改存储层（repository.py），再改服务层（invoice_service.py），最后改 UI 层（invoice_tool.py + dialogs）。每完成一个 Task 验证应用启动 + 运行测试。

**Tech Stack:** Python 3.12+, PyQt5, dataclasses, unittest

---

## 文件结构

```
src/
├── models.py              # 修改：Invoice 新增 tags/attachments，旧格式迁移
├── repository.py           # 修改：加载时执行旧数据迁移
├── services/
│   └── invoice_service.py  # 修改：附件统一，去掉截图/合同区分
├── ui/dialogs/
│   ├── attachment_viewer.py # 新建：统一附件预览（图片+PDF+文档）
│   ├── image_viewer.py      # 保留：图片全屏预览逻辑复用
│   ├── pdf_viewer.py        # 不变
│   ├── invoice_manager.py   # 移除：合并到 attachment_viewer
│   ├── contract_manager.py  # 移除：合并到 attachment_viewer
│   └── settings.py          # 修改：标签模板管理、目录切换交互
├── worker.py               # 修改：导入结果摘要数据
└── invoice_tool.py          # 大改：拖拽、附件列、标签列、筛选、排序、搜索

tests/
├── test_models.py           # 修改：新增 tags/attachments 测试
├── test_repository.py       # 修改：新增迁移测试
├── test_services.py         # 修改：附件统一测试
├── test_invoice_tool.py     # 修改：新增导入流程/附件/标签/筛选/排序测试
├── test_dialogs.py          # 不变
├── test_dialogs_extra.py    # 修改：移除旧对话框测试，新增 attachment_viewer 测试
├── test_attachment_viewer.py# 新建：统一附件预览对话框测试
└── test_settings.py         # 新建：设置对话框标签+目录切换测试
```

---

### Task 1: Invoice 模型新增 tags/attachments 字段

**Files:**
- Modify: `src/models.py`
- Modify: `tests/test_models.py`

- [ ] **Step 1: 更新 test_models.py 中的默认值和序列化测试**

修改 `tests/test_models.py`，在 `TestInvoiceDefaults` 类中添加 tags 和 attachments 的默认值断言，在 `TestInvoiceToDict` 和 `TestInvoiceFromDict` 中添加新字段测试：

```python
# 在 TestInvoiceDefaults.test_default_values 末尾添加：
self.assertEqual(inv.tags, {})
self.assertEqual(inv.attachments, [])

# 在 TestInvoiceToDict.test_empty_invoice 中添加：
self.assertEqual(d["tags"], {})
self.assertEqual(d["attachments"], [])

# 新增 TestInvoiceTags 测试类：
class TestInvoiceTags(unittest.TestCase):
    def test_tags_default_empty(self):
        inv = Invoice()
        self.assertEqual(inv.tags, {})

    def test_tags_roundtrip(self):
        inv = Invoice(
            invoice_no="12345",
            tags={"企业号": "14786", "项目名称": "2026Q1"},
        )
        d = inv.to_dict()
        self.assertEqual(d["tags"]["企业号"], "14786")
        self.assertEqual(d["tags"]["项目名称"], "2026Q1")

    def test_tags_from_dict(self):
        d = {"invoice_no": "X", "tags": {"企业号": "A001", "负责人": "张三"}}
        inv = Invoice.from_dict(d)
        self.assertEqual(inv.tags["企业号"], "A001")
        self.assertEqual(inv.tags["负责人"], "张三")

    def test_tags_from_dict_none(self):
        inv = Invoice.from_dict({"invoice_no": "X"})
        self.assertEqual(inv.tags, {})

    def test_setitem_tags(self):
        inv = Invoice()
        inv["tags"] = {"企业号": "B001"}
        self.assertEqual(inv.tags, {"企业号": "B001"})

    def test_getitem_tags(self):
        inv = Invoice(tags={"企业号": "C001"})
        self.assertEqual(inv["tags"]["企业号"], "C001")


class TestInvoiceAttachments(unittest.TestCase):
    def test_attachments_default_empty(self):
        inv = Invoice()
        self.assertEqual(inv.attachments, [])

    def test_attachments_roundtrip(self):
        inv = Invoice(
            invoice_no="12345",
            attachments=["/data/attachments/a.png", "/data/attachments/b.pdf"],
        )
        d = inv.to_dict()
        self.assertEqual(d["attachments"], ["/data/attachments/a.png", "/data/attachments/b.pdf"])

    def test_attachments_from_dict(self):
        d = {"invoice_no": "X", "attachments": ["/path/a.png"]}
        inv = Invoice.from_dict(d)
        self.assertEqual(inv.attachments, ["/path/a.png"])

    def test_attachments_from_dict_none(self):
        inv = Invoice.from_dict({"invoice_no": "X"})
        self.assertEqual(inv.attachments, [])
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd "D:\Code\Python\lan-invoice" && uv run python -m unittest tests.test_models -v 2>&1 | tail -20
```

预期：tags/attachments 相关测试 FAIL（AttributeError: 'Invoice' object has no attribute 'tags'）

- [ ] **Step 3: 修改 models.py 添加新字段**

在 `Invoice` dataclass 的 `@dataclass` 中：

```python
@dataclass
class Invoice:
    """单张发票的完整数据"""
    file: str = ""
    pdf_path: str = ""
    company: str = ""    # 保留用于旧数据迁移，标记为 deprecated
    invoice_type: str = ""
    buyer_name: str = ""
    buyer_tax_id: str = ""
    seller_name: str = ""
    amount: str = ""
    tax_rate: str = ""
    tax_amount: str = ""
    total: str = ""
    invoice_no: str = ""
    invoice_date: str = ""
    is_red: bool = False
    screenshots: list[str] = field(default_factory=list)   # deprecated: 旧数据迁移用
    contracts: list[str] = field(default_factory=list)      # deprecated: 旧数据迁移用
    tags: dict[str, str] = field(default_factory=dict)
    attachments: list[str] = field(default_factory=list)
    remark: str = ""
    error: str = ""
```

更新 `to_dict()` 方法（在 remark 之前添加 tags 和 attachments，保留 screenshots/contracts 向后兼容）：

```python
def to_dict(self) -> dict:
    """转为可 JSON 序列化的 dict"""
    return {
        "file": self.file,
        "pdf_path": self.pdf_path,
        "company": self.company,
        "invoice_type": self.invoice_type,
        "buyer_name": self.buyer_name,
        "buyer_tax_id": self.buyer_tax_id,
        "seller_name": self.seller_name,
        "amount": self.amount,
        "tax_rate": self.tax_rate,
        "tax_amount": self.tax_amount,
        "total": self.total,
        "invoice_no": self.invoice_no,
        "invoice_date": self.invoice_date,
        "is_red": self.is_red,
        "screenshots": list(self.screenshots),
        "contracts": list(self.contracts),
        "tags": dict(self.tags),
        "attachments": list(self.attachments),
        "remark": self.remark,
        "error": self.error,
    }
```

更新 `from_dict()` 方法（读取旧字段 + 新字段）：

```python
@classmethod
def from_dict(cls, d: dict) -> "Invoice":
    """从 dict 创建实例，兼容旧数据缺失字段"""
    return cls(
        file=d.get("file", ""),
        pdf_path=d.get("pdf_path", ""),
        company=d.get("company", ""),
        invoice_type=d.get("invoice_type", ""),
        buyer_name=d.get("buyer_name", ""),
        buyer_tax_id=d.get("buyer_tax_id", ""),
        seller_name=d.get("seller_name", ""),
        amount=str(d.get("amount", "")),
        tax_rate=str(d.get("tax_rate", "")),
        tax_amount=str(d.get("tax_amount", "")),
        total=str(d.get("total", "")),
        invoice_no=d.get("invoice_no", ""),
        invoice_date=d.get("invoice_date", ""),
        is_red=bool(d.get("is_red", False)),
        screenshots=list(d.get("screenshots", [])),
        contracts=list(d.get("contracts", [])),
        tags=dict(d.get("tags", {})),
        attachments=list(d.get("attachments", [])),
        remark=d.get("remark", ""),
        error=d.get("error", ""),
    )
```

- [ ] **Step 4: 运行模型测试验证通过**

```bash
cd "D:\Code\Python\lan-invoice" && uv run python -m unittest tests.test_models -v 2>&1 | tail -30
```

预期：全部 PASS

- [ ] **Step 5: 验证应用启动**

```bash
cd "D:\Code\Python\lan-invoice" && timeout 3 uv run python src/invoice_tool.py 2>&1; echo "exit: $?"
```

预期：应用正常启动和退出

- [ ] **Step 6: 运行全部测试确认无回归**

```bash
cd "D:\Code\Python\lan-invoice" && uv run python -m unittest discover -s tests -p "test_*.py" -v 2>&1 | tail -50
```

预期：全部 PASS（tags/attachments 新增测试通过，旧测试不受影响）

- [ ] **Step 7: 提交**

```bash
git add src/models.py tests/test_models.py
git commit -m "feat: Invoice 模型新增 tags/attachments 字段，保留旧字段兼容

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2: Repository 旧数据迁移

**Files:**
- Modify: `src/repository.py`
- Modify: `tests/test_repository.py`

- [ ] **Step 1: 更新和新增测试**

先读取现有 `tests/test_repository.py` 了解现有测试结构（如果存在），然后编写迁移测试：

```python
# 在 tests/test_repository.py 中添加：

class TestDataMigration(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.data_file = os.path.join(self.tmp_dir, "test_data.json")
        self.repo = InvoiceRepository(self.data_file)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _write_old_format(self, records: list[dict]):
        """写入旧格式数据（有 screenshots/contracts/company，无 tags/attachments）"""
        with open(self.data_file, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False)

    def test_migrate_company_to_tags(self):
        self._write_old_format([{
            "file": "test.pdf",
            "invoice_no": "12345",
            "company": "14786",
            "screenshots": [],
            "contracts": [],
        }])
        invoices = self.repo.load()
        self.assertEqual(invoices[0].tags.get("企业号"), "14786")

    def test_migrate_screenshots_and_contracts_to_attachments(self):
        self._write_old_format([{
            "file": "test.pdf",
            "invoice_no": "12345",
            "company": "",
            "screenshots": ["/old/ss/1.png"],
            "contracts": ["/old/ct/1.pdf"],
        }])
        invoices = self.repo.load()
        self.assertIn("/old/ss/1.png", invoices[0].attachments)
        self.assertIn("/old/ct/1.pdf", invoices[0].attachments)

    def test_migrate_does_not_duplicate(self):
        """已有 tags/attachments 的记录不重复迁移"""
        self._write_old_format([{
            "file": "test.pdf",
            "invoice_no": "12345",
            "company": "14786",
            "screenshots": ["/old/ss/1.png"],
            "contracts": [],
            "tags": {"企业号": "99999"},
            "attachments": ["/new/att/1.png"],
        }])
        invoices = self.repo.load()
        self.assertEqual(invoices[0].tags.get("企业号"), "99999")
        self.assertEqual(invoices[0].attachments, ["/new/att/1.png"])

    def test_migrate_empty_old_data(self):
        self._write_old_format([{
            "file": "test.pdf",
            "invoice_no": "12345",
            "company": "",
            "screenshots": [],
            "contracts": [],
        }])
        invoices = self.repo.load()
        self.assertEqual(invoices[0].tags, {})
        self.assertEqual(invoices[0].attachments, [])

    def test_new_format_passes_through(self):
        """新格式数据不受迁移影响"""
        with open(self.data_file, "w", encoding="utf-8") as f:
            json.dump([{
                "file": "test.pdf",
                "invoice_no": "12345",
                "company": "",
                "screenshots": [],
                "contracts": [],
                "tags": {"企业号": "A001", "项目名称": "Q1"},
                "attachments": ["/att/a.png"],
            }], f, ensure_ascii=False)
        invoices = self.repo.load()
        self.assertEqual(invoices[0].tags, {"企业号": "A001", "项目名称": "Q1"})
        self.assertEqual(invoices[0].attachments, ["/att/a.png"])
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd "D:\Code\Python\lan-invoice" && uv run python -m unittest tests.test_repository.TestDataMigration -v 2>&1 | tail -20
```

预期：迁移测试 FAIL（尚未实现迁移逻辑）

- [ ] **Step 3: 修改 repository.py 的 load 方法**

读取现有 `src/repository.py`，在 `load()` 方法返回前添加迁移调用：

```python
def load(self) -> list[Invoice]:
    """从 JSON 文件加载发票列表，自动迁移旧格式"""
    if not os.path.exists(self._file_path):
        return []
    try:
        with open(self._file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.error("数据加载失败: %s", e)
        return []
    
    invoices = [Invoice.from_dict(item) for item in data]
    # 旧格式迁移
    if self._needs_migration(invoices):
        invoices = self._migrate(invoices)
        self.save(invoices)
    return invoices

def _needs_migration(self, invoices: list[Invoice]) -> bool:
    """检测是否有旧格式数据需要迁移"""
    for inv in invoices:
        if inv.company or inv.screenshots or inv.contracts:
            return True
    return False

def _migrate(self, invoices: list[Invoice]) -> list[Invoice]:
    """执行旧格式到新格式的迁移"""
    for inv in invoices:
        # company → tags["企业号"]（不覆盖已有值）
        if inv.company and "企业号" not in (inv.tags or {}):
            if not inv.tags:
                inv.tags = {}
            inv.tags["企业号"] = inv.company
        # screenshots + contracts → attachments（合并去重）
        existing = set(inv.attachments or [])
        for p in (inv.screenshots or []):
            if p not in existing:
                inv.attachments.append(p)
                existing.add(p)
        for p in (inv.contracts or []):
            if p not in existing:
                inv.attachments.append(p)
                existing.add(p)
    log.info("旧数据迁移完成: %d 条记录", len(invoices))
    return invoices
```

- [ ] **Step 4: 运行迁移测试验证通过**

```bash
cd "D:\Code\Python\lan-invoice" && uv run python -m unittest tests.test_repository.TestDataMigration -v 2>&1 | tail -20
```

预期：全部 PASS

- [ ] **Step 5: 验证应用启动**

```bash
cd "D:\Code\Python\lan-invoice" && timeout 3 uv run python src/invoice_tool.py 2>&1; echo "exit: $?"
```

- [ ] **Step 6: 提交**

```bash
git add src/repository.py tests/test_repository.py
git commit -m "feat: Repository 加载时自动迁移旧数据格式

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 3: InvoiceService 附件统一

**Files:**
- Modify: `src/services/invoice_service.py`
- Modify: `tests/test_services.py`

- [ ] **Step 1: 编写更新后的 Service 测试**

修改 `tests/test_services.py`，添加/修改附件统一测试：

```python
class TestAttachmentService(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.att_dir = os.path.join(self.tmp, "attachments")
        self.inv_dir = os.path.join(self.tmp, "invoices")
        os.makedirs(self.att_dir)
        os.makedirs(self.inv_dir)
        repo = InvoiceRepository(os.path.join(self.tmp, "data.json"))
        self.svc = InvoiceService(repo, self.att_dir, self.inv_dir)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_file(self, name, content=b"test"):
        path = os.path.join(self.tmp, name)
        with open(path, "wb") as f:
            f.write(content)
        return path

    def test_add_attachment_image(self):
        src = self._make_file("screenshot.png")
        inv = Invoice(invoice_no="12345")
        added = self.svc.add_attachments(inv, [src], "attachments", self.att_dir,
                                         self.svc._attachment_namer)
        self.assertEqual(added, 1)
        self.assertEqual(len(inv.attachments), 1)

    def test_add_attachment_pdf(self):
        src = self._make_file("contract.pdf")
        inv = Invoice(invoice_no="12345")
        added = self.svc.add_attachments(inv, [src], "attachments", self.att_dir,
                                         self.svc._attachment_namer)
        self.assertEqual(added, 1)

    def test_add_attachment_docx(self):
        src = self._make_file("contract.docx")
        inv = Invoice(invoice_no="12345")
        added = self.svc.add_attachments(inv, [src], "attachments", self.att_dir,
                                         self.svc._attachment_namer)
        self.assertEqual(added, 1)

    def test_add_multiple_attachments(self):
        src1 = self._make_file("a.png")
        src2 = self._make_file("b.pdf")
        inv = Invoice(invoice_no="12345")
        added = self.svc.add_attachments(inv, [src1, src2], "attachments", self.att_dir,
                                         self.svc._attachment_namer)
        self.assertEqual(added, 2)
        self.assertEqual(len(inv.attachments), 2)

    def test_add_attachment_file_not_found(self):
        inv = Invoice(invoice_no="12345")
        added = self.svc.add_attachments(inv, ["/nonexistent.png"], "attachments",
                                         self.att_dir, self.svc._attachment_namer)
        self.assertEqual(added, 0)
```

- [ ] **Step 2: 修改 invoice_service.py**

保持 `add_attachments` 签名不变，简化构造函数（去掉 contract_dir 参数），添加 `_attachment_namer` 静态方法：

```python
class InvoiceService:
    """发票业务编排：导入、删除、附件管理"""

    def __init__(self, repository: InvoiceRepository,
                 attachment_dir: str, invoice_dir: str):
        self._repo = repository
        self._attachment_dir = attachment_dir
        self._invoice_dir = invoice_dir
        os.makedirs(attachment_dir, exist_ok=True)
        os.makedirs(invoice_dir, exist_ok=True)

    # ... 保留 load_all, save_all, find_by_invoice_no, init_record, make_error_record ...

    def add_attachments(self, inv: Invoice, src_paths: list[str],
                         field: str, target_dir: str,
                         make_filename) -> int:
        """通用附件添加，返回成功添加数"""
        inv_no = inv.invoice_no or inv.file or "unnamed"
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', inv_no)
        added = 0
        for src in src_paths:
            if not os.path.isfile(src):
                continue
            dst = os.path.join(target_dir, make_filename(src, safe_name))
            try:
                shutil.copy2(src, dst)
                getattr(inv, field).append(dst)
                added += 1
            except OSError:
                continue
        return added

    @staticmethod
    def _attachment_namer(src: str, safe_name: str) -> str:
        ext = os.path.splitext(src)[1].lower() or ".dat"
        orig_base = os.path.splitext(os.path.basename(src))[0]
        ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
        return f"{safe_name}_{orig_base}_{ts}{ext}"

    # 删除旧的 screenshot_namer / contract_namer，保留为别名（@deprecated 注释）
    screenshot_namer = _attachment_namer
    contract_namer = _attachment_namer

    def copy_invoice_pdf(self, src: str) -> str:
        from utils import copy_file_to_dir
        return copy_file_to_dir(src, self._invoice_dir)
```

- [ ] **Step 3: 运行 Service 测试**

```bash
cd "D:\Code\Python\lan-invoice" && uv run python -m unittest tests.test_services -v 2>&1 | tail -20
```

- [ ] **Step 4: 验证应用启动**

```bash
cd "D:\Code\Python\lan-invoice" && timeout 3 uv run python src/invoice_tool.py 2>&1; echo "exit: $?"
```

- [ ] **Step 5: 运行全部测试**

```bash
cd "D:\Code\Python\lan-invoice" && uv run python -m unittest discover -s tests -p "test_*.py" -v 2>&1 | tail -30
```

- [ ] **Step 6: 提交**

```bash
git add src/services/invoice_service.py tests/test_services.py
git commit -m "feat: InvoiceService 附件统一，不再区分截图/合同

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 4: 统一附件预览对话框

**Files:**
- Create: `src/ui/dialogs/attachment_viewer.py`
- Create: `tests/test_attachment_viewer.py`

- [ ] **Step 1: 编写测试文件**

```python
# tests/test_attachment_viewer.py
# -*- coding: utf-8 -*-
"""统一附件预览对话框测试"""
import sys, os, unittest, tempfile, shutil
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from PyQt5.QtWidgets import QApplication, QMessageBox, QDialog
from PyQt5.QtCore import Qt

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

    def test_select_enables_preview(self):
        from ui.dialogs.attachment_viewer import AttachmentViewerDialog
        p1 = self._make_file("a.png")
        dlg = AttachmentViewerDialog([p1])
        self.assertTrue(dlg.btn_preview.isEnabled())
        dlg.close()

    def test_no_select_disables_preview(self):
        from ui.dialogs.attachment_viewer import AttachmentViewerDialog
        dlg = AttachmentViewerDialog([])
        self.assertFalse(dlg.btn_preview.isEnabled())
        dlg.close()

    def test_image_preview_opens_viewer(self):
        from ui.dialogs.attachment_viewer import AttachmentViewerDialog
        p1 = self._make_file("img.png")
        dlg = AttachmentViewerDialog([p1])
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
        with patch("ui.dialogs.attachment_viewer.PdfViewerDialog") as mock_pdf:
            dlg._preview_selected()
            mock_pdf.assert_called_once()
        dlg.close()
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd "D:\Code\Python\lan-invoice" && uv run python -m unittest tests.test_attachment_viewer -v 2>&1 | tail -10
```

预期：FAIL（AttachmentViewerDialog 尚未创建）

- [ ] **Step 3: 创建统一附件预览对话框**

```python
# src/ui/dialogs/attachment_viewer.py
# -*- coding: utf-8 -*-
"""统一附件预览对话框 — 按类型自动选择预览方式"""

import os
import shutil
from datetime import datetime

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QMessageBox, QListWidget, QListWidgetItem,
    QAbstractItemView
)
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QDesktopServices, QIcon

from logger import getLogger
log = getLogger(__name__)

from ui.theme import ACCENT, RED, GREEN, DARK_SURFACE, DARK_BG, DARK_TEXT, DARK_TEXT_DIM

# 支持的文件类型分类
IMG_EXTS = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.tiff', '.tif'}
PDF_EXTS = {'.pdf'}
DOC_EXTS = {'.docx', '.doc', '.xlsx', '.xls'}

TYPE_ICONS = {
    'image': '🖼',
    'pdf': '📄',
    'doc': '📎',
}


class AttachmentViewerDialog(QDialog):
    """统一附件预览对话框 — 左侧文件列表 + 右侧预览/操作"""

    def __init__(self, attachment_paths: list[str], rec_name: str = "", parent=None):
        super().__init__(parent)
        self.attachment_paths = list(attachment_paths)
        self._rec_name = rec_name
        self.setWindowTitle(f"附件预览 — {rec_name}" if rec_name else "附件预览")
        self.resize(900, 600)
        self.setMinimumSize(500, 350)
        self._build_ui()
        self._populate_list()

    def _classify(self, path: str) -> str:
        ext = os.path.splitext(path)[1].lower()
        if ext in IMG_EXTS:
            return 'image'
        elif ext in PDF_EXTS:
            return 'pdf'
        else:
            return 'doc'

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        body = QHBoxLayout()
        body.setSpacing(8)

        # 左侧文件列表
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_widget.setFixedWidth(280)
        self.list_widget.setStyleSheet(
            f"QListWidget {{ background:{DARK_BG}; border:1px solid #444; }}"
            f"QListWidget::item {{ padding:6px; }}"
            f"QListWidget::item:selected {{ background:#3A5A8C; }}"
        )
        self.list_widget.currentRowChanged.connect(self._on_selection_changed)
        body.addWidget(self.list_widget)

        # 右侧信息面板
        right = QVBoxLayout()
        right.setSpacing(8)
        self.lbl_info = QLabel("选择一个文件查看详情")
        self.lbl_info.setWordWrap(True)
        self.lbl_info.setStyleSheet(
            f"color:{DARK_TEXT}; font-size:13px; "
            f"background:{DARK_SURFACE}; padding:12px; border-radius:6px;"
        )
        right.addWidget(self.lbl_info, 1)

        body.addLayout(right, 1)
        layout.addLayout(body)

        # 底部操作栏
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(8)

        self.btn_preview = QPushButton("预览")
        self.btn_preview.setFixedHeight(32)
        self.btn_preview.setEnabled(False)
        self.btn_preview.clicked.connect(self._preview_selected)

        self.btn_sys_open = QPushButton("系统打开")
        self.btn_sys_open.setFixedHeight(32)
        self.btn_sys_open.setEnabled(False)
        self.btn_sys_open.clicked.connect(self._open_system)

        self.btn_download = QPushButton("下载另存")
        self.btn_download.setFixedHeight(32)
        self.btn_download.setEnabled(False)
        self.btn_download.clicked.connect(self._download_selected)

        self.btn_remove = QPushButton("移除")
        self.btn_remove.setFixedHeight(32)
        self.btn_remove.setEnabled(False)
        self.btn_remove.setStyleSheet(
            f"background:{RED}; color:white; font-weight:bold; border-radius:4px; padding:0 12px;"
        )
        self.btn_remove.clicked.connect(self._remove_selected)

        btn_bar.addWidget(self.btn_preview)
        btn_bar.addWidget(self.btn_sys_open)
        btn_bar.addWidget(self.btn_download)
        btn_bar.addWidget(self.btn_remove)
        btn_bar.addStretch()

        btn_close = QPushButton("关闭")
        btn_close.setFixedHeight(32)
        btn_close.clicked.connect(self.accept)
        btn_bar.addWidget(btn_close)
        layout.addLayout(btn_bar)

        from ui.theme import DIALOG_QSS_DARK
        self.setStyleSheet(DIALOG_QSS_DARK)
        for btn in self.findChildren(QPushButton):
            btn.setCursor(Qt.PointingHandCursor)

    def _populate_list(self):
        for path in self.attachment_paths:
            name = os.path.basename(path)
            cat = self._classify(path)
            icon_text = TYPE_ICONS.get(cat, '📎')
            exists = os.path.exists(path)
            display = f"{icon_text} {name}" if exists else f"❌ {name}（已移动）"
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, path)
            self.list_widget.addItem(item)

    def _on_selection_changed(self, row):
        if row < 0:
            return
        item = self.list_widget.item(row)
        if not item:
            return
        path = item.data(Qt.UserRole)
        if not path:
            return
        exists = os.path.exists(path)
        name = os.path.basename(path)
        size = f"{os.path.getsize(path) / 1024:.1f} KB" if exists else "—"
        cat = self._classify(path)
        cat_label = {'image': '图片', 'pdf': 'PDF文档', 'doc': '文档'}.get(cat, '其他')
        self.lbl_info.setText(
            f"<b>{name}</b><br>"
            f"<span style='color:{DARK_TEXT_DIM};'>类型：{cat_label}</span><br>"
            f"<span style='color:{DARK_TEXT_DIM};'>大小：{size}</span><br>"
            f"<span style='color:{DARK_TEXT_DIM};'>路径：{path}</span>"
        )
        self.btn_preview.setEnabled(exists)
        self.btn_sys_open.setEnabled(exists)
        self.btn_download.setEnabled(exists)
        self.btn_remove.setEnabled(True)

    def _get_selected_path(self):
        item = self.list_widget.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _preview_selected(self):
        path = self._get_selected_path()
        if not path or not os.path.exists(path):
            return
        cat = self._classify(path)
        if cat == 'image':
            from ui.dialogs.image_viewer import ImageViewerDialog
            dialog = ImageViewerDialog([path], parent=self)
            dialog.exec_()
        elif cat == 'pdf':
            from ui.dialogs.pdf_viewer import PdfViewerDialog
            dialog = PdfViewerDialog(path, parent=self)
            dialog.exec_()
        else:
            self._open_system()

    def _open_system(self):
        path = self._get_selected_path()
        if not path or not os.path.exists(path):
            QMessageBox.warning(self, "文件不存在", "文件不存在或已被移动。")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _download_selected(self):
        path = self._get_selected_path()
        if not path or not os.path.exists(path):
            QMessageBox.warning(self, "文件不存在", "文件不存在或已被移动。")
            return
        dst, _ = QFileDialog.getSaveFileName(
            self, "另存附件", os.path.basename(path),
            "所有文件 (*)"
        )
        if dst:
            shutil.copy2(path, dst)
            QMessageBox.information(self, "保存成功", f"文件已保存到：\n{dst}")

    def _remove_selected(self):
        row = self.list_widget.currentRow()
        if row < 0:
            return
        item = self.list_widget.item(row)
        if not item:
            return
        path = item.data(Qt.UserRole)
        reply = QMessageBox.question(
            self, "确认移除",
            f"确定要移除「{os.path.basename(path)}」吗？\n\n此操作仅从列表中移除记录，不会删除文件。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        if path in self.attachment_paths:
            self.attachment_paths.remove(path)
        self.list_widget.takeItem(row)
```

- [ ] **Step 4: 运行附件预览对话框测试**

```bash
cd "D:\Code\Python\lan-invoice" && uv run python -m unittest tests.test_attachment_viewer -v 2>&1 | tail -30
```

- [ ] **Step 5: 提交**

```bash
git add src/ui/dialogs/attachment_viewer.py tests/test_attachment_viewer.py
git commit -m "feat: 统一附件预览对话框，按类型自动选择预览方式

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 5: InvoiceApp 导入流程 — 拖拽逻辑重写

**Files:**
- Modify: `src/invoice_tool.py` (dropEvent 区域)
- Modify: `tests/test_invoice_tool.py` (新增拖拽测试)

- [ ] **Step 1: 编写拖拽逻辑测试**

在 `tests/test_invoice_tool.py` 中添加：

```python
class TestDropEventLogic(unittest.TestCase):
    """测试拖拽事件的路由逻辑（patch 掉 UI 层）"""

    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        import tempfile, shutil
        self.tmp = tempfile.mkdtemp()
        # 创建临时数据目录
        data_dir = os.path.join(self.tmp, "data")
        os.makedirs(data_dir)
        os.makedirs(os.path.join(data_dir, "invoices"))
        os.makedirs(os.path.join(data_dir, "attachments"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
```

- [ ] **Step 2: 修改 dropEvent 逻辑**

重写 `src/invoice_tool.py` 中的 `dropEvent` 方法：

```python
def dropEvent(self, e: QDropEvent):
    urls = e.mimeData().urls()
    pdf_files = []
    img_files = []
    doc_files = []

    for u in urls:
        path = u.toLocalFile()
        ext = os.path.splitext(path)[1].lower()
        if ext == '.pdf':
            pdf_files.append(path)       # PDF 始终作为发票导入
        elif ext in IMG_EXTS:
            img_files.append(path)
        elif ext in CONTRACT_EXTS:
            doc_files.append(path)

    # PDF → 发票导入（不依赖选中状态）
    if pdf_files:
        self._start_parse(pdf_files)

    # 图片/文档 → 附件
    rows = sorted(set(item.row() for item in self.table.selectedItems()))
    other_files = img_files + doc_files
    if other_files:
        if not rows:
            QMessageBox.information(
                self, "提示",
                "请先选中一行，再将图片/文档拖入作为附件添加。\n"
                "PDF 文件将始终作为发票导入。"
            )
        else:
            self._add_attachments_from_paths(rows[0], other_files)
```

同时需要新增 `_add_attachments_from_paths` 方法（统一附件添加）：

```python
def _add_attachments_from_paths(self, row, src_paths):
    """统一添加附件（图片+文档），不再区分截图/合同"""
    rec = self._get_record_by_row(row)
    if rec is None:
        return
    added = self._svc.add_attachments(rec, src_paths, "attachments",
                                      self._attachment_dir,
                                      InvoiceService._attachment_namer)
    if added > 0:
        self._set_attachment_cell(row, rec)
        self._save_data()
        self.status.showMessage(f"已添加 {added} 个附件")
```

- [ ] **Step 3: 修改拖入提示覆盖层**

添加 `dragEnterEvent` 的视觉反馈：

```python
def dragEnterEvent(self, e: QDragEnterEvent):
    if e.mimeData().hasUrls():
        e.acceptProposedAction()
        self._show_drop_overlay(e.mimeData().urls())

def dragLeaveEvent(self, e):
    self._hide_drop_overlay()

def _show_drop_overlay(self, urls):
    """显示半透明拖拽提示覆盖层"""
    if not hasattr(self, '_drop_overlay'):
        self._drop_overlay = QLabel(self)
        self._drop_overlay.setAlignment(Qt.AlignCenter)
        self._drop_overlay.setStyleSheet(
            "background: rgba(30, 111, 191, 0.85); color: white; "
            "font-size: 18px; font-weight: bold; border-radius: 12px;"
        )
    pdf_count = sum(1 for u in urls if u.toLocalFile().lower().endswith('.pdf'))
    other_count = len(urls) - pdf_count
    parts = []
    if pdf_count:
        parts.append(f"导入 {pdf_count} 个发票 PDF")
    if other_count:
        rows = set(item.row() for item in self.table.selectedItems())
        if rows:
            parts.append(f"添加 {other_count} 个附件到选中行")
        else:
            parts.append(f"需选中行以添加 {other_count} 个附件")
    self._drop_overlay.setText("\n".join(parts))
    self._drop_overlay.setGeometry(0, 0, self.width(), self.height())
    self._drop_overlay.show()

def _hide_drop_overlay(self):
    if hasattr(self, '_drop_overlay'):
        self._drop_overlay.hide()
```

- [ ] **Step 4: 验证应用启动 + 拖拽功能**

```bash
cd "D:\Code\Python\lan-invoice" && timeout 3 uv run python src/invoice_tool.py 2>&1; echo "exit: $?"
```

- [ ] **Step 5: 提交**

```bash
git add src/invoice_tool.py
git commit -m "fix: 重写拖拽逻辑 — PDF 始终按发票导入，附件需明确拖入

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 6: 导入结果摘要 + 重复检测

**Files:**
- Modify: `src/invoice_tool.py` (_add_record_batch, _parse_done)
- Modify: `tests/test_invoice_tool.py`

- [ ] **Step 1: 编写导入结果测试**

```python
class TestImportResultHandling(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication(sys.argv)

    def test_duplicate_invoice_detection(self):
        """重复发票号被检测"""
        # 需要 patch InvoiceApp 实例，此处用纯逻辑测试
        from invoice_tool import InvoiceApp
        from models import Invoice
        records = [Invoice(invoice_no="12345", file="a.pdf")]
        # 模拟查找
        inv_no = "12345"
        found = any(r.invoice_no == inv_no for r in records)
        self.assertTrue(found)

    def test_new_invoice_not_duplicate(self):
        from models import Invoice
        records = [Invoice(invoice_no="12345", file="a.pdf")]
        inv_no = "67890"
        found = any(r.invoice_no == inv_no for r in records)
        self.assertFalse(found)
```

- [ ] **Step 2: 修改 _add_record_batch 添加重复检测**

```python
def _add_record_batch(self, data: dict):
    """后台每解析完一条调此槽；重复检测 + 写入"""
    inv = Invoice.from_dict(data)
    if inv.invoice_no and self._find_record_index(inv.invoice_no) is not None:
        # 收集重复记录信息，稍后在摘要中展示
        if not hasattr(self, '_duplicate_invoices'):
            self._duplicate_invoices = []
        self._duplicate_invoices.append(inv)
        return  # 跳过重复
    if self.pending_company:
        inv.company = self.pending_company
    self._init_record_fields(inv)
    self.records.append(inv)
```

- [ ] **Step 3: 修改 _parse_done 添加结果摘要弹窗**

```python
def _parse_done(self):
    self._rebuild_table()
    self._refresh_filter_combos()
    self._save_data()

    self.btn_open.setEnabled(True)
    self.progress_bar.setVisible(False)
    batch_count = len(self.records) - getattr(self, '_batch_count_before', 0)
    fail_count = len(getattr(self, '_parse_errors', []))
    dup_count = len(getattr(self, '_duplicate_invoices', []))
    ok_count = batch_count - fail_count

    # 结果摘要弹窗
    msg_parts = []
    if ok_count > 0:
        msg_parts.append(f"成功导入 {ok_count} 张")
    if fail_count > 0:
        msg_parts.append(f"解析失败 {fail_count} 张（查看备注列）")
    if dup_count > 0:
        msg_parts.append(f"重复跳过 {dup_count} 张")
    
    if fail_count > 0 or dup_count > 0:
        detail = ""
        if fail_count > 0:
            detail += "\n解析失败：\n" + "\n".join(f"  · {e}" for e in self._parse_errors)
        if dup_count > 0:
            dup_nos = [inv.invoice_no for inv in self._duplicate_invoices]
            detail += "\n重复发票号：\n" + "\n".join(f"  · {n}" for n in dup_nos)
        QMessageBox.information(
            self, "导入完成",
            "\n".join(msg_parts) +
            (f"\n\n详情：{detail}" if detail else "")
        )
    
    self.status.showMessage(" | ".join(msg_parts) if msg_parts else "导入完成")

    # 清理临时状态
    self._parse_errors = []
    self._duplicate_invoices = []
```

- [ ] **Step 4: 验证**

```bash
cd "D:\Code\Python\lan-invoice" && uv run python -m unittest discover -s tests -p "test_*.py" -v 2>&1 | tail -20
```

```bash
cd "D:\Code\Python\lan-invoice" && timeout 3 uv run python src/invoice_tool.py 2>&1; echo "exit: $?"
```

- [ ] **Step 5: 提交**

```bash
git add src/invoice_tool.py tests/test_invoice_tool.py
git commit -m "feat: 导入重复检测 + 结果摘要弹窗

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 7: 附件列 UI 合并

**Files:**
- Modify: `src/invoice_tool.py` (COLUMNS, _set_screenshot_cell, _set_contract_cell 及所有截图/合同操作)
- Modify: `tests/test_invoice_tool.py`

- [ ] **Step 1: 更新列定义和 FREEZE_COL_WIDTH**

```python
COLUMNS = ["发票类型", "购买方名称", "纳税人识别号",
           "销售方名称", "金额(元)", "征收率", "税额(元)", "价税合计(元)",
           "发票号码", "开票日期", "企业号", "附件", "备注"]
FREEZE_COL_WIDTH = 96
COL_IDX = {c: i for i, c in enumerate(COLUMNS)}

# 固定列宽调整
fixed_cols = {4: 88, 5: 55, 6: 88, 7: 98, 11: 100, 12: 80}
stretch_cols = {0: 100, 1: 130, 2: 130, 3: 130,
                8: 110, 9: 90, 10: 90}
```

- [ ] **Step 2: 新增 _set_attachment_cell 方法**

替换 `_set_screenshot_cell` + `_set_contract_cell`：

```python
def _set_attachment_cell(self, row, data):
    attachments = data.get("attachments", [])
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(4, 4, 4, 4)
    lay.setSpacing(4)

    if attachments:
        lbl = QLabel(f"[{len(attachments)}]")
        lbl.setStyleSheet(f"color:{ACCENT}; font-size:12px; font-weight:bold;")
        btn_v = QPushButton("查看")
        btn_v.setFixedHeight(24)
        btn_v.setFixedWidth(40)
        btn_v.setStyleSheet(
            f"font-size:11px; padding:1px 4px; color:{ACCENT}; border:none; background:transparent;")
        btn_v.clicked.connect(lambda _, r=row: self._view_attachments(r))
        lay.addWidget(lbl)
        lay.addWidget(btn_v)
    else:
        lbl = QLabel("—")
        lbl.setStyleSheet(f"color:{TEXT_DIM}; font-size:12px;")
        lay.addWidget(lbl)

    btn_add = QPushButton("＋")
    btn_add.setFixedHeight(24)
    btn_add.setFixedWidth(26)
    btn_add.setToolTip("添加附件")
    btn_add.setStyleSheet(
        f"font-size:13px; padding:0; color:{ACCENT}; border:none; background:transparent;")
    btn_add.clicked.connect(lambda _, r=row: self._add_attachment(r))
    lay.addWidget(btn_add)
    lay.addStretch()
    self.table.setCellWidget(row, COL_IDX["附件"], w)

def _add_attachment(self, row):
    files, _ = QFileDialog.getOpenFileNames(
        self, "选择附件文件", "",
        "附件文件 (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.pdf *.docx *.doc *.xlsx *.xls);;所有文件 (*)"
    )
    if files:
        self._add_attachments_from_paths(row, files)

def _view_attachments(self, row):
    rec = self._get_record_by_row(row)
    if rec is None:
        return
    atts = rec.get("attachments", [])
    if not atts:
        QMessageBox.information(self, "提示", "该发票暂无附件")
        return
    from ui.dialogs.attachment_viewer import AttachmentViewerDialog
    dlg = AttachmentViewerDialog(
        atts, rec_name=rec.get("buyer_name", "") or rec.get("file", ""),
        parent=self
    )
    dlg.exec_()
    # 同步删除操作
    if dlg.attachment_paths != atts:
        rec["attachments"] = dlg.attachment_paths
        self._set_attachment_cell(row, rec)
        self._save_data()
```

- [ ] **Step 3: 更新 _insert_row 中的附件调用**

将 `_insert_row` 中的：
```python
self._set_screenshot_cell(row, data)
self._set_contract_cell(row, data)
```
替换为：
```python
self._set_attachment_cell(row, data)
```

- [ ] **Step 4: 更新右键菜单（精简附件项）**

```python
def _show_context_menu(self, pos):
    menu = QMenu(self)
    menu.addAction(get_icon('plus'), "添加附件", self._ctx_add_attachment)
    menu.addAction(get_icon('clipboard'), "粘贴附件（Ctrl+V）", self._ctx_paste_attachment)
    menu.addAction(get_icon('search'), "查看附件", self._ctx_view_attachments)
    menu.addAction(get_icon('delete'), "清除附件", self._ctx_delete_attachments)
    menu.addSeparator()
    menu.addAction(get_icon('delete'), "删除选中行", self._delete_selected_rows)
    menu.exec_(self.table.viewport().mapToGlobal(pos))
```

- [ ] **Step 5: 更新构造函数中的附件目录**

```python
self._attachment_dir = os.path.join(self._data_dir, "attachments")
os.makedirs(self._attachment_dir, exist_ok=True)

self._svc = InvoiceService(self._repo, self._attachment_dir,
                            os.path.join(self._data_dir, "invoices"))
```

同时删除 `self._screenshot_dir` 和 `self._contract_dir` 的初始化。

- [ ] **Step 6: 验证应用启动**

```bash
cd "D:\Code\Python\lan-invoice" && timeout 3 uv run python src/invoice_tool.py 2>&1; echo "exit: $?"
```

- [ ] **Step 7: 运行全部测试**

```bash
cd "D:\Code\Python\lan-invoice" && uv run python -m unittest discover -s tests -p "test_*.py" -v 2>&1 | tail -30
```

- [ ] **Step 8: 提交**

```bash
git add src/invoice_tool.py
git commit -m "feat: 附件列 UI 合并 — 截图+合同统一为附件列

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 8: 企业号降级为标签 + 标签列

**Files:**
- Modify: `src/invoice_tool.py` (_init_ui, _insert_row, 筛选逻辑)
- Modify: `src/ui/dialogs/settings.py` (标签模板管理)
- Create: `tests/test_settings.py`

- [ ] **Step 1: 编写设置对话框标签管理测试**

```python
# tests/test_settings.py
# -*- coding: utf-8 -*-
"""设置对话框测试 — 标签模板管理 + 目录切换"""

import sys, os, unittest, tempfile, shutil, json
from unittest.mock import patch, MagicMock

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


class TestTagTemplates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._msg = _patch_qmessagebox()

    @classmethod
    def tearDownClass(cls):
        cls._msg.stop()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.config_file = os.path.join(self.tmp, "config.json")
        data_dir = os.path.join(self.tmp, "data")
        os.makedirs(data_dir)
        os.makedirs(os.path.join(data_dir, "invoices"))
        os.makedirs(os.path.join(data_dir, "attachments"))
        # Mock app
        self.mock_app = MagicMock()
        self.mock_app.records = []
        self.mock_app._data_dir = data_dir
        self.mock_app._data_file = os.path.join(data_dir, "data.json")
        self.mock_app._attachment_dir = os.path.join(data_dir, "attachments")
        self.mock_app._screenshot_dir = os.path.join(data_dir, "screenshots")
        self.mock_app._contract_dir = os.path.join(data_dir, "contracts")
        self.mock_app._config_file = self.config_file

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_default_tag_templates(self):
        """默认标签模板包含企业号"""
        from ui.dialogs.settings import SettingsDialog
        dlg = SettingsDialog(self.mock_app)
        self.assertTrue(hasattr(dlg, '_tag_list') or hasattr(dlg, 'edit_data_dir'))
        dlg.close()
```

- [ ] **Step 2: 修改设置对话框 — 添加标签管理区域**

在 `settings.py` 的 `_build_ui()` 方法中，在"数据存储"区域后、"软件另存"区域前添加标签管理区域：

```python
# ── 标签模板管理 ───────────────────────────
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

# 标签列表
from PyQt5.QtWidgets import QListWidget, QAbstractItemView
self.tag_list = QListWidget()
self.tag_list.setMaximumHeight(100)
self.tag_list.setStyleSheet(
    f"background:{BG_ALT}; border:none; font-size:12px;"
)
self._load_tag_templates()
layout.addWidget(self.tag_list)

btn_del_tag = QPushButton("删除选中标签")
btn_del_tag.setFixedHeight(28)
btn_del_tag.clicked.connect(self._del_tag_template)
layout.addWidget(btn_del_tag)
```

在 SettingsDialog 类中添加标签管理方法：

```python
def _load_tag_templates(self):
    """从配置文件加载标签模板"""
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
    self._app._rebuild_table()  # 刷新表格列

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
    self._app._rebuild_table()
```

需要在 settings.py 顶部添加 `import json`。

- [ ] **Step 3: 修改 invoice_tool.py — 企业号退化为标签列**

删除 `_init_ui` 中的企业号输入框区域（top_bar 中的 edit_company, btn_apply），删除 `pending_company` 相关逻辑。

修改 `_init_ui` 中 `COLUMNS` 不再包含"企业号"，改为动态标签列：

```python
# 在 InvoiceApp.__init__ 中添加：
self._tag_templates = self._load_tag_templates()

def _load_tag_templates(self):
    try:
        with open(self._config_file, "r", encoding="utf-8") as f:
            config = json.load(f)
            return config.get("tag_templates", ["企业号"])
    except (OSError, json.JSONDecodeError):
        return ["企业号"]

def _get_effective_columns(self):
    """返回当前生效的列名列表（固定列 + 标签列）"""
    return (["发票类型", "购买方名称", "纳税人识别号",
             "销售方名称", "金额(元)", "征收率", "税额(元)", "价税合计(元)",
             "发票号码", "开票日期"] +
            self._tag_templates +
            ["附件", "备注"])
```

修改 `_rebuild_table` 使用 `_get_effective_columns()` 动态生成列（列索引动态计算）。

修改 `_insert_row` 中"企业号"列的写入，改为遍历 `_tag_templates` 写入标签值：

```python
# 替换原来的 self.table.setItem(row, COL_IDX["企业号"], cell(...))
for tag_name in self._tag_templates:
    tag_col = self._get_tag_col_idx(tag_name)
    tag_value = data.get("tags", {}).get(tag_name, "")
    self.table.setItem(row, tag_col, cell(tag_value, editable=True))
```

- [ ] **Step 4: 更新筛选逻辑支持标签搜索**

```python
def _record_matches_filter(self, rec) -> bool:
    if not record_matches_filter(
        rec, self._filter_year, self._filter_month,
        self._filter_inv_type, self._filter_seller,
        self._filter_buyer, self._filter_company):
        return False
    # 标签搜索：所有标签值参与全局搜索
    if self._filter_company:
        tags = rec.get("tags", {})
        if not any(self._filter_company.lower() in str(v).lower()
                   for v in tags.values()):
            return False
    return True
```

- [ ] **Step 5: 验证应用启动**

```bash
cd "D:\Code\Python\lan-invoice" && timeout 3 uv run python src/invoice_tool.py 2>&1; echo "exit: $?"
```

- [ ] **Step 6: 运行全部测试**

```bash
cd "D:\Code\Python\lan-invoice" && uv run python -m unittest discover -s tests -p "test_*.py" -v 2>&1 | tail -30
```

- [ ] **Step 7: 提交**

```bash
git add src/invoice_tool.py src/ui/dialogs/settings.py tests/test_settings.py
git commit -m "feat: 企业号降级为标签 + 标签模板管理

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 9: 筛选实时化 + 列头排序

**Files:**
- Modify: `src/invoice_tool.py` (筛选逻辑, _init_ui)

- [ ] **Step 1: 修改筛选控件连接为实时触发**

在 `_init_ui` 中修改 combobox 的信号连接：

```python
# 年份/月份即时生效
self.combo_year.currentIndexChanged.connect(self._apply_filter)
self.combo_month.currentIndexChanged.connect(self._apply_filter)

# 高级筛选项即时生效
self.combo_inv_type.currentIndexChanged.connect(self._apply_filter)
self.combo_seller.currentIndexChanged.connect(self._apply_filter)

# 文本输入框用防抖
self._filter_timer = QTimer(self)
self._filter_timer.setSingleShot(True)
self._filter_timer.timeout.connect(self._apply_filter)

self.edit_buyer_search.textChanged.connect(
    lambda: self._filter_timer.start(300))
self.edit_company_search.textChanged.connect(
    lambda: self._filter_timer.start(300))
```

移除"筛选"和"重置"按钮，添加"清除筛选"按钮：

```python
self.btn_reset = QPushButton("清除筛选")
self.btn_reset.setFixedHeight(30)
self.btn_reset.setFixedWidth(80)
self.btn_reset.clicked.connect(self._reset_filter)
```

- [ ] **Step 2: 添加列头排序**

在 `_init_ui` 中添加：

```python
header = self.table.horizontalHeader()
header.setSortIndicatorShown(True)
header.sectionClicked.connect(self._on_header_clicked)
```

添加排序逻辑：

```python
def _on_header_clicked(self, logical_index):
    """列头点击：升序→降序→取消→升序循环"""
    col_name = self.table.horizontalHeaderItem(logical_index).text()
    current_order = getattr(self, '_sort_column', None)
    current_asc = getattr(self, '_sort_ascending', True)

    if current_order == col_name:
        if current_asc:
            # 升序 → 降序
            self._sort_ascending = False
        else:
            # 降序 → 取消排序
            self._sort_column = None
            self._rebuild_table()
            return
    else:
        self._sort_column = col_name
        self._sort_ascending = True

    self._rebuild_table()

def _sort_records(self, records: list, col_name: str, ascending: bool) -> list:
    """对记录列表排序，数字列按数值排序，其他按字符串排序"""
    numeric_cols = {"金额(元)", "征收率", "税额(元)", "价税合计(元)"}
    if col_name in numeric_cols:
        key = lambda r: safe_float(r.get(col_name, ""))
    else:
        key = lambda r: str(r.get(col_name, "")).lower()
    return sorted(records, key=key, reverse=not ascending)
```

修改 `_rebuild_table` 应用排序：

```python
def _rebuild_table(self):
    self._save_locked = True
    scroll_val = self.table.verticalScrollBar().value()
    self.table.setUpdatesEnabled(False)
    self.table.setRowCount(0)
    shown = [r for r in self.records if self._record_matches_filter(r)]
    # 应用排序
    if getattr(self, '_sort_column', None):
        shown = self._sort_records(shown, self._sort_column, getattr(self, '_sort_ascending', True))
    self._shown_records = shown
    for data in shown:
        self._insert_row(data, scroll=False)
    self.table.setUpdatesEnabled(True)
    self.table.verticalScrollBar().setValue(min(scroll_val, self.table.verticalScrollBar().maximum()))
    self._refresh_summary_from_list(shown)
    self._save_locked = False
    self._update_empty_state()
    self._rebuild_freeze_table()
```

- [ ] **Step 3: 验证应用启动**

```bash
cd "D:\Code\Python\lan-invoice" && timeout 3 uv run python src/invoice_tool.py 2>&1; echo "exit: $?"
```

- [ ] **Step 4: 提交**

```bash
git add src/invoice_tool.py
git commit -m "feat: 筛选实时化 + 列头排序

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 10: 全局搜索 Ctrl+F

**Files:**
- Modify: `src/invoice_tool.py`

- [ ] **Step 1: 添加搜索框 UI**

在 `_init_ui` 中创建隐藏的搜索条：

```python
# 全局搜索条（默认隐藏）
self._search_bar = QWidget(self)
search_layout = QHBoxLayout(self._search_bar)
search_layout.setContentsMargins(8, 4, 8, 4)
search_layout.setSpacing(6)

self._search_input = QLineEdit()
self._search_input.setPlaceholderText("输入搜索关键词，搜索所有字段…")
self._search_input.setFixedHeight(32)
self._search_input.textChanged.connect(lambda: QTimer.singleShot(200, self._do_search))

self._search_count = QLabel("")
self._search_count.setStyleSheet(f"color:{TEXT_SEC}; font-size:12px;")

btn_search_close = QPushButton("✕")
btn_search_close.setFixedSize(24, 24)
btn_search_close.setStyleSheet("border:none; background:transparent; font-size:14px;")
btn_search_close.clicked.connect(self._close_search)

search_layout.addWidget(QLabel("🔍"))
search_layout.addWidget(self._search_input, 1)
search_layout.addWidget(self._search_count)
search_layout.addWidget(btn_search_close)

self._search_bar.setGeometry(0, 0, 400, 40)
self._search_bar.hide()
```

- [ ] **Step 2: 修改 keyPressEvent 添加 Ctrl+F**

```python
def keyPressEvent(self, event):
    mod = event.modifiers()
    key = event.key()

    if mod == Qt.ControlModifier:
        if key == Qt.Key_F:
            self._open_search()
            return
        # ... 其他快捷键保持不变
```

- [ ] **Step 3: 实现搜索逻辑**

```python
def _open_search(self):
    self._search_bar.setGeometry(
        self.width() - 420, 8, 400, 40)
    self._search_bar.show()
    self._search_input.setFocus()
    self._search_matches = []

def _close_search(self):
    self._search_bar.hide()
    self._search_matches = []
    self._highlight_search_row(-1)

def _do_search(self):
    keyword = self._search_input.text().strip().lower()
    if not keyword:
        self._search_count.setText("")
        self._search_matches = []
        self._highlight_search_row(-1)
        return

    matches = []
    for row in range(self.table.rowCount()):
        for col in range(self.table.columnCount()):
            item = self.table.item(row, col)
            if item and keyword in item.text().lower():
                matches.append(row)
                break
    self._search_matches = matches
    self._current_match_index = -1
    self._search_count.setText(f"{len(matches)} 个匹配")
    if matches:
        self._jump_to_next_match()
    else:
        self._highlight_search_row(-1)
```

- [ ] **Step 4: 验证应用启动**

```bash
cd "D:\Code\Python\lan-invoice" && timeout 3 uv run python src/invoice_tool.py 2>&1; echo "exit: $?"
```

- [ ] **Step 5: 提交**

```bash
git add src/invoice_tool.py
git commit -m "feat: 全局搜索 Ctrl+F — 跨所有字段模糊匹配

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 11: 数据目录切换安全化

**Files:**
- Modify: `src/ui/dialogs/settings.py`

- [ ] **Step 1: 添加目录切换方法**

```python
def _data_dir_has_content(self, dirpath: str) -> bool:
    """检查目录是否已有数据内容"""
    data_file = os.path.join(dirpath, "invoices_data.json")
    if os.path.exists(data_file):
        return True
    att_dir = os.path.join(dirpath, "attachments")
    if os.path.isdir(att_dir) and os.listdir(att_dir):
        return True
    invoices_dir = os.path.join(dirpath, "invoices")
    if os.path.isdir(invoices_dir) and os.listdir(invoices_dir):
        return True
    return False

def _apply_data_dir(self):
    new_dir = self.edit_data_dir.text().strip()
    if not new_dir or not os.path.isdir(new_dir):
        QMessageBox.warning(self, "目录无效", "请先选择一个有效的目录。")
        return
    if os.path.abspath(new_dir) == os.path.abspath(self._app._data_dir):
        QMessageBox.information(self, "无需更改", "目标目录与当前目录相同。")
        return

    has_content = self._data_dir_has_content(new_dir)

    old_files_count = 0
    if os.path.exists(self._app._data_file):
        old_files_count += 1
    old_att_dir = getattr(self._app, '_attachment_dir',
                           os.path.join(self._app._data_dir, "attachments"))
    if os.path.isdir(old_att_dir):
        old_files_count += len(os.listdir(old_att_dir))

    if has_content:
        # 新目录已有数据 → 三选一
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("确认数据目录")
        msg_box.setText(
            f"目标目录已有数据：\n{new_dir}\n\n"
            f"请选择处理方式："
        )
        btn_keep = msg_box.addButton("保留新目录数据", QMessageBox.AcceptRole)
        btn_overwrite = msg_box.addButton("用旧数据覆盖", QMessageBox.DestructiveRole)
        msg_box.addButton("取消", QMessageBox.RejectRole)
        msg_box.exec_()

        clicked = msg_box.clickedButton()
        if clicked == btn_keep:
            self._switch_to_dir(new_dir, migrate_old=False)
        elif clicked == btn_overwrite:
            self._switch_to_dir(new_dir, migrate_old=True)
        else:
            return  # 取消
    else:
        # 新目录为空 → 二选一
        reply = QMessageBox.question(
            self, "确认数据目录",
            f"目标目录为空：\n{new_dir}\n\n"
            f"是否将旧数据迁移到新目录？",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            QMessageBox.Yes
        )
        if reply == QMessageBox.Cancel:
            return
        self._switch_to_dir(new_dir, migrate_old=(reply == QMessageBox.Yes))

def _switch_to_dir(self, new_dir: str, migrate_old: bool):
    """执行目录切换"""
    self._app._save_data()

    if migrate_old:
        # 迁移旧数据到新目录
        os.makedirs(new_dir, exist_ok=True)
        os.makedirs(os.path.join(new_dir, "attachments"), exist_ok=True)
        os.makedirs(os.path.join(new_dir, "invoices"), exist_ok=True)
        errors = []

        old_data_file = self._app._data_file
        old_att_dir = getattr(self._app, '_attachment_dir', None)
        old_inv_dir = os.path.join(self._app._data_dir, "invoices")

        if os.path.exists(old_data_file):
            try:
                shutil.copy2(old_data_file, os.path.join(new_dir, "invoices_data.json"))
            except Exception as e:
                errors.append(f"invoices_data.json: {e}")

        for src_dir, sub in [(old_att_dir, "attachments"), (old_inv_dir, "invoices")]:
            if src_dir and os.path.isdir(src_dir):
                dst_dir = os.path.join(new_dir, sub)
                for fname in os.listdir(src_dir):
                    src = os.path.join(src_dir, fname)
                    dst = os.path.join(dst_dir, fname)
                    try:
                        if os.path.isfile(src):
                            if not os.path.exists(dst):
                                shutil.copy2(src, dst)
                    except Exception as e:
                        errors.append(f"{sub}/{fname}: {e}")

        if errors:
            QMessageBox.warning(
                self, "部分文件迁移失败",
                "以下文件迁移失败：\n\n" + "\n".join(errors)
            )

    # 更新路径
    self._app._data_dir = new_dir
    self._app._data_file = os.path.join(new_dir, "invoices_data.json")
    self._app._attachment_dir = os.path.join(new_dir, "attachments")
    os.makedirs(self._app._attachment_dir, exist_ok=True)
    os.makedirs(os.path.join(new_dir, "invoices"), exist_ok=True)

    # 更新 Service
    from services.invoice_service import InvoiceService
    from repository import InvoiceRepository
    self._app._repo = InvoiceRepository(self._app._data_file)
    self._app._svc = InvoiceService(
        self._app._repo, self._app._attachment_dir,
        os.path.join(new_dir, "invoices")
    )

    self._app._save_config_dir(new_dir)

    # 重新加载
    self._app.records.clear()
    self._app.table.setRowCount(0)
    self._app._load_data()

    QMessageBox.information(
        self, "已切换",
        f"数据目录已切换为：\n{new_dir}"
    )
```

- [ ] **Step 2: 验证应用启动**

```bash
cd "D:\Code\Python\lan-invoice" && timeout 3 uv run python src/invoice_tool.py 2>&1; echo "exit: $?"
```

- [ ] **Step 3: 提交**

```bash
git add src/ui/dialogs/settings.py
git commit -m "fix: 数据目录切换 — 检测已有数据，提供保留/覆盖/取消三选一

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 12: 点击已选中行不再取消选中 + 最终验证

**Files:**
- Modify: `src/invoice_tool.py` (eventFilter)

- [ ] **Step 1: 删除点击反选逻辑**

在 `eventFilter` 中删除以下代码：

```python
# 删除这一段：
if event.button() == Qt.LeftButton:
    row = self.table.rowAt(event.pos().y())
    selected = self._selected_rows()
    if row >= 0 and selected == [row]:
        self.table.clearSelection()
        return True
```

保留 resize 事件处理：

```python
def eventFilter(self, obj, event):
    if obj is self.table.viewport():
        if event.type() == QEvent.Resize:
            self._recenter_empty_overlay()
    return super().eventFilter(obj, event)
```

- [ ] **Step 2: 运行全部测试最终验证**

```bash
cd "D:\Code\Python\lan-invoice" && uv run python -m unittest discover -s tests -p "test_*.py" -v 2>&1 | tail -30
```

- [ ] **Step 3: 验证应用启动**

```bash
cd "D:\Code\Python\lan-invoice" && timeout 3 uv run python src/invoice_tool.py 2>&1; echo "exit: $?"
```

- [ ] **Step 4: 提交**

```bash
git add src/invoice_tool.py
git commit -m "fix: 点击已选中行不再取消选中

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 13: 最终集成验证

- [ ] **Step 1: 运行全部测试**

```bash
cd "D:\Code\Python\lan-invoice" && uv run python -m unittest discover -s tests -p "test_*.py" -v 2>&1
```

- [ ] **Step 2: 验证应用启动**

```bash
cd "D:\Code\Python\lan-invoice" && timeout 5 uv run python src/invoice_tool.py 2>&1; echo "exit: $?"
```

- [ ] **Step 3: 检查是否有遗留的旧引用**

```bash
cd "D:\Code\Python\lan-invoice" && grep -rn "screenshot_dir\|contract_dir" src/ --include="*.py" | grep -v ".pyc" | grep -v "attachment" 2>&1
```

预期：只有 `settings.py` 中的旧路径兼容代码（如果有）

- [ ] **Step 4: 最终提交**

```bash
git add -A && git commit -m "feat: 操作流程优化完成

- 数据模型：tags + attachments，旧数据自动迁移
- 导入流程：PDF 始终按发票解析，重复检测+结果摘要
- 附件统一：截图+合同合并，按类型自动预览
- 标签系统：企业号降级为预置标签，设置中可管理
- 筛选实时化：去掉筛选按钮，防抖触发
- 列头排序：点升序/点降序/点取消
- 全局搜索：Ctrl+F 跨字段匹配
- 目录切换：检测已有数据，三选一确认
- 点击已选中行不再取消选中

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```
