import pdfplumber
import requests
from io import BytesIO
from utils import extract_date_from_url
from ai_parser import parse_pdf_text_with_ai
import re
YELLOW_TABLE_KEYWORDS = [
    "AVERAGE RETAIL PRICE",
    "PREVAILING RETAIL PRICE PER UNIT"
]

def parse_pdf(url):
    """
    Extract yellow table from PDF and send to AI parser for accurate extraction
    """
    report_date = extract_date_from_url(url)
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    pdf_file = BytesIO(response.content)

    full_text = ""
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                full_text += page_text + "\n"

        # 🔥 STEP 1: ISOLATE YELLOW TABLE ONLY (robust)
    start_idx = -1
    for key in YELLOW_TABLE_KEYWORDS:
        match = re.search(re.escape(key), full_text, re.IGNORECASE)
        if match:
            start_idx = match.start()
            break

    if start_idx == -1:
        print(f"⚠️ Yellow table not found, sending entire PDF to AI for filtering")
        yellow_text = full_text  # fallback: let AI find yellow table
    else:
        yellow_text = full_text[start_idx:]
        if "SOURCE" in yellow_text:
            yellow_text = yellow_text.split("SOURCE")[0]

    # Call AI parser
    rows = parse_pdf_text_with_ai(yellow_text, report_date, url)
    print(f"Parsed {len(rows)} rows via AI")
    return rows