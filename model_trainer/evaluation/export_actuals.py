"""Prepare Supabase actuals for reconciliation, only after a holdout closes.

Does not score, certify source completeness, or create a reconciled manifest.
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation.frozen_holdout import load_contract


def require_closed(contract_path):
    contract, _, integrity = load_contract(contract_path)
    now = datetime.now(timezone.utc)
    if now < datetime.fromisoformat(integrity["period_closes_at"]):
        raise ValueError(f"Holdout still open until {integrity['period_closes_at']}; Supabase was not queried")
    return contract, integrity


def canonical_actuals(raw):
    import numpy as np
    import pandas as pd
    from data.preprocessor import DataPreprocessor, SERIES_KEY, source_date

    if raw.empty:
        raise ValueError("No source rows; cannot prepare actuals")
    dates = pd.to_datetime(raw.report_date, errors="coerce").dt.normalize()
    if dates.isna().any():
        raise ValueError("Invalid source dates require reconciliation")
    observed = raw.source_pdf.map(source_date).eq(dates)
    prices = pd.to_numeric(raw.price_index, errors="coerce")
    if (observed & (~np.isfinite(prices) | prices.le(0))).any():
        raise ValueError("Invalid observed prices require reconciliation; do not drop labels")
    for column in ("product_name", "product_category"):
        invalid = raw[column].fillna("").astype(str).str.strip().isin(["", "Unknown"])
        if invalid.any():
            raise ValueError(f"Invalid {column} requires reconciliation")
    # The preprocessor rejects conflicting duplicates and preserves observed
    # prices separately from forward-filled inputs. Export only those labels.
    clean = DataPreprocessor().validate(raw)
    labels = clean.loc[clean.is_observed].copy()
    if labels.empty:
        raise ValueError("No observed source labels")
    labels["series"] = labels[SERIES_KEY].astype(str).agg("||".join, axis=1)
    labels["target_date"] = labels.report_date.dt.strftime("%Y-%m-%d")
    labels["actual"] = labels.observed_price
    labels["is_observed"] = "true"
    return labels[["series", "target_date", "actual", "is_observed"]].sort_values(
        ["series", "target_date"]), int(observed.sum())


def export(contract_path, output):
    # Gate before client construction, imports that load configuration, or I/O
    # involving target observations. There is no CLI clock override.
    contract, integrity = require_closed(contract_path)
    from data.fetcher import DataFetcher

    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    raw = DataFetcher().fetch_since(contract["holdout_start"],
                                   through_date=contract["holdout_end"])
    raw_path = output / "supabase_actuals_raw.json"
    with raw_path.open("x", encoding="utf-8") as stream:
        stream.write(raw.to_json(orient="records", date_format="iso"))
    labels, observed_count = canonical_actuals(raw)
    if not labels.target_date.between(contract["holdout_start"], contract["holdout_end"]).all():
        raise ValueError("Export contains out-of-period source rows")
    data_path = output / "actuals.csv"
    labels.to_csv(data_path, index=False, mode="x", float_format="%.17g")
    draft = {
        "status": "requires_source_reconciliation_before_scoring",
        "data_file": data_path.name,
        "sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
        "contract_sha256": integrity["contract_sha256"],
        "exported_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "Supabase food_prices, bounded by the complete frozen target period",
        "is_observed_definition": "Dated source_pdf filename agrees with report_date; export observed_price only, never forward-filled input prices",
        "raw_file": raw_path.name,
        "raw_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
        "raw_rows": len(raw), "raw_observed_rows": observed_count,
        "canonical_observed_rows": len(labels),
        "identical_observed_duplicates_collapsed": observed_count - len(labels),
        "observed_series": int(labels.series.nunique()),
        "observed_rows_by_date": labels.groupby("target_date").size().to_dict(),
        "required_review": "Check DA source reports, ingestion completeness, units, identity changes and missing dates/series. Only after reconciliation, copy this draft to actuals_manifest.json and add reconciled_through with the verified date. Do not infer completeness from the latest row date.",
    }
    with (output / "actuals_manifest.draft.json").open("x", encoding="utf-8") as stream:
        json.dump(draft, stream, indent=2, allow_nan=False)
    print(json.dumps({"directory": str(output), "status": draft["status"],
                      "observed_rows": len(labels)}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", type=Path)
    parser.add_argument("output", type=Path, help="New directory; never overwritten")
    args = parser.parse_args()
    export(args.contract, args.output)
