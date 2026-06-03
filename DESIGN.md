---
name: 发票归档工具
description: 电子发票 PDF 批量识别与归档桌面应用，冷色系工具风格
colors:
  accent: "#2879D0"
  accent-light: "#E8F1FB"
  white: "#FFFFFF"
  bg: "#F2F4F6"
  bg-alt: "#F8F9FA"
  bg-hover: "#EBEEF1"
  bg-select: "#E3EDF7"
  border: "#CFD4DA"
  border-light: "#E0E3E7"
  text: "#1A2130"
  text-sec: "#5C6778"
  text-dim: "#8F99A8"
  red: "#DC2626"
  green: "#16A34A"
typography:
  body:
    fontFamily: "Microsoft YaHei, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Microsoft YaHei, sans-serif"
    fontSize: "11px"
    fontWeight: 400
    lineHeight: 1.4
  title:
    fontFamily: "Microsoft YaHei, sans-serif"
    fontSize: "15px"
    fontWeight: 700
    lineHeight: 1.3
  headline:
    fontFamily: "Microsoft YaHei, sans-serif"
    fontSize: "17px"
    fontWeight: 700
    lineHeight: 1.2
rounded:
  sm: "4px"
  md: "6px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "14px"
  lg: "20px"
components:
  button-primary:
    backgroundColor: "{colors.white}"
    textColor: "{colors.text}"
    rounded: "{rounded.sm}"
    padding: "5px 14px"
  button-primary-hover:
    backgroundColor: "{colors.bg-hover}"
  button-danger:
    backgroundColor: "{colors.red}"
    textColor: "{colors.white}"
    rounded: "{rounded.sm}"
    padding: "7px 22px"
  button-cancel:
    backgroundColor: "#F0F0F0"
    textColor: "#333333"
    rounded: "{rounded.sm}"
    padding: "7px 18px"
  input-text:
    backgroundColor: "{colors.white}"
    textColor: "{colors.text}"
    rounded: "0px"
    padding: "4px 8px"
  combobox:
    backgroundColor: "{colors.white}"
    textColor: "{colors.text}"
    rounded: "0px"
    padding: "3px 8px"
  table-header:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.white}"
    padding: "7px 8px"
  table-cell:
    backgroundColor: "{colors.white}"
    textColor: "{colors.text}"
    padding: "5px 8px"
  summary-frame:
    backgroundColor: "{colors.accent-light}"
    rounded: "0px"
    padding: "8px 12px"
---

# Design System: 发票归档工具

## 1. Overview

**Creative North Star: 「蓝印档案室」**

经典蓝 + 归档的秩序感。像档案室的金属柜，分类清晰、查找高效。冷色系底色承托数据表格，蓝色表头引导视线，克制到没有一个多余的像素。所有视觉元素服务于一个目标：让财务人员一眼看到需要的数字。

这是一个 **product** 型系统：设计服务于功能，信息密度高但不拥挤，操作路径短。在财务人员的日常工作流中，这个界面应该像 Excel 一样给人以"我能掌控数据"的信心。

**Key Characteristics:**
- 冷色工具感：冰蓝 `#2879D0` 作为唯一强调色，灰白梯度构建层次
- 锐利高效：微圆角 (4px) 按钮，清晰 1px 边框，即时响应无动画
- 扁平分层：通过色彩深浅区分层级，不用阴影
- 数据优先：表格是核心交互界面，表头深色吸睛，行交替色辅助扫描

## 2. Colors

冷色档案室调色板。一个经典蓝强调色，一套冷灰中性色，两个语义色（红/绿）。不设次要强调色——蓝色的稀缺性本身就是信息层级。

### Primary
- **档案蓝** (`#2879D0`): 表头背景、焦点边框、进度条填充。是页面上唯一的强调色，出现面积不超过任何界面的 10%。

### Neutral
- **白** (`#FFFFFF`): 表格单元格背景、输入框背景、按钮背景。内容区基底。
- **冷灰底** (`#F2F4F6`): 窗口背景。带极微量冷色倾向 (C≈0.005)，与纯灰区分。
- **浅灰交替** (`#F8F9FA`): 表格交替行背景，辅助长表扫描。
- **悬浮灰** (`#EBEEF1`): 按钮 hover、表格行 hover。比冷灰底稍深，可感知但不过度。
- **选中蓝底** (`#E3EDF7`): 表格选中行背景，是档案蓝的极淡版本，与表头蓝呼应。
- **边框灰** (`#CFD4DA`): 按钮边框、表格网格线。中明度，可见但不喧宾夺主。
- **浅边框** (`#E0E3E7`): 下拉箭头分隔线、进度条底色。比边框灰更轻。
- **正文墨色** (`#1A2130`): 正文文本色。极深蓝灰，不是纯黑 (`#000`)，在白色背景上对比度 ≥12:1。
- **次级灰文** (`#5C6778`): 辅助信息文字。对比度 ≥5.5:1，满足 WCAG AA。
- **三级灰文** (`#8F99A8`): 占位/禁用文字。对比度 ≥3.5:1，仅用于非关键信息。

### Semantic
- **警示红** (`#DC2626`): 删除按钮、错误提示、警告文字。使用克制——仅在需要用户停下来注意时出现。
- **通过绿** (`#16A34A`): 成功状态、完成标记。极少使用，仅在有明确"已完成/成功"语义时。

### Named Rules
**The One Accent Rule.** 档案蓝是唯一强调色。任何新颜色在加入系统前必须证明：不能复用档案蓝、不能用中性色表达、不是装饰。

**The No-Pure-Black Rule.** 正文色 `#1A2130` 替代 `#000`。在白色背景上足够深、足够清晰，但没有纯黑的刺目感。

## 3. Typography

**Font:** Microsoft YaHei（微软雅黑），Windows 系统原生中文字体，无外部依赖。中文笔画清晰，数字等宽感好，适合表格数据展示。

**Character:** 功能优先，不追求字体个性。单一字体通过字重和字号区分层级，避免多字体混排的视觉噪音。

### 层级
- **Headline** (700, 17px, 1.2): 窗口标题、主操作区标题。最大层级，仅用于页面级标题。
- **Title** (700, 15px, 1.3): 区域标题、对话框标题、汇总数值标签。次级强调。
- **Body** (400, 13px, 1.5): 表格内容、按钮文字、输入框文字、下拉选项。默认阅读字号。
- **Label** (400, 11px, 1.4): 辅助说明、版本号、统计标签。最小字号，绝不用于正文。

### Named Rules
**The Single Font Rule.** 全界面仅使用微软雅黑。通过字重 (400/600/700) 和字号 (11/13/15/17px) 建立层级，不引入第二字体。

**The Two-Weight Rule.** 仅使用 Regular (400) 和 Bold (700)。不使用 Light、Medium、Extra Bold 等中间字重。二元对比比多级灰度更清晰。

## 4. Elevation

**扁平分层系统。** 不使用阴影。层次通过背景色深浅区分：

- 窗口底色 `#F2F4F6` → 内容区白底 `#FFFFFF` → 表头蓝底 `#2879D0`
- 浅蓝底 `#E8F1FB` 标记汇总区域，从白底中浮出
- 1px 边框 `#CFD4DA` / `#E0E3E7` 划分区域边界

弹窗对话框使用原生窗口装饰（标题栏 + 边框），不叠加投影。这是桌面应用的标准行为，无需额外视觉提示。

### Named Rules
**The Flat-By-Default Rule.** 所有界面元素在静止状态下都是扁平的。不使用 `box-shadow`。深度感知通过色彩明度差和 1px 边框实现。

## 5. Components

所有组件共享 4px 圆角，1px 实线边框。交互反馈通过背景色变化实现，无过渡动画。

### Buttons

**Shape:** 微圆角 (4px)。足够软化边缘但不产生"圆角按钮"的玩具感。

- **Primary:** 白底 + 边框灰 `#CFD4DA` + 正文墨色文字。Hover 变为悬浮灰 `#EBEEF1`，边框加深为 `#8F99A8`。Pressed 变为 `#E0E3E7`。这是默认按钮风格，中立于强调色体系。
- **Danger:** 红底 `#DC2626` + 白字。唯一有实色背景的按钮变体，专门用于不可逆操作。Disabled 时灰底 `#AAAAAA` + 灰字。
- **Cancel:** 浅灰底 `#F0F0F0` + 深灰字。用于取消/返回操作，视觉回退次于 Primary。

### Inputs / Fields

**Style:** 直角 (0px 圆角)，白底 `#FFFFFF`，1px 边框 `#CFD4DA`，内边距 4px×8px。

- **Focus:** 边框变为档案蓝 `#2879D0`。不发光、不加阴影。边框变色是唯一的聚焦反馈。
- **Placeholder:** 三级灰文 `#8F99A8`，无额外样式。
- **Disabled:** 背景 `#F8F9FA`，文字 `#8F99A8`，边框 `#E0E3E7`。

### ComboBox / Dropdown

**Style:** 同 Input 的直角风格，内边距 3px×8px。右侧 18px 下拉箭头区，`#E0E3E7` 分隔线。

- **Hover:** 边框加深为 `#8F99A8`。
- **Dropdown list:** 白底，选中项使用选中蓝底 `#E3EDF7`，文字保持 `#1A2130`。

### Data Table

签名组件。整个应用的核心交互界面。

- **表头:** 档案蓝底 `#2879D0`，白色粗体字，内边距 7px×8px。列间有半透明白色分隔线。
- **单元格:** 白底 `#FFFFFF`，内边距 5px×8px，1px 网格线 `#E0E3E7`。
- **交替行:** 偶数行使用浅灰交替 `#F8F9FA`。
- **选中行:** 选中蓝底 `#E3EDF7`，文字保持墨色。
- **Hover 行:** 悬浮灰 `#EBEEF1`（未选中时）。

### Progress Bar

**Style:** 4px 高度，无边框，浅边框 `#E0E3E7` 底色，档案蓝 `#2879D0` 填充条。极简——只在导入发票时短暂出现。

### Summary Frame

**Style:** 浅蓝底 `#E8F1FB`，1px 边框 `#C5D4E8`，嵌入汇总统计标签。以色彩区分从表格白底区域中浮出，标记"这是汇总数据，不是行数据"。

## 6. Do's and Don'ts

### Do:
- **Do** 用档案蓝 `#2879D0` 作为唯一强调色，保持 ≤10% 面积占比
- **Do** 用 1px 边框 `#CFD4DA` 划分区域，清晰但不厚重
- **Do** 表头用深色蓝底白字，一眼定位列名
- **Do** 用交替行色 `#F8F9FA` 辅助长表横向扫描
- **Do** 按钮标签用行为动词（"确认删除" > "确定"；"取消" > "否"）
- **Do** 破坏性操作使用红底 `#DC2626` 按钮，与普通按钮形成明确视觉区分
- **Do** 保持直角输入框 (0px 圆角)，与工具类应用的严肃感一致

### Don't:
- **Don't** 使用渐变色。所有背景、按钮、表头均为纯色
- **Don't** 使用投影 (box-shadow)。层次通过色彩明度差表达
- **Don't** 使用圆角大于 6px。过度圆角产生"玩具感"，与 PRODUCT.md 的专业定位冲突
- **Don't** 引入第二个强调色。档案蓝的稀缺性就是它的力量
- **Don't** 在正文中使用 `#000000` 纯黑。用 `#1A2130` 替代
- **Don't** 过度花哨的装饰元素：无渐变文字、无毛玻璃效果、无大圆角卡片、无彩色左边框装饰
- **Don't** 在表格中使用大于 17px 的字体。数据密度优先于视觉舒适度
