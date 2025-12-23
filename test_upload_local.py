
import requests
import os
import json

url = "http://127.0.0.1:5001/upload_bik"
file_path = "uploads/BIK_25.10..pdf"

try:
    if not os.path.exists(file_path):
        print(f"Error: File not found at {file_path}")
        # Try finding any PDF
        files = [f for f in os.listdir("uploads") if f.endswith(".pdf")]
        if files:
            file_path = os.path.join("uploads", files[0])
            print(f"Using alternative file: {file_path}")
        else:
            exit(1)

    print(f"Uploading {file_path} to {url}...")
    with open(file_path, 'rb') as f:
        response = requests.post(url, files={'file': f})
    
    if response.status_code == 200:
        data = response.json()
        print("--- RESPONSE SUCCESS ---")
        print(f"Parser Type: {data.get('parser_type')}")
        pd = data.get("personal_data", {})
        print(f"Name: {pd.get('name')} | PESEL: {pd.get('pesel')} | Date: {pd.get('report_date')}")
        print(f"Score: {data.get('score')} | Inquiries: {data.get('inquiries_12m')}")
        
        active = data.get("active_liabilities", [])
        closed = data.get("closed_liabilities", [])
        stats = data.get("statistical_liabilities", [])
        
        print(f"Active Cnt: {len(active)}")
        for i, a in enumerate(active):
            print(f"  A{i}: {a.get('bank')} | Rata: {a.get('installment')} | Left: {a.get('amount_left')} | Status: {a.get('max_delay_status')}")

        print(f"Closed Cnt: {len(closed)}")
        for i, c in enumerate(closed[:3]):
             print(f"  C{i}: {c.get('bank')} | Delay: {c.get('max_delay_days')}d")
             
        print(f"Statistical Cnt: {len(stats)}")
        
        # Check alerts
        alerts = data.get("alerts", [])
        print(f"Alerts: {len(alerts)}")
        
    else:
        print(f"Error {response.status_code}: {response.text}")

except Exception as e:
    print(f"Exception: {e}")
