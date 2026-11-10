"""Reproducible, read-only evaluation report for a saved model bundle.

The report consumes saved out-of-sample forecasts. It never fetches data,
trains a model, or changes an artifact, which makes it safe to run before
candidate selection and final holdout review.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from utils.metrics import compute_all_metrics


MODEL_COLUMNS = (
    "ensemble", "lstm", "lgbm", "persistence", "seasonal7", "moving_average7"
)
LEAD_BANDS = {
    "1-7": (1, 7),
    "8-14": (8, 14),
    "15-21": (15, 21),
    "22-30": (22, 30),
}


def _summary(frame, prediction):
    actual = frame["actual"].to_numpy(dtype=float)
    predicted = frame[prediction].to_numpy(dtype=float)
    anchors = frame["anchor"].to_numpy(dtype=float) if "anchor" in frame else None
    result = compute_all_metrics(actual, predicted, anchors)
    valid = np.isfinite(actual) & np.isfinite(predicted) & (actual >= 0)
    result["mean_prediction_error"] = (
        float(np.mean(predicted[valid] - actual[valid])) if valid.any() else None
    )
    result["median_prediction_error"] = (
        float(np.median(predicted[valid] - actual[valid])) if valid.any() else None
    )
    result["series_count"] = int(frame.loc[valid, "series"].nunique()) if "series" in frame else None
    result["origin_count"] = int(frame.loc[valid, "origin"].nunique()) if "origin" in frame else None
    return result


def _grouped(frame, group_column, prediction):
    rows = []
    for key, group in frame.groupby(group_column, sort=True):
        row = {group_column: str(key), **_summary(group, prediction)}
        rows.append(row)
    return rows


def build_report(bundle_dir, *, model_columns=MODEL_COLUMNS):
    """Build metrics and provenance from one immutable saved bundle."""
    bundle_dir = Path(bundle_dir)
    metadata = json.loads((bundle_dir / "metadata.json").read_text(encoding="utf-8"))
    forecasts = pd.read_csv(bundle_dir / "test_forecasts.csv")
    required = {"series", "origin", "date", "horizon", "actual", "anchor", *model_columns}
    missing = required - set(forecasts.columns)
    if missing:
        raise ValueError(f"Saved test forecasts lack required columns: {sorted(missing)}")

    forecasts["horizon"] = pd.to_numeric(forecasts["horizon"], errors="raise").astype(int)
    forecasts["date"] = pd.to_datetime(forecasts["date"], errors="raise")
    result = {
        "schema_version": 1,
        "run_id": bundle_dir.name,
        "data_fingerprint": metadata.get("data_fingerprint"),
        "split": metadata.get("split"),
        "evaluation_scope": metadata.get("metrics", {}).get("evaluation_scope"),
        "metric_policy": {
            "mae_rmse": "original PHP price units",
            "mape": "mean absolute percentage error over finite actuals with abs(actual) >= 1e-8",
            "within_5_php": "inclusive absolute error <= PHP 5 over valid rows",
            "within_5_percent": "inclusive absolute percentage error <= 5%; zero/near-zero actuals excluded",
            "bias": "mean(prediction - actual) over valid rows",
        },
        "dataset": {
            "rows": int(len(forecasts)),
            "series_count": int(forecasts.series.nunique()),
            "origin_count": int(forecasts.origin.nunique()),
            "date_start": forecasts.date.min().date().isoformat(),
            "date_end": forecasts.date.max().date().isoformat(),
            "horizon_min": int(forecasts.horizon.min()),
            "horizon_max": int(forecasts.horizon.max()),
        },
        "models": {name: _summary(forecasts, name) for name in model_columns},
        "by_lead": {
            name: _grouped(forecasts, "horizon", name) for name in model_columns
        },
        "by_lead_band": {},
        "by_series": {
            name: _grouped(forecasts, "series", name) for name in ("ensemble", "persistence")
        },
        "by_category": {},
    }

    forecasts["lead_band"] = pd.cut(
        forecasts["horizon"],
        [0, 7, 14, 21, 30],
        labels=list(LEAD_BANDS),
    )
    for name in model_columns:
        result["by_lead_band"][name] = _grouped(forecasts, "lead_band", name)

    forecasts["category"] = forecasts["series"].str.split("||", regex=False).str[0]
    for name in model_columns:
        result["by_category"][name] = _grouped(forecasts, "category", name)
    return result


def write_report(report, output_dir):
    """Write JSON plus flat comparison tables without changing model artifacts."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "baseline_report.json"
    json_path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    series_rows = []
    for model, rows in report["by_series"].items():
        series_rows.extend({"model": model, **row} for row in rows)
    series_path = output_dir / "baseline_by_series.csv"
    pd.DataFrame(series_rows).to_csv(series_path, index=False)

    lead_rows = []
    for model, rows in report["by_lead_band"].items():
        lead_rows.extend({"model": model, **row} for row in rows)
    lead_path = output_dir / "baseline_by_lead_band.csv"
    pd.DataFrame(lead_rows).to_csv(lead_path, index=False)
    return {"json": str(json_path), "by_series": str(series_path), "by_lead_band": str(lead_path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    report = build_report(args.bundle)
    paths = write_report(report, args.output_dir)
    print(json.dumps({"paths": paths, "summary": report["models"]["ensemble"]}, indent=2))


if __name__ == "__main__":
    main()
