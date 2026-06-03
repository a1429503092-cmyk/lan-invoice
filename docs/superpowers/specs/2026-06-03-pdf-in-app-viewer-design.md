# PDF 软件内预览 — 设计规格

## 目标

用 pdfplumber 将 PDF 页面渲染为图片，在软件内置多页查看器中预览。默认图片渲染（轻量零新增依赖），保留「系统打开」按钮作为浏览器/外部程序备选。

## 技术方案

```
PdfViewerDialog (新)
├── pdfplumber.open(path) → pages[]
├── page.to_image(resolution=150) → PageImage → QPixmap
├── QScrollArea + QLabel 显示当前页
├── 导航栏：← → 翻页 + 页码 N/M + 缩放模式
└── 底部按钮：适应宽度 | 适应页面 | 100% | 系统打开 | 关闭
```

- **零新增依赖**：pdfplumber 已是项目依赖
- **延迟渲染**：打开对话框时才加载，不在缓存中保留所有页面
- **复用现有 UI 模式**：导航交互与 ImageViewerDialog 一致，暗色背景复用 DIALOG_QSS_DARK

## 新增文件

### `src/ui/dialogs/pdf_viewer.py` — PDF 内置预览对话框

**构造函数**：`PdfViewerDialog(pdf_path, parent=None)`

**交互**：

| 操作 | 实现 |
|------|------|
| 翻页 | ← → 按钮 + 键盘 ← → 键 |
| 首/末页 | 键盘 Home / End |
| 缩放 | Ctrl+滚轮；底部三个适应模式按钮 |
| 适应宽度 | 打开时默认；缩放至视口宽度，无水平滚动条 |
| 适应页面 | 整页缩放至视口内 |
| 100% | 实际像素显示 |
| 关闭 | Esc 键 + 关闭按钮 |
| 系统打开 | `os.startfile()` 回退到外部程序 |
| 多窗口 | 允许多个 PdfViewerDialog 同时存在，各自独立 |

### 修改文件

**`src/ui/dialogs/invoice_manager.py`**：
- 「打开」按钮 → 改调用 `PdfViewerDialog`（软件内预览）
- 新增「系统打开」按钮 → `os.startfile()` 回退
- 标题栏显示格式：`发票 PDF — {购买方名称} — № {发票号码}`

**`src/invoice_tool.py`**：
- `_set_invoice_pdf_cell` 的「查看」按钮行为不变 → 打开 `InvoiceManagerDialog`

## 边界处理

| 边界 | 处理 |
|------|------|
| 超大 PDF（50+ 页） | 仅渲染当前页，翻页时才加载下一页；不在内存缓存所有页面 |
| 损坏/加密 PDF | `pdfplumber.open()` 异常→提示「文件可能已损坏或加密」 |
| 密码保护 PDF | 弹密码输入框，用户输入密码后重试；取消→提示+提供「系统打开」逃生 |
| 单页 PDF | 隐藏翻页按钮和页码指示器 |
| 空文件/非 PDF | 友好提示，不崩溃 |
| 翻页边界 | 首页禁用 ←，末页禁用 → |
| 内存管理 | 翻页时 `setPixmap(None)` 释放上一页；关闭时释放当前页 |
| 文件被移动/删除 | 渲染前检查 `os.path.exists()`→不存在提示「文件已被移动或删除」 |
| DPI 自适应 | 默认 150 DPI；4K 屏检测系统缩放→ 2x 时用 300 DPI；小票 A5 以下用 200 DPI |
| 旋转页面 | 检测 `page.rotation` 自动旋转图片 |
| 横版发票 | 适应宽度优先，不截断 |
| 渲染超时 | 单页 > 30s 终止，显示「该页渲染超时，请用系统打开查看」 |
| CMYK 印章 | `to_image(antialias=True)` 保证红章不失真 |
| 渲染中关闭 | 取消当前页加载，不残留后台任务 |
| 页面渲染失败 | 该页显示错误提示，保留其他页的导航能力 |

## 快捷键

| 键 | 行为 |
|----|------|
| ← → | 翻页 |
| + - | 缩放 |
| Ctrl+滚轮 | 缩放 |
| Esc | 关闭 |
| Home | 首页 |
| End | 末页 |

## 与设计系统一致

- 导航按钮使用档案蓝 `ACCENT` 色
- 暗色背景复用 `DIALOG_QSS_DARK` tokens
- 微圆角 4px 按钮，扁平分层
- 手型光标（`findChildren` 循环统一设置）

## 不做（YAGNI）

- 全文搜索（UI 过重）
- 缩略图侧栏（发票通常 1-2 页）
- 导出当前页（已有「下载另存」按钮）
- 连续滚动模式（保持单页翻页简洁性）

## 测试策略

测试文件：`tests/test_pdf_viewer.py`（新增）

### 辅助

- 用 `reportlab` 或 `pypdf` 在测试中动态生成临时 PDF（单页/多页/横版/加密），不依赖外部测试数据
- `setUp`/`tearDown` 用 `tempfile.mkdtemp()` + `shutil.rmtree` 管理临时文件
- 对话框测试用 `_patch_qmessagebox()` mock QMessageBox 避免弹窗阻塞
- 所有对话框实例在断言后调用 `.close()` 释放资源

### 基础渲染（6 tests）

| # | 测试 | 断言 |
|---|------|------|
| 1 | 单页 PDF → 打开对话框 | 页码指示器隐藏；`btn_prev`/`btn_next` 不可见 |
| 2 | 3 页 PDF → 打开对话框 | 显示「1 / 3」；`btn_next` 可用、`btn_prev` 禁用 |
| 3 | 3 页 PDF → 翻到第 2 页 | 显示「2 / 3」；← → 均可用 |
| 4 | 3 页 PDF → 翻到第 3 页 | 显示「3 / 3」；`btn_next` 禁用、`btn_prev` 可用 |
| 5 | 文件路径不存在 | `QMessageBox.warning` 被调用；按钮禁用 |
| 6 | 损坏/非 PDF 文件 | 捕获异常→显示友好提示；不崩溃 |

### 键盘导航（4 tests）

| # | 测试 | 断言 |
|---|------|------|
| 7 | 按 `→` 键翻到下一页 | `current_page` 递增；页码更新 |
| 8 | 按 `←` 键翻到上一页 | `current_page` 递减；页码更新 |
| 9 | 第 1 页按 `←` | 无变化；不闪退 |
| 10 | 末页按 `→` | 无变化；`btn_next` 保持禁用 |

### 键盘按钮（3 tests）

| # | 测试 | 断言 |
|---|------|------|
| 11 | 按 `Esc` 关闭对话框 | `dlg.close()` / `reject()` 被触发 |
| 12 | 按 `Home` 跳首页 | `current_page == 0`；首页禁用 ← |
| 13 | 按 `End` 跳末页 | `current_page == len(pages)-1`；末页禁用 → |

### 缩放模式（4 tests）

| # | 测试 | 断言 |
|---|------|------|
| 14 | 默认模式 = 适应宽度 | `_zoom_mode == 'fit_width'` |
| 15 | 点击「适应页面」 | 图片缩放至视口内完全可见 |
| 16 | 点击「100%」 | 图片以原始分辨率显示 |
| 17 | 三种模式循环切换 | 每次切换后 `_zoom_mode` 值正确 |

### 内存管理（2 tests）

| # | 测试 | 断言 |
|---|------|------|
| 18 | 翻页后上一页 pixmap 释放 | `_page_pixmaps` 中仅保留当前页 ±1 页的缓存 |
| 19 | 对话框关闭后资源释放 | 关闭后引用计数为 0（可被 GC 回收） |

### 边界情况（7 tests）

| # | 测试 | 断言 |
|---|------|------|
| 20 | 横版 PDF（宽>高） | `page.rotation` 检测→自动旋转；适应宽度不截断 |
| 21 | 高 DPI 屏幕（2x 缩放） | `_render_dpi` 自动提升至 300；图片分辨率翻倍 |
| 22 | 单页 PDF 不显示页码 | `lbl_page` 隐藏；翻页按钮隐藏 |
| 23 | 密码保护 PDF | `pdfplumber.open()` 抛出 `PasswordError`→弹出密码输入框 |
| 24 | 密码错误 | 提示「密码错误」+ 可重试 + 可取消 |
| 25 | 密码取消 | 提示「需要密码才能查看」+ 「系统打开」按钮可用 |
| 26 | 红章 PDF（CMYK 色彩） | `to_image(antialias=True)` 渲染不失真；红色印章可见 |

### 异常恢复（3 tests）

| # | 测试 | 断言 |
|---|------|------|
| 27 | 单页渲染超时（mock > 30s） | 显示「该页渲染超时」+ 其他页仍可导航 |
| 28 | 文件在打开后被删除 | `os.path.exists()` 检查→提示「文件已被移动或删除」 |
| 29 | 渲染中点击关闭 | 后台渲染被取消；无残留 QThread |

### 多窗口（2 tests）

| # | 测试 | 断言 |
|---|------|------|
| 30 | 同时打开 2 个 PdfViewerDialog | 各自独立；窗口标题不同；互不干扰 |
| 31 | 一个关闭不影响另一个 | 另一个仍可正常翻页 |

### 集成测试 — InvoiceManagerDialog（4 tests）

| # | 测试 | 断言 |
|---|------|------|
| 32 | 「预览」按钮打开 PdfViewerDialog | `PdfViewerDialog` 被实例化（mock 验证） |
| 33 | 「系统打开」按钮调用 `os.startfile` | `os.startfile(path)` 被调用 |
| 34 | 标题栏格式正确 | 标题包含购买方名称 + 发票号码 |
| 35 | 文件不存在时按钮全部禁用 | 预览/系统打开/下载均为 `btn.setEnabled(False)` |

### 表格集成测试（2 tests）

| # | 测试 | 断言 |
|---|------|------|
| 36 | 双击表格行→打开 InvoiceManagerDialog | `_view_invoice_pdf` 被触发 |
| 37 | 「查看」按钮→打开 InvoiceManagerDialog | 同上 |
