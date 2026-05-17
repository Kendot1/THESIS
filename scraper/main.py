import sys
import os
from dotenv import load_dotenv

# Force UTF-8 encoding for Windows console (prevents UnicodeEncodeError when printing emojis)
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
# Load GEMINI_API_KEY
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from datetime import datetime, timedelta
from pdf_detector import get_pdf_links
from parser import parse_pdf
from db import insert_prices, get_last_date, get_processed_pdfs
from fill_missing_days import fill_missing_days

def run():
    print("=" * 50)
    print("📅 Step 1: Determining Date Range...")
    print("=" * 50)
    
    end_date = datetime.now()
    
    last_db_date_str = get_last_date()
    if last_db_date_str:
        last_db_date = datetime.strptime(last_db_date_str, "%Y-%m-%d")
        # To fill your missing May 4 - May 9 gap, let's look back 30 days.
        # It's safe because get_processed_pdfs() skips already scraped days.
        start_date = min(last_db_date, end_date - timedelta(days=30))
    else:
        # Scan the last 30 days if no DB data
        start_date = end_date - timedelta(days=30)
        
    # Ensure we at least start from our base date
    base_date = datetime(2026, 1, 21)
    if start_date < base_date:
        start_date = base_date

    print(f"Scanning for late DA uploads from: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    
    # --- Step 2: Scrape & insert PDF data ---

    pdf_links = get_pdf_links(start_date, end_date)
    print(f"Total PDF links found in date range: {len(pdf_links)}")

    processed_pdfs = get_processed_pdfs()
    new_pdfs = [link for link in pdf_links if link not in processed_pdfs]
    
    if not new_pdfs:
        print("✅ No new or late PDFs found. Database is up-to-date!")
    else:
        print(f"🔍 Found {len(new_pdfs)} new/late PDFs to process!")

    for link in new_pdfs:
        print("Processing:", link)
        try:
            rows = parse_pdf(link)
            insert_prices(rows)
            print(f"Inserted {len(rows)} rows from {link}")
        except Exception as e:
            print(f"Failed to process {link}: {e}")

    # --- Step 2: Fill missing days (copy previous day's data) ---
    print("\n" + "=" * 50)
    print("📅 Step 2: Filling missing days...")
    print("=" * 50)
    try:
        fill_missing_days(start_date.date(), end_date.date())
    except Exception as e:
        print(f"❌ fill_missing_days failed: {e}")

    print("\n✅ Pipeline complete.")

if __name__ == "__main__":
    run()