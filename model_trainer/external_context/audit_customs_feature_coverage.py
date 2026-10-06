"""Measure causal coverage of a reviewed subset before fitting any model.

No target prices are read. Age limits are coverage diagnostics, not selected
hyperparameters or claims that very old reference values remain useful.
"""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

if __package__:
    from .build_context import encode, sha256
    from .customs_features import QuoteArchive, join_reviewed_availability
    from .ocr_customs import write_once
else:
    from build_context import encode, sha256
    from customs_features import QuoteArchive, join_reviewed_availability
    from ocr_customs import write_once


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviewed", type=Path, required=True)
    parser.add_argument("--availability", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reviewed_bytes, availability_bytes = args.reviewed.read_bytes(), args.availability.read_bytes()
    quotes, excluded = join_reviewed_availability(json.loads(reviewed_bytes), json.loads(availability_bytes))
    archive = QuoteArchive(quotes)
    local_tz = timezone(timedelta(hours=8))
    origins = {
        "early_tuning": ["2024-08-26", "2024-09-25", "2024-10-25"],
        "calibration": ["2024-11-24", "2024-12-24", "2025-01-23"],
        "development": ["2025-02-22", "2025-03-24", "2025-04-23", "2025-05-23", "2025-06-22", "2025-07-22"],
    }
    records = []
    for grade, country in sorted({(q.grade, q.country) for q in quotes}):
        for group, days in origins.items():
            for day in days:
                origin = datetime.fromisoformat(day).replace(tzinfo=local_tz)
                for lag in [0, 1, 3, 7, 14, 30]:
                    for age in [30, 90, 180, 365]:
                        value = dict(archive.at(origin, grade=grade, country=country, lag_days=lag, max_age_days=age))
                        records.append({"grade": grade, "country": country, "origin": origin.isoformat(), "split": group, **value})
    summaries = []
    for group in origins:
        for lag in [0, 1, 3, 7, 14, 30]:
            for age in [30, 90, 180, 365]:
                rows = [r for r in records if r["split"] == group and r["lag_days"] == lag and r["max_age_days"] == age]
                summaries.append({"split": group, "lag_days": lag, "max_age_days": age,
                                  "grade_country_origin_cells": len(rows), "nonmissing_cells": sum(r["missing"] == 0 for r in rows),
                                  "reasons": dict(Counter(r["reason"] for r in rows))})
    result = {"schema_version": 1, "reviewed_sha256": sha256(reviewed_bytes), "availability_sha256": sha256(availability_bytes),
              "builder_sha256": sha256(Path(__file__).read_bytes()),
              "scope": "Numerically reviewed subset only. Not coverage of all Customs PDFs. Origins at 00:00 Asia/Manila; no target-price labels accessed.",
              "joined_rows": len(quotes), "excluded_rows": excluded,
              "production_training_admitted": False,
              "age_policy_note": "Age from reference start at actual forecast origin. 180/365-day policies are diagnostic alternatives, not endorsed carry-forward. Lag only delays the information cutoff.",
              "summary": summaries, "lookups": records}
    write_once(args.output, encode(result))
    print(json.dumps({"joined_rows": len(quotes), "lookups": len(records),
                      "zero_lag_summary": [s for s in summaries if s["lag_days"] == 0]}, indent=2))


if __name__ == "__main__":
    main()
