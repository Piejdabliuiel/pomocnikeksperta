from flask import Flask, render_template, request, jsonify
import os
from werkzeug.utils import secure_filename
from parsers.pdf_parser import parse_pdf
from parsers.bik_parser import parse_bik_report
from parsers.bik_llm_parser import parse_bik_with_llm
from dotenv import load_dotenv

load_dotenv()
import pandas as pd

from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes (required for frontend on different domain)
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload_pdfs', methods=['POST'])
def upload_pdfs():
    if 'files[]' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    files = request.files.getlist('files[]')
    results = []
    
    # Deduplication set
    seen_transactions = set()
    unique_results = []
    
    # Pre-scan to map Account -> Canonical Name
    # Priority: if we have "Julia Latko" and "Julia Kuczyńska" for same account, 
    # we ideally want the latest one or similar.
    # For simplicity, we'll store all names seen for an account and pick one (e.g. longest or sorted).
    account_names_map = {} # { "1234...": set(["Julia Latko", "Julia Kuczyńska"]) }
    
    for file in files:
        if file.filename == '': continue
        if file:
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            data = parse_pdf(filepath)
            
            # Deduplication
            if data['status'] == 'success':
                sig = (data.get('date'), data.get('amount'), data.get('title'), data.get('sender'))
                if sig in seen_transactions:
                    data['status'] = 'duplicate'
                    continue
                seen_transactions.add(sig)
                
                # Account mapping
                acc = data.get('account')
                name = data.get('recipient')
                if acc and acc != "Brak Numeru Konta" and name and name != "Nieznany Odbiorca":
                    if acc not in account_names_map:
                        account_names_map[acc] = set()
                    account_names_map[acc].add(name)
            
            unique_results.append(data)
    
    # Resolve Canonical Names for Accounts
    # Heuristic: Pick the name that appears most often? Or just sort and pick last?
    # Let's pick the longest name as it might be most complete? Or just alphabetical.
    resolved_account_names = {}
    for acc, names in account_names_map.items():
        # Clean names (strip whitespace)
        valid_names = [n for n in names if len(n) > 3]
        if valid_names:
            # Sort valid names to have deterministic output. 
            # If we wanted "latest", we'd need parsing order which is random-ish here without dates.
            # Let's just pick one.
            resolved_account_names[acc] = sorted(valid_names)[0] 
        else:
            resolved_account_names[acc] = "Nieznany Właściciel"

    # Grouping Logic
    grouped_data = {}
    
    for item in unique_results:
        recipient = item.get('recipient', 'Nieznany Odbiorca')
        acc = item.get('account')
        
        # Override recipient name IF we have a resolved name for this account
        if acc in resolved_account_names:
            # We append the account number for clarity in UI?
            # Or just use the resolved name. User wants to merge them.
            canonical_name = resolved_account_names[acc]
            # Let's format it: "NAME (Account...)" to be sure
            # short_acc = acc[-4:] if len(acc) > 4 else acc
            # recipient = f"{canonical_name} (....{short_acc})"
            recipient = canonical_name
        
        if item.get('status') == 'error':
            recipient = 'Pliki Nieprzetworzone'

        date = item.get('date', '')
        month_key = "Nieznana Data"
        if date and len(date) >= 7:
            month_key = date[:7] # 2024-12
        
        if recipient not in grouped_data:
            grouped_data[recipient] = {}
        
        if month_key not in grouped_data[recipient]:
            grouped_data[recipient][month_key] = []
        
        # Add the account info to item display if needed, already in item['account']
        grouped_data[recipient][month_key].append(item)

    # Sort Recipients
    sorted_recipients = sorted(grouped_data.keys())
    
    # Sort Months
    final_structure = {}
    for rec in sorted_recipients:
        months = grouped_data[rec]
        sorted_months = sorted(months.keys(), reverse=True)
        final_structure[rec] = {m: months[m] for m in sorted_months}
    
    return jsonify(final_structure)

@app.route('/upload_bik', methods=['POST'])
def upload_bik():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
        
    if file:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(file.filename))
        file.save(filepath)
        
        # PARSER SELECTION: Native Parser (No LLM, No Token Cost)
        print("--- Using NATIVE Parser ---")
        import pdfplumber
        from parsers.bik_native_parser import parse_bik_native
        
        try:
            full_text = ""
            with pdfplumber.open(filepath) as pdf:
                for page in pdf.pages:
                    full_text += (page.extract_text() or "") + "\n"
            
            # Debug: Save extracted text
            try:
                with open("debug_pdf_text.txt", "w") as tf: 
                    tf.write(full_text)
            except: pass
            
            # Native Parser
            analysis = parse_bik_native(full_text)
            
            # Verify minimum data was extracted
            if not analysis.get("active_liabilities") and not analysis.get("closed_liabilities"):
                raise Exception("Native parser found no liabilities, falling back to regex")
            
            return jsonify(analysis)
            
        except Exception as e:
            print(f"Native Parser Failed: {e}")
            # Fallback to old Regex parser
            analysis = parse_bik_report(filepath)
            analysis["parser_type"] = "REGEX_FALLBACK"
            return jsonify(analysis)

    return jsonify({"error": "Upload failed"}), 500






if __name__ == '__main__':
    app.run(debug=True, port=5001)
