# 发票归档工具 v4.0

一个基于 PyQt5 + pdfplumber 的电子发票 PDF 批量识别与归档工具。

## 🎯 功能特性

- ✅ **发票PDF识别**：自动解析电子发票PDF（增值税专用发票/普通发票/票通发票/全电发票）
- ✅ **提取字段**：购买方名称、纳税人识别号、销售方名称、金额、征收率、税额、价税合计、发票号码、开票日期
- ✅ **付款截图管理**：支持添加、查看、下载付款截图
- ✅ **合同附件管理**：支持关联合同文件（PDF/DOC/XLS等）
- ✅ **按月筛选**：支持按年份、月份筛选发票
- ✅ **发票类型筛选**：支持按发票类型筛选
- ✅ **销售方筛选**：支持按销售方名称筛选
- ✅ **企业号管理**：支持批量应用企业号到选中行
- ✅ **累计统计**：实时显示发票总数、金额合计、税额合计、价税合计
- ✅ **一键导出 Excel**：带格式、汇总行、支持按月拆分
- ✅ **双击查看**：双击行可查看发票PDF、付款截图、合同文件
- ✅ **数据持久化**：自动保存到本地 JSON 文件，重启后数据不丢失
- ✅ **便携版支持**：支持打包成单文件 EXE，可拷贝到 U 盘运行

## 📁 项目结构

```
20260425180357/
├── src/                    # 源代码目录
│   └── invoice_tool.py     # 主程序入口
├── tests/                  # 测试代码目录
│   ├── read_pdf.py         # PDF读取测试脚本
│   └── test_parse.py       # 发票解析测试脚本
├── scripts/                # 辅助脚本目录
│   ├── build_exe.bat       # 打包成 EXE 脚本
│   ├── create_shortcut.py  # 创建桌面快捷方式
│   └── 启动.bat            # 开发态启动脚本
├── data/                   # 数据目录（自动创建）
│   ├── invoices_data.json  # 发票数据文件
│   ├── screenshots/        # 付款截图存放目录
│   └── contracts/          # 合同文件存放目录
├── dist/                   # 打包输出目录
│   └── 发票归档工具.exe     # 可执行文件（打包后生成）
├── invoice_tool.spec       # PyInstaller 打包配置
├── requirements.txt        # 依赖清单
└── README.md               # 项目说明
```

## 🛠️ 环境要求

- Python 3.8+
- Windows 10/11（推荐）

## 📦 依赖安装

使用 uv 安装依赖：

```bash
uv pip install -r requirements.txt
```

或使用 pip：

```bash
pip install PyQt5>=5.15.0 pdfplumber>=0.9.0 openpyxl>=3.1.0
```

## 🚀 运行方式

### 开发态运行

```bash
# 方式1：运行启动脚本
scripts/启动.bat

# 方式2：直接运行
python src/invoice_tool.py
```

或在 PyCharm 中右键 `src/invoice_tool.py` → Run

### 便携版运行

```bash
# 先打包（首次）
scripts/build_exe.bat

# 运行打包后的程序
dist/发票归档工具.exe
```

## 📖 使用说明

### 基本操作

1. **导入发票**：点击「📂 导入发票PDF」或将 PDF 文件拖拽到窗口
2. **程序自动解析**：所有字段自动识别并显示在表格中
3. **查看详情**：双击表格行可查看发票PDF、付款截图、合同文件
4. **添加截图**：选中行后点击「📷 添加付款截图」或拖拽图片到窗口（按住 Alt 键）
5. **添加合同**：选中行后点击「📄 管理合同」或拖拽文件到窗口（按住 Shift 键）
6. **筛选功能**：使用顶部下拉框按年份、月份、发票类型筛选
7. **导出 Excel**：点击「📊 导出 Excel」保存汇总表

### 企业号管理

1. 在顶部「企业号」输入框填写企业号
2. 新导入的发票会自动带入该企业号
3. 选中已有发票行后，点击「应用到已选行」批量设置

### 数据目录

程序运行时会自动创建 `data/` 目录，包含：
- `invoices_data.json` - 发票数据（自动保存）
- `screenshots/` - 付款截图存放
- `contracts/` - 合同文件存放

## 📄 支持的发票类型

- 电子发票（增值税专用发票）
- 电子发票（普通发票）
- 票通电子发票
- 全电发票
- 其他含标准字段格式的 PDF 发票

## 📝 脚本说明

| 文件 | 说明 |
|------|------|
| `scripts/build_exe.bat` | 打包成单文件 EXE |
| `scripts/create_shortcut.py` | 创建桌面快捷方式 |
| `scripts/启动.bat` | 开发态启动程序 |
| `tests/test_parse.py` | 发票解析函数测试 |
| `tests/read_pdf.py` | PDF内容提取测试 |

## 🔧 打包说明

如需重新打包：

```bash
# 方式1：运行打包脚本
scripts/build_exe.bat

# 方式2：直接执行
uv run pyinstaller invoice_tool.spec --clean
```

打包输出位于 `dist/` 目录，可直接复制到其他电脑运行。

## 📞 注意事项

1. 首次运行时请确保程序有读写权限
2. 数据文件存放在 `data/` 目录，备份此目录即可备份所有数据
3. 如需迁移数据，复制 `data/` 目录到新位置即可
4. 建议定期备份 `data/invoices_data.json` 文件

---

**版本**：v4.0  
**技术栈**：PyQt5 + pdfplumber + openpyxl  
**平台**：Windows