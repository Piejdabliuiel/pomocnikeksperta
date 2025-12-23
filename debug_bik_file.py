
import pdfplumber
from parsers.bik_parser import parse_bik_report
import json
import os

FILE_PATH = "/Users/paweljaje/Documents/WWW/Matryca biki i potwierdzenia wplywow/BIK 25.10..pdf"

def analyze_pdf():
    print(f"--- ANALYZING: {FILE_PATH} ---")
    
    full_text = ""
    with pdfplumber.open(FILE_PATH) as pdf:
        for page in pdf.pages:
            full_text += page.extract_text() + "\n"
            
    # 1. Check Headers for Sections
    print("\n[SECTION HEADERS CHECK]")
    headers = [
        "Zobowiązania finansowe - w trakcie spłaty",
        "Zobowiązania finansowe - zamknięte",
        "Informacje dodatkowe", # Often statistical section is here or named differently
        "Dane statystyczne",
        "Zapytania kredytowe"
    ]
    for h in headers:
        idx = full_text.find(h)
        print(f"Header '{h}': {'FOUND' if idx != -1 else 'MISSING'} at {idx}")

    # 2. Check Active Liabilities Text (for Bank Name issue)
    print("\n[ACTIVE LIABILITIES SNIPPET]")
    start = full_text.find("Zobowiązania finansowe - w trakcie spłaty")
    if start != -1:
        end = full_text.find("Zobowiązania finansowe - zamknięte")
        if end == -1: end = start + 2000
        print(full_text[start:end][:1000]) # First 1000 chars of active section
        
    # 3. Run Parser
    print("\n[PARSER RESULT]")
    try:
        analysis = parse_bik_report(FILE_PATH)
        print(json.dumps(analysis, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Parser Error: {e}")

if __name__ == "__main__":
    analyze_pdf()
