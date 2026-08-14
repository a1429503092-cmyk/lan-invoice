# -*- coding: utf-8 -*-
"""发票 PDF 解析引擎 — 独立于 GUI，可单独测试"""

import os
import re
import pdfplumber

from logger import getLogger, log_call

log = getLogger(__name__)


# ── PDF 文本提取 ──────────────────────────────

# 匹配两个非 ASCII 字符之间的空白（消除部分 PDF 中文间多余空格）
_CJK_SPACE_RE = re.compile(r'(?<=[^\x00-\x7f])\s+(?=[^\x00-\x7f])')

# 孤立代理字符 U+D800–U+DFFF 映射到 U+FFFD 的转换表
# pdfplumber 偶发产生此类非法 Unicode 字符，必须在此清洗，否则会触发 UTF-8 编码崩溃
_SURROGATE_TABLE = {c: ord('�') for c in range(0xd800, 0xe000)}


def _sanitize_str(text: str) -> str:
    """清洗字符串中的非法代理字符，替换为 �"""
    if not text:
        return text
    return text.translate(_SURROGATE_TABLE)


def _extract_pdf_text(pdf_path: str) -> str:
    """从 PDF 提取全部文本（含表格内容），返回字符串"""
    with pdfplumber.open(pdf_path) as pdf:
        full_text = ""
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                full_text += _sanitize_str(t) + "\n"
            try:
                for table in page.extract_tables():
                    for row in table:
                        if row:
                            full_text += _sanitize_str(
                                " ".join(str(c) or "" for c in row)) + "\n"
            except Exception:
                pass
    return full_text


# ── 发票类型识别 ──────────────────────────────

_INVOICE_TYPE_PATTERNS = [
    (r'增值税专用发票',          '增值税专用发票'),
    (r'增值税普通发票',          '增值税普通发票'),
    (r'增值税电子普通发票',      '增值税电子普通发票'),
    (r'电子普通发票',            '电子普通发票'),
    (r'票\s*通\s*发\s*票|票通电子发票', '票通发票'),
    (r'普通发票',                '普通发票'),
    (r'全面数字化的电子发票|全电发票|数电票', '全电发票'),
    (r'机动车销售统一发票',      '机动车销售统一发票'),
    (r'二手车销售统一发票',      '二手车销售统一发票'),
    (r'通用机打发票|通用手工发票', '通用发票'),
]


def _detect_invoice_type(text: str) -> str:
    """识别发票类型，返回类型名称字符串"""
    # 去中文间空格后做匹配（部分 PDF 文字提取为 电 子 发 票）
    normalized = _CJK_SPACE_RE.sub("", text)
    # 第一优先：标题括号内容
    m = re.search(r'(?:电子|数电)?发票[（(]([^）)]+)[）)]', normalized[:500])
    if m:
        return m.group(1).strip()
    # 第二优先：前 500 字符关键词匹配
    for pattern, label in _INVOICE_TYPE_PATTERNS:
        if re.search(pattern, normalized[:500]):
            return label
    # 第三优先：全文关键词匹配
    for pattern, label in _INVOICE_TYPE_PATTERNS:
        if re.search(pattern, normalized):
            return label
    # 未匹配时：输出原文前 200 字便于排查
    log.warning("无法识别发票类型，原文前段:\n%s", text[:300])
    return ""


# ── 发票号码 ──────────────────────────────────

def _extract_invoice_no(text: str) -> str:
    """提取发票号码"""
    m = re.search(r'发票号码[：:]\s*(\d+)', text)
    if m:
        return m.group(1)
    m = re.search(r'(?:发票)?号\s*码[：:]\s*(\d{8,})', text)
    if m:
        return m.group(1)
    for num in re.findall(r'\b(\d{10,20})\b', text):
        return num
    return ""


# ── 开票日期 ──────────────────────────────────

def _norm_date(y: str, mo: str, d: str | None = None) -> str | None:
    """统一转换为 xxxx年xx月xx日；无日则返回 None"""
    mo = mo.zfill(2)
    if d:
        return f"{y}年{mo}月{d.zfill(2)}日"
    return None


def _extract_invoice_date(text: str) -> str:
    """提取开票日期"""
    # 预处理：折叠多余空白
    clean = re.sub(r'[\t ]+', ' ', text)
    clean = re.sub(r'\n+', ' ', clean)
    clean = re.sub(r'·+|──+', '', clean)

    # 优先：含"开票日期"关键字
    for pat in [
        r'开票日期[：: ]*(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日',
        r'开票日期[：: ]*(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})',
        r'开票日期[：: ]*(\d{4})(\d{2})(\d{2})(?!\d)',
    ]:
        m = re.search(pat, clean)
        if m:
            d = _norm_date(m.group(1), m.group(2), m.group(3))
            if d:
                return d

    # 次优先：含"日期"关键字
    for pat in [
        r'日期[：: ]*(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日',
        r'日期[：: ]*(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})',
    ]:
        m = re.search(pat, clean)
        if m:
            d = _norm_date(m.group(1), m.group(2), m.group(3))
            if d:
                return d

    # 兜底：全文第一个完整年月日
    m = re.search(r'(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日', clean)
    if m:
        return _norm_date(m.group(1), m.group(2), m.group(3))
    m = re.search(r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})', clean)
    if m:
        return _norm_date(m.group(1), m.group(2), m.group(3))
    return ""


# ── 购买方信息 ────────────────────────────────

_COMPANY_NAME_RE = r'[一-龥]{2,}(?:有限公司|有限责任公司|集团|股份|合作社)[一-龥]*'


def _extract_buyer_info(text: str, buyer_section: str) -> tuple[str, str]:
    """提取购买方名称和税号，返回 (name, tax_id)"""
    name = ""
    tax_id = ""

    # ── 购买方名称（5 个模式依次尝试）──────────
    m = re.search(r'名称[：:]\s*(.+?)(?:\s+销\s|销\s*名称|统一社会|$)', text, re.MULTILINE)
    if m:
        name = m.group(1).strip()
    if name:
        name = re.split(r'\s+销\s*$|\s+销\s+名称', name)[0].strip()

    if not name and buyer_section:
        m = re.search(r'名称[：:]\s*([^\n\r]+)', buyer_section)
        if m:
            name = m.group(1).strip()

    if not name and buyer_section:
        m = re.search(_COMPANY_NAME_RE, buyer_section)
        if m:
            name = m.group(0).strip()

    if not name:
        m = re.search(
            r'(?:购买方|买方|购方)[\s\n:：]*([^\n\r]{2,}(?:有限公司|有限责任公司|集团|股份|合作社)[^\n\r]*)',
            text
        )
        if m:
            name = m.group(1).strip()

    if not name:
        matches = re.findall(_COMPANY_NAME_RE, text)
        if matches:
            name = matches[0]

    # ── 购买方税号（4 个模式）──────────────────
    ids = re.findall(r'统一社会信用代码/纳税人识别号[：:]\s*([A-Z0-9]{15,20})', text)
    if ids:
        tax_id = ids[0]

    if not tax_id:
        m = re.search(r'(?:纳税人识别号|税号|识别号)[：:\s]*([A-Z0-9]{15,20})', text)
        if m:
            tax_id = m.group(1)

    if not tax_id and buyer_section:
        m = re.search(r'([A-Z0-9]{15,20})', buyer_section)
        if m:
            tax_id = m.group(1)

    if not tax_id:
        m = re.search(r'(?:购买方|买方|购方)[^纳]*?([A-Z0-9]{15,20})', text, re.DOTALL)
        if m:
            tax_id = m.group(1)

    return name, tax_id


# ── 销售方名称 ────────────────────────────────


def _extract_seller_name(text: str, seller_section: str, buyer_name: str) -> str:
    """提取销售方名称（11 个模式依次尝试）"""
    patterns = [
        r'销售方名称[：:]\s*([^\n\r]+)',
        r'销\s*方\s*名称[：:]\s*([^\n\r]+)',
        r'销\s*名\s*称[：:]\s*([^\n\r]+)',
        r'销货方[：:]\s*([^\n\r]+)',
        r'销售方\s*[（(]名称[）)]\s*[：:]\s*([^\n\r]+)',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1).strip()

    # 两个"名称："，第二个是销售方
    names = re.findall(r'名\s*称[：:]\s*([^\n\r]+)', text)
    if len(names) >= 2:
        return names[-1].strip()

    # 从销售方区域提取
    if seller_section:
        m = re.search(r'名称[：:]\s*([^\n\r]+)', seller_section)
        if m:
            return m.group(1).strip()
        m = re.search(_COMPANY_NAME_RE, seller_section)
        if m:
            return m.group(0).strip()

    # 销售方关键字 + 公司名
    m = re.search(r'销\s*售[^名]*?([一-龥]{2,}(?:有限公司|有限责任公司|集团|股份)[一-龥]*)', text)
    if m:
        return m.group(1).strip()

    m = re.search(r'(?:销售方|销方)[\s\n:：]*([^\n\r]{2,}(?:有限公司|有限责任公司|集团|股份|合作社)[^\n\r]*)', text)
    if m:
        return m.group(1).strip()

    # 最后兜底：取文本中最后一个公司名
    all_names = re.findall(_COMPANY_NAME_RE, text)
    if all_names and len(all_names) >= 2:
        return all_names[-1]
    if all_names and not buyer_name:
        return all_names[-1]

    return ""


# ── 金额/税额 ─────────────────────────────────


def _signed_amount(v: str) -> tuple[str, bool]:
    """解析带符号金额，返回 (绝对值字符串, 是否负数)"""
    v = v.strip()
    neg = False
    if v.startswith('-'):
        neg = True
        v = v[1:]
    elif v.startswith('(') and v.endswith(')'):
        neg = True
        v = v[1:-1]
    return v.replace(',', ''), neg


def _set_financial(result: dict, field: str, raw_val: str, is_neg: bool):
    """设置金额/税额字段，标记红票"""
    if not raw_val:
        return
    val, neg = _signed_amount(raw_val)
    if val and not result[field]:
        result[field] = val
    if neg:
        result["is_red"] = True


def _extract_financials(text: str, result: dict):
    """提取金额、税率、税额、价税合计"""
    # 模式1：合计行
    m = re.search(r'合\s*计\s+[¥￥]?(-?[\d,]+\.?\d*)\s+[¥￥]?(-?[\d,]+\.?\d*)', text)
    if m:
        _set_financial(result, "amount", m.group(1), '-' in m.group(1) or '(' in m.group(1))
        _set_financial(result, "tax_amount", m.group(2), '-' in m.group(2) or '(' in m.group(2))

    # 模式2：税率
    m = re.search(r'\*[^*]+\*[^\n]+?(\d+%)\s+(-?[\d,]+\.?\d*)', text)
    if m:
        result["tax_rate"] = m.group(1)
        if not result["tax_amount"]:
            _set_financial(result, "tax_amount", m.group(2), '-' in m.group(2) or '(' in m.group(2))
    else:
        m = re.search(r'(?<![年月日\d])(\d{1,2}%)', text)
        if m:
            result["tax_rate"] = m.group(1)

    # 模式3：小写金额
    m = re.search(r'[（(]小写[)）]\s*[¥￥]?(-?[\d,]+\.?\d*)', text)
    if m:
        _set_financial(result, "total", m.group(1), '-' in m.group(1) or '(' in m.group(1))

    # 模式4：数量×单价行
    if not result["amount"]:
        m = re.search(r'\*[^*]+\*[^\n]*?(-?[\d,]+\.\d{2})\s+(\d+%)\s+(-?[\d,]+\.\d{2})', text)
        if m:
            _set_financial(result, "amount", m.group(1),
                           '-' in m.group(1) or '(' in m.group(1))
            if not result["tax_rate"]:
                result["tax_rate"] = m.group(2)
            _set_financial(result, "tax_amount", m.group(3),
                           '-' in m.group(3) or '(' in m.group(3))

    # 模式5：价税合计
    if not result["total"]:
        m = re.search(r'价\s*税\s*合\s*计\s*[¥￥]?(-?[\d,]+\.?\d*)', text)
        if m:
            _set_financial(result, "total", m.group(1), '-' in m.group(1) or '(' in m.group(1))

    # 模式6：从税率后面取金额
    if not result["amount"]:
        m = re.search(r'(-?[\d,]+\.\d{2})\s+' + (result["tax_rate"] or r'\d+%'), text)
        if m:
            _set_financial(result, "amount", m.group(1), '-' in m.group(1) or '(' in m.group(1))

    # 模式7：金额关键字
    if not result["amount"]:
        m = re.search(r'金\s*额\s*[：:]\s*[¥￥]?(-?[\d,]+\.?\d*)', text)
        if m:
            _set_financial(result, "amount", m.group(1), '-' in m.group(1) or '(' in m.group(1))

    # 模式8：税关键字
    if not result["tax_amount"]:
        m = re.search(r'税\s*[：:]\s*[¥￥]?(-?[\d,]+\.?\d*)', text)
        if m:
            _set_financial(result, "tax_amount", m.group(1), '-' in m.group(1) or '(' in m.group(1))

    # 自动计算缺失值
    if result["amount"] and result["tax_rate"] and not result["tax_amount"]:
        try:
            rate = float(result["tax_rate"].replace('%', '')) / 100
            result["tax_amount"] = str(abs(round(float(result["amount"]) * rate, 2)))
        except (ValueError, TypeError):
            pass

    if result["amount"] and result["tax_amount"] and not result["total"]:
        try:
            result["total"] = str(abs(round(
                float(result["amount"]) + float(result["tax_amount"]), 2)))
        except (ValueError, TypeError):
            pass


# ── 区域分割 ──────────────────────────────────


def _extract_sections(text: str) -> tuple[str, str]:
    """分割购买方和销售方区域，返回 (buyer_section, seller_section)"""
    buyer_section = ""
    seller_section = ""
    m = re.search(r'(?:购买方|买方|购方)[\s\n:：信息]*(.+?)(?=销售方|销方|销\s*售|项目|$)',
                  text, re.DOTALL)
    if m:
        buyer_section = m.group(1)
    m = re.search(r'(?:销售方|销方)[\s\n:：信息]*(.+?)(?=备注|合\s*计|项\s*目|$)',
                  text, re.DOTALL)
    if m:
        seller_section = m.group(1)
    return buyer_section, seller_section


# ── 主入口 ────────────────────────────────────


@log_call
def parse_invoice_pdf(pdf_path: str) -> dict:
    """解析发票 PDF，返回字段 dict"""
    fname = os.path.basename(pdf_path)
    company_from_filename = ""
    m = re.match(r'^(\d+)-', fname)
    if m:
        company_from_filename = m.group(1)

    result = {
        "file": fname,
        "pdf_path": os.path.abspath(pdf_path),
        "company": company_from_filename,
        "invoice_type": "",
        "buyer_name": "",
        "buyer_tax_id": "",
        "seller_name": "",
        "amount": "",
        "tax_rate": "",
        "tax_amount": "",
        "total": "",
        "invoice_no": "",
        "invoice_date": "",
        "error": "",
        "is_red": False,
    }

    try:
        full_text = _extract_pdf_text(pdf_path)
        if not full_text:
            result["error"] = "无法提取文字内容（可能是扫描件）"
            return result

        result["invoice_type"] = _detect_invoice_type(full_text)
        result["invoice_no"] = _extract_invoice_no(full_text)
        result["invoice_date"] = _extract_invoice_date(full_text)

        buyer_section, seller_section = _extract_sections(full_text)
        result["buyer_name"], result["buyer_tax_id"] = \
            _extract_buyer_info(full_text, buyer_section)

        seller = _extract_seller_name(full_text, seller_section, result["buyer_name"])
        if seller:
            result["seller_name"] = re.sub(r'^\s*[*●·、,，]\s*', '', seller.strip())
            result["seller_name"] = re.sub(r'\s*[*●·、,，]\s*$', '', result["seller_name"])

        _extract_financials(full_text, result)

        if not result["is_red"]:
            if re.search(r'红字|红冲|作废|负数|负\s*额|冲\s*红', full_text):
                result["is_red"] = True

    except Exception as e:
        result["error"] = str(e)

    # 兜底清洗：file/pdf_path 来自 os.path（可能携带 surrogateescape 解码的
    # 代理字符），error 来自异常消息——统一清洗，保证返回数据可安全 UTF-8 编码
    for k, v in list(result.items()):
        if isinstance(v, str):
            result[k] = _sanitize_str(v)

    log.info("解析结果: %s | 类型=%s | 发票号=%s | 购买方=%s | 金额=%s | 税额=%s",
             fname,
             result["invoice_type"] or "(未识别)",
             result["invoice_no"] or "(无)",
             result["buyer_name"] or "(无)",
             result["amount"] or "(无)",
             result["tax_amount"] or "(无)")
    if result["error"]:
        log.warning("解析异常: %s | %s", fname, result["error"])
    return result


# ── 独立测试入口 ──────────────────────────────

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        for path in sys.argv[1:]:
            print(parse_invoice_pdf(path))
    else:
        print("用法: python invoice_parser.py <pdf文件...>")
