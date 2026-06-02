# 界面自适应布局优化

## 问题

1. **表格列全固定宽度** — 16 列用 `setColumnWidth` 写死，窗口放大后右侧大片空白
2. **筛选栏控件全固定宽度** — 6 个下拉框/文本框通通 `setFixedWidth`，窗口缩小时溢出
3. **顶部工具栏控件固定宽度** — 企业号输入框 220px 写死，不随窗口变化

## 设计

### 表格列：智能分配

| 策略 | 列 | 理由 |
|------|-----|------|
| **Fixed**（固定） | 序号(45) 金额(88) 征收率(55) 税额(88) 价税合计(98) 付款截图(90) 合同(90) | 内容宽度固定，拉伸浪费 |
| **Stretch**（弹性） | 发票PDF(160→min) 发票类型(120→min) 购买方名称(150→min) 纳税人识别号(155→min) 销售方名称(150→min) 发票号码(135→min) 开票日期(100→min) 企业号(105→min) 备注(100→min) | 长文本需要更多空间，弹性列之间按比例分配剩余宽度 |

实现：`header.setSectionResizeMode(i, Fixed)` 用于固定列，`Stretch` 用于弹性列。固定列设初始宽度，弹性列设最小宽度（防止被压到看不见）。

### 筛选栏：弹性伸缩

- 所有 `setFixedWidth` → 改为 `setMinimumWidth` + 设置 stretch factor
- 购买方搜索框 `edit_buyer_search` stretch factor=2（优先拉伸）
- 企业号搜索框 `edit_company_search` stretch factor=2
- 销售方下拉框 stretch factor=1
- 发票类型下拉框 stretch factor=1
- 年份/月份保持 `setFixedWidth`（内容宽度确定，无需拉伸）
- 筛选标签保持固定宽度

### 顶部工具栏

- 企业号输入框 `edit_company`：`setFixedWidth(220)` → `setMinimumWidth(120)` + stretch factor=1
- 其余按钮保持固定宽度

### 窗口尺寸

- 最小尺寸保持 `1000x640`
- 默认尺寸保持 `1480x820`

## 涉及文件

- `src/invoice_tool.py` — `_init_ui()` 方法中的表格列宽设置 + 筛选栏控件 + 顶部工具栏控件

## 验证

1. 启动程序，窗口最大化 → 表格列应填满，弹性列等比拉伸，固定列宽度不变
2. 缩窄窗口到最小 1000px → 筛选栏不溢出，弹性列宽度合理缩小
3. 手动拖拽列边界 → 仍可手动调整
