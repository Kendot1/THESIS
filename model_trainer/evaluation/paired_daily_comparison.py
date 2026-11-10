"""Pair a daily candidate with saved active-production forecasts by origin/key."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ACTIVE = ROOT / "model_trainer/artifacts_v2/runs/20261001T025925Z_0661960a/test_forecasts.csv"
DEFAULT_CANDIDATE = ROOT / "audits/foodcast_accuracy_20261017/active_daily_paired_v2/daily/test_predictions.csv"
DEFAULT_OUTPUT = ROOT / "audits/foodcast_accuracy_20261017/active_daily_paired_v2/paired_comparison"
KEYS = ["series", "forecast_origin", "target_date", "lead"]
PRIORITY_FRAGMENTS = (
    "Bell Pepper||Red", "Chili||Labuyo", "Lettuce||Green Ice",
    "Lettuce||Iceberg", "Lettuce||Romaine",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _normalize(active: pd.DataFrame, candidate: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    active_required = {"series", "origin", "date", "horizon", "actual", "ensemble", "persistence"}
    candidate_required = {
        "series", "forecast_origin", "target_start", "lead", "actual",
        "candidate_shared", "persistence",
    }
    if active_required - set(active.columns):
        raise ValueError(f"Active forecasts are missing {sorted(active_required - set(active.columns))}")
    if candidate_required - set(candidate.columns):
        raise ValueError(f"Candidate forecasts are missing {sorted(candidate_required - set(candidate.columns))}")
    left = active.loc[pd.to_numeric(active.horizon, errors="coerce").le(14)].copy()
    left = left.rename(columns={
        "origin": "forecast_origin", "date": "target_date", "horizon": "lead",
        "actual": "actual_active", "persistence": "persistence_active",
    })
    right = candidate.rename(columns={
        "target_start": "target_date", "actual": "actual_candidate",
    }).copy()
    for frame in (left, right):
        frame["forecast_origin"] = pd.to_datetime(frame.forecast_origin, errors="coerce").dt.normalize()
        frame["target_date"] = pd.to_datetime(frame.target_date, errors="coerce").dt.normalize()
        frame["lead"] = pd.to_numeric(frame.lead, errors="coerce")
    if left[KEYS].isna().any().any() or right[KEYS].isna().any().any():
        raise ValueError("Forecast keys contain invalid dates or leads")
    if left.duplicated(KEYS).any() or right.duplicated(KEYS).any():
        raise ValueError("Forecasts contain duplicate series/origin/date/lead keys")
    return left, right


def _metrics(frame: pd.DataFrame, prediction: str) -> dict:
    actual_all = pd.to_numeric(frame.actual_candidate, errors="coerce").to_numpy(dtype=float)
    predicted_all = pd.to_numeric(frame[prediction], errors="coerce").to_numpy(dtype=float)
    valid = np.isfinite(actual_all) & np.isfinite(predicted_all) & (actual_all >= 0)
    actual, predicted = actual_all[valid], predicted_all[valid]
    if not len(actual):
        return {"n": 0, "mae_php": None, "rmse_php": None, "mape_pct": None,
                "mape_n": 0, "within_5_percent_pct": None, "within_5_php_pct": None,
                "relative_hit_n": 0, "zero_actual_n": 0,
                "excluded_nonfinite_or_negative_n": int(len(frame)), "bias_php": None}
    error = predicted - actual
    absolute = np.abs(error)
    positive = actual > 0
    return {
        "n": int(len(actual)),
        "mae_php": float(absolute.mean()),
        "rmse_php": float(np.sqrt(np.mean(error ** 2))),
        "mape_pct": float(np.mean(absolute[positive] / actual[positive]) * 100.0) if positive.any() else None,
        "mape_n": int(positive.sum()),
        "within_5_percent_pct": float(np.mean(absolute[positive] / actual[positive] <= 0.05) * 100.0) if positive.any() else None,
        "within_5_php_pct": float(np.mean(absolute <= 5.0) * 100.0),
        "relative_hit_n": int(positive.sum()),
        "zero_actual_n": int((actual == 0).sum()),
        "excluded_nonfinite_or_negative_n": int(len(frame) - len(actual)),
        "bias_php": float(error.mean()),
    }


def _mean_or_none(values: np.ndarray) -> float | None:
    finite = values[np.isfinite(values)]
    return float(finite.mean()) if len(finite) else None


def _by_origin_volatility(paired: pd.DataFrame, predictions: list[str]) -> dict:
    """Describe errors by the candidate's origin-only volatility bucket."""
    if "volatility_bucket" not in paired:
        return {"status": "unavailable_missing_origin_feature"}
    buckets = paired.volatility_bucket.astype("string").fillna("missing")
    return {
        str(bucket): {
            "n_rows": int(mask.sum()),
            "models": {name: _metrics(paired.loc[mask], name) for name in predictions},
        }
        for bucket in ("low", "medium", "high", "missing")
        if (mask := buckets.eq(bucket)).any()
    }


def _by_realized_move(paired: pd.DataFrame, predictions: list[str]) -> dict:
    """Retrospective error slices by realized move from the frozen origin anchor."""
    anchor_column = "anchor_candidate" if "anchor_candidate" in paired else "anchor"
    if anchor_column not in paired:
        return {"status": "unavailable_missing_origin_anchor"}
    actual = pd.to_numeric(paired.actual_candidate, errors="coerce").to_numpy(dtype=float)
    anchor = pd.to_numeric(paired[anchor_column], errors="coerce").to_numpy(dtype=float)
    valid_label = np.isfinite(actual) & (actual >= 0) & np.isfinite(anchor)
    move = actual - anchor
    absolute_move = np.abs(move)
    labels = np.full(len(paired), "", dtype=object)
    labels[valid_label & (absolute_move <= 5.0)] = "abs_move_le_5_php"
    labels[valid_label & (absolute_move > 5.0) & (absolute_move <= 15.0)] = "abs_move_gt_5_le_15_php"
    labels[valid_label & (absolute_move > 15.0)] = "abs_move_gt_15_php"

    result = {}
    for label in ("abs_move_le_5_php", "abs_move_gt_5_le_15_php", "abs_move_gt_15_php"):
        mask = labels == label
        rows = paired.loc[mask]
        group_move = move[mask]
        group_anchor = anchor[mask]
        model_results = {}
        for name in predictions:
            prediction = pd.to_numeric(rows[name], errors="coerce").to_numpy(dtype=float)
            valid_prediction = np.isfinite(prediction) & np.isfinite(group_anchor)
            direction_rows = valid_prediction & (np.abs(group_move) > 5.0)
            direction_n = int(direction_rows.sum())
            correct_direction = (
                np.sign(prediction[direction_rows] - group_anchor[direction_rows])
                == np.sign(group_move[direction_rows])
            )
            model_results[name] = {
                "metrics": _metrics(rows, name),
                "mean_abs_forecast_move_php": _mean_or_none(
                    np.abs(prediction[valid_prediction] - group_anchor[valid_prediction])
                ),
                "direction_n_abs_realized_move_gt_5_php": direction_n,
                "direction_accuracy_pct_abs_realized_move_gt_5_php": (
                    float(correct_direction.mean() * 100.0) if direction_n else None
                ),
            }
        result[label] = {
            "n_rows": int(mask.sum()),
            "mean_abs_realized_move_php": _mean_or_none(absolute_move[mask]),
            "mean_signed_realized_move_php": _mean_or_none(group_move),
            "models": model_results,
        }
    return result


def pair_forecasts(active: pd.DataFrame, candidate: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    left, right = _normalize(active, candidate)
    paired = left.merge(right, on=KEYS, how="inner", validate="one_to_one", suffixes=("_active", "_candidate"))
    if paired.empty:
        raise ValueError("No common forecast keys between active and candidate")
    paired["actual_label_mismatch"] = paired.actual_active.ne(paired.actual_candidate)
    paired["actual_difference_php"] = paired.actual_active - paired.actual_candidate
    paired["canonical_actual_php"] = pd.to_numeric(paired.actual_candidate, errors="coerce")
    predictions = ["ensemble", "candidate_shared", "persistence_active", "lgbm", "lstm"]
    predictions = [name for name in predictions if name in paired]
    per_series = {
        str(series): {name: _metrics(rows, name) for name in predictions}
        for series, rows in paired.groupby("series", sort=True)
    }
    macro = {}
    for name in predictions:
        rows = [result[name] for result in per_series.values() if result[name]["mae_php"] is not None]
        macro[name] = {
            metric: float(np.mean([row[metric] for row in rows]))
            for metric in ("mae_php", "rmse_php", "mape_pct", "within_5_percent_pct",
                           "within_5_php_pct", "bias_php")
        }
    by_lead = {
        str(int(lead)): {name: _metrics(rows, name) for name in predictions}
        for lead, rows in paired.groupby("lead", sort=True)
    }
    priority = {
        series: per_series[series]
        for series in per_series
        if any(fragment in series for fragment in PRIORITY_FRAGMENTS)
    }
    candidate_regressions = {
        metric: sum(
            per_series[series]["candidate_shared"][metric]
            > per_series[series]["ensemble"][metric]
            for series in per_series
        )
        for metric in ("mae_php", "rmse_php", "mape_pct")
    }
    comparison = {
        "evaluation_status": "historical_paired_diagnostic_not_prospective_holdout",
        "paired_rows": int(len(paired)),
        "forecast_origins": sorted(paired.forecast_origin.dt.strftime("%Y-%m-%d").unique().tolist()),
        "origin_count": int(paired.forecast_origin.nunique()),
        "series_count": int(paired.series.nunique()),
        "lead_values": sorted(int(x) for x in paired.lead.unique()),
        "active_daily_rows_leads_1_to_14": int(len(left)),
        "candidate_rows": int(len(right)),
        "candidate_rows_without_active_key": int(len(right.merge(left[KEYS], on=KEYS, how="left", indicator=True).query("_merge == 'left_only'"))),
        "active_rows_without_candidate_key": int(len(left.merge(right[KEYS], on=KEYS, how="left", indicator=True).query("_merge == 'left_only'"))),
        "actual_label_mismatch_count": int(paired.actual_label_mismatch.sum()),
        "actual_label_policy": "use candidate frozen-snapshot actual for both forecasts on every common key",
        "metric_policy": (
            "MAE/RMSE/bias/Within-PHP-5 include finite predictions with nonnegative actuals, including zero actuals; "
            "MAPE and relative-Within-5 use positive actuals only; negative/nonfinite actuals and nonfinite predictions "
            "are explicitly counted as excluded. No near-zero denominator floor is applied."
        ),
        "actual_label_mismatches": paired.loc[
            paired.actual_label_mismatch,
            KEYS + ["actual_active", "actual_candidate", "actual_difference_php"],
        ].assign(
            forecast_origin=lambda x: x.forecast_origin.dt.strftime("%Y-%m-%d"),
            target_date=lambda x: x.target_date.dt.strftime("%Y-%m-%d"),
        ).to_dict(orient="records"),
        "aggregate_metrics": {name: _metrics(paired, name) for name in predictions},
        "macro_series_metrics_equal_weight": macro,
        "per_series_regression_counts_vs_active_ensemble": candidate_regressions,
        "by_lead": by_lead,
        "origin_volatility_bucket_definition": (
            "Daily rolling coefficient of variation at each forecast origin: population standard "
            "deviation over the trailing 30 observed daily periods divided by the origin anchor; "
            "low < 0.05, medium [0.05, 0.15), high >= 0.15."
        ),
        "by_origin_volatility_bucket": _by_origin_volatility(paired, predictions),
        "realized_move_diagnostic_policy": (
            "Retrospective descriptive stratification only: absolute canonical actual minus the "
            "forecast-origin anchor, in PHP bins <=5, >5 to 15, and >15. Outcome-derived bins "
            "are not features, selection criteria, or promotion evidence. Direction is scored only "
            "when the absolute realized move exceeds PHP 5."
        ),
        "by_realized_move_from_origin_anchor": _by_realized_move(paired, predictions),
        "priority_series": priority,
        "error_reduction_pct_candidate_vs_active": {
            metric: float((
                _metrics(paired, "ensemble")[metric]
                - _metrics(paired, "candidate_shared")[metric]
            ) / _metrics(paired, "ensemble")[metric] * 100.0)
            for metric in ("mae_php", "rmse_php", "mape_pct")
        },
        "relative_hit_rate_delta_percentage_points_candidate_vs_active": float(
            _metrics(paired, "candidate_shared")["within_5_percent_pct"]
            - _metrics(paired, "ensemble")["within_5_percent_pct"]
        ),
    }
    return paired, comparison


def run(active_path: Path, candidate_path: Path, output_dir: Path) -> dict:
    active = pd.read_csv(active_path)
    candidate = pd.read_csv(candidate_path)
    paired, report = pair_forecasts(active, candidate)
    report["sources"] = {
        "active_forecasts": {"path": str(active_path), "sha256": _sha256(active_path)},
        "candidate_forecasts": {"path": str(candidate_path), "sha256": _sha256(candidate_path)},
        "analysis_script": {"path": str(Path(__file__).resolve()), "sha256": _sha256(Path(__file__))},
    }
    report["canonical_snapshot_sha256"] = "1d61cb78c839efb54b677440d3b94daa8d82e339f5a7bed0d2b05a761f8dfba4"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    paired.assign(
        forecast_origin=paired.forecast_origin.dt.strftime("%Y-%m-%d"),
        target_date=paired.target_date.dt.strftime("%Y-%m-%d"),
    ).to_csv(output_dir / "paired_predictions.csv", index=False)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--active", type=Path, default=DEFAULT_ACTIVE)
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = run(args.active, args.candidate, args.output)
    print(json.dumps({
        "paired_rows": report["paired_rows"],
        "origin_count": report["origin_count"],
        "actual_label_mismatch_count": report["actual_label_mismatch_count"],
        "active": report["aggregate_metrics"]["ensemble"],
        "candidate": report["aggregate_metrics"]["candidate_shared"],
        "error_reduction_pct_candidate_vs_active": report["error_reduction_pct_candidate_vs_active"],
    }, indent=2))


if __name__ == "__main__":
    main()
