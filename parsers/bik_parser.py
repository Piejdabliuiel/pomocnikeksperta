import re
import pdfplumber
import os
from datetime import datetime
import os
from datetime import datetime

def parse_bik_report(file_path):
    """
    Parses a BIK report PDF and returns an analysis dict.
    """
    try:
        with pdfplumber.open(file_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                full_text += page.extract_text() + "\n"

        analysis = {
            "score": None,
            "inquiries_12m": 0,
            "active_liabilities": [],
            "closed_liabilities": [],
            "statistical_liabilities": [],
            "alerts": [],
            "summary": {
                "total_installment": 0.0,
                "total_limits": 0.0,
                "mortgage_installment": 0.0
            }
        }

        # 0. PERSONAL DATA & METADATA
        analysis["personal_data"] = {
            "name": None,
            "pesel": None,
            "birth_date": None,
            "report_date": None,
            "is_stale": False
        }
        
        # Date Strategies
        # 1. "Data generowania..."
        # 2. Top right date "25.10.2024 | 16:46"
        
        r_date = None
        # Pattern 1: DD.MM.YYYY | HH:MM
        date_pattern1 = re.search(r"(\d{2}[\.-]\d{2}[\.-]\d{4})\s*\|\s*\d{2}:\d{2}", full_text[:1000])
        if date_pattern1:
            date_str = date_pattern1.group(1).replace('.', '-')
        else:
            # Pattern 2: Explicit label
            date_pattern2 = re.search(r"Data generowania.*?:?\s*(\d{2}[\.-]\d{2}[\.-]\d{4}|\d{4}-\d{2}-\d{2})", full_text)
            date_str = date_pattern2.group(1).replace('.', '-') if date_pattern2 else None

        if date_str:
            try:
                if len(date_str) == 10:
                    if date_str[2] == '-': # DD-MM-YYYY
                        r_date = datetime.strptime(date_str, "%d-%m-%Y")
                    elif date_str[4] == '-': # YYYY-MM-DD
                        r_date = datetime.strptime(date_str, "%Y-%m-%d")
                    
                    if r_date:
                        analysis["personal_data"]["report_date"] = r_date.strftime("%Y-%m-%d")
                        if (datetime.now() - r_date).days > 7:
                            analysis["personal_data"]["is_stale"] = True
                            analysis["alerts"].append({"level": "yellow", "msg": f"Raport starszy niż 7 dni ({analysis['personal_data']['report_date']})"})
            except: pass

        # Name Strategies
        # 1. Look for PESEL line, take line above it (ignoring empty/header lines like "Wskaźnik BIK")
        pesel_idx = full_text.find("PESEL:")
        if pesel_idx != -1:
            # Extract PESEL
            pesel_match = re.search(r"PESEL:?\s*(\d{11})", full_text[pesel_idx:pesel_idx+30])
            if pesel_match:
                p = pesel_match.group(1)
                analysis["personal_data"]["pesel"] = p
                
                # Try to find Name above PESEL
                # Get text up to PESEL
                pre_text = full_text[:pesel_idx].strip()
                lines = pre_text.split('\n')
                # Walk backwards
                found_name = None
                for l in reversed(lines):
                    l = l.strip()
                    if not l: continue
                    # Ignore common labels
                    if any(x in l for x in ["Wskaźnik", "Biuro", "Raport", "Ocena"]): continue
                    # Potential name? Length > 3, not too long
                    if 3 < len(l) < 50:
                        found_name = l
                        break
                
                if found_name:
                    analysis["personal_data"]["name"] = found_name.upper()


                # Decode Birth Date
                try:
                    year = int(p[0:2])
                    month = int(p[2:4])
                    day = int(p[4:6])
                    century = 1900
                    if 21 <= month <= 32: 
                        month -= 20
                        century = 2000
                    elif 41 <= month <= 52:
                        month -= 40
                        century = 2100
                    full_year = century + year
                    birth_date = f"{full_year}-{month:02d}-{day:02d}"
                    analysis["personal_data"]["birth_date"] = birth_date
                except: pass


        # 1. SCORE
        # Patterns:
        # "Ocena punktowa 67/ 100"
        # "Ocena punktowa\nBrak / 100"
        # "Ocena punktowa\n67 / 100"
        # Look for "Ocena punktowa" then nearby "X / 100"
        score_match = re.search(r"Ocena\s*punktowa.*?(\d+|Brak)\s*/\s*100", full_text, re.DOTALL | re.IGNORECASE)
        if score_match:
            val = score_match.group(1).strip()
            if val.lower() == "brak":
                analysis["score"] = 0
            else:
                analysis["score"] = int(val)

        # 2. SECTIONS
        # 2. SECTIONS
        # Define markers with potential dash variations (hyphen, en-dash)
        closed_markers = [
            "Zobowiązania finansowe - zamknięte", 
            "Zobowiązania finansowe – zamknięte",
            "Zobowiązania finansowe — zamknięte"
        ]
        
        stat_markers = [
            "Zobowiązania przetwarzane w celach statystycznych",
            "Zobowiązania przetwarzane w celach  statystycznych" # extra space?
        ]
        
        # --- ACTIVE ---
        # Ends at Closed section start
        active_section = None
        for cm in closed_markers:
            active_section = find_section(full_text, "Zobowiązania finansowe - w trakcie spłaty", cm)
            if active_section: break
            # Try with en-dash for active too
            active_section = find_section(full_text, "Zobowiązania finansowe – w trakcie spłaty", cm)
            if active_section: break
            
        if not active_section:
             active_section = find_section(full_text, "Zobowiązania finansowe - w trakcie spłaty", "Informacje dodatkowe")
        
        if active_section:
            parse_liabilities(active_section, analysis["active_liabilities"], analysis, section_type="active")

        # --- CLOSED ---
        closed_section = None
        # End at Statistical or Info
        end_marker = "Informacje dodatkowe"
        # Try finding stat header first
        for sm in stat_markers:
            if sm in full_text:
                end_marker = sm
                break
        
        for cm in closed_markers:
            closed_section = find_section(full_text, cm, end_marker)
            if not closed_section:
                 # Try finding until Zapytania if Stat is missing
                 closed_section = find_section(full_text, cm, "Zapytania kredytowe")
            if closed_section: break
              
        if closed_section:
            parse_liabilities(closed_section, analysis["closed_liabilities"], analysis, section_type="closed")
             
        if closed_section:
            parse_liabilities(closed_section, analysis["closed_liabilities"], analysis, section_type="closed")
            
        # --- STATISTICAL ---
        stat_section = find_section(full_text, "Zobowiązania przetwarzane w celach statystycznych", "Informacje dodatkowe")
        if not stat_section: 
             stat_section = find_section(full_text, "Zobowiązania przetwarzane w celach statystycznych", "Zapytania kredytowe")

        if stat_section:
             parse_liabilities(stat_section, analysis["statistical_liabilities"], analysis, section_type="statistical")
        
        # --- ZAPYTANIA ---
        inq_idx = full_text.find("Zapytania kredytowe w BIK")
        if inq_idx != -1:
            context = full_text[max(0, inq_idx-50):min(len(full_text), inq_idx+100)]
            pre_match = re.search(r"(\d+)\s*Zapytania kredytowe w BIK", context)
            if pre_match:
                analysis["inquiries_12m"] = int(pre_match.group(1))
            else:
                post_match = re.search(r"z ostatnich 12 miesięcy\s*(\d+)", context)
                if post_match:
                     analysis["inquiries_12m"] = int(post_match.group(1))

        # --- ALERTS GENERATION ---
        generate_alerts(analysis)

        return analysis
    except Exception as e:
        return {"error": str(e), "status": "error"}

def find_section(text, start_marker, end_marker):
    start_idx = text.find(start_marker)
    if start_idx == -1: return None
    end_idx = text.find(end_marker, start_idx)
    if end_idx == -1: return text[start_idx:]
    return text[start_idx:end_idx]

def parse_liabilities(text_section, target_list, analysis_obj, section_type="active"):
    lines = text_section.split('\n')
    current_item = None
    
    # Regex for History Row: Anchored to start to avoid mid-line matches
    # Updated to allow optional 'PLN' (e.g. 0 0 0)
    # Added \b to prevent matching "15" from "159 PLN"
    # Example: "18.08.2024 0 0 0" or "10.03.2024 3273 PLN 413 PLN 86"
    history_pattern = re.compile(r"^(\d{2}\.\d{2}\.\d{4})\s+([\d\.]+)(?:\s*PLN)?\s+([\d\.]+)(?:\s*PLN)?\s+(\d+)\b(?!\s*PLN)")
    
    # Generic Date line for main info
    main_date_pattern = re.compile(r"(\d{2}\.\d{2}\.\d{4})")

    for line in lines:
        line = line.strip()
        if not line: continue
        
        # FAILSAFE: Stop if we hit Inquiries or Info section
        if "Zapytania kredytowe" in line or "Informacje dodatkowe" in line:
            break

        # 1. Detect New Item (Type)
        # Avoid "Kredytobiorca" or headers
        is_type_line = False
        if any(t in line for t in ["Kredyt", "Pożyczka", "Karta", "Limit"]):
            if "Kredytobiorca" not in line and "Zapytania" not in line and "reklamacji" not in line and "Ostatnia" not in line and "Rachunek" not in line:
                 is_type_line = True
        
        if is_type_line:
            # Save previous
            if current_item: 
                finalize_item(current_item, target_list)
            
            current_item = {
                "type": line, 
                "bank": "Unknown", 
                "installment": 0, 
                "amount_left": 0, 
                "limit": 0, 
                "delays": [], # Strings of specific delays
                "closing_date": None,
                "arrears_amount": 0,
                "max_delay_days": 0,
                "max_delay_status": None,
                "description": ""
            }
            continue

        if not current_item: continue

        # 2. History Row Parsing (Priority)
        # Check if line matches history pattern
        hist_match = history_pattern.search(line)
        if hist_match:
            # Check debug
            # print(f"DEBUG HIST MATCH: {line} -> {hist_match.groups()}")
            arrears = float(hist_match.group(3).replace('.', ''))
            days = int(hist_match.group(4))
            
            if days > 0:
                # Add to delays list
                # Prioritize EXACT day strings for frontend
                current_item["delays"].append(f"{days} dni")
                
                # Update Max
                if days > current_item["max_delay_days"]:
                    current_item["max_delay_days"] = days
                    # Map to bucket
                    if days <= 30: current_item["max_delay_status"] = "0-30 dni"
                    elif days <= 90: current_item["max_delay_status"] = "31-90 dni"
                    elif days <= 180: current_item["max_delay_status"] = "91-180 dni"
                    else: current_item["max_delay_status"] = ">180 dni"
                
                if arrears > current_item["arrears_amount"]:
                    current_item["arrears_amount"] = arrears
            continue

        # 3. Bank Detection
        # Heuristic: Uppercase, not Date, no "PLN", no "Kredytobiorca"
        # And usually appearing early in the item text
        if current_item["bank"] == "Unknown":
            # Filter out headers/garbage
            if not main_date_pattern.search(line) and "PLN" not in line and "Kredytobiorca" not in line:
                 if len(line) > 2 and not any(x in line for x in ["Relacja", "Kwota", "Status", "Data", "Historia", "spłaty", "waluta", "kapitał"]):
                     # Garbage check: "64 / 71" or digits
                     if not re.search(r"^\d+(\s*/\s*\d+)?$", line.strip()):
                         current_item["bank"] = line
                     continue
        
        # 4. Main Amounts Parsing (if not history)
        # Look for the line with main amounts (usually has date and PLN)
        # Example: ALIOR BANK 5.250 PLN umowa zakończona dn. 15.08.2024
        match = main_date_pattern.search(line)
        if match and "PLN" in line:
            # Extract Bank Name from START of line if present
            start_index = match.start()
            if start_index > 3:
                potential_name = line[:start_index].strip()
                # Check if it looks like a bank name
                if len(potential_name) > 2 and "Kredytobiorca" not in potential_name:
                     current_item["bank"] = potential_name

            # Extract all amounts
            clean_line = line.replace("PLN", "")
            tokens = clean_line.split()
            amounts = []
            for t in tokens:
                # SKIP DATES detected as amounts (e.g. 16.10.2024 -> 16102024.0)
                if re.match(r"^\d{2}\.\d{2}\.\d{4},?$", t): continue

                clean_t = t.replace(".", "").replace(",", ".")
                if re.match(r"^\d+(\.\d+)?$", clean_t):
                    # Safety check for date-like numbers (YYYYMMDD) - unlikely to be a loan amount in this context?
                    # Limit could be high, but 19M/20M is rare. Dates start with 19/20.
                    if len(clean_t) == 8 and (clean_t.startswith("19") or clean_t.startswith("20")):
                         continue
                    amounts.append(float(clean_t))
            
            # Extract Status string if present "Umorzony", "Windykacja"
            if any(x in line.upper() for x in ["WINDYKACJA", "EGZEKUCJA", "UMORZONY", "ODZYSKANY"]):
                 status_match = re.search(r"(WINDYKACJA|EGZEKUCJA|UMORZONY|ODZYSKANY)", line.upper())
                 if status_match:
                     current_item["max_delay_status"] = status_match.group(1)
            
            # Parse main fields if not set
            if amounts:
                if section_type == "active":
                    # Active: Limit/Orig, Left, Installment
                    if len(amounts) >= 3:
                         current_item["installment"] = amounts[2]
                         current_item["amount_left"] = amounts[1]
                         current_item["limit"] = amounts[0]
                    # Logic for limit vs loan
                    if "karta" not in current_item["type"].lower() and "limit" not in current_item["type"].lower():
                        current_item["limit"] = 0
                    
                    # Add to summary
                    if current_item["installment"] > 0:
                         if "mieszkaniowy" in current_item["type"].lower():
                             analysis_obj["summary"]["mortgage_installment"] = max(analysis_obj["summary"]["mortgage_installment"], analysis_obj["summary"]["mortgage_installment"] + current_item["installment"]) # rough sum
                         else:
                             analysis_obj["summary"]["total_installment"] = max(analysis_obj["summary"]["total_installment"], analysis_obj["summary"]["total_installment"] + current_item["installment"])


            # Extract Closing Date
            # "zakończona dn. 15.08.2024" or just "15.08.2024"
            date_matches = main_date_pattern.findall(line)
            if date_matches:
                # Usually last date is closing date or current status date
                current_item["closing_date"] = date_matches[-1]
            
            continue # Done with main line

        # 5. Capture other info (e.g. Consent info)
        current_item["description"] += line + " "

    # Add last item
    if current_item: 
        finalize_item(current_item, target_list)
    
    # POST-PROCESSING: Move 'Brak zgody' items to statistical_liabilities
    if section_type == "closed":
        to_remove = []
        for item in target_list:
            desc = item["description"].upper()
            if "BRAK ZGODY" in desc or "ODWOŁANA" in desc or "PRZETWARZANE W CELACH STATYSTYCZNYCH" in desc:
                # Move to statistical
                analysis_obj["statistical_liabilities"].append(item)
                to_remove.append(item)
        
        for item in to_remove:
            target_list.remove(item)

def finalize_item(item, target_list):
    # HELPER: Clean Bank Name and Filter Garbage
    bank = item["bank"]
    
    # 1. Cleaning: Remove digits/amounts/dates
    # "ALIOR BANK 2.342 PLN ..." -> "ALIOR BANK"
    # Find first digit or "PLN"
    match_digit = re.search(r"\d", bank)
    if match_digit:
        bank = bank[:match_digit.start()]
    
    if "PLN" in bank:
        bank = bank.split("PLN")[0]
        
    # Remove clutter words
    for bad in ["umowa", "zakończona", "dn.", "dnia", "kredyt", "pożyczka"]:
        if bad in bank.lower():
            # Cut off from that word onwards usually, or just remove
            # Usually these come after the name
            idx = bank.lower().find(bad)
            if idx != -1:
                bank = bank[:idx]
                
    item["bank"] = bank.strip().replace("  ", " ")
    
    # 2. Garbage Filter
    # Reject if bank is empty or blacklisted phrase
    b_upper = item["bank"].upper()
    if not b_upper or len(b_upper) < 2: return # Skip empty
    if "DO ZOBOWIĄZANIA" in b_upper or "DO SPŁATY" in b_upper or "KWOTA KREDYTU" in b_upper: return
    
    target_list.append(item)


def generate_alerts(analysis):
    # Inquiries
    if analysis["inquiries_12m"] > 5:
        analysis["alerts"].append({"level": "red", "msg": f"Duża liczba zapytań w ost. 12 mies.: {analysis['inquiries_12m']} (>5)"})
    elif analysis["inquiries_12m"] >= 3:
        analysis["alerts"].append({"level": "yellow", "msg": f"Podwyższona liczba zapytań: {analysis['inquiries_12m']} (3-5)"})

    # Active Liabilities Delays (>30 days check)
    # Statuses often: "0-30", "31-90", "91-180"
    for l in analysis["active_liabilities"]:
         for d in l["delays"]: # d is a string like "31-90" or "WINDYKACJA"
             if any(x in d for x in ["31-", "windykacja", "egzekucja", "odzysk"]): 
                 analysis["alerts"].append({"level": "red", "msg": f"Opóźnienie >30 dni w {l['bank']} ({l['type']}): {d}"})
    
    # Closed Liabilities Delays (History)
    for l in analysis["closed_liabilities"]:
         for d in l["delays"]:
             if any(x in d for x in ["31-", "windykacja", "egzekucja"]):
                 analysis["alerts"].append({"level": "yellow", "msg": f"Historyczne opóźnienie >30 dni w {l['bank']} (Zamknięty)"})

