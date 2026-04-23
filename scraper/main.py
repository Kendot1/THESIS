from datetime import datetime, timedelta
from pdf_detector import get_pdf_links
from parser import parse_pdf
from db import insert_prices
from fill_missing_days import fill_missing_days

def run():
    # --- Step 1: Scrape & insert PDF data ---
    start_date = datetime(2026, 1, 21)
    end_date = datetime(2026, 1, 26)

    pdf_links = get_pdf_links(start_date, end_date)
    print(f"PDF links found: {len(pdf_links)}")

    for link in pdf_links:
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