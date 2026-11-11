"""
Department of Energy (DOE) Metro Manila Retail Pump Price Scraper
Scrapes official weekly retail fuel price bulletins directly from doe.gov.ph
Extracts Diesel and Gasoline price ranges and prevailing retail prices into a clean CSV.
"""

import io
import re
import ssl
import urllib.request
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup
import pandas as pd
import pypdf

def extract_dates_from_title(title: str, url: str) -> str:
    """Extract standard ISO date representation from DOE report title or filename."""
    # Match patterns like: "November 3 to 9 2026" or "10202026" or "Sep 1-7 2026"
    months = 'january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec'
    
    text = (title + " " + url).replace("%20", " ").lower()
    
    # Pattern: Month D to D YYYY (e.g., November 3 to 9 2026)
    m = re.search(r'(' + months + r')\s+(\d{1,2})\s*(?:to|-)\s*(\d{1,2})?,?\s*(20\d{2})', text)
    if m:
        month_str, d1, d2, year_str = m.groups()
        day = d2 or d1
        try:
            dt = datetime.strptime(f"{month_str[:3]} {day} {year_str}", "%b %d %Y")
            return dt.strftime("%Y-%m-%d")
        except Exception:
            pass

    # Pattern: MMDDYYYY in url (e.g. 10202026)
    m_num = re.search(r'(\d{2})(\d{2})(20\d{2})\.pdf', text)
    if m_num:
        mo, da, yr = m_num.groups()
        try:
            return f"{yr}-{mo}-{da}"
        except Exception:
            pass

    return ""

def main():
    root = Path(__file__).resolve().parent.parent
    out_dir = root / "foodcast/artifacts/features"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    print("1. Fetching DOE NCR pump price index page...")
    url = "https://doe.gov.ph/data-and-prices/liquid-fuels/retail-pump-prices/ncr-pump-prices"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
        html = r.read().decode("utf-8")

    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "pdf" in href.lower() and ("price" in href.lower() or "ncr" in href.lower() or "fuel" in href.lower()):
            title = a.get_text(strip=True)
            links.append((title, href))

    print(f"   Found {len(links)} DOE NCR PDF monitoring bulletins.")
    
    records = []
    # Scrape latest 40 weekly bulletins for historical coverage
    for idx, (title, pdf_url) in enumerate(links[:40], 1):
        try:
            report_date = extract_dates_from_title(title, pdf_url)
            r = urllib.request.urlopen(urllib.request.Request(pdf_url, headers=headers), timeout=20, context=ctx)
            pdf = pypdf.PdfReader(io.BytesIO(r.read()))
            text = pdf.pages[0].extract_text()
            
            # Extract Diesel line: e.g., DIESEL ... 89.00 - 97.20 95.40
            d_match = re.search(r'DIESEL.*?([0-9]{2}\.[0-9]{2})\s*-\s*([0-9]{2}\.[0-9]{2})\s+([0-9]{2}\.[0-9]{2})', text)
            # Extract Gasoline (RON 91) line: e.g., RON 91 ... 78.90 - 91.00 84.90
            g_match = re.search(r'RON\s*91.*?([0-9]{2}\.[0-9]{2})\s*-\s*([0-9]{2}\.[0-9]{2})\s+([0-9]{2}\.[0-9]{2})', text)
            
            if d_match:
                d_low, d_high, d_common = float(d_match.group(1)), float(d_match.group(2)), float(d_match.group(3))
                g_common = float(g_match.group(3)) if g_match else None
                
                records.append({
                    "report_title": title,
                    "date": report_date,
                    "diesel_low_php": d_low,
                    "diesel_high_php": d_high,
                    "diesel_common_php": d_common,
                    "gasoline_ron91_common_php": g_common,
                    "source_url": pdf_url,
                })
                print(f"   [{idx:02d}/40] Scraped: {title[:35]} -> Diesel Common=₱{d_common:.2f}/L")
        except Exception as e:
            print(f"   [{idx:02d}/40] Skipped {title[:30]}: {e}")

    df = pd.DataFrame(records)
    if not df.empty:
        # Sort and clean
        df = df.dropna(subset=["diesel_common_php"]).drop_duplicates("source_url")
        out_csv = out_dir / "doe_scraped_ncr_fuel_prices.csv"
        df.to_csv(out_csv, index=False)
        print(f"\nSuccessfully scraped {len(df)} official DOE weekly fuel reports to: {out_csv}")
    else:
        print("No fuel records parsed.")

if __name__ == "__main__":
    main()
