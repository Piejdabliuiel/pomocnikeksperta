
from parsers.bik_parser import parse_bik_report
import json
import os

# Using the file found previously
FILE_PATH = "/Users/paweljaje/Documents/WWW/Matryca biki i potwierdzenia wplywow/BIK 25.10..pdf"

def debug_run():
    print(f"--- PARSING: {FILE_PATH} ---")
    if not os.path.exists(FILE_PATH):
        print("File not found!")
        return

    analysis = parse_bik_report(FILE_PATH)
    
    print("\n--- CLOSED LIABILITIES ---")
    print(f"Count: {len(analysis.get('closed_liabilities', []))}")
    print(json.dumps(analysis.get('closed_liabilities', []), indent=2, ensure_ascii=False))

    print("\n--- STATISTICAL LIABILITIES ---")
    print(f"Count: {len(analysis.get('statistical_liabilities', []))}")
    print(json.dumps(analysis.get('statistical_liabilities', []), indent=2, ensure_ascii=False))

if __name__ == "__main__":
    debug_run()
