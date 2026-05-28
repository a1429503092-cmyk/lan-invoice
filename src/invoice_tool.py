# -*- coding: utf-8 -*-
"""
发票归档 v4.0
功能：发票PDF识别、付款截图管理、合同附件管理、按月筛选、导出Excel
"""

import sys
import os
import re
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import pdfplumber
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QTableWidget, QTableWidgetItem,
    QFileDialog, QMessageBox, QHeaderView, QStatusBar, QFrame,
    QProgressBar, QAbstractItemView, QDialog, QScrollArea,
    QComboBox, QSizePolicy, QMenu, QAction, QListWidget, QListWidgetItem,
    QSplitter, QInputDialog, QCheckBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer, QMimeData, QUrl, QEvent
from PyQt5.QtGui import QColor, QPixmap, QDragEnterEvent, QDropEvent, QIcon


# ─────────────────────────────────────────────
#  发票解析核心
# ─────────────────────────────────────────────

def parse_invoice_pdf(pdf_path: str) -> dict:
    fname = os.path.basename(pdf_path)
    # 从文件名提取企业号：格式如 "14786-福建长富乳品有限公司.pdf"
    company_from_filename = ""
    m = re.match(r'^(\d+)-', fname)
    if m:
        company_from_filename = m.group(1)

    result = {
        "file": fname,
        "pdf_path": os.path.abspath(pdf_path),  # 保留原始PDF完整路径
        "company": company_from_filename,  # 从文件名提取企业号（如 14786-xxx.pdf）
        "invoice_type": "",   # 发票类型：增值税专用发票 / 票通发票 / 其他
        "buyer_name": "",
        "buyer_tax_id": "",
        "seller_name": "",    # 销售方名称
        "amount": "",
        "tax_rate": "",
        "tax_amount": "",
        "total": "",
        "invoice_no": "",
        "invoice_date": "",
        "screenshots": [],   # 付款截图路径列表
        "contracts": [],     # 合同文件路径列表
        "error": "",
        "is_red": False,     # 是否为红票（金额为负数则为红票）
    }
    try:
        with pdfplumber.open(pdf_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    full_text += t + "\n"
                # 也从表格提取，防止日期被截断或跨行
                try:
                    tables = page.extract_tables()
                    for table in tables:
                        for row in table:
                            if row:
                                full_text += " ".join(str(c) or "" for c in row) + "\n"
                except Exception:
                    pass

        if not full_text:
            result["error"] = "无法提取文字内容（可能是扫描件）"
            return result

        # ── 发票类型识别 ──────────────────────────
        # 第一优先：提取标题括号内容，如「电子发票（增值税专用发票）」「电子发票（普通发票）」
        # 括号支持全角（）和半角()，内含发票类型名称
        title_match = re.search(
            r'电子发票[（(]([^）)]+)[）)]',
            full_text[:500]
        )
        if title_match:
            inner = title_match.group(1).strip()
            # 直接使用括号内文字作为类型（如「增值税专用发票」「普通发票」）
            result["invoice_type"] = inner
        else:
            # 第二优先：全文关键词匹配（兼容老格式）
            type_patterns = [
                (r'增值税专用发票',  '增值税专用发票'),
                (r'票\s*通\s*发\s*票|票通电子发票', '票通发票'),
                (r'增值税普通发票',  '增值税普通发票'),
                (r'普通发票',        '普通发票'),
                (r'电子普通发票',    '电子普通发票'),
                (r'全电发票',        '全电发票'),
            ]
            for pattern, label in type_patterns:
                if re.search(pattern, full_text[:500]):
                    result["invoice_type"] = label
                    break
            if not result["invoice_type"]:
                for pattern, label in type_patterns:
                    if re.search(pattern, full_text):
                        result["invoice_type"] = label
                        break

        # ── 发票号码 ──────────────────────────────
        m = re.search(r'发票号码[：:]\s*(\d+)', full_text)
        if m:
            result["invoice_no"] = m.group(1)
        # 兜底：发票号码可能写成"发票代码：xxx 发票号码：xxx"或直接"号码："
        if not result["invoice_no"]:
            m = re.search(r'(?:发票)?号\s*码[：:]\s*(\d{8,})', full_text)
            if m:
                result["invoice_no"] = m.group(1)
        if not result["invoice_no"]:
            # 找全文中纯数字且长度>=8的长串（排除金额），作为发票号码
            for num in re.findall(r'\b(\d{10,20})\b', full_text):
                if num not in (result.get("invoice_no", ""),):
                    result["invoice_no"] = num
                    break

        # ── 开票日期 ──────────────────────────────
        def _norm_date(y, mo, d=None):
            """统一转换为 xxxx年xx月xx日；必须有日才返回"""
            mo = mo.zfill(2)
            if d:
                return f"{y}年{mo}月{d.zfill(2)}日"
            return None

        # 预处理：折叠多余空白，让跨行/跨空格日期变成连续格式
        # 注：\s 在 Python re 中匹配空格、Tab、换行，不需要写 \\s\\n
        _clean = re.sub(r'[\t ]+', ' ', full_text)     # 多余空格→单空格
        _clean = re.sub(r'\n+', ' ', _clean)           # 换行→空格
        _clean = re.sub(r'·+|──+', '', _clean)         # 去除 PDF 常见装饰字符

        # 优先：含"开票日期"关键字（最精确）
        for pat in [
            r'开票日期[：: ]*(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日',           # 2024年01月01日
            r'开票日期[：: ]*(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})',             # 2024-01-01 / 2024/01/01 / 2024.01.01
            r'开票日期[：: ]*(\d{4})(\d{2})(\d{2})(?!\d)',                     # 20240101 纯数字
        ]:
            if result["invoice_date"]:
                break
            m = re.search(pat, _clean)
            if m:
                d = _norm_date(m.group(1), m.group(2), m.group(3))
                if d:
                    result["invoice_date"] = d

        # 次优先：含"日期"关键字
        for pat in [
            r'日期[：: ]*(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日',
            r'日期[：: ]*(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})',
        ]:
            if result["invoice_date"]:
                break
            m = re.search(pat, _clean)
            if m:
                d = _norm_date(m.group(1), m.group(2), m.group(3))
                if d:
                    result["invoice_date"] = d

        # 最后兜底：全文找第一个完整的年月日日期（不加关键字限制）
        if not result["invoice_date"]:
            m = re.search(r'(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日', _clean)
            if m:
                result["invoice_date"] = _norm_date(m.group(1), m.group(2), m.group(3))
        if not result["invoice_date"]:
            m = re.search(r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})', _clean)
            if m:
                result["invoice_date"] = _norm_date(m.group(1), m.group(2), m.group(3))

        # ── 区域化解析：先尝试提取"购买方"和"销售方"整块区域 ──
        # 先提取购买方区域
        buyer_section = ""
        seller_section = ""
        m_buyer = re.search(r'(?:购买方|买方|购方)[\s\n:：信息]*(.+?)(?=销售方|销方|销\s*售|项目|$)', full_text, re.DOTALL)
        if m_buyer:
            buyer_section = m_buyer.group(1)
        m_seller = re.search(r'(?:销售方|销方)[\s\n:：信息]*(.+?)(?=备注|合\s*计|项\s*目|$)', full_text, re.DOTALL)
        if m_seller:
            seller_section = m_seller.group(1)

        # ── 购买方名称 ────────────────────────────
        # 模式1：标准"名称："匹配
        m = re.search(r'名称[：:]\s*(.+?)(?:\s+销\s|销\s*名称|统一社会|$)', full_text, re.MULTILINE)
        if m:
            result["buyer_name"] = m.group(1).strip()
        if result["buyer_name"]:
            result["buyer_name"] = re.split(r'\s+销\s*$|\s+销\s+名称', result["buyer_name"])[0].strip()
        # 模式2：从购买方区域提取名称
        if not result["buyer_name"] and buyer_section:
            m = re.search(r'名称[：:]\s*([^\n\r]+)', buyer_section)
            if m:
                result["buyer_name"] = m.group(1).strip()
        # 模式3：从购买方区域提取公司名
        if not result["buyer_name"] and buyer_section:
            m = re.search(r'([\u4e00-\u9fa5]{2,}(?:有限公司|有限责任公司|集团|股份|合作社)[\u4e00-\u9fa5]*)', buyer_section)
            if m:
                result["buyer_name"] = m.group(1).strip()
        # 模式4：找"购买方"或"买方"后面的公司名
        if not result["buyer_name"]:
            m = re.search(r'(?:购买方|买方|购方)[\s\n:：]*([^\n\r]{2,}(?:有限公司|有限责任公司|集团|股份|合作社)[^\n\r]*)', full_text)
            if m:
                result["buyer_name"] = m.group(1).strip()
        # 模式5：找第一个带"有限公司"/"公司"的长文本
        if not result["buyer_name"]:
            matches = re.findall(r'[\u4e00-\u9fa5]{2,}(?:有限公司|有限责任公司|集团|股份|合作社)[\u4e00-\u9fa5]*', full_text)
            if matches:
                for name in matches:
                    if name not in (result.get("seller_name", ""),):
                        result["buyer_name"] = name
                        break

        # ── 购买方税号 ────────────────────────────
        # 模式1：标准格式
        ids = re.findall(r'统一社会信用代码/纳税人识别号[：:]\s*([A-Z0-9]{15,20})', full_text)
        if ids:
            result["buyer_tax_id"] = ids[0]
        # 模式2：简化格式
        if not result["buyer_tax_id"]:
            m = re.search(r'(?:纳税人识别号|税号|识别号)[：:\s]*([A-Z0-9]{15,20})', full_text)
            if m:
                result["buyer_tax_id"] = m.group(1)
        # 模式3：从购买方区域提取
        if not result["buyer_tax_id"] and buyer_section:
            m = re.search(r'([A-Z0-9]{15,20})', buyer_section)
            if m:
                result["buyer_tax_id"] = m.group(1)
        # 模式4：在"购买方"附近抓
        if not result["buyer_tax_id"]:
            m = re.search(r'(?:购买方|买方|购方)[^纳]*?([A-Z0-9]{15,20})', full_text, re.DOTALL)
            if m:
                result["buyer_tax_id"] = m.group(1)

        # ── 销售方名称 ────────────────────────────
        # 模式1：找"销售方名称："
        m = re.search(r'销售方名称[：:]\s*([^\n\r]+)', full_text)
        if m:
            result["seller_name"] = m.group(1).strip()
        # 模式2：找"销方名称："或"销 名称："（带空格变体）
        if not result["seller_name"]:
            m = re.search(r'销\s*方\s*名称[：:]\s*([^\n\r]+)', full_text)
            if m:
                result["seller_name"] = m.group(1).strip()
        # 模式3：找"销 名 称："（分散字符）
        if not result["seller_name"]:
            m = re.search(r'销\s*名\s*称[：:]\s*([^\n\r]+)', full_text)
            if m:
                result["seller_name"] = m.group(1).strip()
        # 模式4：找"销货方："
        if not result["seller_name"]:
            m = re.search(r'销货方[：:]\s*([^\n\r]+)', full_text)
            if m:
                result["seller_name"] = m.group(1).strip()
        # 模式5：两个"名称："，第二个是销售方（购方在前，销方在后）
        if not result["seller_name"]:
            names = re.findall(r'名\s*称[：:]\s*([^\n\r]+)', full_text)
            if len(names) >= 2:
                result["seller_name"] = names[-1].strip()  # 取最后一个名称作为销售方
        # 模式6：找"销售方（名称）："格式
        if not result["seller_name"]:
            m = re.search(r'销售方\s*[（(]名称[）)]\s*[：:]\s*([^\n\r]+)', full_text)
            if m:
                result["seller_name"] = m.group(1).strip()
        # 模式7：从销售方区域提取名称
        if not result["seller_name"] and seller_section:
            m = re.search(r'名称[：:]\s*([^\n\r]+)', seller_section)
            if m:
                result["seller_name"] = m.group(1).strip()
        # 模式8：从销售方区域提取公司名
        if not result["seller_name"] and seller_section:
            m = re.search(r'([\u4e00-\u9fa5]{2,}(?:有限公司|有限责任公司|集团|股份|合作社)[\u4e00-\u9fa5]*)', seller_section)
            if m:
                result["seller_name"] = m.group(1).strip()
        # 模式9：找"销售"关键字后面的公司名
        if not result["seller_name"]:
            m = re.search(r'销\s*售[^名]*?([\u4e00-\u9fa5]{2,}(?:有限公司|有限责任公司|集团|股份)[\u4e00-\u9fa5]*)', full_text)
            if m:
                result["seller_name"] = m.group(1).strip()
        # 模式10：找"销售方"或"销方"后面直接跟的公司名（不经过"名称"）
        if not result["seller_name"]:
            m = re.search(r'(?:销售方|销方)[\s\n:：]*([^\n\r]{2,}(?:有限公司|有限责任公司|集团|股份|合作社)[^\n\r]*)', full_text)
            if m:
                result["seller_name"] = m.group(1).strip()
        # 模式11：如果文本中有两个以上公司名，取最后一个作为销售方
        if not result["seller_name"]:
            all_names = re.findall(r'[\u4e00-\u9fa5]{2,}(?:有限公司|有限责任公司|集团|股份|合作社)[\u4e00-\u9fa5]*', full_text)
            if all_names and len(all_names) >= 2:
                result["seller_name"] = all_names[-1]
            elif all_names and not result.get("buyer_name"):
                result["seller_name"] = all_names[-1]
        # 清理销售方名称：移除首尾空格和特殊字符，但保留中间空格
        if result["seller_name"]:
            result["seller_name"] = re.sub(r'^\s*[*●·、,，]\s*', '', result["seller_name"].strip())
            result["seller_name"] = re.sub(r'\s*[*●·、,，]\s*$', '', result["seller_name"])

        # ── 金额/税额 ─────────────────────────────
        # 辅助：提取带符号金额，返回 (绝对值字符串, 是否负数)
        def _signed(v):
            v = v.strip()
            neg = False
            if v.startswith('-'):
                neg = True; v = v[1:]
            elif v.startswith('(') and v.endswith(')'):
                neg = True; v = v[1:-1]
            return v.replace(',', ''), neg

        def _set(field, raw_val, is_neg):
            if not raw_val:
                return
            val, neg = _signed(raw_val)
            if val and not result[field]:
                result[field] = val
            if neg:
                result["is_red"] = True

        # 模式1：找"合计"行的金额和税额（支持负数）
        m = re.search(r'合\s*计\s+[¥￥]?(-?[\d,]+\.?\d*)\s+[¥￥]?(-?[\d,]+\.?\d*)', full_text)
        if m:
            _set("amount", m.group(1), '-' in m.group(1) or '(' in m.group(1))
            _set("tax_amount", m.group(2), '-' in m.group(2) or '(' in m.group(2))

        # 模式2：找税率和对应税额
        m = re.search(r'\*[^*]+\*[^\n]+?(\d+%)\s+(-?[\d,]+\.?\d*)', full_text)
        if m:
            result["tax_rate"] = m.group(1)
            if not result["tax_amount"]:
                _set("tax_amount", m.group(2), '-' in m.group(2) or '(' in m.group(2))
        else:
            m = re.search(r'(?<![年月日\d])(\d{1,2}%)', full_text)
            if m:
                result["tax_rate"] = m.group(1)

        # 模式3：找"小写"金额
        m = re.search(r'[（(]小写[)）]\s*[¥￥]?(-?[\d,]+\.?\d*)', full_text)
        if m:
            _set("total", m.group(1), '-' in m.group(1) or '(' in m.group(1))

        # 模式4：兜底找金额（匹配"数量×单价"行）
        if not result["amount"]:
            m = re.search(r'\*[^*]+\*[^\n]*?(-?[\d,]+\.\d{2})\s+(\d+%)\s+(-?[\d,]+\.\d{2})', full_text)
            if m:
                _set("amount", m.group(1), '-' in m.group(1) or '(' in m.group(1))
                if not result["tax_rate"]: result["tax_rate"] = m.group(2)
                _set("tax_amount", m.group(3), '-' in m.group(3) or '(' in m.group(3))

        # 模式5：找"价税合计"行
        if not result["total"]:
            m = re.search(r'价\s*税\s*合\s*计\s*[¥￥]?(-?[\d,]+\.?\d*)', full_text)
            if m:
                _set("total", m.group(1), '-' in m.group(1) or '(' in m.group(1))

        # 模式6：找金额行（从税率后面取金额）
        if not result["amount"]:
            m = re.search(r'(-?[\d,]+\.\d{2})\s+' + (result["tax_rate"] or r'\d+%'), full_text)
            if m:
                _set("amount", m.group(1), '-' in m.group(1) or '(' in m.group(1))

        # 模式7：从表格中提取金额（匹配"金额"关键字）
        if not result["amount"]:
            m = re.search(r'金\s*额\s*[：:]\s*[¥￥]?(-?[\d,]+\.?\d*)', full_text)
            if m:
                _set("amount", m.group(1), '-' in m.group(1) or '(' in m.group(1))

        # 模式8：从"税"关键字后面提取税额
        if not result["tax_amount"]:
            m = re.search(r'税\s*[：:]\s*[¥￥]?(-?[\d,]+\.?\d*)', full_text)
            if m:
                _set("tax_amount", m.group(1), '-' in m.group(1) or '(' in m.group(1))

        # 自动计算缺失值
        if result["amount"] and result["tax_rate"] and not result["tax_amount"]:
            try:
                rate = float(result["tax_rate"].replace('%', '')) / 100
                amount = float(result["amount"])
                result["tax_amount"] = str(abs(round(amount * rate, 2)))
            except:
                pass

        if result["amount"] and result["tax_amount"] and not result["total"]:
            try:
                result["total"] = str(abs(round(float(result["amount"]) + float(result["tax_amount"]), 2)))
            except:
                pass

        # ── 红票/蓝票识别（基于文本关键字）──────────
        if not result["is_red"]:
            if re.search(r'红字|红冲|作废|负数|负\s*额|冲\s*红', full_text):
                result["is_red"] = True

    except Exception as e:
        result["error"] = str(e)

    return result


# ─────────────────────────────────────────────
#  后台解析线程
# ─────────────────────────────────────────────

class ParseWorker(QThread):
    progress = pyqtSignal(int)
    result_ready = pyqtSignal(dict)
    finished = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self, files, data_dir: str = ""):
        super().__init__()
        self.files    = files
        self.data_dir = data_dir   # 目标目录；非空时在后台完成文件复制
        self._abort   = False

    def abort(self):
        self._abort = True

    def _copy_pdf(self, src: str) -> str:
        """在后台线程把 PDF 复制到 data_dir/invoices/，返回目标路径；失败返回原路径。"""
        if not self.data_dir or not src or not os.path.isfile(src):
            return src
        invoices_dir = os.path.join(self.data_dir, "invoices")
        os.makedirs(invoices_dir, exist_ok=True)
        fname     = os.path.basename(src)
        dest      = os.path.join(invoices_dir, fname)
        counter   = 1
        while os.path.exists(dest):
            name, ext = os.path.splitext(fname)
            dest = os.path.join(invoices_dir, f"{name}_{counter}{ext}")
            counter += 1
        try:
            shutil.copy2(src, dest)
            return dest
        except Exception:
            return src

    def run(self):
        total = len(self.files)
        for i, f in enumerate(self.files, 1):
            if self._abort:
                break
            try:
                data = parse_invoice_pdf(f)
                # 文件复制在后台完成，主线程槽无需做 IO
                data["pdf_path"] = self._copy_pdf(data.get("pdf_path", "") or f)
            except Exception as e:
                self.error_occurred.emit(f"解析 {os.path.basename(f)} 时出错: {str(e)}")
                data = {
                    "pdf_path": f,
                    "error": str(e),
                    "invoice_type": "", "buyer_name": "", "buyer_tax_id": "",
                    "seller_name": "", "amount": "", "tax_rate": "",
                    "tax_amount": "", "total": "", "invoice_no": "",
                    "invoice_date": "", "company": "",
                    "screenshots": [], "contracts": [], "remark": "", "is_red": False
                }
            self.result_ready.emit(data)
            self.progress.emit(int(i / total * 100))
        self.finished.emit()


# ─────────────────────────────────────────────
#  截图大图预览对话框
# ─────────────────────────────────────────────

class ImageViewerDialog(QDialog):
    def __init__(self, image_paths, current_index=0, parent=None):
        super().__init__(parent)
        self.image_paths = image_paths
        self.current_index = current_index
        self.setWindowTitle("付款截图预览")
        self.resize(900, 700)
        self.setMinimumSize(400, 300)
        self._build_ui()
        self._show_image()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.scroll = QScrollArea()
        self.scroll.setAlignment(Qt.AlignCenter)
        self.scroll.setStyleSheet("QScrollArea { background:#2b2b2b; border:none; }")
        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignCenter)
        self.img_label.setStyleSheet("background:#2b2b2b;")
        self.scroll.setWidget(self.img_label)
        self.scroll.setWidgetResizable(True)
        layout.addWidget(self.scroll)

        nav = QHBoxLayout()
        nav.setSpacing(8)

        self.btn_prev = QPushButton("◀ 上一张")
        self.btn_prev.setFixedHeight(32)
        self.btn_prev.clicked.connect(self._prev)

        self.lbl_index = QLabel()
        self.lbl_index.setAlignment(Qt.AlignCenter)
        self.lbl_index.setStyleSheet("color:#eee; font-size:13px; background:transparent;")

        self.btn_next = QPushButton("下一张 ▶")
        self.btn_next.setFixedHeight(32)
        self.btn_next.clicked.connect(self._next)

        self.btn_save = QPushButton("💾 下载当前截图")
        self.btn_save.setFixedHeight(32)
        self.btn_save.setStyleSheet(
            "background:#1E6FBF; color:white; font-weight:bold; border-radius:4px; padding:0 12px;")
        self.btn_save.clicked.connect(self._save_current)

        self.btn_save_all = QPushButton("📦 下载全部截图")
        self.btn_save_all.setFixedHeight(32)
        self.btn_save_all.setStyleSheet(
            "background:#2E8B57; color:white; font-weight:bold; border-radius:4px; padding:0 12px;")
        self.btn_save_all.clicked.connect(self._save_all)

        nav.addWidget(self.btn_prev)
        nav.addStretch()
        nav.addWidget(self.lbl_index)
        nav.addStretch()
        nav.addWidget(self.btn_next)
        nav.addSpacing(20)
        nav.addWidget(self.btn_save)
        nav.addWidget(self.btn_save_all)
        layout.addLayout(nav)

        self.setStyleSheet("""
            QDialog { background:#1e1e1e; }
            QPushButton {
                border:1px solid #555; border-radius:4px;
                padding:4px 14px; background:#3a3a3a; color:#eee; font-size:13px;
            }
            QPushButton:hover { background:#4a4a4a; }
        """)

    def _show_image(self):
        if not self.image_paths:
            self.img_label.setText("暂无截图")
            return
        path = self.image_paths[self.current_index]
        if os.path.exists(path):
            pix = QPixmap(path)
            max_w = max(self.scroll.width() - 20, 100)
            max_h = max(self.scroll.height() - 20, 100)
            if pix.width() > max_w or pix.height() > max_h:
                pix = pix.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.img_label.setPixmap(pix)
        else:
            self.img_label.setText(f"图片文件不存在：\n{path}")

        n = len(self.image_paths)
        self.lbl_index.setText(f"{self.current_index + 1} / {n}")
        self.btn_prev.setEnabled(self.current_index > 0)
        self.btn_next.setEnabled(self.current_index < n - 1)
        self.btn_save_all.setVisible(n > 1)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._show_image()

    def _prev(self):
        if self.current_index > 0:
            self.current_index -= 1
            self._show_image()

    def _next(self):
        if self.current_index < len(self.image_paths) - 1:
            self.current_index += 1
            self._show_image()

    def _save_current(self):
        if not self.image_paths:
            return
        src = self.image_paths[self.current_index]
        if not os.path.exists(src):
            QMessageBox.warning(self, "错误", f"文件不存在：{src}")
            return
        ext = os.path.splitext(src)[1] or ".png"
        dst, _ = QFileDialog.getSaveFileName(
            self, "保存截图", os.path.basename(src),
            f"图片文件 (*{ext});;所有文件 (*)"
        )
        if dst:
            shutil.copy2(src, dst)
            QMessageBox.information(self, "保存成功", f"截图已保存到：\n{dst}")

    def _save_all(self):
        if not self.image_paths:
            return
        dst_dir = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if not dst_dir:
            return
        saved = 0
        for src in self.image_paths:
            if os.path.exists(src):
                dst = os.path.join(dst_dir, os.path.basename(src))
                if os.path.exists(dst):
                    base, ext = os.path.splitext(os.path.basename(src))
                    dst = os.path.join(dst_dir, f"{base}_{datetime.now().strftime('%H%M%S%f')}{ext}")
                shutil.copy2(src, dst)
                saved += 1
        QMessageBox.information(self, "保存成功", f"已保存 {saved} 张截图到：\n{dst_dir}")


# ─────────────────────────────────────────────
#  发票 PDF 查看/下载对话框
# ─────────────────────────────────────────────

class InvoiceManagerDialog(QDialog):
    """发票 PDF 查看与下载对话框（仿合同管理）"""

    def __init__(self, pdf_path: str, rec_name: str = "", parent=None):
        super().__init__(parent)
        self.pdf_path = pdf_path
        self.rec_name = rec_name
        title = f"发票PDF — {rec_name}" if rec_name else "发票PDF"
        self.setWindowTitle(title)
        self.resize(520, 200)
        self.setMinimumSize(380, 160)
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        lbl_title = QLabel("📄 发票原始 PDF 文件")
        lbl_title.setStyleSheet("font-size:13px; font-weight:bold; color:#333;")
        layout.addWidget(lbl_title)

        # 文件信息展示
        self.lbl_path = QLabel()
        self.lbl_path.setWordWrap(True)
        self.lbl_path.setStyleSheet(
            "font-size:12px; color:#555; background:#F5F8FC; "
            "border:1px solid #D0DCF0; border-radius:4px; padding:6px 8px;"
        )
        layout.addWidget(self.lbl_path)

        # 按钮行
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(8)

        self.btn_open = QPushButton("📂 打开")
        self.btn_open.setFixedHeight(32)
        self.btn_open.clicked.connect(self._open_pdf)

        self.btn_download = QPushButton("💾 下载另存")
        self.btn_download.setFixedHeight(32)
        self.btn_download.clicked.connect(self._download_pdf)

        self.btn_close = QPushButton("关闭")
        self.btn_close.setFixedHeight(32)
        self.btn_close.clicked.connect(self.accept)

        btn_bar.addWidget(self.btn_open)
        btn_bar.addWidget(self.btn_download)
        btn_bar.addStretch()
        btn_bar.addWidget(self.btn_close)
        layout.addLayout(btn_bar)

        self.setStyleSheet("""
            QDialog { background:#F5F8FC; }
            QPushButton {
                border:1px solid #B0C4DE; border-radius:4px;
                padding:4px 14px; background:#FFFFFF; font-size:13px;
            }
            QPushButton:hover { background:#E8F0FE; border-color:#1E6FBF; }
        """)

    def _refresh(self):
        if self.pdf_path and os.path.exists(self.pdf_path):
            size_kb = os.path.getsize(self.pdf_path) / 1024
            size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.2f} MB"
            self.lbl_path.setText(
                f"<b>{os.path.basename(self.pdf_path)}</b><br>"
                f"<span style='color:#888;'>{self.pdf_path}</span><br>"
                f"<span style='color:#1E6FBF;'>文件大小：{size_str}</span>"
            )
            self.btn_open.setEnabled(True)
            self.btn_download.setEnabled(True)
        else:
            self.lbl_path.setText(
                f"<span style='color:#CC0000;'>⚠️ 文件不存在或路径未记录</span><br>"
                f"<span style='color:#aaa;'>{self.pdf_path or '（无路径信息）'}</span>"
            )
            self.btn_open.setEnabled(False)
            self.btn_download.setEnabled(False)

    def _open_pdf(self):
        if not os.path.exists(self.pdf_path):
            QMessageBox.warning(self, "文件不存在", f"找不到文件：\n{self.pdf_path}")
            return
        try:
            os.startfile(self.pdf_path)
        except Exception as e:
            QMessageBox.warning(self, "打开失败", f"无法打开文件：\n{e}")

    def _download_pdf(self):
        if not os.path.exists(self.pdf_path):
            QMessageBox.warning(self, "文件不存在", f"找不到文件：\n{self.pdf_path}")
            return
        dst, _ = QFileDialog.getSaveFileName(
            self, "另存发票PDF", os.path.basename(self.pdf_path),
            "PDF 文件 (*.pdf);;所有文件 (*)"
        )
        if dst:
            shutil.copy2(self.pdf_path, dst)
            QMessageBox.information(self, "下载成功", f"发票PDF已保存到：\n{dst}")


# ─────────────────────────────────────────────
#  合同管理对话框
# ─────────────────────────────────────────────

class ContractManagerDialog(QDialog):
    """合同列表管理对话框：查看、下载、打开合同"""

    def __init__(self, contract_paths, rec_name="", parent=None):
        super().__init__(parent)
        self.contract_paths = list(contract_paths)  # 副本，不直接改原列表
        self.rec_name = rec_name
        self.setWindowTitle(f"合同管理 — {rec_name}" if rec_name else "合同管理")
        self.resize(600, 420)
        self.setMinimumSize(400, 300)
        self._build_ui()
        self._refresh_list()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        lbl = QLabel("📄 合同文件列表（双击打开）")
        lbl.setStyleSheet("font-size:13px; font-weight:bold; color:#333;")
        layout.addWidget(lbl)

        self.list_widget = QListWidget()
        self.list_widget.setAlternatingRowColors(True)
        self.list_widget.setStyleSheet("""
            QListWidget { font-size:13px; border:1px solid #ccc; border-radius:4px; }
            QListWidget::item { padding:6px 8px; }
            QListWidget::item:selected { background:#BDD7EE; color:#000; }
            QListWidget::item:alternate { background:#F5F8FC; }
        """)
        self.list_widget.itemDoubleClicked.connect(self._open_selected)
        # 选中项变化时同步更新按钮可用状态
        self.list_widget.currentItemChanged.connect(lambda *_: self._update_btn_state())
        layout.addWidget(self.list_widget)

        # 底部按钮行
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(8)

        self.btn_open = QPushButton("📂 打开")
        self.btn_open.setFixedHeight(32)
        self.btn_open.clicked.connect(self._open_selected)

        self.btn_download = QPushButton("💾 下载另存")
        self.btn_download.setFixedHeight(32)
        self.btn_download.clicked.connect(self._download_selected)

        self.btn_del = QPushButton("🗑 移除")
        self.btn_del.setFixedHeight(32)
        self.btn_del.setStyleSheet("color:#CC0000;")
        self.btn_del.clicked.connect(self._remove_selected)

        self.btn_close = QPushButton("关闭")
        self.btn_close.setFixedHeight(32)
        self.btn_close.clicked.connect(self.accept)

        btn_bar.addWidget(self.btn_open)
        btn_bar.addWidget(self.btn_download)
        btn_bar.addWidget(self.btn_del)
        btn_bar.addStretch()
        btn_bar.addWidget(self.btn_close)
        layout.addLayout(btn_bar)

        hint = QLabel("提示：支持 PDF 和 Word（.docx/.doc）格式，用系统默认程序打开")
        hint.setStyleSheet("color:#888; font-size:11px;")
        layout.addWidget(hint)

        self.setStyleSheet("""
            QDialog { background:#F5F8FC; }
            QPushButton {
                border:1px solid #B0C4DE; border-radius:4px;
                padding:4px 14px; background:#FFFFFF; font-size:13px;
            }
            QPushButton:hover { background:#E8F0FE; border-color:#1E6FBF; }
        """)

    def _refresh_list(self):
        self.list_widget.clear()
        for path in self.contract_paths:
            fname = os.path.basename(path)
            exists = os.path.exists(path)
            item = QListWidgetItem()
            ext = os.path.splitext(fname)[1].lower()
            if ext == ".pdf":
                icon_txt = "📄"
            elif ext in (".docx", ".doc"):
                icon_txt = "📝"
            else:
                icon_txt = "📎"
            status = "" if exists else "  ⚠️ 文件已移动"
            item.setText(f"  {icon_txt}  {fname}{status}")
            item.setData(Qt.UserRole, path)
            if not exists:
                item.setForeground(QColor("#CC0000"))
            self.list_widget.addItem(item)
        # 有条目时自动选中第一项，确保按钮默认可用
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)
        self._update_btn_state()

    def _update_btn_state(self):
        has_sel = self.list_widget.currentRow() >= 0
        self.btn_open.setEnabled(has_sel)
        self.btn_download.setEnabled(has_sel)
        self.btn_del.setEnabled(has_sel)

    def _get_selected_path(self):
        item = self.list_widget.currentItem()
        if item:
            return item.data(Qt.UserRole)
        return None

    def _open_selected(self):
        path = self._get_selected_path()
        if not path:
            return
        if not os.path.exists(path):
            QMessageBox.warning(self, "文件不存在", f"找不到文件：\n{path}")
            return
        try:
            os.startfile(path)
        except Exception as e:
            QMessageBox.warning(self, "打开失败", f"无法打开文件：\n{e}")

    def _download_selected(self):
        path = self._get_selected_path()
        if not path:
            return
        if not os.path.exists(path):
            QMessageBox.warning(self, "文件不存在", f"找不到文件：\n{path}")
            return
        ext = os.path.splitext(path)[1]
        dst, _ = QFileDialog.getSaveFileName(
            self, "另存合同文件", os.path.basename(path),
            f"文件 (*{ext});;所有文件 (*)"
        )
        if dst:
            shutil.copy2(path, dst)
            QMessageBox.information(self, "下载成功", f"合同已保存到：\n{dst}")

    def _remove_selected(self):
        row = self.list_widget.currentRow()
        if row < 0:
            return
        fname = os.path.basename(self.contract_paths[row])
        reply = QMessageBox.question(
            self, "确认移除",
            f"确认从列表中移除「{fname}」？\n（文件本身不会被删除）",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.contract_paths.pop(row)
            self._refresh_list()


# ─────────────────────────────────────────────
#  设置对话框
# ─────────────────────────────────────────────

class SettingsDialog(QDialog):
    """设置对话框：数据目录配置 + 软件另存"""

    def __init__(self, app_ref, parent=None):
        super().__init__(parent)
        self._app = app_ref  # InvoiceApp 实例
        self.setWindowTitle("⚙️ 设置")
        self.resize(560, 320)
        self.setMinimumSize(480, 280)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        # ── 标题 ──────────────────────────────────
        lbl_title = QLabel("⚙️ 软件设置")
        lbl_title.setStyleSheet("font-size:15px; font-weight:bold; color:#1E6FBF;")
        layout.addWidget(lbl_title)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#D0DCF0;")
        layout.addWidget(sep)

        # ── 1. 数据目录设置 ───────────────────────
        grp_data = QFrame()
        grp_data.setStyleSheet(
            "QFrame { background:#F0F7FF; border:1px solid #B8D4F0; border-radius:6px; }")
        data_layout = QVBoxLayout(grp_data)
        data_layout.setContentsMargins(14, 10, 14, 10)
        data_layout.setSpacing(8)

        lbl_data_title = QLabel("📁  数据存储位置")
        lbl_data_title.setStyleSheet("font-size:13px; font-weight:bold; color:#333;")
        data_layout.addWidget(lbl_data_title)

        lbl_hint = QLabel("软件的数据文件（JSON）、截图、合同将保存在此目录下。\n"
                          "⚠️ 更改目录后，旧目录中的文件不会自动迁移，请手动复制。")
        lbl_hint.setStyleSheet("font-size:11px; color:#777;")
        lbl_hint.setWordWrap(True)
        data_layout.addWidget(lbl_hint)

        row_dir = QHBoxLayout()
        row_dir.setSpacing(6)
        self.edit_data_dir = QLineEdit(self._app._data_dir)
        self.edit_data_dir.setReadOnly(True)
        self.edit_data_dir.setFixedHeight(30)
        self.edit_data_dir.setStyleSheet(
            "background:#fff; border:1px solid #B0C4DE; border-radius:4px; padding:2px 6px;")
        btn_browse = QPushButton("浏览…")
        btn_browse.setFixedHeight(30)
        btn_browse.setFixedWidth(70)
        btn_browse.clicked.connect(self._browse_data_dir)
        row_dir.addWidget(self.edit_data_dir, 1)
        row_dir.addWidget(btn_browse)
        data_layout.addLayout(row_dir)

        btn_apply_dir = QPushButton("✅ 应用新目录")
        btn_apply_dir.setFixedHeight(32)
        btn_apply_dir.setStyleSheet(
            "background:#1E6FBF; color:white; font-weight:bold; border-radius:4px;")
        btn_apply_dir.clicked.connect(self._apply_data_dir)
        data_layout.addWidget(btn_apply_dir)

        layout.addWidget(grp_data)

        # ── 2. 软件另存 ───────────────────────────
        grp_save = QFrame()
        grp_save.setStyleSheet(
            "QFrame { background:#F0FFF4; border:1px solid #A8D8B0; border-radius:6px; }")
        save_layout = QVBoxLayout(grp_save)
        save_layout.setContentsMargins(14, 10, 14, 10)
        save_layout.setSpacing(6)

        lbl_save_title = QLabel("💾  软件另存（制作便携版）")
        lbl_save_title.setStyleSheet("font-size:13px; font-weight:bold; color:#2E7D32;")
        save_layout.addWidget(lbl_save_title)

        lbl_save_hint = QLabel(
            "将软件主程序（invoice_tool.py）及当前所有数据（JSON、截图、合同）\n"
            "复制到您选择的目标文件夹，复制后直接运行即可，无需重新安装。"
        )
        lbl_save_hint.setStyleSheet("font-size:11px; color:#777;")
        lbl_save_hint.setWordWrap(True)
        save_layout.addWidget(lbl_save_hint)

        btn_saveas = QPushButton("📂 选择目标位置并另存软件")
        btn_saveas.setFixedHeight(32)
        btn_saveas.setStyleSheet(
            "background:#2E7D32; color:white; font-weight:bold; border-radius:4px;")
        btn_saveas.clicked.connect(self._saveas_software)
        save_layout.addWidget(btn_saveas)

        layout.addWidget(grp_save)
        layout.addStretch()

        # ── 底部关闭 ──────────────────────────────
        btn_close = QPushButton("关闭")
        btn_close.setFixedHeight(32)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignRight)

        self.setStyleSheet("""
            QDialog { background:#F5F8FC; }
            QPushButton {
                border:1px solid #B0C4DE; border-radius:4px;
                padding:4px 14px; background:#FFFFFF; font-size:13px;
            }
            QPushButton:hover { background:#E8F0FE; border-color:#1E6FBF; }
        """)

    def _browse_data_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择数据存储目录", self._app._data_dir)
        if d:
            self.edit_data_dir.setText(d)

    def _apply_data_dir(self):
        new_dir = self.edit_data_dir.text().strip()
        if not new_dir or not os.path.isdir(new_dir):
            QMessageBox.warning(self, "目录无效", "请先选择一个有效的目录。")
            return
        if os.path.abspath(new_dir) == os.path.abspath(self._app._data_dir):
            QMessageBox.information(self, "无需更改", "目标目录与当前目录相同。")
            return

        # 统计旧目录中的文件数量
        old_files_count = 0
        if os.path.exists(self._app._data_file):
            old_files_count += 1
        if os.path.isdir(self._app._screenshot_dir):
            old_files_count += len(os.listdir(self._app._screenshot_dir))
        if os.path.isdir(self._app._contract_dir):
            old_files_count += len(os.listdir(self._app._contract_dir))

        migration_hint = ""
        if old_files_count > 0:
            migration_hint = f"\n\n📦 检测到旧目录有 {old_files_count} 个文件，将自动迁移到新目录。"

        reply = QMessageBox.question(
            self, "确认更改数据目录",
            f"确认将数据目录切换为：\n{new_dir}\n\n"
            f"✅ 新目录下的数据文件会自动加载。\n{migration_hint}"
            "软件将立即以新目录重新初始化。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if reply != QMessageBox.Yes:
            return

        # 先保存当前数据到旧路径
        self._app._save_data()

        # 自动迁移旧目录文件
        if old_files_count > 0:
            old_data_file = self._app._data_file
            old_screenshot_dir = self._app._screenshot_dir
            old_contract_dir = self._app._contract_dir
            
            # 确保新目录结构存在
            os.makedirs(new_dir, exist_ok=True)
            os.makedirs(os.path.join(new_dir, "screenshots"), exist_ok=True)
            os.makedirs(os.path.join(new_dir, "contracts"), exist_ok=True)
            
            errors = []
            
            # 迁移数据 JSON
            if os.path.exists(old_data_file):
                try:
                    dst = os.path.join(new_dir, "invoices_data.json")
                    shutil.copy2(old_data_file, dst)
                except Exception as e:
                    errors.append(f"invoices_data.json: {e}")
            
            # 迁移截图目录
            if os.path.isdir(old_screenshot_dir):
                for fname in os.listdir(old_screenshot_dir):
                    src = os.path.join(old_screenshot_dir, fname)
                    dst = os.path.join(new_dir, "screenshots", fname)
                    try:
                        if os.path.isfile(src):
                            shutil.copy2(src, dst)
                    except Exception as e:
                        errors.append(f"screenshots/{fname}: {e}")
            
            # 迁移合同目录
            if os.path.isdir(old_contract_dir):
                for fname in os.listdir(old_contract_dir):
                    src = os.path.join(old_contract_dir, fname)
                    dst = os.path.join(new_dir, "contracts", fname)
                    try:
                        if os.path.isfile(src):
                            shutil.copy2(src, dst)
                    except Exception as e:
                        errors.append(f"contracts/{fname}: {e}")
            
            if errors:
                QMessageBox.warning(
                    self, "部分文件迁移失败",
                    "以下文件迁移失败：\n\n" + "\n".join(errors) +
                    "\n\n请手动将旧目录文件复制到新目录。"
                )

        # 切换目录
        self._app._data_dir       = new_dir
        self._app._data_file      = os.path.join(new_dir, "invoices_data.json")
        self._app._screenshot_dir = os.path.join(new_dir, "screenshots")
        self._app._contract_dir   = os.path.join(new_dir, "contracts")
        os.makedirs(self._app._screenshot_dir, exist_ok=True)
        os.makedirs(self._app._contract_dir,   exist_ok=True)

        # 保存配置（下次启动时自动使用此目录）
        self._app._save_config_dir(new_dir)

        # 重新加载（新目录可能有历史数据）
        self._app.records.clear()
        self._app.table.setRowCount(0)
        self._app._load_data()

        QMessageBox.information(
            self, "已切换",
            f"数据目录已切换为：\n{new_dir}\n\n"
            f"旧目录的文件已自动迁移到新目录。\n\n"
            f"下次启动软件时将自动使用此目录。"
        )

    def _saveas_software(self):
        """将软件及数据整体复制到目标文件夹（便携版）"""
        dst_dir = QFileDialog.getExistingDirectory(self, "选择软件保存目录")
        if not dst_dir:
            return

        src_script = os.path.abspath(__file__)  # invoice_tool.py 所在绝对路径
        src_base   = self._app._base_dir

        # 计算要复制的内容
        items = []
        # 主程序脚本
        if os.path.exists(src_script):
            items.append(("file", src_script, os.path.join(dst_dir, os.path.basename(src_script))))
        # requirements.txt（如果存在）
        req_src = os.path.join(src_base, "requirements.txt")
        if os.path.exists(req_src):
            items.append(("file", req_src, os.path.join(dst_dir, "requirements.txt")))
        # 启动批处理（如果存在）
        bat_src = os.path.join(src_base, "启动.bat")
        if os.path.exists(bat_src):
            items.append(("file", bat_src, os.path.join(dst_dir, "启动.bat")))
        # 数据 JSON
        if os.path.exists(self._app._data_file):
            items.append(("file", self._app._data_file, os.path.join(dst_dir, "invoices_data.json")))
        # screenshots 目录
        if os.path.isdir(self._app._screenshot_dir):
            items.append(("dir", self._app._screenshot_dir, os.path.join(dst_dir, "screenshots")))
        # contracts 目录
        if os.path.isdir(self._app._contract_dir):
            items.append(("dir", self._app._contract_dir, os.path.join(dst_dir, "contracts")))

        if not items:
            QMessageBox.warning(self, "无内容", "未找到可复制的软件文件。")
            return

        reply = QMessageBox.question(
            self, "确认另存",
            f"确认将软件及数据复制到：\n{dst_dir}\n\n"
            f"包含：主程序、数据文件、截图目录、合同目录",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if reply != QMessageBox.Yes:
            return

        errors = []
        for kind, src, dst in items:
            try:
                if kind == "file":
                    shutil.copy2(src, dst)
                elif kind == "dir":
                    if os.path.exists(dst):
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst)
            except Exception as e:
                errors.append(f"{os.path.basename(src)}：{e}")

        if errors:
            QMessageBox.warning(self, "部分文件复制失败",
                "以下文件复制失败：\n\n" + "\n".join(errors))
        else:
            QMessageBox.information(
                self, "另存成功",
                f"软件已成功复制到：\n{dst_dir}\n\n"
                "将此文件夹拷贝到任意位置（含U盘）均可直接运行。\n"
                "运行方式：双击 启动.bat 或直接执行 invoice_tool.py"
            )
            try:
                os.startfile(dst_dir)
            except Exception:
                pass


# ─────────────────────────────────────────────
#  删除确认对话框（双重保险：勾选后才能删除）
# ─────────────────────────────────────────────

class DeleteConfirmDialog(QDialog):
    """带勾选框的删除确认弹窗，必须勾选才可点击「确认删除」"""

    def __init__(self, records: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚠️ 确认删除")
        self.setMinimumWidth(560)
        self._build_ui(records)

    def _build_ui(self, records: list):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # 警告图标 + 标题
        title = QLabel("⚠️ 即将永久删除以下发票记录，请仔细核对：")
        title.setStyleSheet("font-size:14px; font-weight:bold; color:#CC0000;")
        layout.addWidget(title)

        # 发票列表
        detail = QLabel()
        lines = []
        for r in records:
            inv_date = r.get("invoice_date", "—")
            inv_no   = r.get("invoice_no",   "无发票号")
            seller   = r.get("seller_name",   "—")
            total    = r.get("total",        "—")
            fname    = r.get("file",          "未知文件")
            lines.append(
                f"📄 {fname}\n"
                f"   发票号：{inv_no}   日期：{inv_date}\n"
                f"   销售方：{seller}   合计：¥{total}"
            )
        detail.setText("\n\n".join(lines))
        detail.setStyleSheet(
            "background:#FFF3CD; border:1px solid #FFEAA7; "
            "border-radius:6px; padding:10px 12px; "
            "font-size:12px; color:#333; line-height:1.6;"
        )
        detail.setWordWrap(True)
        layout.addWidget(detail)

        # 危险提示
        warn = QLabel("⚠️ 原始 PDF 文件将同步永久删除，无法恢复！")
        warn.setStyleSheet("font-size:13px; font-weight:bold; color:#CC0000;")
        layout.addWidget(warn)

        # 勾选框（必须勾选）
        self.cb = QCheckBox("我已确认上述信息，知晓删除后果，自愿删除")
        self.cb.setStyleSheet("font-size:13px; font-weight:bold; color:#1A1A1A;")
        self.cb.stateChanged.connect(self._on_check)
        layout.addWidget(self.cb)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_ok = QPushButton("✅ 确认删除")
        self.btn_ok.setEnabled(False)   # 默认禁用，必须勾选
        self.btn_ok.setStyleSheet("""
            QPushButton { background:#CC0000; color:white; border-radius:4px;
                          font-size:13px; font-weight:bold; padding:7px 22px; }
            QPushButton:enabled { background:#CC0000; }
            QPushButton:!enabled { background:#AAAAAA; color:#666; }
        """)
        self.btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("取消")
        btn_cancel.setStyleSheet(
            "QPushButton { background:#F0F0F0; color:#333; border-radius:4px; "
            "font-size:13px; padding:7px 18px; }"
        )
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_ok)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

    def _on_check(self, state):
        self.btn_ok.setEnabled(state == Qt.Checked)


# ─────────────────────────────────────────────
#  主窗口
# ─────────────────────────────────────────────

# 表格列定义
COLUMNS = ["序号", "发票PDF", "发票类型", "购买方名称", "纳税人识别号",
           "销售方名称", "金额(元)", "征收率", "税额(元)", "价税合计(元)",
           "发票号码", "开票日期", "企业号", "付款截图", "合同", "备注"]
COL_IDX = {c: i for i, c in enumerate(COLUMNS)}

# 支持的文件扩展名
IMG_EXTS      = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.tiff', '.tif'}
CONTRACT_EXTS = {'.pdf', '.docx', '.doc', '.xlsx', '.xls'}  # 合同支持格式


class InvoiceApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.records = []
        self.pending_company = ""
        
        # 配置文件路径
        self._config_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "config.json"
        )
        
        # 先读取配置文件获取数据目录（直接存储 _data_dir，不再嵌套 data 子目录）
        self._data_dir = self._load_config_dir()
        self._data_file      = os.path.join(self._data_dir, "invoices_data.json")
        self._screenshot_dir = os.path.join(self._data_dir, "screenshots")
        self._contract_dir   = os.path.join(self._data_dir, "contracts")
        os.makedirs(self._data_dir,       exist_ok=True)
        os.makedirs(self._screenshot_dir, exist_ok=True)
        os.makedirs(self._contract_dir,   exist_ok=True)

        self._filter_year        = None
        self._filter_month       = None
        self._filter_inv_type    = None   # 发票类型筛选
        self._filter_seller      = None   # 销售方名称筛选
        self._filter_company     = ""     # 企业号搜索（模糊匹配）
        self._filter_buyer       = ""     # 购买方名称/税号搜索（模糊匹配）

        # 拖拽模式：'pdf'=导入发票, 'screenshot'=添加截图, 'contract'=添加合同
        # 通过键盘修饰键区分：Alt=截图, Shift=合同, 无修饰=PDF
        self._drag_mode = None

        self._init_ui()
        self.setAcceptDrops(True)
        self._load_data()

    # ── UI 构建 ─────────────────────────────────
    def _init_ui(self):
        self.setWindowTitle("发票归档 v4.0")
        self.resize(1480, 820)
        self.setMinimumSize(1000, 640)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 6)
        main_layout.setSpacing(8)

        # ── 工具栏第一行 ──────────────────────────
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        self.btn_open = QPushButton("📂 导入发票PDF")
        self.btn_open.setFixedHeight(36)
        self.btn_open.setToolTip("选择一个或多个PDF发票文件（也可直接拖拽PDF到窗口）")
        self.btn_open.clicked.connect(self.open_files)

        self.btn_clear = QPushButton("🗑 清空列表")
        self.btn_clear.setFixedHeight(36)
        self.btn_clear.clicked.connect(self.clear_records)

        self.btn_settings = QPushButton("⚙️ 设置")
        self.btn_settings.setFixedHeight(36)
        self.btn_settings.setToolTip("数据目录设置 / 软件另存")
        self.btn_settings.clicked.connect(self._open_settings)

        self.btn_export = QPushButton("📊 导出 Excel")
        self.btn_export.setFixedHeight(36)
        self.btn_export.setStyleSheet(
            "background:#1E6FBF; color:white; font-weight:bold; border-radius:4px;")
        self.btn_export.clicked.connect(self.export_excel)

        top_bar.addWidget(self.btn_open)
        top_bar.addWidget(self.btn_clear)
        top_bar.addWidget(self.btn_settings)
        top_bar.addStretch()

        lbl = QLabel("企业号（手动）：")
        lbl.setFixedWidth(110)
        self.edit_company = QLineEdit()
        self.edit_company.setPlaceholderText("输入后新导入发票自动填入")
        self.edit_company.setFixedWidth(220)
        self.edit_company.setFixedHeight(32)
        self.edit_company.textChanged.connect(self._on_company_changed)

        self.btn_apply = QPushButton("应用到已选行")
        self.btn_apply.setFixedHeight(32)
        self.btn_apply.clicked.connect(self.apply_company_to_selected)

        top_bar.addWidget(lbl)
        top_bar.addWidget(self.edit_company)
        top_bar.addWidget(self.btn_apply)
        top_bar.addSpacing(12)
        top_bar.addWidget(self.btn_export)
        main_layout.addLayout(top_bar)

        # ── 工具栏第二行：多维筛选 ───────────────
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(6)

        lbl_filter = QLabel("🔍 筛选：")
        lbl_filter.setStyleSheet("font-size:13px; color:#333;")

        # 年份
        lbl_y = QLabel("年份")
        lbl_y.setStyleSheet("font-size:12px; color:#666;")
        self.combo_year = QComboBox()
        self.combo_year.setFixedWidth(90)
        self.combo_year.setFixedHeight(30)
        self.combo_year.addItem("全部", None)

        # 月份
        lbl_m = QLabel("月份")
        lbl_m.setStyleSheet("font-size:12px; color:#666;")
        self.combo_month = QComboBox()
        self.combo_month.setFixedWidth(80)
        self.combo_month.setFixedHeight(30)
        self.combo_month.addItem("全部", None)
        for i in range(1, 13):
            self.combo_month.addItem(f"{i:02d} 月", i)

        # 发票类型
        lbl_type = QLabel("发票类型")
        lbl_type.setStyleSheet("font-size:12px; color:#666;")
        self.combo_inv_type = QComboBox()
        self.combo_inv_type.setFixedWidth(130)
        self.combo_inv_type.setFixedHeight(30)
        self.combo_inv_type.addItem("全部", None)

        # 销售方名称
        lbl_seller = QLabel("销售方")
        lbl_seller.setStyleSheet("font-size:12px; color:#666;")
        self.combo_seller = QComboBox()
        self.combo_seller.setFixedWidth(160)
        self.combo_seller.setFixedHeight(30)
        self.combo_seller.addItem("全部", None)

        # 购买方名称/税号搜索
        lbl_buyer_search = QLabel("购买方")
        lbl_buyer_search.setStyleSheet("font-size:12px; color:#666;")
        self.edit_buyer_search = QLineEdit()
        self.edit_buyer_search.setPlaceholderText("名称或税号")
        self.edit_buyer_search.setFixedWidth(160)
        self.edit_buyer_search.setFixedHeight(30)
        # 回车直接触发筛选
        self.edit_buyer_search.returnPressed.connect(self._apply_filter)

        # 企业号搜索
        lbl_company_search = QLabel("企业号")
        lbl_company_search.setStyleSheet("font-size:12px; color:#666;")
        self.edit_company_search = QLineEdit()
        self.edit_company_search.setPlaceholderText("输入企业号搜索")
        self.edit_company_search.setFixedWidth(130)
        self.edit_company_search.setFixedHeight(30)
        # 回车直接触发筛选
        self.edit_company_search.returnPressed.connect(self._apply_filter)

        self.btn_filter = QPushButton("筛 选")
        self.btn_filter.setFixedHeight(30)
        self.btn_filter.setFixedWidth(70)
        self.btn_filter.clicked.connect(self._apply_filter)

        self.btn_reset = QPushButton("重置")
        self.btn_reset.setFixedHeight(30)
        self.btn_reset.setFixedWidth(60)
        self.btn_reset.clicked.connect(self._reset_filter)

        self.lbl_filter_hint = QLabel("")
        self.lbl_filter_hint.setStyleSheet("color:#E06020; font-size:12px;")

        filter_bar.addWidget(lbl_filter)
        filter_bar.addWidget(lbl_y)
        filter_bar.addWidget(self.combo_year)
        filter_bar.addWidget(lbl_m)
        filter_bar.addWidget(self.combo_month)
        filter_bar.addWidget(lbl_type)
        filter_bar.addWidget(self.combo_inv_type)
        filter_bar.addWidget(lbl_seller)
        filter_bar.addWidget(self.combo_seller)
        filter_bar.addWidget(lbl_buyer_search)
        filter_bar.addWidget(self.edit_buyer_search)
        filter_bar.addWidget(lbl_company_search)
        filter_bar.addWidget(self.edit_company_search)
        filter_bar.addWidget(self.btn_filter)
        filter_bar.addWidget(self.btn_reset)
        filter_bar.addWidget(self.lbl_filter_hint)
        filter_bar.addStretch()
        main_layout.addLayout(filter_bar)

        # ── 进度条 ───────────────────────────────
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(
            "QProgressBar { border:none; background:#ddd; border-radius:3px; }"
            "QProgressBar::chunk { background:#1E6FBF; border-radius:3px; }")
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        # ── 统计汇总栏 ───────────────────────────
        self.summary_frame = QFrame()
        self.summary_frame.setFrameShape(QFrame.StyledPanel)
        self.summary_frame.setStyleSheet(
            "QFrame { background:#F0F7FF; border:1px solid #B8D4F0; border-radius:5px; }")
        sum_layout = QHBoxLayout(self.summary_frame)
        sum_layout.setContentsMargins(16, 6, 16, 6)
        sum_layout.setSpacing(40)

        self.lbl_count     = self._stat_label("发票总数", "0 张")
        self.lbl_total_amt = self._stat_label("金额合计", "¥ 0.00")
        self.lbl_total_tax = self._stat_label("税额合计", "¥ 0.00")
        self.lbl_total_all = self._stat_label("价税合计", "¥ 0.00")

        for w in [self.lbl_count, self.lbl_total_amt, self.lbl_total_tax, self.lbl_total_all]:
            sum_layout.addWidget(w)
        sum_layout.addStretch()
        main_layout.addWidget(self.summary_frame)

        # ── 主表格 ───────────────────────────────
        self.table = QTableWidget()
        self.table.setColumnCount(len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.verticalHeader().setDefaultSectionSize(36)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        # 列宽：序号, 发票PDF, 发票类型, 购买方名称, 税号, 销售方名称, 金额, 税率, 税额, 合计, 发票号, 日期, 企业号, 截图, 合同, 备注
        col_widths = [45, 160, 120, 150, 155, 150, 88, 55, 88, 98, 135, 100, 105, 90, 90, 100]
        for i, w in enumerate(col_widths):
            self.table.setColumnWidth(i, w)

        self.table.setStyleSheet("""
            QTableWidget { font-size:13px; gridline-color:#dce6f1; }
            QHeaderView::section {
                background-color: #1E6FBF; color: white;
                font-weight: bold; font-size: 13px;
                padding: 5px; border: none;
                border-right: 1px solid #4A90D9;
            }
            QTableWidget::item {
                padding: 2px 6px;
                background-color: white;
            }
            QTableWidget::item:alternate { background:#EEF4FB; }
            QTableWidget::item:selected {
                background: #FFA500;
                color: #1A1A1A;
                font-weight: bold;
            }
            QTableWidget::item:hover:!selected { background:#FFF3CD; }
            QTableWidget::item:selected:hover {
                background: #FF8C00;
            }
        """)
        main_layout.addWidget(self.table)

        # ── 状态栏 ───────────────────────────────
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage(
            "就绪 — 拖拽 PDF 导入发票 | 选中行后拖拽图片添加截图 | 选中行后拖拽合同文件添加合同 | Ctrl+V 粘贴截图/合同")

        self._set_global_style()
        self._save_locked = False
        self.table.cellChanged.connect(self._on_cell_changed)
        self.table.clicked.connect(self._on_table_clicked)
        # 安装 viewport 事件过滤器：点击已选中行取消选中
        self.table.viewport().installEventFilter(self)

    def _stat_label(self, title, value):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(1)
        lbl_t = QLabel(title)
        lbl_t.setStyleSheet("color:#666; font-size:11px;")
        lbl_v = QLabel(value)
        lbl_v.setStyleSheet("color:#1E6FBF; font-size:16px; font-weight:bold;")
        v.addWidget(lbl_t)
        v.addWidget(lbl_v)
        w._value_label = lbl_v
        return w

    def _set_global_style(self):
        self.setStyleSheet("""
            QMainWindow { background: #F5F8FC; }
            QPushButton {
                border: 1px solid #B0C4DE; border-radius: 4px;
                padding: 4px 14px; background: #FFFFFF; font-size: 13px;
            }
            QPushButton:hover { background: #E8F0FE; border-color: #1E6FBF; }
            QPushButton:pressed { background: #CCE0FF; }
            QLineEdit {
                border: 1px solid #B0C4DE; border-radius: 4px;
                padding: 4px 8px; font-size: 13px; background: white;
            }
            QComboBox {
                border: 1px solid #B0C4DE; border-radius: 4px;
                padding: 2px 8px; font-size: 13px; background: white;
            }
        """)

    # ── 筛选条件 ─────────────────────────────────
    def _get_available_years(self):
        years = set()
        for r in self.records:
            m = re.match(r'(\d{4})年', r.get("invoice_date", ""))
            if m:
                years.add(int(m.group(1)))
        return sorted(years)

    def _get_available_inv_types(self):
        types = set()
        for r in self.records:
            t = r.get("invoice_type", "").strip()
            if t:
                types.add(t)
        return sorted(types)

    def _get_available_sellers(self):
        sellers = set()
        for r in self.records:
            s = r.get("seller_name", "").strip()
            if s:
                sellers.add(s)
        return sorted(sellers)

    def _refresh_year_combo(self):
        current = self.combo_year.currentData()
        self.combo_year.blockSignals(True)
        self.combo_year.clear()
        self.combo_year.addItem("全部", None)
        for y in self._get_available_years():
            self.combo_year.addItem(str(y), y)
        idx = self.combo_year.findData(current)
        if idx >= 0:
            self.combo_year.setCurrentIndex(idx)
        self.combo_year.blockSignals(False)

    def _refresh_filter_combos(self):
        """动态刷新发票类型、销售方下拉选项（保留当前选中值）"""
        # 发票类型
        cur_type = self.combo_inv_type.currentData()
        self.combo_inv_type.blockSignals(True)
        self.combo_inv_type.clear()
        self.combo_inv_type.addItem("全部", None)
        for t in self._get_available_inv_types():
            self.combo_inv_type.addItem(t, t)
        idx = self.combo_inv_type.findData(cur_type)
        self.combo_inv_type.setCurrentIndex(idx if idx >= 0 else 0)
        self.combo_inv_type.blockSignals(False)

        # 销售方名称
        cur_seller = self.combo_seller.currentData()
        self.combo_seller.blockSignals(True)
        self.combo_seller.clear()
        self.combo_seller.addItem("全部", None)
        for s in self._get_available_sellers():
            self.combo_seller.addItem(s, s)
        idx = self.combo_seller.findData(cur_seller)
        self.combo_seller.setCurrentIndex(idx if idx >= 0 else 0)
        self.combo_seller.blockSignals(False)

        self._refresh_year_combo()

    def _apply_filter(self):
        self._filter_year     = self.combo_year.currentData()
        self._filter_month    = self.combo_month.currentData()
        self._filter_inv_type = self.combo_inv_type.currentData()
        self._filter_seller   = self.combo_seller.currentData()
        self._filter_buyer    = self.edit_buyer_search.text().strip()
        self._filter_company  = self.edit_company_search.text().strip()
        self._rebuild_table()
        parts = []
        if self._filter_year:
            parts.append(f"{self._filter_year}年")
        if self._filter_month:
            parts.append(f"{self._filter_month:02d}月")
        if self._filter_inv_type:
            parts.append(self._filter_inv_type)
        if self._filter_seller:
            parts.append(f"销售方:{self._filter_seller}")
        if self._filter_buyer:
            parts.append(f"购买方:{self._filter_buyer}")
        if self._filter_company:
            parts.append(f"企业号:{self._filter_company}")
        self.lbl_filter_hint.setText(f"当前筛选：{'  '.join(parts)}" if parts else "")

    def _reset_filter(self):
        self._filter_year     = None
        self._filter_month    = None
        self._filter_inv_type = None
        self._filter_seller   = None
        self._filter_buyer    = ""
        self._filter_company  = ""
        self.combo_year.setCurrentIndex(0)
        self.combo_month.setCurrentIndex(0)
        self.combo_inv_type.setCurrentIndex(0)
        self.combo_seller.setCurrentIndex(0)
        self.edit_buyer_search.clear()
        self.edit_company_search.clear()
        self.lbl_filter_hint.setText("")
        self._rebuild_table()

    def _record_matches_filter(self, rec) -> bool:
        # 年月筛选
        if self._filter_year is not None or self._filter_month is not None:
            m = re.match(r'(\d{4})年(\d{2})月', rec.get("invoice_date", ""))
            if not m:
                return False
            y, mo = int(m.group(1)), int(m.group(2))
            if self._filter_year  is not None and y  != self._filter_year:
                return False
            if self._filter_month is not None and mo != self._filter_month:
                return False
        # 发票类型筛选
        if self._filter_inv_type is not None:
            if rec.get("invoice_type", "").strip() != self._filter_inv_type:
                return False
        # 销售方筛选
        if self._filter_seller is not None:
            if rec.get("seller_name", "").strip() != self._filter_seller:
                return False
        # 购买方名称/税号模糊搜索（不区分大小写）
        if self._filter_buyer:
            buyer_name = rec.get("buyer_name", "").lower()
            buyer_tax_id = rec.get("buyer_tax_id", "").lower()
            search_text = self._filter_buyer.lower()
            if search_text not in buyer_name and search_text not in buyer_tax_id:
                return False
        # 企业号模糊搜索（不区分大小写）
        if self._filter_company:
            company = rec.get("company", "")
            if self._filter_company.lower() not in company.lower():
                return False
        return True

    def _rebuild_table(self):
        self._save_locked = True
        self.table.setUpdatesEnabled(False)   # 暂停 UI 重绘，批量插行时不卡顿
        self.table.setRowCount(0)
        shown = [r for r in self.records if self._record_matches_filter(r)]
        for data in shown:
            self._insert_row(data, scroll=False)
        self.table.setUpdatesEnabled(True)    # 恢复 UI，一次性刷新
        self._refresh_summary_from_list(shown)
        self._save_locked = False
        active = any([self._filter_year, self._filter_month,
                      self._filter_inv_type, self._filter_seller])
        if active:
            self.status.showMessage(f"筛选结果：显示 {len(shown)} 张 / 共 {len(self.records)} 张")

    # ── 数据持久化 ──────────────────────────────
    def _save_data(self):
        try:
            self._sync_records_from_table()
            with open(self._data_file, "w", encoding="utf-8") as f:
                json.dump(self.records, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _sync_records_from_table(self):
        shown = [r for r in self.records if self._record_matches_filter(r)]
        for i in range(self.table.rowCount()):
            inv_no_item = self.table.item(i, COL_IDX["发票号码"])
            inv_no = inv_no_item.text() if inv_no_item else ""

            # 优先通过发票号精确定位，兜底用行位置
            rec = None
            if inv_no:
                for r in self.records:
                    if r.get("invoice_no") == inv_no:
                        rec = r
                        break
            if rec is None and 0 <= i < len(shown):
                rec = shown[i]
            if rec is None:
                continue

            co_item = self.table.item(i, COL_IDX["企业号"])
            bk_item = self.table.item(i, COL_IDX["备注"])
            if co_item:
                rec["company"] = co_item.text()
            if bk_item and bk_item.text() != "✓":
                rec["remark"] = bk_item.text()

    def _load_config_dir(self):
        """从配置文件读取数据目录，如果配置不存在或无效则使用默认路径"""
        default_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data"
        )
        if not os.path.exists(self._config_file):
            return default_dir
        try:
            with open(self._config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
                data_dir = config.get("data_dir", "")
                if data_dir and os.path.isdir(data_dir):
                    return data_dir
        except Exception:
            pass
        return default_dir

    def _save_config_dir(self, data_dir):
        """保存数据目录到配置文件"""
        try:
            with open(self._config_file, "w", encoding="utf-8") as f:
                json.dump({"data_dir": data_dir}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_data(self):
        if not os.path.exists(self._data_file):
            return
        try:
            with open(self._data_file, "r", encoding="utf-8") as f:
                self.records = json.load(f)
            if not isinstance(self.records, list):
                self.records = []
            self._save_locked = True
            self.table.setUpdatesEnabled(False)
            for data in self.records:
                data.setdefault("company", "")
                data.setdefault("pdf_path", "")
                data.setdefault("invoice_type", "")
                data.setdefault("seller_name", "")
                data.setdefault("screenshots", [])
                data.setdefault("contracts", [])
                data.setdefault("remark", "")
                data.setdefault("is_red", False)
                # 旧数据兼容：红票金额统一转负数
                if data.get("is_red"):
                    for f in ("amount", "tax_amount", "total"):
                        v = data.get(f, "")
                        if v and not str(v).startswith('-'):
                            data[f] = '-' + str(v)
                self._insert_row(data, scroll=False)
            self.table.setUpdatesEnabled(True)
            self._refresh_summary()
            self._refresh_filter_combos()
            if self.records:
                self.status.showMessage(f"已自动加载 {len(self.records)} 条历史记录")
            self._save_locked = False
        except Exception:
            self._save_locked = False
            self.table.setUpdatesEnabled(True)

    # ── 拖拽支持 ────────────────────────────────
    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent):
        urls = e.mimeData().urls()
        pdf_files      = []
        img_files      = []
        contract_files = []

        for u in urls:
            path = u.toLocalFile()
            ext  = os.path.splitext(path)[1].lower()
            if ext in IMG_EXTS:
                img_files.append(path)
            elif ext in CONTRACT_EXTS:
                # PDF 需区分：是发票还是合同？
                # 规则：如果有选中行 → 作为合同；没有选中行 → 作为发票
                rows = set(item.row() for item in self.table.selectedItems())
                if ext == '.pdf' and not rows:
                    pdf_files.append(path)
                else:
                    contract_files.append(path)

        if pdf_files:
            self._start_parse(pdf_files)

        rows = sorted(set(item.row() for item in self.table.selectedItems()))

        if img_files:
            if not rows:
                QMessageBox.information(
                    self, "提示",
                    "请先在表格中选中一行，再将图片拖拽到窗口，\n图片将被添加到该行的付款截图。"
                )
            else:
                self._add_screenshots_from_paths(rows[0], img_files)

        if contract_files:
            if not rows:
                QMessageBox.information(
                    self, "提示",
                    "请先在表格中选中一行，再将合同文件拖拽到窗口，\n文件将被添加到该行的合同。"
                )
            else:
                self._add_contracts_from_paths(rows[0], contract_files)

    # ── 槽函数 ───────────────────────────────────
    def _on_company_changed(self, text):
        self.pending_company = text.strip()

    def _on_table_clicked(self, index):
        """点击表格行时，在状态栏显示当前行摘要信息"""
        row = index.row()
        try:
            rec = self._get_record_by_row(row)
            if rec:
                seller = rec.get("seller_name", "") or "—"
                date   = rec.get("invoice_date", "") or "—"
                total  = rec.get("total", "") or "—"
                self.status.showMessage(
                    f"第 {row + 1} 行 | {seller} | {date} | 价税合计：¥{total}"
                    "  ·  Ctrl+V 粘贴截图/合同"
                )
        except Exception:
            pass

    def _on_cell_changed(self, row, col):
        if self._save_locked:
            return
        header = self.table.horizontalHeaderItem(col).text()
        if header in ("企业号", "备注"):
            self._save_data()

    def closeEvent(self, event):
        self._save_data()
        event.accept()

    def _open_settings(self):
        """打开设置对话框"""
        dlg = SettingsDialog(self, parent=self)
        dlg.exec_()

    def keyPressEvent(self, event):
        """
        Ctrl+V：根据剪贴板内容类型判断操作：
          - 图片数据 → 添加截图
          - 文件路径（图片扩展名）→ 添加截图
          - 文件路径（合同扩展名）→ 添加合同
        """
        if event.key() == Qt.Key_V and event.modifiers() == Qt.ControlModifier:
            rows = sorted(set(item.row() for item in self.table.selectedItems()))
            if not rows:
                self.status.showMessage("请先选中一行，再按 Ctrl+V 粘贴截图或合同")
                return
            self._paste_from_clipboard(rows[0])
            return
        super().keyPressEvent(event)

    def open_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择发票PDF文件", "",
            "PDF文件 (*.pdf);;所有文件 (*)"
        )
        if files:
            self._start_parse(files)

    def clear_records(self):
        if not self.records:
            return
        reply = QMessageBox.question(self, "确认清空", "确定要清空所有记录吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.records.clear()
            self.table.setRowCount(0)
            self._refresh_summary()
            self._refresh_filter_combos()
            self._save_data()
            self.status.showMessage("已清空")

    def apply_company_to_selected(self):
        rows = set(item.row() for item in self.table.selectedItems())
        if not rows:
            QMessageBox.information(self, "提示", "请先在表格中选中需要修改的行")
            return
        company = self.pending_company
        if not company:
            company, ok = QInputDialog.getText(self, "输入企业号", "企业号：")
            if not ok or not company:
                return
        col = COL_IDX["企业号"]
        shown = [r for r in self.records if self._record_matches_filter(r)]
        for row in rows:
            self.table.setItem(row, col, QTableWidgetItem(company))
            inv_no_item = self.table.item(row, COL_IDX["发票号码"])
            inv_no = inv_no_item.text() if inv_no_item else ""
            rec = None
            if inv_no:
                for r in self.records:
                    if r.get("invoice_no") == inv_no:
                        rec = r
                        break
            if rec is None and 0 <= row < len(shown):
                rec = shown[row]
            if rec:
                rec["company"] = company
        self.status.showMessage(f"已将企业号「{company}」应用到 {len(rows)} 行")
        self._save_data()

    # ── 解析流程 ─────────────────────────────────
    def _start_parse(self, files):
        self.btn_open.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status.showMessage(f"正在解析 {len(files)} 个文件...")
        self._parse_errors = []

        # data_dir 传给 Worker，让文件复制在后台完成
        self._worker = ParseWorker(files, data_dir=self._data_dir)
        self._worker.progress.connect(self.progress_bar.setValue)
        self._worker.result_ready.connect(self._add_record_batch)
        self._worker.error_occurred.connect(self._on_parse_error)
        self._worker.finished.connect(self._parse_done)
        self._worker.start()

    def _on_parse_error(self, error_msg):
        self._parse_errors.append(error_msg)
        self.status.showMessage(f"解析错误: {error_msg}")

    # ── 批量导入专用槽（纯内存操作，不碰 UI）────────────────
    def _add_record_batch(self, data: dict):
        """后台每解析完一条调此槽；只写 self.records，UI 留给 _parse_done 统一渲染。"""
        if self.pending_company:
            data["company"] = self.pending_company
        data.setdefault("pdf_path", "")
        data.setdefault("invoice_type", "")
        data.setdefault("seller_name", "")
        data.setdefault("screenshots", [])
        data.setdefault("contracts", [])
        data.setdefault("remark", "")
        data.setdefault("is_red", False)
        # 红票金额统一存为负数，便于后续核对
        if data.get("is_red"):
            for f in ("amount", "tax_amount", "total"):
                v = data.get(f, "")
                if v and not str(v).startswith('-'):
                    data[f] = '-' + str(v)
        self.records.append(data)   # 只追加到列表，不插行、不刷新、不存文件

    def _add_record(self, data: dict):
        """单条记录添加（拖放/非批量场景），保留 save + refresh"""
        if self.pending_company:
            data["company"] = self.pending_company
        data.setdefault("pdf_path", "")
        data.setdefault("invoice_type", "")
        data.setdefault("seller_name", "")
        data.setdefault("screenshots", [])
        data.setdefault("contracts", [])
        data.setdefault("remark", "")
        data.setdefault("is_red", False)
        # 红票金额统一存为负数，便于后续核对
        if data.get("is_red"):
            for f in ("amount", "tax_amount", "total"):
                v = data.get(f, "")
                if v and not str(v).startswith('-'):
                    data[f] = '-' + str(v)

        # 复制 PDF 到数据目录
        original_pdf_path = data.get("pdf_path", "")
        if original_pdf_path and os.path.isfile(original_pdf_path):
            invoices_dir = os.path.join(self._data_dir, "invoices")
            os.makedirs(invoices_dir, exist_ok=True)
            fname     = os.path.basename(original_pdf_path)
            save_path = os.path.join(invoices_dir, fname)
            counter = 1
            while os.path.exists(save_path):
                name, ext = os.path.splitext(fname)
                save_path = os.path.join(invoices_dir, f"{name}_{counter}{ext}")
                counter += 1
            try:
                shutil.copy2(original_pdf_path, save_path)
                data["pdf_path"] = save_path
            except Exception as e:
                self.status.showMessage(f"警告：无法保存发票副本 - {fname}")

        self.records.append(data)
        if self._record_matches_filter(data):
            self._insert_row(data)
        self._refresh_summary()
        self._refresh_filter_combos()
        self._save_data()

    def _insert_row(self, data: dict, scroll: bool = True):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setRowHeight(row, 36)

        is_red = data.get("is_red", False)

        def cell(text, editable=False, fg=None, bg=None):
            it = QTableWidgetItem(str(text) if text else "")
            if not editable:
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            if fg:
                it.setForeground(QColor(fg))
            if bg:
                it.setBackground(QColor(bg))
            return it

        # 红票整行浅红背景
        row_bg = "#FFE4E4" if is_red else None

        self.table.setItem(row, COL_IDX["序号"],         cell(row + 1, bg=row_bg))
        # 发票PDF列：显示文件名 + 查看按钮（内嵌 widget）
        self._set_invoice_pdf_cell(row, data)

        # 发票类型：红票显示"🔴 红票-类型"，蓝票显示"🔵 类型"
        inv_type = data.get("invoice_type", "")
        if is_red:
            type_text = f"🔴 红票{'-' + inv_type if inv_type else ''}"
            type_fg   = "#CC0000"
        else:
            type_text = f"🔵 {inv_type}" if inv_type else ""
            type_fg   = "#1E6FBF"
        type_item = cell(type_text, fg=type_fg, bg=row_bg)
        self.table.setItem(row, COL_IDX["发票类型"], type_item)

        # 金额列：负数标红（红票金额已在入库时转负）
        def amount_cell(field):
            v = data.get(field, "")
            v = str(v) if v is not None else ""
            neg = v.startswith('-')
            return cell(v, fg="#CC0000" if neg else None, bg=row_bg if row_bg else ("#FFF0F0" if neg else None))

        self.table.setItem(row, COL_IDX["购买方名称"],   cell(data.get("buyer_name", ""), bg=row_bg))
        self.table.setItem(row, COL_IDX["纳税人识别号"],  cell(data.get("buyer_tax_id", ""), bg=row_bg))
        self.table.setItem(row, COL_IDX["销售方名称"],   cell(data.get("seller_name", ""), bg=row_bg))
        self.table.setItem(row, COL_IDX["金额(元)"],     amount_cell("amount"))
        self.table.setItem(row, COL_IDX["征收率"],       cell(data.get("tax_rate", ""), bg=row_bg))
        self.table.setItem(row, COL_IDX["税额(元)"],     amount_cell("tax_amount"))
        self.table.setItem(row, COL_IDX["价税合计(元)"],  amount_cell("total"))
        self.table.setItem(row, COL_IDX["发票号码"],      cell(data.get("invoice_no", ""), bg=row_bg))
        self.table.setItem(row, COL_IDX["开票日期"],      cell(data.get("invoice_date", ""), bg=row_bg))
        self.table.setItem(row, COL_IDX["企业号"],        cell(data.get("company", ""), editable=True, bg=row_bg))

        self._set_screenshot_cell(row, data)
        self._set_contract_cell(row, data)

        remark_val  = data.get("remark", "") or data.get("error", "") or "✓"
        remark_item = cell(remark_val, editable=True,
                           fg="#CC0000" if data.get("error") else ("#CC0000" if is_red else ("#1E8B1E" if remark_val == "✓" else "#333")),
                           bg=row_bg)
        self.table.setItem(row, COL_IDX["备注"], remark_item)

        if scroll:
            self.table.scrollToBottom()

    # ── 发票PDF单元格 ────────────────────────────
    def _set_invoice_pdf_cell(self, row, data):
        """发票PDF列：文件名 + 查看按钮"""
        fname    = data.get("file", "")
        pdf_path = data.get("pdf_path", "")
        exists   = bool(pdf_path) and os.path.exists(pdf_path)

        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(4, 1, 2, 1)
        lay.setSpacing(3)

        lbl = QLabel(fname)
        lbl.setStyleSheet(
            f"font-size:12px; color:{'#1E6FBF' if exists else '#999'};"
        )
        lbl.setToolTip(pdf_path or "（路径未记录）")
        lay.addWidget(lbl, 1)

        if exists:
            btn_v = QPushButton("查看")
            btn_v.setFixedHeight(24)
            btn_v.setFixedWidth(40)
            btn_v.setStyleSheet("font-size:11px; padding:1px 4px; color:#1E6FBF;")
            btn_v.setToolTip("打开 / 下载发票原文件")
            btn_v.clicked.connect(lambda _, r=row: self._view_invoice_pdf(r))
            lay.addWidget(btn_v)

        self.table.setCellWidget(row, COL_IDX["发票PDF"], w)

    def _view_invoice_pdf(self, row):
        """打开发票PDF查看/下载对话框"""
        rec = self._get_record_by_row(row)
        if rec is None:
            return
        dlg = InvoiceManagerDialog(
            pdf_path=rec.get("pdf_path", ""),
            rec_name=rec.get("buyer_name", "") or rec.get("file", ""),
            parent=self
        )
        dlg.exec_()

    # ── 截图单元格 ───────────────────────────────
    def _set_screenshot_cell(self, row, data):
        screenshots = data.get("screenshots", [])
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(2, 1, 2, 1)
        lay.setSpacing(3)

        if screenshots:
            lbl = QLabel(f"📷{len(screenshots)}")
            lbl.setStyleSheet("color:#1E6FBF; font-size:12px;")
            btn_v = QPushButton("查看")
            btn_v.setFixedHeight(24)
            btn_v.setFixedWidth(40)
            btn_v.setStyleSheet("font-size:11px; padding:1px 4px;")
            btn_v.clicked.connect(lambda _, r=row: self._view_screenshots(r))
            lay.addWidget(lbl)
            lay.addWidget(btn_v)
        else:
            lbl = QLabel("—")
            lbl.setStyleSheet("color:#aaa; font-size:12px;")
            lay.addWidget(lbl)

        btn_add = QPushButton("＋")
        btn_add.setFixedHeight(24)
        btn_add.setFixedWidth(26)
        btn_add.setToolTip("添加付款截图")
        btn_add.setStyleSheet("font-size:13px; padding:0; color:#1E6FBF;")
        btn_add.clicked.connect(lambda _, r=row: self._add_screenshot(r))
        lay.addWidget(btn_add)
        lay.addStretch()
        self.table.setCellWidget(row, COL_IDX["付款截图"], w)

    # ── 合同单元格 ───────────────────────────────
    def _set_contract_cell(self, row, data):
        contracts = data.get("contracts", [])
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(2, 1, 2, 1)
        lay.setSpacing(3)

        if contracts:
            lbl = QLabel(f"📄{len(contracts)}")
            lbl.setStyleSheet("color:#2E7D32; font-size:12px;")
            btn_v = QPushButton("查看")
            btn_v.setFixedHeight(24)
            btn_v.setFixedWidth(40)
            btn_v.setStyleSheet("font-size:11px; padding:1px 4px; color:#2E7D32;")
            btn_v.clicked.connect(lambda _, r=row: self._view_contracts(r))
            lay.addWidget(lbl)
            lay.addWidget(btn_v)
        else:
            lbl = QLabel("—")
            lbl.setStyleSheet("color:#aaa; font-size:12px;")
            lay.addWidget(lbl)

        btn_add = QPushButton("＋")
        btn_add.setFixedHeight(24)
        btn_add.setFixedWidth(26)
        btn_add.setToolTip("添加合同文件（PDF/Word）")
        btn_add.setStyleSheet("font-size:13px; padding:0; color:#2E7D32;")
        btn_add.clicked.connect(lambda _, r=row: self._add_contract(r))
        lay.addWidget(btn_add)
        lay.addStretch()
        self.table.setCellWidget(row, COL_IDX["合同"], w)

    # ── 截图操作 ─────────────────────────────────
    def _get_record_by_row(self, row):
        """通过发票号码或行序号（辅助）定位 record"""
        inv_no_item = self.table.item(row, COL_IDX["发票号码"])
        inv_no = inv_no_item.text() if inv_no_item else ""

        # 先精确匹配发票号码
        if inv_no:
            for rec in self.records:
                if rec.get("invoice_no") == inv_no:
                    return rec

        # 兜底：行在当前可见列表中的位置（筛选后 records 子集）
        shown = [r for r in self.records if self._record_matches_filter(r)]
        if 0 <= row < len(shown):
            return shown[row]
        return None

    def _add_screenshot(self, row):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择付款截图", "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;所有文件 (*)"
        )
        if files:
            self._add_screenshots_from_paths(row, files)

    def _add_screenshots_from_paths(self, row, src_paths):
        rec = self._get_record_by_row(row)
        if rec is None:
            return
        inv_no    = rec.get("invoice_no", "") or rec.get("file", "unnamed")
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', inv_no)
        added = 0
        for src in src_paths:
            if not os.path.exists(src):
                continue
            ext = os.path.splitext(src)[1].lower() or ".png"
            ts  = datetime.now().strftime("%Y%m%d%H%M%S%f")
            dst = os.path.join(self._screenshot_dir, f"{safe_name}_{ts}{ext}")
            try:
                shutil.copy2(src, dst)
                rec.setdefault("screenshots", []).append(dst)
                added += 1
            except Exception as ex:
                QMessageBox.warning(self, "复制失败",
                    f"文件 {os.path.basename(src)} 复制失败：{ex}")
        if added > 0:
            self._set_screenshot_cell(row, rec)
            self._save_data()
            self.status.showMessage(f"已为该发票添加 {added} 张付款截图")

    def _view_screenshots(self, row):
        rec = self._get_record_by_row(row)
        if rec is None:
            return
        screenshots = rec.get("screenshots", [])
        if not screenshots:
            QMessageBox.information(self, "提示", "该发票暂无付款截图")
            return
        dlg = ImageViewerDialog(screenshots, parent=self)
        dlg.exec_()

    # ── 合同操作 ─────────────────────────────────
    def _add_contract(self, row):
        """通过文件选择对话框添加合同"""
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择合同文件", "",
            "合同文件 (*.pdf *.docx *.doc *.xlsx *.xls);;所有文件 (*)"
        )
        if files:
            self._add_contracts_from_paths(row, files)

    def _add_contracts_from_paths(self, row, src_paths):
        """将合同文件复制到 contracts 目录并绑定到指定行"""
        rec = self._get_record_by_row(row)
        if rec is None:
            return
        inv_no    = rec.get("invoice_no", "") or rec.get("file", "unnamed")
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', inv_no)
        added = 0
        for src in src_paths:
            if not os.path.exists(src):
                continue
            ext      = os.path.splitext(src)[1].lower()
            orig_base = os.path.splitext(os.path.basename(src))[0]
            ts       = datetime.now().strftime("%Y%m%d%H%M%S%f")
            dst_name = f"{safe_name}_{orig_base}_{ts}{ext}"
            dst      = os.path.join(self._contract_dir, dst_name)
            try:
                shutil.copy2(src, dst)
                rec.setdefault("contracts", []).append(dst)
                added += 1
            except Exception as ex:
                QMessageBox.warning(self, "复制失败",
                    f"文件 {os.path.basename(src)} 复制失败：{ex}")
        if added > 0:
            self._set_contract_cell(row, rec)
            self._save_data()
            self.status.showMessage(f"已为该发票添加 {added} 份合同")

    def _view_contracts(self, row):
        """打开合同管理对话框"""
        rec = self._get_record_by_row(row)
        if rec is None:
            return
        contracts = rec.get("contracts", [])
        if not contracts:
            QMessageBox.information(self, "提示", "该发票暂无合同文件")
            return
        dlg = ContractManagerDialog(
            contracts,
            rec_name=rec.get("buyer_name", "") or rec.get("file", ""),
            parent=self
        )
        dlg.exec_()
        # 同步对话框中可能的删除操作
        if dlg.contract_paths != contracts:
            rec["contracts"] = dlg.contract_paths
            self._set_contract_cell(row, rec)
            self._save_data()

    # ── 剪贴板粘贴 ──────────────────────────────
    def _paste_from_clipboard(self, row):
        """Ctrl+V：图片数据→截图，文件路径→按扩展名分类"""
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()

        # 图片像素数据（截图工具）
        if mime.hasImage():
            img = clipboard.image()
            if not img.isNull():
                rec = self._get_record_by_row(row)
                if rec is None:
                    return
                inv_no    = rec.get("invoice_no", "") or rec.get("file", "unnamed")
                safe_name = re.sub(r'[\\/:*?"<>|]', '_', inv_no)
                ts  = datetime.now().strftime("%Y%m%d%H%M%S%f")
                dst = os.path.join(self._screenshot_dir, f"{safe_name}_{ts}.png")
                try:
                    img.save(dst, "PNG")
                    rec.setdefault("screenshots", []).append(dst)
                    self._set_screenshot_cell(row, rec)
                    self._save_data()
                    self.status.showMessage("已从剪贴板粘贴图片并添加为付款截图")
                except Exception as ex:
                    QMessageBox.warning(self, "粘贴失败", f"保存剪贴板图片失败：{ex}")
                return

        # 文件路径
        if mime.hasUrls():
            img_files      = []
            contract_files = []
            for u in mime.urls():
                path = u.toLocalFile()
                ext  = os.path.splitext(path)[1].lower()
                if ext in IMG_EXTS:
                    img_files.append(path)
                elif ext in CONTRACT_EXTS:
                    contract_files.append(path)
            if img_files:
                self._add_screenshots_from_paths(row, img_files)
            if contract_files:
                self._add_contracts_from_paths(row, contract_files)
            if img_files or contract_files:
                return

        self.status.showMessage("剪贴板中没有可用内容（图片或合同文件），请先复制后再粘贴")

    # ── 点击同一行取消选中（viewport 事件过滤器）────
    def eventFilter(self, obj, event):
        if obj is self.table.viewport() and event.type() == QEvent.MouseButtonPress:
            if event.button() == Qt.LeftButton:
                row = self.table.rowAt(event.pos().y())
                selected = self._selected_rows()
                if row >= 0 and selected == [row]:
                    # 再次点击同一已选中行 → 取消选中
                    self.table.clearSelection()
                    return True   # 消费事件，不再触发选中
        return super().eventFilter(obj, event)



    # ── 右键菜单 ─────────────────────────────────
    def _show_context_menu(self, pos):
        menu = QMenu(self)

        # 截图区
        menu.addAction("📷 添加付款截图（文件选择）", self._ctx_add_screenshot)
        menu.addAction("📋 粘贴截图（Ctrl+V）",        self._ctx_paste_screenshot)
        menu.addAction("🔍 查看付款截图",               self._ctx_view_screenshot)
        menu.addAction("🗑 清除此行截图",               self._ctx_delete_screenshots)
        menu.addSeparator()

        # 合同区
        menu.addAction("📄 添加合同（文件选择）",       self._ctx_add_contract)
        menu.addAction("📋 粘贴合同文件（Ctrl+V）",     self._ctx_paste_contract)
        menu.addAction("📂 查看/管理合同",              self._ctx_view_contracts)
        menu.addAction("🗑 清除此行合同",               self._ctx_delete_contracts)
        menu.addSeparator()

        menu.addAction("❌ 删除选中行", self._delete_selected_rows)
        menu.exec_(self.table.viewport().mapToGlobal(pos))

    def _selected_rows(self):
        return sorted(set(item.row() for item in self.table.selectedItems()))

    def _ctx_add_screenshot(self):
        for row in self._selected_rows():
            self._add_screenshot(row)

    def _ctx_paste_screenshot(self):
        rows = self._selected_rows()
        if rows:
            self._paste_from_clipboard(rows[0])

    def _ctx_view_screenshot(self):
        rows = self._selected_rows()
        if rows:
            self._view_screenshots(rows[0])

    def _ctx_delete_screenshots(self):
        for row in self._selected_rows():
            rec = self._get_record_by_row(row)
            if rec:
                rec["screenshots"] = []
                self._set_screenshot_cell(row, rec)
        self._save_data()
        self.status.showMessage("已清除选中行的截图记录")

    def _ctx_add_contract(self):
        for row in self._selected_rows():
            self._add_contract(row)

    def _ctx_paste_contract(self):
        rows = self._selected_rows()
        if rows:
            self._paste_from_clipboard(rows[0])

    def _ctx_view_contracts(self):
        rows = self._selected_rows()
        if rows:
            self._view_contracts(rows[0])

    def _ctx_delete_contracts(self):
        for row in self._selected_rows():
            rec = self._get_record_by_row(row)
            if rec:
                rec["contracts"] = []
                self._set_contract_cell(row, rec)
        self._save_data()
        self.status.showMessage("已清除选中行的合同记录")

    def _delete_selected_rows(self):
        rows = sorted(set(item.row() for item in self.table.selectedItems()), reverse=True)
        if not rows:
            return

        # 收集待删除记录信息（先收集再删）
        shown = [r for r in self.records if self._record_matches_filter(r)]
        to_delete = []
        for row in rows:
            inv_no_item = self.table.item(row, COL_IDX["发票号码"])
            inv_no = inv_no_item.text() if inv_no_item else ""
            rec = None
            if inv_no:
                for r in self.records:
                    if r.get("invoice_no") == inv_no:
                        rec = r
                        break
            if rec is None and 0 <= row < len(shown):
                rec = shown[row]
            if rec and rec not in to_delete:
                to_delete.append(rec)

        if not to_delete:
            return

        # 双重确认弹窗：必须勾选才能点删除
        dlg = DeleteConfirmDialog(to_delete, self)
        if dlg.exec_() != QDialog.Accepted:
            return

        # 删除原始PDF并从 records 移除
        deleted_files = 0
        failed_files  = []
        for rec in to_delete:
            pdf_path = rec.get("pdf_path", "")
            if pdf_path and os.path.exists(pdf_path):
                try:
                    os.remove(pdf_path)
                    deleted_files += 1
                except Exception as ex:
                    failed_files.append(f"{os.path.basename(pdf_path)}：{ex}")
            self.records.remove(rec)

        # 重建表格
        self._rebuild_table()
        self._refresh_filter_combos()
        self._save_data()

        msg = f"已删除 {len(to_delete)} 条记录"
        if deleted_files:
            msg += f"，{deleted_files} 个PDF文件已删除"
        if failed_files:
            msg += f"，{len(failed_files)} 个文件删除失败"
            QMessageBox.warning(self, "部分文件删除失败",
                "以下文件删除失败（记录已从列表移除）：\n\n" +
                "\n".join(failed_files))
        self.status.showMessage(msg)

    # ── 统计汇总 ─────────────────────────────────
    def _refresh_summary(self):
        self._refresh_summary_from_list(self.records)

    def _refresh_summary_from_list(self, recs):
        count     = len(recs)
        total_amt = sum(self._safe_float(r.get("amount"))     for r in recs)
        total_tax = sum(self._safe_float(r.get("tax_amount")) for r in recs)
        total_all = sum(self._safe_float(r.get("total"))      for r in recs)
        self.lbl_count._value_label.setText(f"{count} 张")
        self.lbl_total_amt._value_label.setText(f"¥ {total_amt:,.2f}")
        self.lbl_total_tax._value_label.setText(f"¥ {total_tax:,.2f}")
        self.lbl_total_all._value_label.setText(f"¥ {total_all:,.2f}")

    def _parse_done(self):
        # 所有记录已在 self.records，一次性重建表格（比逐行 insertRow 快得多）
        self._rebuild_table()
        self._refresh_filter_combos()
        self._save_data()

        self.btn_open.setEnabled(True)
        self.progress_bar.setVisible(False)
        # 统计本次新增（含错误标记的为失败）
        batch_total = len(self.records)
        ok   = sum(1 for r in self.records if not r.get("error"))
        fail = batch_total - ok
        msg  = f"导入完成：共 {batch_total} 张发票，成功识别 {ok} 张"
        if fail:
            msg += f"，{fail} 张解析异常（查看备注列）"
        if self._parse_errors:
            msg += f"  |  {len(self._parse_errors)} 个错误"
        self.status.showMessage(msg)

    # ── 导出 Excel ───────────────────────────────
    def export_excel(self):
        export_records = [r for r in self.records if self._record_matches_filter(r)]
        if not export_records:
            QMessageBox.information(self, "提示", "暂无数据，请先导入发票")
            return

        month_hint = ""
        if self._filter_year or self._filter_month:
            y  = self._filter_year or "全年"
            mo = f"{self._filter_month:02d}月" if self._filter_month else ""
            month_hint = f"_{y}{mo}"

        default_name = f"发票归档{month_hint}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        save_path, _ = QFileDialog.getSaveFileName(
            self, "保存Excel文件", default_name, "Excel文件 (*.xlsx)"
        )
        if not save_path:
            return

        # 导出列：不含「付款截图」和「合同」
        xl_columns = [c for c in COLUMNS if c not in ("付款截图", "合同")]

        try:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "发票归档"

            header_fill  = PatternFill("solid", fgColor="1E6FBF")
            header_font  = Font(color="FFFFFF", bold=True, size=12)
            header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
            thin   = Side(style="thin", color="AAAAAA")
            border = Border(left=thin, right=thin, top=thin, bottom=thin)

            ws.append(xl_columns)
            for cell in ws[1]:
                cell.fill      = header_fill
                cell.font      = header_font
                cell.alignment = header_align
                cell.border    = border
            ws.row_dimensions[1].height = 28

            alt_fill     = PatternFill("solid", fgColor="EEF4FB")
            normal_align = Alignment(horizontal="left",   vertical="center")
            center_align = Alignment(horizontal="center", vertical="center")

            for i, rec in enumerate(export_records, 2):
                row_data = [
                    i - 1,
                    rec.get("file", ""),
                    rec.get("invoice_type", ""),
                    rec.get("buyer_name", ""),
                    rec.get("buyer_tax_id", ""),
                    rec.get("seller_name", ""),
                    rec.get("amount", ""),
                    rec.get("tax_rate", ""),
                    rec.get("tax_amount", ""),
                    rec.get("total", ""),
                    rec.get("invoice_no", ""),
                    rec.get("invoice_date", ""),
                    rec.get("company", ""),
                    rec.get("remark", "") or rec.get("error", "") or "✓"
                ]
                ws.append(row_data)
                fill = alt_fill if i % 2 == 0 else None
                for j, cell in enumerate(ws[i]):
                    if fill:
                        cell.fill = fill
                    cell.border    = border
                    cell.alignment = center_align if j in [0, 5] else normal_align
                ws.row_dimensions[i].height = 20

            # 汇总行
            ws.append([])
            sum_row   = ws.max_row + 1
            total_amt = sum(self._safe_float(r.get("amount"))     for r in export_records)
            total_tax = sum(self._safe_float(r.get("tax_amount")) for r in export_records)
            total_all = sum(self._safe_float(r.get("total"))      for r in export_records)
            ws.cell(sum_row, 1, "合计")
            ws.cell(sum_row, 7, round(total_amt, 2))
            ws.cell(sum_row, 9, round(total_tax, 2))
            ws.cell(sum_row, 10, round(total_all, 2))
            sum_font = Font(bold=True, color="1E6FBF", size=12)
            sum_fill = PatternFill("solid", fgColor="D6E4F5")
            for cell in ws[sum_row]:
                cell.font      = sum_font
                cell.fill      = sum_fill
                cell.border    = border
                cell.alignment = center_align
            ws.row_dimensions[sum_row].height = 24

            # 列宽：序号, 发票PDF, 发票类型, 购买方名称, 税号, 销售方名称, 金额, 税率, 税额, 合计, 发票号, 日期, 企业号, 备注
            xl_widths = [6, 26, 16, 20, 22, 20, 12, 8, 12, 14, 20, 14, 15, 14]
            for i, w in enumerate(xl_widths, 1):
                ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

            ws.freeze_panes = "A2"
            wb.save(save_path)
            QMessageBox.information(self, "导出成功",
                f"已成功导出 {len(export_records)} 条记录\n\n路径：{save_path}")
            self.status.showMessage(f"Excel 已保存：{save_path}")
            os.startfile(os.path.dirname(save_path))

        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出时出错：\n{e}")

    @staticmethod
    def _safe_float(val):
        try:
            return float(val or 0)
        except (ValueError, TypeError):
            return 0.0


# ─────────────────────────────────────────────
#  入口
# ─────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("发票归档")
    app.setStyle("Fusion")
    app.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    win = InvoiceApp()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
