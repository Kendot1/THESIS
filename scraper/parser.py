import pdfplumber
import re
import requests
from io import BytesIO
from statistics import mean
from utils import extract_date_from_url

def parse_price_numbers(s):
    """Extract all numbers from a string and convert to float."""
    numbers = re.findall(r"\d+\.?\d*", s.replace(",", ""))
    return [float(n) for n in numbers]

def clean_product_name(name):
    # Remove units like (per kg), (per piece), etc.
    name = re.sub(r"\(per [^)]+\)", "", name, flags=re.IGNORECASE)
    # Remove extra spaces
    return name.strip()

def is_valid_line(text):
    skip_keywords = [
        "COMMODITIES", "SOURCE", "DISCLAIMER", "PREVAILING",
        "VEGETABLES", "RICE", "CORN", "LIVESTOCK", "POULTRY", "FISH", "OILS",
        "MARKET", "SATURDAY", "SUNDAY", "MONDAY", "TUESDAY", "WEDNESDAY",
        "THURSDAY", "FRIDAY", "GRACE MARKETPLACE", "KAMUNING", "AGORA", "ALABANG"
    ]
    upper_text = text.upper()
    if any(k in upper_text for k in skip_keywords):
        return False
    if re.search(r"\bMarket\b", text, re.IGNORECASE):
        return False
    if "/" in text:  # likely a market name
        return False
    if re.search(r"\(.\) available only in", text, re.IGNORECASE):
        return False
    if re.match(r"^\(.\)$", text.strip()):  # lone footnote symbol
        return False
    if not re.search(r"\d", text):  # must contain at least one number
        return False
    return True

def parse_pdf(url):
    rows = []
    report_date = extract_date_from_url(url)

    response = requests.get(url, timeout=10)
    response.raise_for_status()
    pdf_file = BytesIO(response.content)

    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            for line in lines:
                line = line.strip()
                if not line or not is_valid_line(line):
                    continue

                # Split name and price part
                match = re.match(r"^(.*?)([\d,].*)$", line)
                if not match:
                    continue

                product_name = clean_product_name(match.group(1))
                price_part = match.group(2)
                price_numbers = parse_price_numbers(price_part)
                if not price_numbers:
                    continue

                avg_price = mean(price_numbers)

                rows.append({
                    "product_name": product_name,
                    "product_type": None,
                    "price_index": avg_price,
                    "report_date": report_date.isoformat(),
                    "source_pdf": url
                })

    return rows