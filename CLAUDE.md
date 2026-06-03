# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

发票归档工具 v4.0 — 基于 PyQt5 + pdfplumber 的电子发票 PDF 批量识别与归档桌面应用（Windows），单文件 `src/invoice_tool.py` 约 2700 行。

## 常用命令

```bash
# 运行主程序
uv run python src/invoice_tool.py

# 安装依赖
uv pip install -r requirements.txt

# 测试发票解析（独立运行，不启动 GUI）
uv run python tests/test_parse.py

# 测试 PDF 原始内容提取
uv run python tests/read_pdf.py

# 打包 EXE
uv run pyinstaller invoice_tool.spec --clean
```

没有 lint、格式化或测试套件配置。

## 核心架构

### 整体结构

```
src/invoice_tool.py    # 唯一源代码文件，包含所有逻辑
data/                  # 运行时自动创建，存放 JSON 数据/截图/合同
  invoices_data.json   # 持久化的发票记录列表
  screenshots/         # 付款截图副本
  contracts/           # 合同文件副本
  invoices/            # 导入的发票 PDF 副本
config.json            # 项目根目录，存储 data_dir 路径配置
```

### 代码分层（按 section 注释划分）

1. **`parse_invoice_pdf()`**（第 36-404 行）— 纯函数，用 pdfplumber 提取 PDF 文本，正则匹配发票号、日期、购买方、销售方、金额/税率/税额、发票类型、红票识别。返回 dict，字段见下表。
2. **`ParseWorker(QThread)`**（第 411-467 行）— 后台解析线程，批量调 `parse_invoice_pdf` + 复制 PDF 到 data/invoices/，通过信号 `result_ready`/`progress`/`finished` 与主线程通信。
3. **对话框组件** — `ImageViewerDialog`（截图预览）、`InvoiceManagerDialog`（PDF 查看/下载）、`ContractManagerDialog`（合同列表管理）、`SettingsDialog`（数据目录切换 + 便携版另存）、`DeleteConfirmDialog`（勾选框确认删除）。
4. **`InvoiceApp(QMainWindow)`**（第 1282-2696 行）— 主窗口，包含表格 UI、多维筛选、拖拽/粘贴、右键菜单、Excel 导出、数据持久化全部逻辑。

### 数据模型

每条发票记录是一个 dict，字段：

| 字段 | 说明 |
|------|------|
| `file` | PDF 文件名 |
| `pdf_path` | PDF 绝对路径（导入后变为 data/invoices/ 下的副本） |
| `company` | 企业号（从文件名 `数字-` 前缀或手动填入） |
| `invoice_type` | 发票类型（增值税专用发票/普通发票/票通发票等） |
| `buyer_name` / `buyer_tax_id` | 购买方名称/纳税人识别号 |
| `seller_name` | 销售方名称 |
| `amount` / `tax_rate` / `tax_amount` / `total` | 金额/征收率/税额/价税合计 |
| `invoice_no` / `invoice_date` | 发票号码/开票日期 |
| `is_red` | 红票标记（bool），红票金额存为负值 |
| `screenshots` | 截图路径 list |
| `contracts` | 合同路径 list |
| `remark` | 备注（默认"✓"，error 字段有值时显示错误） |

### 数据流

- **导入**：拖拽/打开文件 → `ParseWorker` 后台解析 → `result_ready` 信号追加到 `self.records` → 全部完成后 `_rebuild_table()` 一次性渲染 + `_save_data()` 写 JSON
- **加载**：启动时 `_load_data()` 读 JSON → 遍历插行到表格
- **编辑**：表格中企业号/备注列可编辑 → `cellChanged` 自动触发 `_save_data()`
- **筛选**：年月/发票类型/销售方下拉 + 购买方/企业号文本模糊搜索 → `_rebuild_table()` 按 `_record_matches_filter` 过滤重建

### UI 关键模式

- 表格使用 `setCellWidget` 嵌入自定义 widget（发票 PDF 列含"查看"按钮，截图/合同列含数量标签 + "查看"/"＋"按钮）
- 拖拽分三类：无选中行时 PDF → 导入发票，选中行 + 图片 → 添加截图，选中行 + 合同文件 → 添加合同
- Ctrl+V 粘贴从剪贴板取图片数据或文件路径，分类处理
- 右键菜单提供截图/合同的增删查操作 + 删除行（带双重确认对话框）
- 点击已选中行自动取消选中（viewport eventFilter）

## 依赖

- **PyQt5** ≥ 5.15 — GUI 框架
- **pdfplumber** ≥ 0.9.0 — PDF 文字/表格提取
- **openpyxl** ≥ 3.1.0 — Excel 读写
- Python ≥ 3.12（`pyproject.toml` 声明）
