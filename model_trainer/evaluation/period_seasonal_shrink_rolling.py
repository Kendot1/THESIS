"""Refit the frozen seasonal-shrink rule before each calendar-year window."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from evaluation.period_seasonal_shrink import (
    DIRECT_ROOT, INPUT, INPUT_REPORT, KEYS, TARGET_CUTOFF, HOLDOUT_START,
    add_candidate, compare, fit_beta, sha256,
)


ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "audits/foodcast_accuracy_20261018/period_seasonal_shrink_rolling_plan.md"
YEARS = (2023, 2024, 2025, 2026)


def split_target_year(rows: pd.DataFrame, year: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    evaluation = rows.loc[rows.target_end.dt.year.eq(year)].copy()
    if evaluation.empty:
        raise ValueError(f"No target rows for rolling year {year}")
    first_origin = evaluation.forecast_origin.min()
    calibration = rows.loc[rows.target_end.lt(first_origin)].copy()
    if calibration.empty or calibration.target_end.max() >= first_origin:
        raise ValueError(f"No strictly earlier calibration for {year}")
    if (evaluation.target_start.le(evaluation.forecast_origin).any()
            or evaluation.target_end.le(evaluation.forecast_origin).any()):
        raise ValueError("Evaluation target is not future to its origin")
    return calibration, evaluation


def validate_input(rows: pd.DataFrame) -> pd.DataFrame:
    if not set(KEYS + ["actual", "persistence", "seasonal_value",
                       "seasonal_supported"]).issubset(rows):
        raise ValueError("Seasonal-shrink input schema is incomplete")
    result = rows.copy()
    for column in ("forecast_origin", "target_start", "target_end"):
        result[column] = pd.to_datetime(result[column], errors="raise").dt.normalize()
    result["lead"] = pd.to_numeric(result.lead, errors="raise").astype(int)
    result["seasonal_supported"] = result.seasonal_supported.astype(str).str.lower().eq("true")
    if result.duplicated(KEYS).any():
        raise ValueError("Duplicate target keys")
    if (result.target_end.max() > TARGET_CUTOFF
            or result.target_end.max() >= HOLDOUT_START
            or result.target_start.le(result.forecast_origin).any()
            or result.target_end.le(result.forecast_origin).any()):
        raise ValueError("Input reaches the holdout or contains a nonfuture target")
    weekly = result.loc[result.horizon.eq("weekly")]
    monthly = result.loc[result.horizon.eq("monthly")]
    if not result.horizon.isin(["weekly", "monthly"]).all() or result.empty:
        raise ValueError("Input contains unsupported horizon values")
    if (not weekly.empty and not (weekly.target_start.dt.weekday.eq(0)
            & weekly.target_end.eq(weekly.target_start + pd.Timedelta(days=6))).all()):
        raise ValueError("Weekly input does not use complete Monday-Sunday periods")
    if (not monthly.empty and not (monthly.target_start.dt.day.eq(1)
            & monthly.target_end.eq(monthly.target_start + pd.offsets.MonthEnd(0))).all()):
        raise ValueError("Monthly input does not use complete calendar months")
    if (not np.isfinite(result[["actual", "persistence"]].to_numpy(dtype=float)).all()
            or result.actual.le(0).any() or result.persistence.le(0).any()):
        raise ValueError("Invalid actual or persistence point")
    return result


def run(input_path: Path, input_report_path: Path, plan_path: Path,
        output_dir: Path) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite rolling seasonal-shrink results: {output_dir}")
    upstream = json.loads(input_report_path.read_text(encoding="utf-8"))
    if (upstream.get("holdout_labels_used") is not False
            or upstream.get("production_promotion_permitted") is not False
            or upstream.get("source_report_date_max", "9999") >= "2026-10-06"):
        raise ValueError("Upstream seasonal-naive screen is not holdout-safe")
    rows = validate_input(pd.read_csv(input_path, float_precision="round_trip"))
    horizon_results, prediction_parts = {}, []
    for horizon in ("weekly", "monthly"):
        horizon_rows = rows.loc[rows.horizon.eq(horizon)].copy()
        if horizon_rows.empty:
            raise ValueError(f"No input rows for {horizon}")
        horizon_results[horizon] = {}
        for year in YEARS:
            calibration, evaluation = split_target_year(horizon_rows, year)
            fit = fit_beta(calibration)
            predicted = add_candidate(evaluation, fit["beta"])
            comparison = compare(predicted)
            record = {
                "fit": fit,
                "calibration": {
                    "targets": int(len(calibration)),
                    "series": int(calibration.series.nunique()),
                    "origins": int(calibration.forecast_origin.nunique()),
                    "latest_target_end": calibration.target_end.max().date().isoformat(),
                },
                "evaluation": {
                    "targets": int(len(predicted)),
                    "series": int(predicted.series.nunique()),
                    "origins": int(predicted.forecast_origin.nunique()),
                    "first_origin": predicted.forecast_origin.min().date().isoformat(),
                    "last_origin": predicted.forecast_origin.max().date().isoformat(),
                    "target_start_min": predicted.target_start.min().date().isoformat(),
                    "target_end_max": predicted.target_end.max().date().isoformat(),
                    "metrics": comparison,
                },
            }
            horizon_results[horizon][str(year)] = record
            predicted["rolling_window"] = year
            prediction_parts.append(predicted)
    predictions = pd.concat(prediction_parts, ignore_index=True)
    if (predictions.duplicated(KEYS).any()
            or predictions.target_end.max() > TARGET_CUTOFF
            or predictions.target_end.max() >= HOLDOUT_START):
        raise ValueError("Rolling evaluation output failed duplicate/date checks")
    report = {
        "experiment": "rolling_year_equal_series_lad_seasonal_shrink_vs_persistence",
        "input_sha256": sha256(input_path),
        "input_audit_report_sha256": sha256(input_report_path),
        "source_sha256": upstream["source_sha256"],
        "targets_sha256": upstream["targets_sha256"],
        "upstream_plan_sha256": upstream["plan_sha256"],
        "plan_sha256": sha256(plan_path),
        "script_sha256": sha256(Path(__file__)),
        "years": list(YEARS), "target_cutoff": TARGET_CUTOFF.date().isoformat(),
        "holdout_labels_used": False, "production_promotion_permitted": False,
        "retrospective_reuse_note": "All windows use overlapping reconstructed historical forecast paths and research-exposed labels; no prospective promotion evidence.",
        "horizons": horizon_results,
    }
    output_dir.mkdir(parents=True)
    predictions.to_csv(output_dir / "rolling_predictions.csv", index=False)
    (output_dir / "report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=INPUT)
    parser.add_argument("--input-report", type=Path, default=INPUT_REPORT)
    parser.add_argument("--plan", type=Path, default=PLAN)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.input, args.input_report, args.plan, args.output_dir)
    compact = {}
    for horizon, years in report["horizons"].items():
        compact[horizon] = {}
        for year, entry in years.items():
            pooled = entry["evaluation"]["metrics"]["persistence_all_rows"]["pooled"]
            shrink = entry["evaluation"]["metrics"]["shrink_all_rows"]["pooled"]
            compact[horizon][year] = {
                "beta": entry["fit"]["beta"],
                "targets": entry["evaluation"]["targets"],
                "origins": entry["evaluation"]["origins"],
                "mae_reduction_pct": entry["evaluation"]["metrics"][
                    "error_reduction_pct"]["all_rows"]["mae_php"],
                "rmse_reduction_pct": entry["evaluation"]["metrics"][
                    "error_reduction_pct"]["all_rows"]["rmse_php"],
                "mape_reduction_pct": entry["evaluation"]["metrics"][
                    "error_reduction_pct"]["all_rows"]["mape_pct"],
                "persistence_mae": pooled["mae_php"],
                "shrink_mae": shrink["mae_php"],
                "mae_regressions_over_10": len(entry["evaluation"]["metrics"][
                    "series_mae_regressions_over_10pct"]),
            }
    print(json.dumps(compact, indent=2))


if __name__ == "__main__":
    main()
