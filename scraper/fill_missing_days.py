"""Report missing DA observations without creating synthetic price rows."""
from __future__ import annotations

from datetime import date, datetime, timedelta

try:
    from .utils import extract_date_from_url
except ImportError:  # Script execution from the scraper directory.
    from utils import extract_date_from_url


def _default_supabase_client():
    try:
        from .db import supabase
    except ImportError:  # Script execution from the scraper directory.
        from db import supabase
    return supabase


def _as_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def get_all_rows_in_range(
    start: date, end: date, supabase_client=None
) -> list[dict]:
    """Read the existing rows in the range using a stable paginated query."""
    client = (_default_supabase_client() if supabase_client is None
              else supabase_client)
    all_data = []
    page_size = 1000
    start_idx = 0

    while True:
        response = (
            client.table("food_prices")
            .select("report_date,source_pdf")
            .gte("report_date", start.isoformat())
            .lte("report_date", end.isoformat())
            .order("report_date")
            .range(start_idx, start_idx + page_size - 1)
            .execute()
        )
        data = response.data
        if not data:
            break
        all_data.extend(data)
        if len(data) < page_size:
            break
        start_idx += page_size

    return all_data


def _has_matching_source_date(row: dict) -> bool:
    report_date = _as_date(row.get("report_date"))
    try:
        source_date = extract_date_from_url(str(row.get("source_pdf") or ""))
    except (TypeError, ValueError):
        source_date = None
    explicit_observed = row.get("is_observed")
    if explicit_observed is False or str(explicit_observed).lower() == "false":
        return False
    return report_date is not None and source_date == report_date


def fill_missing_days(
    start: date, end: date, supabase_client=None
) -> dict:
    """Report dates without source-backed rows; never insert copied prices.

    The historical function inserted yesterday's prices under missing report
    dates. That made fabricated rows look like observations to downstream
    consumers. Existing rows are left untouched; training code can still apply
    its explicitly causal, bounded fill for input features.
    """
    if end < start:
        raise ValueError("end date must be on or after start date")

    rows = get_all_rows_in_range(start, end, supabase_client)
    observed_dates = set()
    copied_rows_detected = 0
    for row in rows:
        report_date = _as_date(row.get("report_date"))
        if _has_matching_source_date(row):
            observed_dates.add(report_date)
        elif report_date is not None:
            copied_rows_detected += 1

    date_count = (end - start).days + 1
    missing_dates = [
        (start + timedelta(days=offset)).isoformat()
        for offset in range(date_count)
        if start + timedelta(days=offset) not in observed_dates
    ]
    if missing_dates:
        print(
            "No price rows were created for dates without a matching DA source. "
            f"Missing source dates: {len(missing_dates)}."
        )
    else:
        print("Every date in the requested range has source-backed rows.")
    if copied_rows_detected:
        print(
            f"Found {copied_rows_detected} rows whose source date does not match "
            "their report date; they remain untouched."
        )

    # Retain the legacy summary keys so the scraper's existing job output stays
    # compatible. `filled` is always zero because synthetic observations are
    # prohibited.
    return {
        "filled": 0,
        "skipped": len(missing_dates),
        "rows_inserted": 0,
        "insert_failures": 0,
        "missing_dates": missing_dates,
        "source_backed_dates": len(observed_dates),
        "copied_rows_detected": copied_rows_detected,
    }
