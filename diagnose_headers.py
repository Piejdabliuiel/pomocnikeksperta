
import pdfplumber
import re

pdf_path = "uploads/BIK_25.10..pdf"

def find_section(text, start_marker, end_marker):
    start_idx = text.find(start_marker)
    if start_idx == -1: return None
    end_idx = text.find(end_marker, start_idx)
    if end_idx == -1: return text[start_idx:]
    return text[start_idx:end_idx]

try:
    with pdfplumber.open(pdf_path) as pdf:
        full_text = "\n".join([page.extract_text() or "" for page in pdf.pages])
    
    print(f"Total Length: {len(full_text)}")
    
    print("\n--- HEADER ANALYSIS ---")
    for line in full_text.split('\n'):
        if "Zobowiązania" in line:
            print(f"HEADER FOUND: '{line.strip()}' Hex: {line.strip().encode('utf-8').hex()}")

    print("\n--- CURRENT LOGIC SIMULATION ---")
    closed_markers = [
        "Zobowiązania finansowe - zamknięte", 
        "Zobowiązania finansowe – zamknięte",
        "Zobowiązania finansowe — zamknięte"
    ]
    
    active_section = None
    used_marker = None
    for cm in closed_markers:
        active_section = find_section(full_text, "Zobowiązania finansowe - w trakcie spłaty", cm)
        if active_section:
            used_marker = cm
            break
            
    print(f"Active Section Split Marker: {used_marker}")
    if active_section:
        print(f"Active Section Length: {len(active_section)}")
        print("Active Section Last 200 chars:")
        print(active_section[-200:])
    else:
        print("Active Section NOT FOUND using Closed Markers.")
        
except Exception as e:
    print(f"Error: {e}")
