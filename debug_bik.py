
from parsers.bik_parser import parse_bik_report, parse_liabilities
import json
from datetime import datetime

# Simulated text based on User Screenshots and typical BIK header
sample_text = """
RAPORT BIK                             25.10.2024 | 16:46
Wskaźnik BIK
                                       Paweł Heuser
                                       PESEL: 94060104211
Płacę bez opóźnień

Ocena punktowa BIK
Ocena: Niska
52 / 100

Zobowiązania finansowe - w trakcie spłaty
Kredyt gotówkowy, pożyczka bankowa
05.11.2023 6.174 PLN 6.174 PLN 159 PLN 0 BRAK
ALIOR BANK SA

Karta kredytowa
10.10.2020 5.000 PLN 0 PLN ND BRAK
MBANK
"""

def test_parser():
    analysis = {
        "score": None,
        "personal_data": {},
        "active_liabilities": [],
        "closed_liabilities": [],
        "alerts": [],
        "summary": {"total_installment": 0.0, "total_limits": 0.0, "mortgage_installment": 0.0}
    }
    
    print("--- PARSING HEADER ---")
    # Simulate header parsing logic here before moving to main file
    lines = sample_text.split('\n')
    for line in lines:
        if "Data generowania" in line:
            print(f"Found Date: {line}")
        if "PESEL" in line:
            print(f"Found PESEL: {line}")
            
    print("\n--- PARSING LIABILITIES ---")
    # Extract just the liabilities part for function test
    liab_section = sample_text.split("Zobowiązania finansowe - w trakcie spłaty")[1]
    parse_liabilities(liab_section, analysis["active_liabilities"], analysis)
    
    print(json.dumps(analysis["active_liabilities"], indent=2, ensure_ascii=False))

if __name__ == "__main__":
    test_parser()
