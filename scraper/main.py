import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from pdf_detector import get_pdf_links
from parser import parse_pdf
from db import insert_prices, get_last_date, get_processed_pdfs
from fill_missing_days import fill_missing_days
from utils import extract_date_from_url


def run():
    print("=" * 50)
    print("Step 1: Determine report-date range")
    print("=" * 50)

    # GitHub-hosted runners use UTC; the DA reports use Philippine dates.
    end_date = datetime.now(ZoneInfo("Asia/Manila")).replace(tzinfo=None)
    last_db_date_str = get_last_date()
    if last_db_date_str:
        last_db_date = datetime.strptime(last_db_date_str, "%Y-%m-%d")
        start_date = min(last_db_date, end_date - timedelta(days=30))
    else:
        start_date = end_date - timedelta(days=30)

    base_date = datetime(2026, 1, 21)
    start_date = max(start_date, base_date)
    print(
        f"Scanning DA uploads from {start_date:%Y-%m-%d} "
        f"through {end_date:%Y-%m-%d} (Asia/Manila)."
    )

    pdf_links = get_pdf_links(start_date, end_date)
    print(f"Found {len(pdf_links)} DA PDF link(s).")
    pdf_dates = [extract_date_from_url(link) for link in pdf_links]
    pdf_dates = [report_date for report_date in pdf_dates if report_date is not None]
    if not pdf_dates:
        raise RuntimeError(
            "No DA price-monitoring PDFs were found in the scan window; "
            "check the official URL pattern and source availability"
        )
    latest_pdf_date = max(pdf_dates)
    age_days = (end_date.date() - latest_pdf_date).days
    if age_days < 0 or age_days > 7:
        raise RuntimeError(
            f"Latest DA source PDF is {age_days} day(s) old ({latest_pdf_date}); "
            "refusing to train from stale filled-forward prices"
        )

    processed_pdfs = get_processed_pdfs()
    new_pdfs = [link for link in pdf_links if link not in processed_pdfs]
    print(f"{len(new_pdfs)} new or late PDF(s) to process.")

    failures = []
    parsed_rows = 0
    for link in new_pdfs:
        print(f"Processing {link}")
        try:
            rows = parse_pdf(link)
            if not rows:
                raise RuntimeError("The PDF parser returned no price rows")
            stored = insert_prices(rows)
            parsed_rows += stored
            print(f"Upserted {stored} price row(s).")
        except Exception as exc:
            print(f"Failed to process {link}: {exc}")
            failures.append((link, exc))

    if failures:
        details = "; ".join(f"{link}: {exc}" for link, exc in failures[:3])
        raise RuntimeError(f"Failed to process {len(failures)} DA PDF(s): {details}")

    print("=" * 50)
    print("Step 2: Fill missing report dates")
    print("=" * 50)
    fill_result = fill_missing_days(start_date.date(), end_date.date())
    if fill_result.get("insert_failures", 0):
        raise RuntimeError(
            f"Failed to fill {fill_result['insert_failures']} missing report date(s)"
        )

    latest_db_date = get_last_date()
    if latest_db_date is None:
        raise RuntimeError("DA scrape finished, but food_prices is still empty")

    result = {
        "pdfs_found": len(pdf_links),
        "latest_source_pdf_date": latest_pdf_date.isoformat(),
        "pdfs_processed": len(new_pdfs),
        "price_rows_upserted": parsed_rows,
        "gap_dates_filled": fill_result.get("filled", 0),
        "latest_report_date": latest_db_date,
    }
    print(f"DA scrape complete: {result}")
    return result


if __name__ == "__main__":
    run()
