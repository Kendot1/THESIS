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

MONTH_MAP = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
    'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12,
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
}

def resolve_exact_doe_date(label: str, url: str, pdf_text: str, table_year: int) -> str:
    """Extract exact calendar date of price effectivity or monitoring week start."""
    # 1. Search PDF text for explicit Date of Effectivity
    m_eff = re.search(r'Date of Effectivity\s*:\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})', pdf_text, re.IGNORECASE)
    if m_eff:
        mo, da, yr = m_eff.groups()
        mo_num = MONTH_MAP.get(mo.lower()[:3])
        if mo_num and 1 <= int(da) <= 31:
            return f"{int(yr):04d}-{mo_num:02d}-{int(da):02d}"

    # 2. Search PDF text for 'as of Month DD, YYYY'
    m_asof = re.search(r'as of\s+([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})', pdf_text, re.IGNORECASE)
    if m_asof:
        mo, da, yr = m_asof.groups()
        mo_num = MONTH_MAP.get(mo.lower()[:3])
        if mo_num and 1 <= int(da) <= 31:
            return f"{int(yr):04d}-{mo_num:02d}-{int(da):02d}"

    # 3. Search URL for MMDDYYYY (e.g. ncr-price-monitoring-12022025-pdf or 10062026)
    m_url = re.search(r'(\d{2})(\d{2})(20\d{2})', url)
    if m_url:
        mo, da, yr = m_url.groups()
        if 1 <= int(mo) <= 12 and 1 <= int(da) <= 31:
            return f"{int(yr):04d}-{int(mo):02d}-{int(da):02d}"

    # 4. Search label (e.g. 'October 27 to November 2', 'November 3 to 9', 'December 7', 'Nov 26 to Dec 2')
    m_label = re.search(r'([A-Za-z]+)\s+(\d{1,2})', label)
    if m_label:
        mo, da = m_label.groups()
        mo_num = MONTH_MAP.get(mo.lower()[:3])
        if mo_num and 1 <= int(da) <= 31:
            return f"{table_year:04d}-{mo_num:02d}-{int(da):02d}"

    # 5. Search URL slug for month-day (e.g. petro_ncr_2023-dec-07-pdf or petro_mm_2019_december_05)
    m_slug = re.search(r'(20\d{2})[-_]([A-Za-z]{3,9})[-_](\d{1,2})', url)
    if m_slug:
        yr, mo, da = m_slug.groups()
        mo_num = MONTH_MAP.get(mo.lower()[:3])
        if mo_num and 1 <= int(da) <= 31:
            return f"{int(yr):04d}-{mo_num:02d}-{int(da):02d}"

    return ""

def parse_doe_pdf(pdf_bytes: bytes, label: str, url: str, default_year: int) -> dict:
    """Extract exact date, whole-market NCR average, low, high, and common prices from all districts."""
    pdf = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    full_text = "\n".join(p.extract_text() or "" for p in pdf.pages)
    
    exact_date = resolve_exact_doe_date(label, url, full_text[:600], default_year)
    if not exact_date:
        return {}

    # Extract all individual city/district DIESEL lines across all pages
    district_lows, district_highs, district_commons = [], [], []
    for line in full_text.split('\n'):
        if re.search(r'\bDIESEL\b', line, re.IGNORECASE) and not re.search(r'DIESEL PLUS', line, re.IGNORECASE):
            m = re.search(r'([0-9]{2}\.[0-9]{2})\s*-\s*([0-9]{2}\.[0-9]{2})\s+([0-9]{2}\.[0-9]{2}|#N/A)', line)
            if m:
                l, h, c = m.groups()
                district_lows.append(float(l))
                district_highs.append(float(h))
                if c != '#N/A':
                    district_commons.append(float(c))

    # Look for the Master NCR Summary Table at the end
    summary_match = re.search(r'\bDiesel\b\s+([0-9]{2}\.[0-9]{2})\s*(?:-|\s)\s*([0-9]{2}\.[0-9]{2})\s+([0-9]{2}\.[0-9]{2})', full_text, re.IGNORECASE)
    
    if summary_match:
        s_low, s_high, s_common = map(float, summary_match.groups())
    elif district_lows:
        s_low = min(district_lows)
        s_high = max(district_highs)
        s_common = float(pd.Series(district_commons).median()) if district_commons else (s_low + s_high) / 2
    else:
        return {}

    # Calculate whole-market average across all sampled NCR cities/districts
    district_mids = [(l + h) / 2 for l, h in zip(district_lows, district_highs)] if district_lows else [(s_low + s_high) / 2]
    ncr_average_price = round(float(sum(district_mids) / len(district_mids)), 2)

    return {
        'report_date': exact_date,
        'diesel_low_php': s_low,
        'diesel_high_php': s_high,
        'diesel_common_php': s_common,
        'diesel_prevailing_php': s_common,
        'diesel_average_php': ncr_average_price,
        'diesel_spread_php': round(s_high - s_low, 2),
        'districts_count': len(district_lows),
    }

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
                    res = parse_doe_pdf(r.read(), label, pdf_url, int(y))
                    if res and res.get('report_date') and res.get('diesel_prevailing_php'):
                        res['source_url'] = pdf_url
                        res['bulletin_label'] = label
                        res['year'] = int(y)
                        records.append(res)
                        print(f"   [{idx:02d}/{len(sampled)}] Exact Date: {res['report_date']} | Common: ₱{res['diesel_common_php']:.2f} | Whole NCR Avg: ₱{res['diesel_average_php']:.2f} (Low: ₱{res['diesel_low_php']:.2f}, High: ₱{res['diesel_high_php']:.2f}) across {res['districts_count']} districts [Label: {label[:20]}]")
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
        out_csv = feat_dir / "doe_exact_retail_diesel_2019_2026.csv"
        df.to_csv(out_csv, index=False)
        print(f"\nSuccessfully compiled {len(df)} multi-year DOE retail fuel reports!")
        print(f"Date range: {df['report_date'].min()} to {df['report_date'].max()}")
        print(f"Diesel price span: ₱{df['diesel_prevailing_php'].min():.2f} to ₱{df['diesel_prevailing_php'].max():.2f}/L")
        print(f"Saved to: {out_csv}")
    else:
        print("No multi-year DOE records extracted.")

if __name__ == "__main__":
    main()
