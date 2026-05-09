import sys
sys.stdout.reconfigure(encoding='utf-8')

# 只测试解析函数，不启动 GUI
import re
import pdfplumber

def parse_invoice_pdf(pdf_path: str) -> dict:
    result = {
        "file": "",
        "buyer_name": "",
        "buyer_tax_id": "",
        "amount": "",
        "tax_rate": "",
        "tax_amount": "",
        "total": "",
        "invoice_no": "",
        "invoice_date": "",
        "error": ""
    }
    try:
        with pdfplumber.open(pdf_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    full_text += t + "\n"

        if not full_text:
            result["error"] = "无法提取文字内容"
            return result

        m = re.search(r'发票号码[：:]\s*(\d+)', full_text)
        if m: result["invoice_no"] = m.group(1)

        m = re.search(r'开票日期[：:]\s*(\d{4}年\d{2}月\d{2}日)', full_text)
        if m: result["invoice_date"] = m.group(1)

        m = re.search(r'名称[：:]\s*(.+?)(?:\s+销\s|销\s*名称|统一社会|$)', full_text, re.MULTILINE)
        if m:
            result["buyer_name"] = m.group(1).strip()
        if result["buyer_name"]:
            result["buyer_name"] = re.split(r'\s+销\s*$|\s+销\s+名称', result["buyer_name"])[0].strip()

        ids = re.findall(r'统一社会信用代码/纳税人识别号[：:]\s*([A-Z0-9]+)', full_text)
        if ids: result["buyer_tax_id"] = ids[0]

        m = re.search(r'合\s*计\s+[¥￥]?([\d,]+\.?\d*)\s+[¥￥]?([\d,]+\.?\d*)', full_text)
        if m:
            result["amount"] = m.group(1).replace(',', '')
            result["tax_amount"] = m.group(2).replace(',', '')

        m = re.search(r'\*[^*]+\*[^\n]+?(\d+%)\s+([\d,]+\.?\d*)', full_text)
        if m:
            result["tax_rate"] = m.group(1)

        m = re.search(r'[（(]小写[)）]\s*[¥￥]?([\d,]+\.?\d*)', full_text)
        if m: result["total"] = m.group(1).replace(',', '')

    except Exception as e:
        result["error"] = str(e)

    return result


data = parse_invoice_pdf('C:/Users/dell/Desktop/发票/14786-福建长富乳品有限公司.pdf')
for k, v in data.items():
    print(f"  {k:20s}: {v}")
