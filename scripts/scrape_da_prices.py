"""
Department of Agriculture (DA) Daily Price Index Scraper
Scrapes official Daily Price Index PDFs directly from https://www.da.gov.ph/price-monitoring/
Extracts commodity prices, specifications, units, and dates into a verified CSV.
"""

import io
import re
import sys
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo
import pdfplumber
import requests
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper.pdf_detector import get_pdf_links, USER_AGENT
from scraper.parser import parse_daily_tables
from scraper.build_daily_price_index_sql import _embedded_report_date

def scrape_da_daily_prices(start_date: date, end_date: date, max_reports: int = 15) -> pd.DataFrame:
    print(f"1. Scanning DA Price Monitoring portal ({start_date} to {end_date})...")
    links = get_pdf_links(start_date, end_date)
    print(f"   Found {len(links)} Daily Price Index PDF links on da.gov.ph")
    
    if not links:
        print("   No PDF links found for given range.")
        return pd.DataFrame()

    all_records = []
    # Scrape up to max_reports
    selected_links = links[:max_reports]
    for idx, url in enumerate(selected_links, 1):
        print(f"\n   [{idx:02d}/{len(selected_links)}] Downloading {url}...")
        try:
            resp = requests.get(url, headers={'User-Agent': USER_AGENT}, timeout=(25, 45))
            if resp.status_code != 200:
                print(f"       HTTP error: {resp.status_code}")
                continue
                
            with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
                printed_date = _embedded_report_date(pdf.pages[0].extract_text())
                rows, stats = parse_daily_tables(pdf.pages, printed_date, url, raw_only=True)
                raw_rows = stats.get('raw_rows', [])
                valid_count = 0
                for r in raw_rows:
                    if r.get('available') and r.get('price_index'):
                        all_records.append({
                            'report_date': str(printed_date),
                            'product_category': r.get('section', '').strip(),
                            'product_name': r.get('commodity', '').strip(),
                            'product_specification': r.get('specification', '').strip(),
                            'price_index': float(r['price_index']),
                            'unit': r.get('reported_unit') or 'kg',
                            'source_pdf': url,
                        })
                        valid_count += 1
                print(f"       Extracted {valid_count} price items for report date {printed_date}")
        except Exception as e:
            print(f"       Error parsing {url}: {e}")

    df = pd.DataFrame(all_records)
    return df

def main():
    root = Path(__file__).resolve().parent.parent
    out_dir = root / "foodcast/artifacts"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    today = datetime.now(ZoneInfo('Asia/Manila')).date()
    # Default to past 14 days
    start = date(2026, 11, 1)
    end = today
    
    df = scrape_da_daily_prices(start, end, max_reports=10)
    if not df.empty:
        out_csv = out_dir / "scraped_da_daily_price_index.csv"
        df.to_csv(out_csv, index=False)
        print(f"\nSuccessfully compiled {len(df)} price observations across {df['report_date'].nunique()} days!")
        print(f"Saved to: {out_csv}")
        print("\nSample records:")
        print(df.head(10)[['report_date', 'product_category', 'product_name', 'price_index', 'unit']])
    else:
        print("No records scraped.")

if __name__ == "__main__":
    main()
