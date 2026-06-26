# 发票归档

电子发票 PDF 批量识别与归档桌面应用。Python 3.12+ / PyQt5 / SQLite。

## 快速开始

```bash
uv pip install -r requirements.txt
uv run python src/invoice_tool.py
```

## 功能

- 拖入 PDF 自动识别发票号、日期、购买方、销售方、金额/税率/税额
- 标签系统：企业号、项目名称等自定义字段
- 附件管理：截图、合同等文件关联到发票
- 多维筛选：年月/发票类型/销售方/购买方/标签/全文搜索
- 一键导出 Excel（带格式、汇总行）
- 数据自动备份到多个硬盘分区（隐藏目录，防误删）
- Gitee 自动更新检查
- MCP Server：AI 客户端直接操作发票数据库

## MCP Server

发票工具提供 MCP stdio 接口，**Claude Code、Hermes 等 AI 客户端可直接控制**。

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

如果 `cwd` 路径不对，改成你的项目实际路径。打包后用 EXE 路径：

```json
{
  "mcpServers": {
    "invoice": {
      "command": "D:/path/发票归档.exe",
      "args": ["--mcp"]
    }
  }
}
```

### 可用工具

| 工具 | 说明 | 示例 |
|------|------|------|
| `search_invoices` | 多维度筛选、排序、分页 | "搜索 2025 年 1 月的增值税专用发票" |
| `import_invoice` | 导入 PDF 发票 | "导入 D:/发票/xxx.pdf，企业号 14786" |
| `export_excel` | 筛选后导出 Excel | "导出 2026 年 1 月发票到桌面" |
| `get_summary` | 统计摘要（金额/税额/类型分布） | "本月发票总金额多少" |
| `manage_tags` | 标签模板管理 | "添加标签'项目名称'" |
| `update_invoice` | 修改发票标签和备注 | "给发票号 1234 备注'已对账'" |
| `add_attachment` | 给发票添加附件 | "把 D:/截图/a.png 加到发票号 1234" |
| `delete_invoice` | 删除发票记录 | "删除发票号 1234" |
| `check_update` | 检查 Gitee 新版本 | "有新版本吗" |

### 使用示例（在 Claude Code 中）

```
> 搜索 2025 年全年的发票，按金额降序排列

> 把 D:\财务\1月\*.pdf 全部导入，企业号统一标 14786

> 导出一份包含所有增值税专用发票的 Excel，放桌面

> 给我 2026 年上半年（1-6月）的发票总金额和税额合计
```

AI 会自动匹配合适的工具调用，无需手动指定。

## 发布新版本

```bash
export GITEE_TOKEN=你的令牌
uv run python scripts/release.py
```

脚本自动：递增版本号 → 构建 EXE → 打 tag 并推送 → 创建 Gitee Release 并上传 EXE。

## 数据存储

- 主库：`%APPDATA%/lan-invoice/data/invoices.db`（SQLite WAL 模式）
- 备份：各分区根目录 `.lan-invoice-backup/data_TIMESTAMP/`（整个数据目录完整复制）
- MD5 去重：同内容附件只存一份
