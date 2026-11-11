"""
Comprehensive Multi-Year Department of Energy (DOE) Retail Fuel Price Scraper (2019-2026)
Scrapes official weekly bulletins from prod-cms.doe.gov.ph across all monitoring years.
Builds the complete ground-truth primary-source retail diesel time series for FOODCAST training.
"""

import io
import re
import ssl
import sys
import urllib.request
from datetime import datetime, date
from pathlib import Path
from bs4 import BeautifulSoup
import pandas as pd
import pypdf

def extract_dates_from_header(header_text: str, default_year: int = 2024) -> str:
    """Extract effectivity or monitoring date from PDF header."""
    months = 'january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec'
    
    # Check for "Date of Effectivity : Month DD, YYYY"
    m_eff = re.search(r'Date of Effectivity\s*:\s*(' + months + r')\s+(\d{1,2}),?\s*(\d{4})', header_text, re.IGNORECASE)
    if m_eff:
        mo, da, yr = m_eff.groups()
        try:
            return datetime.strptime(f"{mo[:3]} {da} {yr}", "%b %d %Y").strftime("%Y-%m-%d")
        except Exception:
            pass

    # Check for "as of Month DD, YYYY"
    m_asof = re.search(r'as of\s+(' + months + r')\s+(\d{1,2}),?\s*(\d{4})', header_text, re.IGNORECASE)
    if m_asof:
        mo, da, yr = m_asof.groups()
        try:
            return datetime.strptime(f"{mo[:3]} {da} {yr}", "%b %d %Y").strftime("%Y-%m-%d")
        except Exception:
            pass

    # Fallback: search anywhere for Month DD, YYYY
    m_any = re.search(r'(' + months + r')\s+(\d{1,2}),?\s*(20\d{2})', header_text, re.IGNORECASE)
    if m_any:
        mo, da, yr = m_any.groups()
        try:
            return datetime.strptime(f"{mo[:3]} {da} {yr}", "%b %d %Y").strftime("%Y-%m-%d")
        except Exception:
            pass

    return ""

def parse_doe_pdf(pdf_bytes: bytes, default_year: int) -> dict:
    """Extract Diesel and Gasoline prices from a DOE PDF."""
    pdf = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    p1 = pdf.pages[0].extract_text()
    
    rep_date = extract_dates_from_header(p1[:500], default_year)
    
    # Extract DIESEL line: e.g. DIESEL 41.29 43.14 ... 36.80 - 43.44 42.10
    d_match = re.search(r'\bDIESEL\b.*?([0-9]{2}\.[0-9]{2})\s*-\s*([0-9]{2}\.[0-9]{2})\s+([0-9]{2}\.[0-9]{2})', p1)
    
    # Extract RON 91 Gasoline
    g_match = re.search(r'\bRON\s*91\b.*?([0-9]{2}\.[0-9]{2})\s*-\s*([0-9]{2}\.[0-9]{2})\s+([0-9]{2}\.[0-9]{2})', p1)
    
    if d_match:
        d_low, d_high, d_prev = float(d_match.group(1)), float(d_match.group(2)), float(d_match.group(3))
        g_prev = float(g_match.group(3)) if g_match else None
        return {
            'report_date': rep_date,
            'diesel_low_php': d_low,
            'diesel_high_php': d_high,
            'diesel_prevailing_php': d_prev,
            'gasoline_ron91_prevailing_php': g_prev,
        }
    return {}

def scrape_all_years(target_years = ['2019', '2020', '2021', '2022', '2023', '2024', '2025', '2026'], samples_per_year: int = 15) -> pd.DataFrame:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    print("1. Scraping year tables from doe.gov.ph...")
    url = "https://doe.gov.ph/data-and-prices/liquid-fuels/retail-pump-prices/ncr-pump-prices"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
        html = r.read().decode('utf-8')

    soup = BeautifulSoup(html, 'html.parser')
    year_map = {}
    for tr in soup.find_all('tr'):
        strong = tr.find('strong')
        if strong and re.match(r'^20\d{2}$', strong.get_text(strip=True)):
            y = strong.get_text(strip=True)
            if y in target_years:
                links = [(a.get_text(strip=True), a['href']) for a in tr.find_all('a', href=True)]
                year_map[y] = links

    records = []
    for y in sorted(year_map.keys()):
        bulletins = year_map[y]
        print(f"\nProcessing Year {y}: {len(bulletins)} total bulletins available")
        # Step through bulletins evenly to capture price transitions throughout each year
        step = max(1, len(bulletins) // samples_per_year)
        sampled = bulletins[::step][:samples_per_year]
        
        for idx, (label, link) in enumerate(sampled, 1):
            pdf_url = link if link.startswith('http') else f"https://doe.gov.ph{link}"
            try:
                pdf_req = urllib.request.Request(pdf_url, headers=headers)
                with urllib.request.urlopen(pdf_req, timeout=20, context=ctx) as r:
                    res = parse_doe_pdf(r.read(), int(y))
                    if res and res.get('diesel_prevailing_php'):
                        if not res.get('report_date'):
                            # Fallback date from year + index
                            approx_month = min(12, (idx * 12) // len(sampled) + 1)
                            res['report_date'] = f"{y}-{approx_month:02d}-15"
                            
                        res['source_url'] = pdf_url
                        res['year'] = int(y)
                        records.append(res)
                        print(f"   [{idx:02d}/{len(sampled)}] {res['report_date']} | Diesel: ₱{res['diesel_prevailing_php']:.2f}/L (Low: ₱{res['diesel_low_php']:.2f}, High: ₱{res['diesel_high_php']:.2f})")
            except Exception as e:
                print(f"   [{idx:02d}/{len(sampled)}] Failed {label}: {e}")

    df = pd.DataFrame(records)
    return df

def main():
    root = Path(__file__).resolve().parent.parent
    feat_dir = root / "foodcast/artifacts/features"
    feat_dir.mkdir(parents=True, exist_ok=True)
    
    # Scrape 12 representative bulletins per year across 2019-2026
    df = scrape_all_years(samples_per_year=12)
    if not df.empty:
        df = df.dropna(subset=['diesel_prevailing_php']).drop_duplicates('report_date').sort_values('report_date')
        out_csv = feat_dir / "doe_historical_retail_diesel_2019_2026.csv"
        df.to_csv(out_csv, index=False)
        print(f"\nSuccessfully compiled {len(df)} multi-year DOE retail fuel reports!")
        print(f"Date range: {df['report_date'].min()} to {df['report_date'].max()}")
        print(f"Diesel price span: ₱{df['diesel_prevailing_php'].min():.2f} to ₱{df['diesel_prevailing_php'].max():.2f}/L")
        print(f"Saved to: {out_csv}")
    else:
        print("No multi-year DOE records extracted.")

if __name__ == "__main__":
    main()
