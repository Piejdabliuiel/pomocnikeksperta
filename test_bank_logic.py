
from parsers.bik_parser import parse_liabilities
import json

sample_text = """
Kredyt gotówkowy, pożyczka bankowa
16.10.2024 6.143 PLN 6.174 PLN 159 PLN BRAK
SANTANDER CONSUMER BANK
"""

def test():
    analysis = {
        "active_liabilities": [],
        "summary": {"total_installment": 0.0, "total_limits": 0.0, "mortgage_installment": 0.0}
    }
    parse_liabilities(sample_text, analysis["active_liabilities"], analysis)
    print(json.dumps(analysis["active_liabilities"], indent=2, ensure_ascii=False))

if __name__ == "__main__":
    test()
