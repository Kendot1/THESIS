"""
Department of Agriculture (DA) Prevailing Price Range Scraper
Scrapes official Price Monitoring bulletins from https://www.da.gov.ph/price-monitoring/
Extracts the full distribution: Low, High, Prevailing, and Average retail prices per commodity.
"""

import io
import re
import ssl
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import pdfplumber
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scraper.pdf_detector import USER_AGENT

def extract_date_from_filename(filename: str) -> str:
    """Extract standard ISO date (YYYY-MM-DD) from DA Price-Monitoring filename."""
    months = 'january|february|march|april|may|june|july|august|september|october|november|december'
    m = re.search(r'price-monitoring-(' + months + r')-(\d{1,2})-(\d{4})', filename.lower())
    if m:
        month_str, day_str, year_str = m.groups()
        try:
            dt = datetime.strptime(f"{month_str} {day_str} {year_str}", "%B %d %Y")
            return dt.strftime("%Y-%m-%d")
        except Exception:
            pass
    return ""

def scrape_prevailing_price_ranges(max_reports: int = 10) -> pd.DataFrame:
    print("1. Fetching DA Price Monitoring index page...")
    url = "https://www.da.gov.ph/price-monitoring/"
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
        html = r.read().decode('utf-8')

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    
    # Locate Price-Monitoring-*.pdf links
    links = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        if 'pdf' in href.lower() and 'price-monitoring-' in href.lower():
            links.append(href)
            
    # Deduplicate and sort
    unique_links = sorted(list(set(links)), reverse=True)
    print(f"   Found {len(unique_links)} official DA Price Monitoring (Range) PDF bulletins.")
    
    records = []
    selected = unique_links[:max_reports]
    for idx, pdf_url in enumerate(selected, 1):
        filename = pdf_url.split('/')[-1]
        report_date = extract_date_from_filename(filename)
        print(f"\n   [{idx:02d}/{len(selected)}] Processing {filename} ({report_date})...")
        try:
            pdf_req = urllib.request.Request(pdf_url, headers={'User-Agent': USER_AGENT})
            with urllib.request.urlopen(pdf_req, timeout=35, context=ctx) as r:
                pdf_bytes = r.read()
                
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                # Range tables are located on pages 4, 5, 6
                target_pages = [p for i, p in enumerate(pdf.pages) if i >= 3]
                day_records = 0
                for page in target_pages:
                    text = page.extract_text() or ""
                    for line in text.split('\n'):
                        # Match: Name Low High Prevailing Average
                        # e.g.: Bittergourd (Ampalaya) 50.00- 150.00 120.00 112.04
                        matches = re.findall(r'([A-Za-z][A-Za-z0-9\s\(\),-\.\/\*ᵃᵇᶜ]+?)\s+([0-9]{1,4}\.[0-9]{2})\s*(?:-|\s)\s*([0-9]{1,4}\.[0-9]{2})\*?\s+([0-9]{1,4}\.[0-9]{2})\s+([0-9]{1,4}\.[0-9]{2})', line)
                        for match in matches:
                            raw_name, low_s, high_s, prev_s, avg_s = match
                            name = re.sub(r'^(IMPORTED|LOCAL|COMMODITIES|AND|PRODUCTS|CORN|per kg\)|HIGHLAND|LOWLAND|VEGETABLES|OTHER|SPICES|FRUITS)\s+', '', raw_name.strip(), flags=re.IGNORECASE).strip()
                            name = re.sub(r'\s+', ' ', name)
                            
                            if len(name) < 3 or any(k in name.lower() for k in ['market', 'price', 'selected', 'commodities', 'agri-fishery', 'retail']):
                                continue
                                
                            low = float(low_s)
                            high = float(high_s)
                            prev = float(prev_s)
                            avg = float(avg_s)
                            
                            records.append({
                                'report_date': report_date,
                                'commodity': name,
                                'price_low': low,
                                'price_high': high,
                                'price_prevailing': prev,
                                'price_average': avg,
                                'price_spread': round(high - low, 2),
                                'source_pdf': pdf_url,
                            })
                            day_records += 1
                print(f"       Extracted {day_records} range entries for {report_date}")
        except Exception as e:
            print(f"       Skipped {filename}: {e}")

    df = pd.DataFrame(records)
    return df

def main():
    root = Path(__file__).resolve().parent.parent
    out_dir = root / "foodcast/artifacts"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    df = scrape_prevailing_price_ranges(max_reports=10)
    if not df.empty:
        # Deduplicate
        df = df.drop_duplicates(subset=['report_date', 'commodity'])
        out_csv = out_dir / "scraped_da_prevailing_price_ranges.csv"
        df.to_csv(out_csv, index=False)
        print(f"\nSuccessfully compiled {len(df)} commodity price range observations across {df['report_date'].nunique()} days!")
        print(f"Saved to: {out_csv}")
        print("\nSample records:")
        print(df.head(10)[['report_date', 'commodity', 'price_low', 'price_high', 'price_prevailing', 'price_spread']])
    else:
        print("No price range records extracted.")

if __name__ == "__main__":
    main()
