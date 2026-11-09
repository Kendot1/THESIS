import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import argparse
import json
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

if __package__:
    from .pdf_detector import get_pdf_links
    from .utils import extract_date_from_url
else:
    from pdf_detector import get_pdf_links
    from utils import extract_date_from_url


def run(max_reports=None):
    # Keep credential loading and DB initialization exclusively on the write path.
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
    if __package__:
        from .parser import parse_pdf
        from .db import insert_prices, get_last_date, get_processed_pdfs
        from .fill_missing_days import fill_missing_days
    else:
        from parser import parse_pdf
        from db import insert_prices, get_last_date, get_processed_pdfs
        from fill_missing_days import fill_missing_days
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
    legacy_range_pdfs = [
        source for source in processed_pdfs
        if "price-monitoring-" in str(source).casefold()
    ]
    if legacy_range_pdfs:
        raise RuntimeError(
            "DA source cutover is pending: food_prices still references "
            f"{len(legacy_range_pdfs)} Daily Retail Price Range PDF(s). "
            "Refusing to mix those historical values with Daily Price Index "
            "values; an approved full-history rebuild is required first."
        )

    new_pdfs = [link for link in pdf_links if link not in processed_pdfs]
    if max_reports is not None:
        new_pdfs = sorted(new_pdfs, key=extract_date_from_url, reverse=True)[:max_reports]
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
        "gap_dates_unfilled": len(fill_result.get("missing_dates", [])),
        "gap_dates_without_source": fill_result.get("missing_dates", []),
        "copied_placeholder_rows_detected": fill_result.get(
            "copied_rows_detected", 0),
        "latest_report_date": latest_db_date,
    }
    print(f"DA scrape complete: {result}")
    return result


def run_dry(output, max_reports=1):
    """Download newest listed reports, preserving source cells locally only."""
    if __package__:
        from .parser import parse_pdf
        from .pdf_detector import DA_PRICE_MONITORING_PAGE
    else:
        from parser import parse_pdf
        from pdf_detector import DA_PRICE_MONITORING_PAGE
    end_date = datetime.now(ZoneInfo('Asia/Manila')).date()
    start_date = end_date - timedelta(days=30)
    links = get_pdf_links(start_date, end_date)
    if not links:
        raise RuntimeError('No official Daily Price Index reports discovered; refusing empty success')
    links = sorted(links, key=extract_date_from_url, reverse=True)[:max_reports]
    reports, all_rows = [], []
    for link in links:
        rows, metadata = parse_pdf(link, deterministic=True,
                                   artifact_dir=Path(output).parent / 'source_reports',
                                   return_metadata=True)
        if not rows:
            raise RuntimeError(f'No actual price rows parsed from {link}')
        reports.append(metadata)
        all_rows.extend(rows)
    return {'source_listing': DA_PRICE_MONITORING_PAGE, 'source_urls': links,
            'reports_processed': len(reports), 'reports': reports,
            'latest_report_date': max(item['report_date'] for item in reports),
            'row_count': len(all_rows), 'rows': all_rows,
            'row_contract': 'official_source_cells_not_database_crosswalk',
            'database_writes': 0}


def cli(argv=None):
    args_parser = argparse.ArgumentParser(description="Scrape official DA Daily Price Index reports")
    args_parser.add_argument("--dry-run", action="store_true", help="Local artifacts only; no credentials, AI API, or database")
    args_parser.add_argument("--max-reports", type=int, default=None, help="Maximum reports to process (dry-run defaults to 1)")
    args_parser.add_argument("--output", type=Path, default=Path("artifacts/da.json"))
    args = args_parser.parse_args(argv)
    if args.max_reports is not None and args.max_reports < 1:
        args_parser.error("--max-reports must be positive")
    result = {"status": "failed", "dry_run": args.dry_run, "errors": []}
    try:
        if args.dry_run:
            result.update(run_dry(args.output, args.max_reports or 1))
        else:
            result.update(run(args.max_reports))
        result["status"] = "ok"
    except Exception as exc:
        result["errors"].append(f"{type(exc).__name__}: {exc}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items()
                      if key not in {'rows', 'reports'}}, default=str))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(cli())
