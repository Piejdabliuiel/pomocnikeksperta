"""
Native BIK Report Parser - No LLM Dependencies
Deterministic, fast, and free.
"""

import re
from datetime import datetime


# Non-bank lenders (pozabankowe) - these are red flags for traditional banks
POZABANKOWE_COMPANIES = [
    "ALLEGRO PAY", "TWISTO", "VIVUS", "PROVIDENT", "WONGA", "LENDON",
    "NETCREDIT", "SZYBKA GOTÓWKA", "INCREDIT", "AASA", "HAPIPOŻYCZKI",
    "FILARUM", "WANDOO", "KUKI", "SOLVEN", "POŻYCZKA PLUS", "EXTRA PORTFEL",
    "KREDITO24", "FERRATUM", "EKSPRES KASA", "SMART POŻYCZKA", "POZYCZKOMAT",
    "TAKTO FINANSE", "CREDIT-AGRICOLE", "OPTIMA", "BOCIAN", "EVEREST",
    "PROFI CREDIT", "DELTA", "MONEY GRATIS", "RAPIDA", "MILOAN"
]


def parse_bik_native(full_text):
    """
    Parse BIK report text using pattern matching and section detection.
    Returns a structured dictionary compatible with the frontend.
    """
    lines = full_text.split('\n')
    
    result = {
        "personal_data": {
            "name": None,
            "pesel": None,
            "birth_date": None,
            "report_date": None,
            "is_stale": False
        },
        "score": None,
        "inquiries_12m": 0,
        "summary": {
            "total_installment": 0,
            "total_limits": 0,
            "mortgage_installment": 0
        },
        "active_liabilities": [],
        "closed_liabilities": [],
        "statistical_liabilities": [],
        "alerts": [],
        "parser_type": "NATIVE"
    }
    
    # === PHASE 1: Header Extraction (First 50 lines) ===
    header_text = '\n'.join(lines[:50])
    
    # Date: DD.MM.YYYY format at the start
    date_match = re.search(r'^(\d{2}\.\d{2}\.\d{4})', header_text)
    if date_match:
        try:
            dt = datetime.strptime(date_match.group(1), "%d.%m.%Y")
            result["personal_data"]["report_date"] = dt.strftime("%Y-%m-%d")
        except:
            pass
    
    # PESEL: 11 digits
    pesel_match = re.search(r'PESEL[:\s]*(\d{11})', header_text)
    if pesel_match:
        result["personal_data"]["pesel"] = pesel_match.group(1)
    
    # Name: Line after date, before PESEL (usually line 3)
    # Handle both "Paweł Heuser" and "SZYMON MACKIEWICZ" formats
    for i, line in enumerate(lines[:10]):
        line_clean = line.strip()
        # Skip if line has PESEL or other keywords
        if 'PESEL' in line_clean or 'Wskaźnik' in line_clean or ':' in line_clean:
            continue
        # Match: 2+ words, each starting with uppercase letter
        if re.match(r'^[A-ZĄĆĘŁŃÓŚŹŻ][A-ZĄĆĘŁŃÓŚŹŻa-ząćęłńóśźż]+(?:\s+[A-ZĄĆĘŁŃÓŚŹŻ][A-ZĄĆĘŁŃÓŚŹŻa-ząćęłńóśźż]+)+$', line_clean):
            # Skip if it's a date line
            if not re.search(r'\d{2}\.\d{2}\.\d{4}', line_clean):
                result["personal_data"]["name"] = line_clean.title()  # Normalize to Title Case
                break
    
    # Score: "52/ 100" or "52 / 100" pattern
    score_match = re.search(r'(\d{1,3})\s*/\s*100', header_text)
    if score_match:
        result["score"] = int(score_match.group(1))
    
    # Inquiries: Line with pattern "14 19 0 12" (4 numbers) near "Zapytania"
    # Search in first 100 lines (may be after summary table)
    extended_text = '\n'.join(lines[:100])
    inquiries_match = re.search(r'^(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$', extended_text, re.MULTILINE)
    if inquiries_match:
        result["inquiries_12m"] = int(inquiries_match.group(1))
    
    # === PHASE 2: Section Detection ===
    section_markers = {
        "active": r'Zobowiązania finansowe.*w trakcie spłaty',
        "closed": r'Zobowiązania finansowe.*zamknięte',
        "statistical": r'Zobowiązania.*przetwarzane w celach statystycznych'
    }
    
    current_section = None
    section_lines = {"active": [], "closed": [], "statistical": []}
    
    for i, line in enumerate(lines):
        # Check for section headers
        if re.search(section_markers["statistical"], line, re.IGNORECASE):
            current_section = "statistical"
        elif re.search(section_markers["closed"], line, re.IGNORECASE):
            current_section = "closed"
        elif re.search(section_markers["active"], line, re.IGNORECASE):
            current_section = "active"
        elif current_section:
            section_lines[current_section].append((i, line))
    
    # === PHASE 3: Parse Active Liabilities ===
    result["active_liabilities"] = parse_active_section(section_lines["active"], lines)
    
    # === PHASE 4: Parse Closed Liabilities ===
    result["closed_liabilities"] = parse_closed_section(section_lines["closed"], lines)
    
    # === PHASE 5: Parse Statistical Liabilities ===
    result["statistical_liabilities"] = parse_statistical_section(section_lines["statistical"], lines)
    
    # === PHASE 6: Calculate Summary ===
    for liability in result["active_liabilities"]:
        result["summary"]["total_installment"] += liability.get("installment", 0)
        result["summary"]["total_limits"] += liability.get("limit", 0)
    
    # === PHASE 7: Detect Pozabankowe (Non-Bank Lenders) ===
    # These are red flags for traditional banks
    for liability in result["active_liabilities"]:
        bank = liability.get("bank", "").upper()
        for company in POZABANKOWE_COMPANIES:
            if company.upper() in bank:
                liability["is_pozabankowe"] = True
                result["alerts"].append({
                    "type": "POZABANKOWE_ACTIVE",
                    "severity": "WARNING",
                    "message": f"Aktywna pożyczka pozabankowa: {liability.get('bank')}",
                    "bank": liability.get("bank")
                })
                break
    
    for liability in result["closed_liabilities"]:
        bank = liability.get("bank", "").upper()
        for company in POZABANKOWE_COMPANIES:
            if company.upper() in bank:
                liability["is_pozabankowe"] = True
                result["alerts"].append({
                    "type": "POZABANKOWE_CLOSED",
                    "severity": "INFO",
                    "message": f"Zamknięta pożyczka pozabankowa: {liability.get('bank')}",
                    "bank": liability.get("bank")
                })
                break
    
    return result


def parse_active_section(section_lines, all_lines):
    """Parse active liabilities from summary table only (not history)."""
    liabilities = []
    
    # Known bank/lender names (including pozabankowe)
    bank_names = ["SANTANDER CONSUMER BANK", "MBANK WYDZIAŁ BANKOWOŚCI", "ALIOR BANK", 
                  "CREDIT AGRICOLE", "ING BANK ŚLĄSKI", "ING BANK",
                  "SANTANDER", "MBANK", "PKO BP", "PKO", "ING", "BNP", "CITI", "GETIN", 
                  "MILLENNIUM", "NEST BANK", "SKOK", "BANK MILLENNIUM", "ELEKTRONICZNEJ",
                  # Pozabankowe
                  "ALLEGRO PAY", "TWISTO", "VIVUS", "PROVIDENT", "WONGA", "LENDON",
                  "NETCREDIT", "INCREDIT", "AASA", "FILARUM", "WANDOO", "KUKI",
                  "PROFI CREDIT", "FERRATUM", "SP. Z O.O."]
    
    # Credit types that use LIMIT instead of Amount Left
    limit_based_types = ["kredyt odnawialny", "karta kredytowa", "debet", "limit"]
    
    # Find where summary table ends (at "Łącznie" line)
    summary_end_idx = len(section_lines)
    for idx, (line_num, line) in enumerate(section_lines):
        if line.strip().startswith("Łącznie"):
            summary_end_idx = idx
            break
        # Also stop if we hit detailed section
        if "Informacje szczegółowe" in line or "Historia spłaty" in line:
            summary_end_idx = idx
            break
    
    # Only process summary table lines
    summary_lines = section_lines[:summary_end_idx]
    lines_list = [(i, line) for i, line in summary_lines]
    
    # Track current credit type
    current_type = "Kredyt"
    pending_bank = None  # Bank name waiting to be matched with amounts
    
    for idx, (line_num, line) in enumerate(lines_list):
        line_clean = line.strip()
        
        # Skip empty lines
        if not line_clean:
            continue
        
        # Detect credit type
        if "kredyt odnawialny" in line_clean.lower():
            current_type = "Kredyt odnawialny"
            continue
        elif "karta kredytowa" in line_clean.lower():
            current_type = "Karta kredytowa"
            continue
        elif "kredyt gotówkowy" in line_clean.lower() or "pożyczka" in line_clean.lower():
            current_type = "Kredyt gotówkowy"
            continue
        elif "kredyt mieszkaniowy" in line_clean.lower() or "hipot" in line_clean.lower():
            current_type = "Kredyt hipoteczny"
            continue
        
        # Extract amounts properly - look for patterns like "167.837 PLN" or "0" or "1.054 PLN"
        # First, remove the date from the line to avoid confusion
        date_match = re.search(r'\d{2}\.\d{2}\.\d{4}', line_clean)
        has_date = bool(date_match)
        
        if has_date:
            # Get text after the date (where amounts should be)
            after_date = line_clean[date_match.end():].strip()
            
            # Look for PLN amounts in after_date section
            # Pattern: number followed by PLN, or standalone number followed by space/ND
            amounts = []
            
            # Find all explicitly marked PLN amounts
            pln_amounts = re.findall(r'([\d.,]+)\s*PLN', after_date)
            amounts.extend(pln_amounts)
            
            # Also find standalone "0" which often means 0 PLN
            # But only if followed by space or ND or BRAK
            standalone_zeros = re.findall(r'\b(0)\s+(?:ND|BRAK|PLN|\d)', after_date)
            amounts.extend(standalone_zeros)
            
        else:
            amounts = []
        
        # This is likely a liability line if it has date + at least 2 amounts
        if has_date and len(amounts) >= 2:
            # Extract amounts
            def to_float(s):
                try:
                    return float(s.replace('.', '').replace(',', '.'))
                except:
                    return 0.0
            
            original_amount = to_float(amounts[0]) if len(amounts) > 0 else 0
            amount_left = to_float(amounts[1]) if len(amounts) > 1 else 0
            
            # Installment: either third amount or 0 if "ND"
            installment = 0.0
            if len(amounts) > 2:
                installment = to_float(amounts[2])
            elif "ND" in line_clean.upper():
                installment = 0.0  # ND = Nie Dotyczy
            
            # Find bank name
            bank = "Nieznany Bank"
            
            # Check if bank is on same line (before the date)
            date_match = re.search(r'\d{2}\.\d{2}\.\d{4}', line_clean)
            if date_match:
                before_date = line_clean[:date_match.start()].strip()
                if before_date and any(name.upper() in before_date.upper() for name in bank_names):
                    bank = before_date
            
            # If not found, check next line
            if bank == "Nieznany Bank" and idx + 1 < len(lines_list):
                next_line = lines_list[idx + 1][1].strip()
                if any(name.upper() in next_line.upper() for name in bank_names):
                    bank = next_line
            
            # If still not found, use pending bank from previous line
            if bank == "Nieznany Bank" and pending_bank:
                bank = pending_bank
            
            # Determine if this is limit-based
            is_limit_based = any(lt in current_type.lower() for lt in limit_based_types)
            
            liability = {
                "bank": bank,
                "type": current_type,
                "installment": installment,
                "amount_left": amount_left,
                "limit": original_amount if is_limit_based else 0,
                "original_amount": original_amount,
                "is_limit_based": is_limit_based,
                "max_delay_status": "OK",
                "max_delay_days": 0,
                "delays": ["OK"]
            }
            liabilities.append(liability)
            
            # Reset for next entry
            current_type = "Kredyt"
            pending_bank = None
        
        # Check if this line is just a bank name (for next iteration)
        elif any(name.upper() in line_clean.upper() for name in bank_names) and not has_date:
            pending_bank = line_clean
    
    # If no liabilities found, try alternate parsing
    if not liabilities:
        liabilities = parse_active_alternate(section_lines, all_lines)
    
    return liabilities


def parse_active_alternate(section_lines, all_lines):
    """Alternate parsing for active section - look in detailed info."""
    liabilities = []
    
    # Look for patterns like:
    # "SANTANDER CONSUMER BANK" (line 41)
    # "Kredytobiorca 9.399 PLN 6.174 PLN 60 Otwarte" (line 50)
    
    full_text = '\n'.join([line for _, line in section_lines])
    
    # Find bank + amount patterns in detailed section
    bank_names = re.findall(r'^([A-ZĄĆĘŁŃÓŚŹŻ][A-ZĄĆĘŁŃÓŚŹŻ\s]+(?:BANK|CONSUMER BANK|BANKOWOŚCI))$', full_text, re.MULTILINE)
    
    for bank in bank_names:
        # Look for "Kwota raty" value nearby
        rata_match = re.search(rf'{re.escape(bank)}.*?(\d+)\s*PLN.*?Kredytobiorca.*?([\d.,]+)\s*PLN\s+([\d.,]+)\s*PLN', full_text, re.DOTALL)
        if rata_match:
            def to_float(s):
                return float(s.replace('.', '').replace(',', '.'))
            
            liabilities.append({
                "bank": bank.strip(),
                "type": "Kredyt",
                "installment": to_float(rata_match.group(1)),
                "amount_left": to_float(rata_match.group(3)),
                "limit": to_float(rata_match.group(2)),
                "max_delay_status": "OK",
                "max_delay_days": 0,
                "delays": ["OK"]
            })
    
    return liabilities


def parse_closed_section(section_lines, all_lines):
    """Parse closed liabilities from section text."""
    liabilities = []
    
    full_text = '\n'.join([line for _, line in section_lines])
    
    # Known bank names to look for (order matters - more specific first)
    bank_names = ["SANTANDER CONSUMER BANK", "MBANK WYDZIAŁ BANKOWOŚCI", "ALIOR BANK", "SANTANDER", "MBANK", "PKO", "ING", "BNP", "CITI", "GETIN", "MILLENNIUM", "CONSUMER BANK"]
    
    # Find each bank entry with closing date pattern
    # Pattern: "z dn. DD.MM.YYYY" ... "umowa zakończona dn. DD.MM.YYYY"
    entry_pattern = re.compile(
        r'z dn\.\s*(\d{2}\.\d{2}\.\d{4})\s*'
        r'([\d.,]+)\s*PLN\s*'
        r'umowa zakończona dn\.\s*(\d{2}\.\d{2}\.\d{4})',
        re.IGNORECASE
    )
    
    for match in entry_pattern.finditer(full_text):
        start_date = match.group(1)
        amount = match.group(2)
        closing_date = match.group(3)
        
        # Look backwards for bank name (within 200 chars before match)
        context_start = max(0, match.start() - 200)
        context = full_text[context_start:match.start()]
        
        bank = "Nieznany Bank"
        for name in bank_names:
            if name.upper() in context.upper():
                # Get the full line containing the bank name
                for line in context.split('\n'):
                    if name.upper() in line.upper():
                        bank = line.strip()
                        break
                break
        
        # Clean bank name (remove trailing garbage)
        bank = re.sub(r'\s+(Kredyt|Karta|Pożyczka).*$', '', bank, flags=re.IGNORECASE)
        
        # Extract max delay from history after this entry
        max_delay = extract_max_delay(full_text, match.end())
        
        liabilities.append({
            "bank": bank,
            "type": "Kredyt zamknięty",
            "closing_date": closing_date,
            "max_delay_days": max_delay,
            "max_delay_status": f"{max_delay} dni" if max_delay > 0 else "OK",
            "arrears_amount": 0,
            "delays": [f"{max_delay} dni" if max_delay > 0 else "OK"]
        })
    
    return liabilities


def parse_statistical_section(section_lines, all_lines):
    """Parse statistical liabilities from section text."""
    liabilities = []
    
    full_text = '\n'.join([line for _, line in section_lines])
    
    # Known bank names to look for (order matters - more specific first)
    bank_names = ["SANTANDER CONSUMER BANK", "MBANK WYDZIAŁ BANKOWOŚCI", "ALIOR BANK", "SANTANDER", "MBANK", "PKO", "ING", "BNP", "CITI", "GETIN", "MILLENNIUM", "CONSUMER BANK"]
    
    # Pattern: "X PLN umowa zakończona dn. DD.MM.YYYY"
    entry_pattern = re.compile(
        r'([\d.,]+)\s*PLN\s*umowa zakończona dn\.\s*(\d{2}\.\d{2}\.\d{4})',
        re.IGNORECASE
    )
    
    for match in entry_pattern.finditer(full_text):
        amount = match.group(1)
        closing_date = match.group(2)
        
        # Look backwards for bank name (within 200 chars before match)
        context_start = max(0, match.start() - 200)
        context = full_text[context_start:match.start()]
        
        bank = "Nieznany Bank"
        for name in bank_names:
            if name.upper() in context.upper():
                # Get the full line containing the bank name
                for line in context.split('\n'):
                    if name.upper() in line.upper():
                        bank = line.strip()
                        break
                break
        
        # Clean bank name (keep only bank part)
        bank = re.sub(r'\s+\d+.*$', '', bank)  # Remove amounts after bank name
        bank = re.sub(r'\s+(Kredyt|Karta|Pożyczka).*$', '', bank, flags=re.IGNORECASE)
        
        # Extract max delay from history after this entry
        max_delay = extract_max_delay(full_text, match.end())
        
        liabilities.append({
            "bank": bank,
            "type": "Statystyczny",
            "closing_date": closing_date,
            "max_delay_days": max_delay,
            "max_delay_status": f"{max_delay} dni" if max_delay > 0 else "OK",
            "delays": [f"{max_delay} dni" if max_delay > 0 else "OK"]
        })
    
    return liabilities


def extract_max_delay(text, start_pos):
    """Extract maximum delay days from history section near given position."""
    # Look at next 50 lines/1000 chars for delay pattern
    search_text = text[start_pos:start_pos + 3000]
    
    # Pattern: "DD.MM.YYYY amount amount DELAY_DAYS" where DELAY_DAYS > 0
    delay_pattern = re.compile(r'\d{2}\.\d{2}\.\d{4}\s+[\d.,]+\s*(?:PLN)?\s+[\d.,]+\s*(?:PLN)?\s+(\d+)')
    
    max_delay = 0
    for match in delay_pattern.finditer(search_text):
        delay = int(match.group(1))
        if delay > max_delay:
            max_delay = delay
    
    return max_delay
