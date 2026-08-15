# 发票归档

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

电子发票 PDF 批量识别与归档桌面应用。Python 3.12+ / PyQt5 / SQLite。

## 快速开始

```bash
uv pip install -r requirements.txt
uv run python src/invoice_tool.py
```

## 功能

### 发票管理
- 拖入 PDF 自动识别发票号、日期、购买方、销售方、金额/税率/税额
- 标签系统：企业号、项目名称等自定义字段
- 附件管理：截图、合同等文件关联到发票（悬停显示文件名列表）
- 导入前预览去重：解析后展示新/重复/失败，可勾选导入
- 多维筛选：年月/发票类型/销售方/购买方/标签/全文搜索
- 一键导出 Excel（带格式、汇总行）
- Gitee 自动更新检查

### 备份策略系统

设置对话框内独立配置两套备份策略，各有触发时机 + 保留规则：

| 策略 | 目标 | 触发时机 | 保留规则 |
|------|------|---------|---------|
| 本地多盘备份 | 所有固定硬盘隐藏目录 `.lan-invoice-backup` | 每次保存 / 定时 / 仅关闭 / 手动 | 最多 N 份 + 最少 N 份 + 保留 N 天 |
| WebDAV 远程同步 | 群晖、Nextcloud 等 | 每次保存 / 定时 / 仅关闭 / 手动 | 增量覆盖 / 保留最近 N 个版本 |

其他安全机制：
- 备份前自动 `PRAGMA optimize` 清理数据库碎片
- 退出时备份失败弹窗提醒
- 目录切换前自动 ZIP 快照（存于系统临时目录）
- 启动时 `PRAGMA integrity_check`，损坏则从备份自动恢复
- 状态栏可见：备份份数、覆盖分区数、最近时间、总大小

## MCP Server

发票工具提供 MCP **stdio** 接口（本地进程直连，经标准输入/输出通信），**Claude Code 等 AI 客户端可直接控制**。

> 传输方式说明：MCP 有两种传输——**stdio**（本程序采用，由 AI 客户端在本机启动进程，无需 URL/端口）和 **HTTP**（分 **SSE** 与 **Streamable HTTP** 两种，用于远程服务器，本程序不提供 HTTP MCP 端点）。以下配置均为 stdio 格式。

### 配置

项目根目录已有 `.mcp.json`，重启 AI 客户端即生效：

```json
{
  "mcpServers": {
    "invoice": {
      "command": "uv",
      "args": ["run", "python", "src/invoice_tool.py", "--mcp"],
      "cwd": "D:/Code/Python/lan-invoice"
    }
  }
}
```

打包后用 EXE 路径（安装版 EXE 为固定名 `lan-invoice.exe`，覆盖更新后路径不变，MCP 配置无需改动）：

```json
{
  "mcpServers": {
    "invoice": {
      "command": "C:/Program Files/lan-invoice/lan-invoice.exe",
      "args": ["--mcp"]
    }
  }
}
```

### 可用工具

| 工具 | 说明 |
|------|------|
| `search_invoices` | 多维度筛选、排序、分页 |
| `import_invoice` | 导入 PDF 发票，可附带标签和备注 |
| `export_excel` | 筛选后导出 Excel |
| `get_summary` | 统计摘要（金额/税额/类型分布） |
| `manage_tags` | 标签模板管理（增/删/查） |
| `update_invoice` | 修改发票标签和备注 |
| `add_attachment` | 给发票添加附件（截图、文档等） |
| `delete_invoice` | 删除发票记录及关联 PDF |
| `check_update` | 检查 Gitee 新版本 |

### 使用示例（在 Claude Code 中）

```
> 搜索 2025 年全年的发票，按金额降序排列

> 把 D:\财务\1月\*.pdf 全部导入，企业号统一标 14786

> 导出一份包含所有增值税专用发票的 Excel，放桌面

> 给我 2026 年上半年（1-6月）的发票总金额和税额合计
```

## HTTP API Server

零额外依赖的标准库 REST API：

```bash
uv run python src/invoice_tool.py --http --port 8080
```

端点：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1` | 服务信息 + 端点列表 |
| GET | `/api/v1/invoices?year=&type=&keyword=&sort_by=` | 搜索发票 |
| GET | `/api/v1/invoices/{invoice_no}` | 获取单条 |
| POST | `/api/v1/invoices/import` | 导入（JSON 或 multipart 上传） |
| PUT | `/api/v1/invoices/{invoice_no}` | 更新标签/备注 |
| DELETE | `/api/v1/invoices/{invoice_no}` | 删除发票 |
| GET | `/api/v1/summary?year=&month=` | 统计摘要 |
| GET | `/api/v1/tags` | 标签列表 |
| POST | `/api/v1/tags` | 添加标签 |
| DELETE | `/api/v1/tags/{tag_name}` | 删除标签 |
| GET | `/api/v1/export?year=&type=` | 导出 Excel |
| GET | `/api/v1/backup/status` | 备份统计 |

## 发布新版本

### 方式一：GitHub Actions（推荐，无需本地环境）

推送 `v*` 标签自动触发 `.github/workflows/build.yml`：

```bash
git push origin v5.6.3
```

双 job 并行构建：

- **build-installer**（主产物）：Nuitka standalone → Inno Setup 安装包。standalone 目录启动免解压（MCP 连接 0.2s、GUI 2s 内、杀毒零误报），安装版 EXE 固定名 `lan-invoice.exe`，覆盖更新后 MCP 配置无需改动。
- **build-portable**：PyInstaller 单文件便携版（单文件易分发，启动稍慢）。

> 注：两者均不支持交叉编译，必须在 Windows 环境打包（CI runner 原生 Windows）。

### 方式二：Docker 容器（本地，不依赖本机配置）

```bash
docker build -t lan-invoice-builder -f Dockerfile.build .
docker run --rm -v $PWD:/src -v $PWD/dist:/out lan-invoice-builder
```

Wine 交叉编译：Windows Python + PyInstaller + UPX + Inno Setup，产物输出到 `dist/`（仅便携版/旧式安装包，Nuitka 不支持 Wine 构建）。

### 方式三：本机一键打包（Windows）

```bash
build.bat        # Windows
bash build.sh    # Git Bash / macOS / Linux
```

本机构建 Nuitka standalone（约 1.5 小时，pymupdf C 扩展编译耗时）或 PyInstaller（排除 17 个未使用 Qt 模块 + UPX，约 105MB → 84MB）。

## 数据存储

- 主库：`%APPDATA%/lan-invoice/data/invoices.db`（SQLite WAL 模式）
- 配置：`%APPDATA%/lan-invoice/config.json`（备份策略、标签模板、数据目录路径）
- 备份：各分区根目录 `.lan-invoice-backup/data_TIMESTAMP/`（整个数据目录完整复制）
- 远程：WebDAV 增量同步（MD5 manifest 驱动，仅上传变更文件）

## 架构

```
GUI (invoice_tool.py) ──┐
MCP (mcp_server.py)    ──┼──> InvoiceService ──> Database + BackupService + ConfigManager
HTTP (http_server.py)  ──┘       业务层统一         存储抽象（InvoiceStorage Protocol）
```

## 开源协议

[MIT License](LICENSE) — 可自由使用、修改、商用，需保留版权声明。
