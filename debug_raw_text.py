
import pdfplumber
import os

FILE_PATH = "/Users/paweljaje/Documents/WWW/Matryca biki i potwierdzenia wplywow/BIK 25.10..pdf"

def find_section(text, start_marker, end_marker):
    start_idx = text.find(start_marker)
    if start_idx == -1: return None
    end_idx = text.find(end_marker, start_idx)
    if end_idx == -1: return text[start_idx:]
    return text[start_idx:end_idx]

def run():
    with pdfplumber.open(FILE_PATH) as pdf:
        full_text = ""
        for page in pdf.pages:
            full_text += page.extract_text() + "\n"

    print("--- FULL TEXT LENGTH:", len(full_text))
    
    print("\n=== DEBUGGING SPECIFIC BLOCKS ===")
    lines = full_text.split('\n')
    
    # helper
    def print_context(keyword, lines, count=2):
        print(f"\n--- Searching for '{keyword}' ---")
        found = 0
        for i, line in enumerate(lines):
            if keyword in line.upper():
                print(f"MATCH @ Line {i}: {line}")
                for j in range(1, 25):
                    if i+j < len(lines):
                        print(f"  +{j}: {lines[i+j]}")
                found += 1
                if found >= count: break

    print_context("SANTANDER", lines)
    print_context("ALIOR", lines, count=3)

    closed = find_section(full_text, "Zobowiązania finansowe - zamknięte", "Zobowiązania przetwarzane w celach statystycznych")
    if not closed:
        closed = find_section(full_text, "Zobowiązania finansowe - zamknięte", "Informacje dodatkowe")
    
    print("\n=== RAW CLOSED SECTION ===")
    print(closed)

    # RAW STATISTICAL SECTION
    stat = find_section(full_text, "Zobowiązania przetwarzane w celach statystycznych", "Informacje dodatkowe")
    if not stat:
        stat = find_section(full_text, "Zobowiązania przetwarzane w celach statystycznych", "Zapytania kredytowe")
        
    print("\n=== RAW STATISTICAL SECTION ===")
    print(stat)

if __name__ == "__main__":
    run()
