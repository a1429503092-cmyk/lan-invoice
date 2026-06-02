# 界面自适应布局优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** 表格列智能分配（固定列+弹性列）、筛选栏控件弹性伸缩、顶部工具栏自适应

**Architecture:** 仅修改 `_init_ui()` 方法中的布局代码，不涉及任何逻辑变更

**Tech Stack:** PyQt5 QHeaderView stretch modes, QSizePolicy

---

### Task 1: 表格列宽智能分配

**Files:**
- Modify: `src/invoice_tool.py:368-373`

- [ ] **Step 1: 替换表格列宽设置**

将当前第 368-373 行：

```python
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        # 列宽：序号, 发票PDF, 发票类型, 购买方名称, 税号, 销售方名称, 金额, 税率, 税额, 合计, 发票号, 日期, 企业号, 截图, 合同, 备注
        col_widths = [45, 160, 120, 150, 155, 150, 88, 55, 88, 98, 135, 100, 105, 90, 90, 100]
        for i, w in enumerate(col_widths):
            self.table.setColumnWidth(i, w)
```

改为：

```python
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        # 固定列：序号(0) 金额(6) 征收率(7) 税额(8) 价税合计(9) 付款截图(13) 合同(14)
        # 单位均为像素
        fixed_cols = {
            0: 45,   # 序号
            6: 88,   # 金额(元)
            7: 55,   # 征收率
            8: 88,   # 税额(元)
            9: 98,   # 价税合计(元)
            13: 90,  # 付款截图
            14: 90,  # 合同
        }
        # 弹性列及最小宽度：发票PDF(1) 发票类型(2) 购买方名称(3) 税号(4)
        #   销售方名称(5) 发票号码(10) 开票日期(11) 企业号(12) 备注(15)
        stretch_cols = {
            1: 120,   # 发票PDF
            2: 100,   # 发票类型
            3: 130,   # 购买方名称
            4: 130,   # 纳税人识别号
            5: 130,   # 销售方名称
            10: 110,  # 发票号码
            11: 90,   # 开票日期
            12: 90,   # 企业号
            15: 80,   # 备注
        }
        for col, width in fixed_cols.items():
            header.setSectionResizeMode(col, QHeaderView.Fixed)
            self.table.setColumnWidth(col, width)
        for col, width in stretch_cols.items():
            header.setSectionResizeMode(col, QHeaderView.Stretch)
            self.table.setColumnWidth(col, width)  # 初始宽度，也作为 Stretch 模式下的权重参考
```

- [ ] **Step 2: 语法检查**

```bash
cd "D:\Code\Python\lan-invoice" && "C:\Users\ewy\AppData\Local\Programs\Python\Python312\python.exe" -c "import py_compile; py_compile.compile('src/invoice_tool.py', doraise=True); print('OK')"
```

- [ ] **Step 3: 启动验证**

```bash
cd "D:\Code\Python\lan-invoice" && uv run python src/invoice_tool.py 2>&1 &
sleep 4
```

期望：窗口正常打开，无报错

- [ ] **Step 4: 提交**

```bash
git add src/invoice_tool.py
git commit -m "$(cat <<'EOF'
feat: 表格列智能分配——固定列保持宽度，文本列弹性伸缩

7 个固定列（序号/金额/税率/税额/合计/截图/合同）保持像素宽度；
9 个弹性列（购买方/销售方/发票号/日期/企业号/备注等）按比例
分配剩余空间，窗口拉大时自动填满。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: 筛选栏控件弹性伸缩

**Files:**
- Modify: `src/invoice_tool.py:245-294`（筛选栏控件宽度设置）

- [ ] **Step 1: 替换筛选栏固定宽度为弹性策略**

将筛选栏中 6 个控件的 `setFixedWidth` 改为最小宽度 + stretch：

```python
        # 年份 — 保持固定（内容确定）
        self.combo_year.setFixedWidth(90)
        self.combo_year.setFixedHeight(30)
        self.combo_year.addItem("全部", None)

        # 月份 — 保持固定（内容确定）
        self.combo_month.setFixedWidth(80)
        self.combo_month.setFixedHeight(30)
        self.combo_month.addItem("全部", None)

        # 发票类型 — 弹性，最小宽度 100
        self.combo_inv_type.setMinimumWidth(100)
        self.combo_inv_type.setFixedHeight(30)
        self.combo_inv_type.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.combo_inv_type.addItem("全部", None)

        # 销售方名称 — 弹性，最小宽度 120
        self.combo_seller.setMinimumWidth(120)
        self.combo_seller.setFixedHeight(30)
        self.combo_seller.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.combo_seller.addItem("全部", None)

        # 购买方搜索 — 弹性，优先级高（stretch factor 会在 layout 中设置）
        self.edit_buyer_search.setMinimumWidth(120)
        self.edit_buyer_search.setFixedHeight(30)

        # 企业号搜索 — 弹性
        self.edit_company_search.setMinimumWidth(100)
        self.edit_company_search.setFixedHeight(30)
```

然后调整 `_build_filter_bar` 中添加 widget 的部分，对弹性控件设 stretch factor：

在 `filter_bar.addWidget(self.edit_buyer_search)` 之前：

查找现有的 addWidget 调用序列，给弹性控件加 stretch factor。具体是通过在 filter_bar 布局中调用 `setStretchFactor` 或使用 `addWidget(widget, stretch)`。

筛选栏控件添加顺序及 stretch factor：
```python
filter_bar.addWidget(lbl_filter)
filter_bar.addWidget(lbl_y)
filter_bar.addWidget(self.combo_year)
filter_bar.addWidget(lbl_m)
filter_bar.addWidget(self.combo_month)
filter_bar.addWidget(lbl_type)
filter_bar.addWidget(self.combo_inv_type, 1)       # stretch=1
filter_bar.addWidget(lbl_seller)
filter_bar.addWidget(self.combo_seller, 1)          # stretch=1
filter_bar.addWidget(lbl_buyer_search)
filter_bar.addWidget(self.edit_buyer_search, 2)     # stretch=2 优先
filter_bar.addWidget(lbl_company_search)
filter_bar.addWidget(self.edit_company_search, 2)   # stretch=2 优先
filter_bar.addWidget(self.btn_filter)
filter_bar.addWidget(self.btn_reset)
filter_bar.addWidget(self.lbl_filter_hint)
filter_bar.addStretch()
```

注意：需要将原来的 `filter_bar.addWidget(...)` 调用改为带 stretch 参数的版本。当前代码使用循环式的 `addWidget` 逐行调用，需要修改对应行的参数。

- [ ] **Step 2: 语法检查 + 启动验证**

同 Task 1。

- [ ] **Step 3: 提交**

```bash
git add src/invoice_tool.py
git commit -m "$(cat <<'EOF'
feat: 筛选栏控件弹性伸缩——搜索框优先拉伸

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: 顶部工具栏自适应

**Files:**
- Modify: `src/invoice_tool.py:217-220`（企业号输入框）

- [ ] **Step 1: 企业号输入框改为弹性**

```python
        lbl = QLabel("企业号（手动）：")
        lbl.setFixedWidth(110)
        self.edit_company = QLineEdit()
        self.edit_company.setPlaceholderText("输入后新导入发票自动填入")
        self.edit_company.setMinimumWidth(120)    # 替代 setFixedWidth(220)
        self.edit_company.setFixedHeight(32)
```

同时给布局中的 `edit_company` 设 stretch factor，在 `top_bar.addWidget(self.edit_company)` 改为 `top_bar.addWidget(self.edit_company, 1)`。

- [ ] **Step 2: 语法检查 + 启动验证**

同 Task 1。

- [ ] **Step 3: 提交**

```bash
git add src/invoice_tool.py
git commit -m "$(cat <<'EOF'
feat: 顶部工具栏企业号输入框自适应宽度

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

**Spec coverage:** 3 tasks cover 表格列/筛选栏/工具栏，全部在 spec 范围内。

**Placeholder scan:** 无 TBD/TODO，所有步骤含具体代码。

**Type consistency:** 单一文件修改，无跨任务依赖。
