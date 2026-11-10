"""Historical screen for reweighting direct LSTM and recursive LightGBM paths.

The script never trains or promotes a model. Calibration uses the first six
saved validation origins only; later validation is the gate, and the previously
exposed saved test partition is included only as a retrospective diagnostic.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
RUN_ID = "20261001T025925Z_0661960a"
RUN_DIR = ROOT / "model_trainer" / "artifacts_v2" / "runs" / RUN_ID
MANIFEST_PATH = ROOT / "model_trainer" / "artifacts_v2" / "manifest.json"
VALIDATION_PATH = RUN_DIR / "validation_forecasts.csv"
TEST_PATH = RUN_DIR / "test_forecasts.csv"
DEFAULT_OUTPUT = ROOT / "audits" / "foodcast_accuracy_20261018" / "recursive_component_mix_v1"
PLAN_PATH = ROOT / "audits" / "foodcast_accuracy_20261018" / "recursive_component_mix_plan.md"
HOLDOUT_START = pd.Timestamp("2026-10-06")
CALIBRATION_ORIGIN_COUNT = 6
WEIGHT_GRID = np.linspace(0.0, 1.0, 1001)
KEYS = ["series", "forecast_origin", "target_date", "lead"]
MODELS = ("production_ensemble", "candidate_mix", "lstm_direct", "lgbm_recursive", "persistence")
PRIORITY_FRAGMENTS = (
    "chili||labuyo", "lettuce||romaine", "lettuce||green ice",
    "lettuce||iceberg", "bell pepper||red",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _finite(values: pd.Series) -> np.ndarray:
    return np.isfinite(pd.to_numeric(values, errors="coerce").to_numpy(dtype=float))


def load_forecasts(path: Path, partition: str) -> tuple[pd.DataFrame, dict]:
    """Load only observed, aligned 14-day rows and enforce the holdout seal."""
    frame = pd.read_csv(path)
    required = {
        "series", "origin", "date", "horizon", "actual", "lstm", "lgbm",
        "ensemble", "persistence",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{partition} forecasts missing columns: {sorted(missing)}")
    frame = frame.rename(columns={
        "origin": "forecast_origin", "date": "target_date", "horizon": "lead",
        "ensemble": "production_ensemble", "lstm": "lstm_direct",
        "lgbm": "lgbm_recursive",
    })
    frame["forecast_origin"] = pd.to_datetime(frame.forecast_origin, errors="coerce").dt.normalize()
    frame["target_date"] = pd.to_datetime(frame.target_date, errors="coerce").dt.normalize()
    frame["lead"] = pd.to_numeric(frame.lead, errors="coerce")
    for column in ("actual", "lstm_direct", "lgbm_recursive", "production_ensemble", "persistence"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if frame[KEYS].isna().any().any():
        raise ValueError(f"{partition} forecasts contain invalid key values")
    if frame.duplicated(KEYS).any():
        raise ValueError(f"{partition} forecasts contain duplicate keys")
    if frame.target_date.ge(HOLDOUT_START).any():
        raise ValueError(f"{partition} forecasts overlap the sealed prospective holdout")
    daily = frame.loc[frame.lead.between(1, 14)].copy()
    expected_target = daily.forecast_origin + pd.to_timedelta(daily.lead, unit="D")
    if not expected_target.eq(daily.target_date).all():
        raise ValueError(f"{partition} daily targets do not align with origin and lead")
    prediction_columns = ["lstm_direct", "lgbm_recursive", "production_ensemble", "persistence"]
    valid = np.isfinite(daily.actual.to_numpy(dtype=float)) & daily.actual.ge(0).to_numpy()
    for column in prediction_columns:
        valid &= _finite(daily[column])
    excluded = int((~valid).sum())
    daily = daily.loc[valid].sort_values(KEYS).reset_index(drop=True)
    if daily.empty:
        raise ValueError(f"{partition} has no complete observed daily rows")
    return daily, {
        "path": str(path.relative_to(ROOT)),
        "sha256": sha256(path),
        "source_rows": int(len(frame)),
        "daily_rows_before_validity_filter": int(len(frame.loc[frame.lead.between(1, 14)])),
        "scored_rows": int(len(daily)),
        "excluded_rows_with_invalid_actual_or_prediction": excluded,
        "series_count": int(daily.series.nunique()),
        "origins": [date.date().isoformat() for date in sorted(daily.forecast_origin.unique())],
        "target_start": daily.target_date.min().date().isoformat(),
        "target_end": daily.target_date.max().date().isoformat(),
    }


def fit_equal_series_weight(frame: pd.DataFrame, lead_start: int, lead_end: int) -> dict:
    """Fit direct-LSTM weight by equal-series macro MAE on supplied rows."""
    rows = frame.loc[frame.lead.between(lead_start, lead_end)]
    if rows.empty:
        raise ValueError(f"No calibration rows for leads {lead_start}-{lead_end}")
    actual = rows.actual.to_numpy(dtype=float)
    lstm = rows.lstm_direct.to_numpy(dtype=float)
    lgbm = rows.lgbm_recursive.to_numpy(dtype=float)
    series = rows.series.astype(str).to_numpy()
    groups = [np.flatnonzero(series == key) for key in sorted(set(series))]
    if len(groups) < 8:
        raise ValueError(f"Only {len(groups)} calibration series for leads {lead_start}-{lead_end}")
    losses = []
    for weight in WEIGHT_GRID:
        absolute_error = np.abs(actual - (weight * lstm + (1.0 - weight) * lgbm))
        losses.append(float(np.mean([absolute_error[index].mean() for index in groups])))
    minimum = min(losses)
    # Deterministic, conservative tie-break: prefer less recursive-component weight.
    best_indices = [index for index, loss in enumerate(losses) if np.isclose(loss, minimum, rtol=0, atol=1e-12)]
    best_index = max(best_indices)
    return {
        "lead_start": int(lead_start),
        "lead_end": int(lead_end),
        "lstm_weight": float(WEIGHT_GRID[best_index]),
        "recursive_lgbm_weight": float(1.0 - WEIGHT_GRID[best_index]),
        "calibration_macro_mae_php": float(losses[best_index]),
        "calibration_rows": int(len(rows)),
        "calibration_series": int(rows.series.nunique()),
        "calibration_origins": int(rows.forecast_origin.nunique()),
    }


def apply_mix(frame: pd.DataFrame, weights: list[dict]) -> pd.DataFrame:
    result = frame.copy()
    by_band = np.full(len(result), np.nan, dtype=float)
    for item in weights:
        mask = result.lead.between(item["lead_start"], item["lead_end"]).to_numpy()
        by_band[mask] = item["lstm_weight"]
    if not np.isfinite(by_band).all():
        raise ValueError("A forecast lead has no frozen component weight")
    result["candidate_mix"] = (
        by_band * result.lstm_direct.to_numpy(dtype=float)
        + (1.0 - by_band) * result.lgbm_recursive.to_numpy(dtype=float)
    )
    return result


def _one_series_metrics(rows: pd.DataFrame, prediction: str) -> dict:
    actual = rows.actual.to_numpy(dtype=float)
    predicted = rows[prediction].to_numpy(dtype=float)
    error = predicted - actual
    absolute = np.abs(error)
    positive = actual > 0
    return {
        "n": int(len(rows)),
        "mape_sample_count": int(positive.sum()),
        "zero_actual_count": int((actual == 0).sum()),
        "mae_php": float(absolute.mean()),
        "rmse_php": float(np.sqrt(np.mean(error ** 2))),
        "mape_pct": float(np.mean(absolute[positive] / actual[positive]) * 100.0) if positive.any() else None,
        "wape_pct": float(absolute.sum() / actual.sum() * 100.0) if actual.sum() > 0 else None,
        "bias_php": float(error.mean()),
        "within_5_php_pct": float(np.mean(absolute <= 5.0) * 100.0),
        "within_5_percent_pct": float(np.mean(absolute[positive] / actual[positive] <= 0.05) * 100.0) if positive.any() else None,
    }


def summarize(frame: pd.DataFrame, prediction: str) -> dict:
    """Pooled and equal-series macro metrics on one identical key set."""
    if frame.empty:
        raise ValueError("Cannot score an empty forecast frame")
    pooled = _one_series_metrics(frame, prediction)
    product_metrics = {
        str(series): _one_series_metrics(rows, prediction)
        for series, rows in frame.groupby("series", sort=True)
    }
    macro_fields = ("mae_php", "rmse_php", "mape_pct", "wape_pct", "bias_php",
                    "within_5_php_pct", "within_5_percent_pct")
    macro = {
        key: float(np.mean([metric[key] for metric in product_metrics.values() if metric[key] is not None]))
        if any(metric[key] is not None for metric in product_metrics.values()) else None
        for key in macro_fields
    }
    return {
        **pooled,
        "series_count": int(frame.series.nunique()),
        "origin_count": int(frame.forecast_origin.nunique()),
        "macro_equal_series": macro,
        "by_series": product_metrics,
    }


def _relative_reduction(baseline: float | None, candidate: float | None) -> float | None:
    if baseline is None or candidate is None or baseline == 0:
        return None
    return float((baseline - candidate) / baseline * 100.0)


def comparison(active: dict, candidate: dict) -> dict:
    primary = ("mae_php", "rmse_php", "mape_pct")
    pooled_reductions = {
        key: _relative_reduction(active.get(key), candidate.get(key))
        for key in primary
    }
    active_macro = active["macro_equal_series"]
    candidate_macro = candidate["macro_equal_series"]
    macro_reductions = {
        key: _relative_reduction(active_macro.get(key), candidate_macro.get(key))
        for key in primary
    }
    series_changes = {}
    for series, active_metric in active["by_series"].items():
        candidate_metric = candidate["by_series"].get(series)
        if candidate_metric is None:
            continue
        baseline = active_metric["mae_php"]
        change = (candidate_metric["mae_php"] - baseline) / baseline * 100.0 if baseline > 0 else None
        series_changes[series] = {
            "active_mae_php": baseline,
            "candidate_mae_php": candidate_metric["mae_php"],
            "mae_deterioration_pct": change,
            "priority_product": any(part in series.casefold() for part in PRIORITY_FRAGMENTS),
        }
    priority_regressions = {
        series: value for series, value in series_changes.items()
        if value["priority_product"] and value["mae_deterioration_pct"] is not None
        and value["mae_deterioration_pct"] > 10.0
    }
    within5_delta = (
        candidate.get("within_5_php_pct") - active.get("within_5_php_pct")
        if candidate.get("within_5_php_pct") is not None and active.get("within_5_php_pct") is not None
        else None
    )
    all_primary_improve = all(value is not None and value > 0 for value in pooled_reductions.values())
    all_macro_improve = all(value is not None and value > 0 for value in macro_reductions.values())
    return {
        "pooled_error_reduction_pct": pooled_reductions,
        "macro_error_reduction_pct": macro_reductions,
        "within_5_php_change_percentage_points": within5_delta,
        "series_count_with_mae_regression": sum(
            value["mae_deterioration_pct"] is not None and value["mae_deterioration_pct"] > 0
            for value in series_changes.values()),
        "series_count_with_mae_regression_over_10_pct": sum(
            value["mae_deterioration_pct"] is not None and value["mae_deterioration_pct"] > 10
            for value in series_changes.values()),
        "priority_series_mae_regressions_over_10_pct": priority_regressions,
        "all_prespecified_comparison_conditions_met": bool(
            all_primary_improve and all_macro_improve and not priority_regressions
            and (within5_delta is None or within5_delta >= 0.0)),
        "per_series_comparison": series_changes,
    }


def _score_partition(frame: pd.DataFrame) -> dict:
    predictions = {}
    for model in MODELS:
        predictions[model] = summarize(frame, model)
    by_lead = {}
    for lead, rows in frame.groupby("lead", sort=True):
        by_lead[str(int(lead))] = {
            "pooled": {model: _one_series_metrics(rows, model) for model in MODELS},
            "by_series": {
                str(series): {model: _one_series_metrics(product_rows, model)
                              for model in MODELS}
                for series, product_rows in rows.groupby("series", sort=True)
            },
        }
    return {"models": predictions, "by_lead": by_lead}


def run_experiment(
    validation_path: Path = VALIDATION_PATH,
    test_path: Path = TEST_PATH,
    manifest_path: Path = MANIFEST_PATH,
    output_dir: Path = DEFAULT_OUTPUT,
) -> dict:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Refusing to overwrite nonempty output directory: {output_dir}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("active_run") != RUN_ID:
        raise ValueError(f"Expected active run {RUN_ID}, found {manifest.get('active_run')}")
    validation, validation_meta = load_forecasts(validation_path, "validation")
    test, test_meta = load_forecasts(test_path, "historical test")
    if validation.target_date.max() >= test.target_date.min():
        raise ValueError("Validation and test target periods overlap or are out of order")
    origins = sorted(validation.forecast_origin.unique())
    if len(origins) <= CALIBRATION_ORIGIN_COUNT:
        raise ValueError("Not enough validation origins after six-origin calibration")
    calibration_origins = set(origins[:CALIBRATION_ORIGIN_COUNT])
    calibration = validation.loc[validation.forecast_origin.isin(calibration_origins)].copy()
    gate = validation.loc[~validation.forecast_origin.isin(calibration_origins)].copy()
    weights = [
        fit_equal_series_weight(calibration, 1, 7),
        fit_equal_series_weight(calibration, 8, 14),
    ]
    calibration = apply_mix(calibration, weights)
    gate = apply_mix(gate, weights)
    test = apply_mix(test, weights)
    gate_scores = _score_partition(gate)
    gate_comparison = comparison(
        gate_scores["models"]["production_ensemble"],
        gate_scores["models"]["candidate_mix"],
    )
    test_scores = _score_partition(test)
    test_comparison = comparison(
        test_scores["models"]["production_ensemble"],
        test_scores["models"]["candidate_mix"],
    )
    calibration_scores = _score_partition(calibration)
    report = {
        "schema_version": 1,
        "experiment": "recursive_component_mix",
        "run_id": RUN_ID,
        "active_pointer": manifest.get("active_run"),
        "target_definition": "14 consecutive daily targets; lead equals calendar days after origin",
        "candidate_definition": "lead-band convex mix of direct LSTM point and recursively fed LightGBM point",
        "fit_rule": "equal-series macro MAE; 0.001 grid; ties favor more LSTM weight",
        "calibration_origin_count": CALIBRATION_ORIGIN_COUNT,
        "calibration_origins": [date.date().isoformat() for date in sorted(calibration_origins)],
        "validation_gate_origins": [date.date().isoformat() for date in sorted(gate.forecast_origin.unique())],
        "frozen_weights": weights,
        "input_files": {
            "manifest": {"path": str(manifest_path.relative_to(ROOT)), "sha256": sha256(manifest_path)},
            "validation": validation_meta,
            "historical_test": test_meta,
            "plan": {"path": str(PLAN_PATH.relative_to(ROOT)), "sha256": sha256(PLAN_PATH)},
        },
        "validation_calibration_metrics": calibration_scores,
        "later_validation_metrics": gate_scores,
        "later_validation_comparison_to_production": gate_comparison,
        "historical_test_metrics": test_scores,
        "historical_test_comparison_to_production": test_comparison,
        "historical_test_independence": (
            "not independent: these saved active-vintage outcomes appeared in previous audits "
            "and were viewed in preliminary same-turn candidate screening"
        ),
        "mape_policy": "mean absolute percentage error on positive actual prices only; zero actuals remain in PHP metrics",
        "macro_policy": "unweighted mean of per-series MAE/RMSE/MAPE; RMSE is averaged from each series' RMSE",
        "promotion_permitted": False,
        "production_changed": False,
        "sealed_prospective_holdout_read": False,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    predictions = pd.concat([
        calibration.assign(partition="calibration"),
        gate.assign(partition="later_validation"),
        test.assign(partition="historical_test_diagnostic"),
    ], ignore_index=True).sort_values(KEYS).reset_index(drop=True)
    predictions.to_csv(output_dir / "predictions.csv", index=False)
    report["script_sha256"] = sha256(Path(__file__).resolve())
    (output_dir / "report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation", type=Path, default=VALIDATION_PATH)
    parser.add_argument("--test", type=Path, default=TEST_PATH)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    report = run_experiment(args.validation, args.test, args.manifest, args.output_dir)
    def compact(partition, label):
        models = report[partition]["models"]
        fields = ("n", "series_count", "origin_count", "mae_php", "rmse_php",
                  "mape_pct", "bias_php", "within_5_php_pct")
        return {
            label: {
                model: {key: models[model][key] for key in fields}
                for model in ("production_ensemble", "candidate_mix", "lstm_direct",
                              "lgbm_recursive", "persistence")
            }
        }
    print(json.dumps({
        "output_dir": str(args.output_dir),
        "weights": report["frozen_weights"],
        "validation_gate_passed": report["later_validation_comparison_to_production"]["all_prespecified_comparison_conditions_met"],
        **compact("later_validation_metrics", "later_validation"),
        **compact("historical_test_metrics", "historical_test_diagnostic"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
