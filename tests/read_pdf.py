import pdfplumber
import sys
import os

sys.stdout.reconfigure(encoding='utf-8')

with pdfplumber.open('C:/Users/dell/Desktop/发票/14786-福建长富乳品有限公司.pdf') as pdf:
    for i, page in enumerate(pdf.pages):
        print(f'=== Page {i+1} ===')
        text = page.extract_text()
        print(repr(text[:2000]) if text else "None")
        print('\n--- Tables ---')
        tables = page.extract_tables()
        for j, table in enumerate(tables):
            print(f'Table {j+1}:')
            for row in table:
                print(row)
        print('\n--- Words ---')
        words = page.extract_words()
        for w in words[:50]:
            print(w)
