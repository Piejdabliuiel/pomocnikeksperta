import pdfplumber
import re
import os

def parse_pdf(file_path):
    """
    Parses a single PDF bank confirmation and extracts:
    - Date (Data operacji/księgowania)
    - Amount (Kwota)
    - Title (Tytuł)
    - Sender (Nadawca)
    - Recipient (Odbiorca/Właściciel)
    """
    try:
        with pdfplumber.open(file_path) as pdf:
            page = pdf.pages[0]
            text = page.extract_text()
            
            if not text:
                return {"filename": os.path.basename(file_path), "error": "No text extracted"}

            # --- COMMON VARIABLES ---
            amount = 0.0
            date = ""
            title = ""
            sender = ""
            recipient = "Unknown"
            account_number = "Unknown Account"

            # --- MBANK LOGIC ---
            if "mBank S.A." in text or "mBankS.A." in text or "mBank" in text:
                # Amount: Kwotaprzelewu: 3376,53PLN
                amt_match = re.search(r"Kwota\s*przelewu:\s*([\d\s\.,]+)PLN", text, re.IGNORECASE)
                if amt_match:
                    amount = float(amt_match.group(1).replace(" ", "").replace(",", "."))
                
                # Date: Dataoperacji: 2024-12-10
                date_match = re.search(r"Data\s*operacji:\s*(\d{4}-\d{2}-\d{2})", text, re.IGNORECASE)
                if date_match:
                    date = date_match.group(1)
                
                rec_match = re.search(r"Odbiorca:\s*(.+)", text, re.IGNORECASE)
                if rec_match: recipient = rec_match.group(1).strip()
                
                snd_match = re.search(r"Nadawca:\s*(.+)", text, re.IGNORECASE)
                if snd_match: sender = snd_match.group(1).strip()
                
                ttl_match = re.search(r"Tytuł\s*operacji:\s*(.+)", text, re.IGNORECASE)
                if ttl_match: title = ttl_match.group(1).strip()

                # Account Number for mBank (Odbiorca usually has account details nearby or look for "Rachunek odbiorcy")
                # mBank PDF usually: "Rachunek odbiorcy: ... " or just under Odbiorca. 
                # Let's try generic fallback for 26 digit number if specific label missing
                acc_match = re.search(r"Rachunek\s*odbiorcy:\s*([\d\s]{20,})", text, re.IGNORECASE)
                if not acc_match:
                     # Try generic pattern for IBAN/Account line
                     acc_match = re.search(r"(\d{2}[ \d]{20,})", text)
                
                if acc_match:
                     account_number = acc_match.group(1).replace(" ", "").strip()


            # --- PEKAO LOGIC ---
            elif "Bank Pekao S.A." in text or "Pekao" in text:
                # Amount
                amt_match = re.search(r"Kwota\s*uznania:\s*([\d\.,]+)\s*PLN", text, re.IGNORECASE)
                if not amt_match:
                    amt_match = re.search(r"Kwota\s*operacji:\s*([\d\.,]+)\s*PLN", text, re.IGNORECASE)
                
                if amt_match:
                    raw_amt = amt_match.group(1).replace(".", "").replace(",", ".")
                    try: amount = float(raw_amt)
                    except: pass
                
                # Date
                date_match = re.search(r"Data\s*księgowania:\s*(\d{2}/\d{2}/\d{4})", text, re.IGNORECASE)
                if date_match:
                    d, m, y = date_match.group(1).split("/")
                    date = f"{y}-{m}-{d}"

                rec_match = re.search(r"Właściciel:\s*(.+)", text, re.IGNORECASE)
                if rec_match: recipient = rec_match.group(1).strip()
                
                # Account Number: "Numer rachunku: 88 1240 ..."
                acc_match = re.search(r"Numer\s*rachunku:\s*([\d\s]{20,})", text, re.IGNORECASE)
                if acc_match:
                    account_number = acc_match.group(1).replace(" ", "").strip()
                
                # Title heuristics
                lines = text.split('\n')
                for line in lines:
                    if "TYTUŁ:" in line.upper(): # Explicit title
                        title = line.split(":", 1)[1].strip()
                        break
                    if "WYNAGRODZENIE" in line.upper() or "PŁACE" in line.upper() or "PRZELEW" in line.upper():
                         if "TYP OPERACJI" not in line.upper():
                             title = line.strip()
                             break

            # --- UNKNOWN BANK ---
            else:
                return {
                    "filename": os.path.basename(file_path),
                    "error": "Nie rozpoznano formatu banku (nie mBank/Pekao)",
                    "status": "error"
                }

            if amount == 0:
                 return {
                    "filename": os.path.basename(file_path),
                    "error": "Nie udało się znaleźć kwoty przelewu",
                    "status": "error"
                }
            
            return {
                "filename": os.path.basename(file_path),
                "date": date or "Nieznana Data",
                "amount": amount,
                "title": title or "Brak Tytułu",
                "sender": sender or "Brak Nadawcy",
                "recipient": recipient if recipient != "Unknown" else "Nieznany Odbiorca",
                "account": account_number if len(account_number) > 10 else "Brak Numeru Konta",
                "status": "success"
            }



    except Exception as e:
        return {
            "filename": os.path.basename(file_path),
            "error": str(e),
            "status": "error"
        }

