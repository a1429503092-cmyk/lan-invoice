# 发票归档工具 — 便携版使用说明

## 📦 文件结构

```
发票归档工具/
├── invoice_tool.py      ← 主程序
├── 启动.bat             ← 启动脚本（双击运行）
├── requirements.txt     ← 依赖包列表
├── invoices_data.json   ← 数据文件（自动生成）
├── screenshots/         ← 付款截图（自动生成）
└── contracts/           ← 合同文件（自动生成）
```

## 🚀 安装与运行

### 方法一：使用系统 Python（推荐新手）

1. 安装 Python 3.9+（https://www.python.org/downloads/）
   - 安装时勾选 **"Add Python to PATH"**
2. 打开命令提示符，进入软件目录：
   ```
   cd /d 软件所在路径
   pip install -r requirements.txt
   ```
3. 双击 `启动.bat` 运行

### 方法二：便携 Python（U盘/免安装）

1. 下载 Python 官方 Embeddable 版（免安装）：
   - 访问 https://www.python.org/downloads/windows/
   - 选择 **Windows embeddable package (64-bit)**
2. 解压到软件目录下的 `python/` 文件夹：
   ```
   发票归档工具/
   └── python/
       ├── python.exe
       └── ...
   ```
3. 安装 pip（便携版默认无 pip）：
   ```
   python\python.exe -m ensurepip
   python\python.exe -m pip install PyQt5 pdfplumber openpyxl
   ```
4. 双击 `启动.bat` 即可运行，插入U盘后同样有效

## 💾 数据迁移

- 工具支持更换数据目录：点击主界面 **「⚙️ 设置」→「数据存储位置」**
- 也可使用 **「软件另存」** 功能，将整个软件和数据复制到新位置

## ⚠️ 注意事项

- 建议将整个软件文件夹一起复制，不要单独复制 `invoice_tool.py`
- 截图和合同文件保存在 `screenshots/` 和 `contracts/` 目录中，迁移时需一并复制
