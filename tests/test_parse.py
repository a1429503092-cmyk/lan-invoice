import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.stdout.reconfigure(encoding='utf-8')

from invoice_parser import parse_invoice_pdf

if __name__ == "__main__":
    test_path = os.environ.get('TEST_PDF') or 'C:/Users/dell/Desktop/发票/14786-福建长富乳品有限公司.pdf'
    data = parse_invoice_pdf(test_path)
    for k, v in data.items():
        print(f"  {k:20s}: {v}")
