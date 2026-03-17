import pdfplumber
import re
import requests
from io import BytesIO
from statistics import mean
from utils import extract_date_from_url

CATEGORY_KEYWORDS = {
    "RICE": "Rice",
    "CORN": "Corn",
    "LIVESTOCK": "Livestock",
    "POULTRY": "Poultry",
    "FISH": "Fish",
    "LOWLAND VEGETABLES": "Vegetables",
    "HIGHLAND VEGETABLES": "Vegetables",
    "VEGETABLES": "Vegetables",
    "FRUITS": "Fruits",
    "SUGAR": "Sugar",
    "OIL": "Oils"
}

def get_product_category(raw_name, current_category):
    lower_name = raw_name.lower()
    if "egg" in lower_name:
        return "Poultry"
    if "chicken" in lower_name and "egg" not in lower_name:
        return "Livestock"
    return current_category

def parse_price_numbers(text):
    return [float(n) for n in re.findall(r"\d+\.?\d*", text.replace(",", ""))]

def normalize_product_name(raw_name):
    # Special case: Chicken Egg -> keep as "Chicken Egg"
    if "egg" in raw_name.lower():
        return "Chicken Egg"
    # Remove variant and origin labels
    name = re.sub(r"\(([^)]+)\)", "", raw_name)
    name = re.sub(r"\b(Local|Imported)\b", "", name, flags=re.IGNORECASE)
    return name.strip()

def extract_variant(raw_name):
    match = re.search(r"\(([^)]+)\)", raw_name)
    return match.group(1) if match else None

def extract_origin(raw_name):
    return "Imported" if "imported" in raw_name.lower() else "Local"

def normalize_unit(raw_name, detected_unit):
    lower_name = raw_name.lower()
    if any(word in lower_name for word in ["beef", "pork", "chicken", "egg", "livestock"]):
        return "kg"
    return detected_unit.lower() if detected_unit else None

def extract_unit(line):
    match = re.search(r"\(per ([^)]+)\)", line, re.IGNORECASE)
    return match.group(1).lower() if match else None

def is_valid_line(text):
    upper = text.upper()
    skip_keywords = [
        "COMMODITIES", "SOURCE", "DISCLAIMER", "PREVAILING",
        "MARKET", "SATURDAY", "SUNDAY", "MONDAY", "TUESDAY",
        "WEDNESDAY", "THURSDAY", "FRIDAY",
        "GRACE MARKETPLACE", "KAMUNING", "AGORA", "ALABANG",
        "PRODUCTS", "SPICES", "COMMERCIAL", "CORN", "VEGETABLES", "FRUITS", "LIVESTOCK", "POULTRY", "FISH", "RICE", "SUGAR", "OIL"
    ]
    if any(k in upper for k in skip_keywords):
        return False
    if re.search(r"\bMarket\b", text, re.IGNORECASE):
        return False
    if "/" in text or "available only in" in text.lower():
        return False
    if re.match(r"^\(.\)$", text.strip()):
        return False
    return bool(re.search(r"\d", text))

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

            current_category = None
            current_unit = None

            for line in text.split("\n"):
                line = line.strip()
                if not line:
                    continue

                upper = line.upper()

                # Detect category headers
                for key, value in CATEGORY_KEYWORDS.items():
                    if upper.strip() == key:
                        current_category = value
                        break

                # Detect unit-only lines
                unit = extract_unit(line)
                if unit:
                    current_unit = unit
                    continue

                # Validate product line
                if not is_valid_line(line):
                    continue

                # Split product name and prices
                match = re.match(r"^(.*?)([\d,].*)$", line)
                if not match:
                    continue

                raw_name = match.group(1).strip()
                price_part = match.group(2)

                prices = parse_price_numbers(price_part)
                if not prices:
                    continue

                avg_price = mean(prices)
                product_name = normalize_product_name(raw_name)

                rows.append({
                    "product_name": product_name,                                # Chicken Egg
                    "product_category": get_product_category(raw_name, current_category),
                    "product_variant": extract_variant(raw_name),               # White, Pewee
                    "unit": normalize_unit(raw_name, current_unit),             # kg for poultry/livestock
                    "origin": extract_origin(raw_name),                         # Local/Imported
                    "price_index": avg_price,
                    "report_date": report_date.isoformat(),
                    "source_pdf": url
                })

    return rows