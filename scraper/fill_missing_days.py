# fill_missing_days.py  (improved version)
# Key change: fetch ALL existing rows for the full range in ONE query,
# then do all the "find previous date" logic in Python — no more
# 30 DB round-trips per missing day.

from datetime import date, timedelta, datetime
from db import supabase


def get_all_rows_in_range(start: date, end: date) -> list[dict]:
    """Fetch every row between start and end using pagination."""
    all_data = []
    page_size = 1000
    start_idx = 0
    
    while True:
        response = (
            supabase.table("food_prices")
            .select("*")
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


def fill_missing_days(start: date, end: date) -> dict:
    """
    For every date in [start, end] that has no records,
    copy the most recent previous day's records into that date.
    All data is fetched in ONE initial query — efficient.
    """
    # Fetch from 7 days prior to ensure we capture the previous recorded date
    fetch_start = start - timedelta(days=7)
    all_rows = get_all_rows_in_range(fetch_start, end)

    # Group rows by date
    rows_by_date: dict[date, list[dict]] = {}
    for row in all_rows:
        d = datetime.strptime(row["report_date"], "%Y-%m-%d").date()
        rows_by_date.setdefault(d, []).append(row)

    recorded_dates = sorted(rows_by_date.keys())
    all_dates = [start + timedelta(days=i)
                 for i in range((end - start).days + 1)]
    missing_dates = [d for d in all_dates if d not in rows_by_date]

    summary = {"filled": 0, "skipped": 0, "rows_inserted": 0, "insert_failures": 0}
    if not missing_dates:
        print("✅ No missing dates found.")
        return summary

    print(f"📋 {len(missing_dates)} missing date(s) found.")

    import bisect
    for missing_date in missing_dates:
        # Find the latest recorded date BEFORE this missing date
        idx = bisect.bisect_left(recorded_dates, missing_date)
        if idx == 0:
            print(f"  ⚠️  {missing_date}: No previous record found (skipped)")
            summary["skipped"] += 1
            continue

        prev_date = recorded_dates[idx - 1]
        prev_rows = rows_by_date[prev_date]

        new_rows = [
            {**{k: v for k, v in row.items() if k != "id"},
             "report_date": missing_date.isoformat()}
            for row in prev_rows
        ]

        try:
            supabase.table("food_prices").insert(new_rows).execute()
            # Add to our local cache so subsequent missing dates
            # can use THIS newly filled date as their "previous"
            rows_by_date[missing_date] = new_rows
            recorded_dates.insert(idx, missing_date)  # keep sorted

            print(f"  ✅ {missing_date}: copied {len(new_rows)} rows from {prev_date}")
            summary["filled"] += 1
            summary["rows_inserted"] += len(new_rows)
        except Exception as e:
            summary["insert_failures"] += 1
            print(f"  ❌ {missing_date}: insert failed — {e}")
            summary["skipped"] += 1

    print(f"\n📊 {summary['filled']} day(s) filled, "
          f"{summary['rows_inserted']} row(s) inserted, "
          f"{summary['skipped']} skipped.")
    return summary
