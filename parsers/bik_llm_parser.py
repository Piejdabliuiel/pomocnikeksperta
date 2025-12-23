
import os
import json
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def parse_bik_with_llm(full_text):
    """
    Parses BIK report text using OpenAI/LLM API.
    Returns a structured dictionary compatible with the frontend.
    """
    
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    model_name = os.getenv("OPENAI_MODEL_NAME", "gpt-4o")

    if not api_key:
        return {"error": "Missing OPENAI_API_KEY in .env file", "status": "error"}

    # Initialize Client
    client = OpenAI(
        api_key=api_key,
        base_url=base_url if base_url else None
    )

    # Define Schema (Structured Output)
    schema = {
        "type": "object",
        "properties": {
            "personal_data": {
                "type": "object",
                "properties": {
                     "name": {"type": "string", "description": "Full Name (e.g. PAWEŁ HEUSER)"},
                     "pesel": {"type": "string"},
                     "birth_date": {"type": "string", "description": "YYYY-MM-DD"},
                     "report_date": {"type": "string", "description": "YYYY-MM-DD"},
                     "is_stale": {"type": "boolean"}
                },
                "required": ["name", "pesel", "report_date"]
            },
            "score": {"type": "integer", "description": "Credit Score (0-100)"},
            "inquiries_12m": {"type": "integer", "description": "Count of credit inquiries in last 12 months"},
             "summary": {
                "type": "object",
                "properties": {
                    "total_installment": {"type": "number"},
                    "total_limits": {"type": "number"},
                    "mortgage_installment": {"type": "number"}
                }
            },
            "active_liabilities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "bank": {"type": "string"},
                        "type": {"type": "string"},
                        "installment": {"type": "number"},
                        "amount_left": {"type": "number"},
                        "limit": {"type": "number"},
                        "max_delay_status": {"type": "string", "description": "Status string e.g. '0-30 dni', 'OK', 'WINDYKACJA'"},
                        "closing_date": {"type": "string", "nullable": True},
                        "description": {"type": "string", "nullable": True}
                    },
                    "required": ["bank", "type", "installment", "amount_left", "limit", "max_delay_status"]
                }
            },
            "closed_liabilities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "bank": {"type": "string"},
                        "type": {"type": "string"},
                        "closing_date": {"type": "string", "description": "DD.MM.YYYY"},
                        "max_delay_days": {"type": "integer"},
                        "max_delay_status": {"type": "string", "description": "Bucket e.g. '31-90 dni'"},
                        "arrears_amount": {"type": "number", "description": "Max historical arrears amount"},
                        "description": {"type": "string", "nullable": True}
                    },
                     "required": ["bank", "max_delay_days"]
                }
            },
            "statistical_liabilities": {
                "type": "array",
                "items": {
                    "type": "object",
                     "properties": {
                        "bank": {"type": "string"},
                        "type": {"type": "string"},
                         "closing_date": {"type": "string"},
                        "max_delay_days": {"type": "integer"},
                        "max_delay_status": {"type": "string"}
                    }
                }
            }
        },
        "required": ["personal_data", "score", "active_liabilities", "closed_liabilities"]
    }

    # System Prompt with specific fallback instructions
    system_prompt = """You are a specialized Credit Analyst AI.
Your task is to extract financial liability data from the provided BIK Report.
Output valid JSON matching the schema.

CRITICAL: You must scan the ENTIRE document from start to finish. Do not stop after the header.

### 1. PERSONAL DATA (At the top)
- **Name**: Find "Wnioskodawca" (e.g. Paweł Heuser).
- **PESEL**: 11 digits.
- **Score**: "Ocena punktowa" (e.g. 52/100). Extract ONLY the number.
- **Date**: "Data raportu" (YYYY-MM-DD).

### 2. SECTION MAPPING Rules (Liabilities)
- **active_liabilities**: Items under "Zobowiązania finansowe w trakcie spłaty".
   - Headers may have dashes.
   - Required: `bank`, `installment` (Rata), `amount_left`.
- **closed_liabilities**: Items under "Zobowiązania finansowe zamknięte".
   - Stop when you see Statistical header.
   - Extract `closing_date`, `arrears_amount`.
- **statistical_liabilities**: Items under "Zobowiązania przetwarzane w celach statystycznych".
   - **MUST** be placed here. Extract ALL items (likely ~13).

### 3. EXTRACTION RULES
- **Bank Name**: Look for "SANTANDER", "ALIOR", "MBANK".
- **Status**: If history "0 0 0", status "OK".
- **Amounts**: Return strings or numbers.
"""

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Analyze this BIK Report:\n\n{full_text}"}
            ],
            response_format={"type": "json_object"},
            temperature=0  # Deterministic
        )
        
        raw_json = response.choices[0].message.content
        # Debug Log
        with open("server_debug.log", "a") as f:
            f.write(f"RAW LLM JSON: {raw_json}\n")
        
        parsed_data = json.loads(raw_json)
        
        # --- NORMALIZATION STRATEGIES ---
        # 1. Flatten 'liabilities' wrapper if present
        if "liabilities" in parsed_data:
            liabs = parsed_data.pop("liabilities")
            if isinstance(liabs, dict):
                for key in ["active_liabilities", "closed_liabilities", "statistical_liabilities"]:
                   if key in liabs: parsed_data[key] = liabs[key]
        
        # 2. Extract Score to Root
        if "personal_data" in parsed_data:
            pd = parsed_data["personal_data"]
            if "score" in pd and "score" not in parsed_data:
                parsed_data["score"] = pd.pop("score")
            # 3. Map Date -> report_date
            if "date" in pd:
                pd["report_date"] = pd.pop("date")
                
        # 4. Ensure Keys Exist
        for k in ["active_liabilities", "closed_liabilities", "statistical_liabilities"]:
            if k not in parsed_data: parsed_data[k] = []

        # Helper to clean numbers
        def to_float(val):
            if isinstance(val, (int, float)): return float(val)
            if isinstance(val, str):
                clean = val.replace("PLN", "").replace(" ", "").replace(",", ".").strip()
                try: 
                    return float(clean)
                except: 
                    return 0.0
            return 0.0

        # Post-Processing / Normalization
        for l in parsed_data.get("active_liabilities", []):
            if "delays" not in l: l["delays"] = [l.get("max_delay_status", "")]
            # Enforce Numbers
            l["installment"] = to_float(l.get("installment"))
            l["amount_left"] = to_float(l.get("amount_left"))
            l["limit"] = to_float(l.get("limit"))

        for l in parsed_data.get("closed_liabilities", []):
            if "delays" not in l: l["delays"] = [f"{l.get('max_delay_days', 0)} dni"]
            l["arrears_amount"] = to_float(l.get("arrears_amount"))
            
        # Clean Score
        if "score" in parsed_data:
             val = parsed_data["score"]
             if isinstance(val, str):
                 # "52 / 100" -> 52
                 import re
                 m = re.search(r"(\d+)", val)
                 if m: parsed_data["score"] = int(m.group(1))

        parsed_data["alerts"] = [] 
        
        return parsed_data

    except Exception as e:
        return {"error": f"LLM Parsing Failed: {str(e)}", "status": "error"}
