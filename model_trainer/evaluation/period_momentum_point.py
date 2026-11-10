"""Frozen one-coefficient period-momentum screen against persistence.

The evaluation window has been inspected in earlier diagnostics. This script
is reproducible research and cannot authorize production promotion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from data.preprocessor import DataPreprocessor
from evaluation.horizon_specific import SPECS, build_period_panel
from evaluation.period_persistence_intervals import (
    MAX_ANCHOR_AGE_DAYS, SOURCE, eligible_anchor,
)


ROOT = Path(__file__).resolve().parents[2]
TARGETS = ROOT / "audits/foodcast_accuracy_20261018/period_persistence_intervals_v3/paired_period_targets.csv"
DIRECT_ROOT = ROOT / "audits/foodcast_accuracy_20261017/relative5_test_confirmation_v2"
PLAN = ROOT / "audits/foodcast_accuracy_20261018/period_momentum_point_plan.md"
OUTPUT_ROOT = ROOT / "audits/foodcast_accuracy_20261018"
KEYS = ["series", "forecast_origin", "lead", "target_start", "target_end"]
EVALUATION_START = pd.Timestamp("2026-04-05")
TARGET_CUTOFF = pd.Timestamp("2026-09-30")
HOLDOUT_START = pd.Timestamp("2026-10-06")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def origin_features(raw_source: pd.DataFrame, targets: pd.DataFrame,
                    horizon: str) -> pd.DataFrame:
    """Compute consecutive completed-period movement at each saved origin."""
    panel = build_period_panel(DataPreprocessor().validate(raw_source), SPECS[horizon])
    result = []
    key_names = ["product_category", "product_name", "product_variant", "origin", "unit"]
    subset = targets.loc[targets.horizon.eq(horizon)]
    for key, target_group in subset.groupby("series", sort=True):
        parts = str(key).split("||")
        if len(parts) != len(key_names):
            raise ValueError(f"Malformed canonical series: {key}")
        history = panel
        for column, value in zip(key_names, parts):
            history = history.loc[history[column].astype(str).eq(value)]
        history = history.sort_values("period_start").reset_index(drop=True)
        if history.empty:
            raise ValueError(f"No period history for {key}")
        for origin_value, group in target_group.groupby("forecast_origin", sort=True):
            origin = pd.Timestamp(origin_value).normalize()
            eligible = history.loc[pd.to_datetime(history.period_end).le(origin)]
            expected_anchor = eligible_anchor(history, origin)
            if expected_anchor is None:
                raise ValueError(f"Origin has no eligible point anchor: {key} {origin}")
            point, age = expected_anchor
            if not np.isclose(point, group.persistence.iloc[0], rtol=0, atol=1e-8):
                raise ValueError(f"Period persistence mismatch at {key} {origin}")
            latest = eligible.iloc[-1]
            previous_start = (pd.Timestamp(latest.period_start) - pd.Timedelta(days=7)
                              if horizon == "weekly" else
                              (pd.Timestamp(latest.period_start) - pd.offsets.MonthBegin(1)))
            previous = eligible.loc[pd.to_datetime(eligible.period_start).eq(previous_start)]
            prior = float(previous.period_value.iloc[-1]) if len(previous) == 1 else np.nan
            change = point / prior - 1.0 if np.isfinite(prior) and prior > 0 else np.nan
            result.append({"series": str(key), "forecast_origin": origin,
                           "anchor": point, "return_1": float(change),
                           "prior_period_value": prior, "anchor_age_days": int(age),
                           "adjacent_prior_period_supported": bool(np.isfinite(change))})
    frame = pd.DataFrame(result)
    if (frame.empty or frame.duplicated(["series", "forecast_origin"]).any()
            or (frame.anchor_age_days > MAX_ANCHOR_AGE_DAYS).any()):
        raise ValueError("Period origin feature construction failed")
    return frame


def fit_beta(calibration: pd.DataFrame, horizon: str) -> dict:
    required = {"series", "forecast_origin", "lead", "actual", "persistence", "return_1"}
    if calibration.empty or not required.issubset(calibration):
        raise ValueError("Calibration rows or period movement are missing")
    data = calibration.loc[np.isfinite(calibration.return_1)].copy()
    multiplier = data.lead.to_numpy(dtype=float) if horizon == "weekly" else 1.0
    x = data.return_1.to_numpy(dtype=float) * multiplier
    anchor = data.persistence.to_numpy(dtype=float)
    actual = data.actual.to_numpy(dtype=float)
    y = actual / anchor - 1.0
    valid = np.isfinite(x) & np.isfinite(y) & (anchor > 0) & (np.abs(x) > 1e-12)
    data = data.loc[valid].copy()
    x, y = x[valid], y[valid]
    if data.empty:
        raise ValueError(f"No usable origin momentum for {horizon}")
    counts = data.series.value_counts()
    weights = np.abs(x) / data.series.map(counts).to_numpy(dtype=float)
    ratios = y / x
    order = np.argsort(ratios, kind="mergesort")
    ratios, weights = ratios[order], weights[order]
    if not np.isfinite(ratios).all() or not np.isfinite(weights).all() or weights.sum() <= 0:
        raise ValueError("Invalid weighted trend-response fit")
    beta = float(ratios[np.searchsorted(np.cumsum(weights), weights.sum() / 2,
                                        side="left")])
    series_counts = data.groupby("series").forecast_origin.nunique()
    return {"beta": beta, "fit_targets": int(len(data)),
            "fit_series": int(data.series.nunique()),
            "fit_origins": int(data.forecast_origin.nunique()),
            "minimum_origins_per_fitted_series": int(series_counts.min()),
            "median_origins_per_fitted_series": float(series_counts.median()),
            "method": "equal-series weighted median LAD of target_relative / (return_1 * lead); monthly lead=1"}


def add_predictions(targets: pd.DataFrame, features: pd.DataFrame,
                    horizon: str, beta: float) -> pd.DataFrame:
    result = targets.merge(features, on=["series", "forecast_origin"], how="left",
                           validate="many_to_one")
    if result.anchor.isna().any() or not np.allclose(
            result.persistence, result.anchor, rtol=0, atol=1e-8):
        raise ValueError("Candidate rows do not retain matched persistence anchors")
    change = result.return_1.to_numpy(dtype=float)
    if horizon == "weekly":
        change = change * result.lead.to_numpy(dtype=float)
    response = np.where(np.isfinite(change), beta * change, 0.0)
    result["momentum_point"] = np.maximum(0.01,
                                          result.persistence.to_numpy(dtype=float)
                                          * (1.0 + response))
    result["momentum_applied"] = np.isfinite(result.return_1)
    result["relative_feature"] = change
    if not np.isfinite(result.momentum_point).all():
        raise ValueError("Nonfinite momentum forecast")
    return result


def metric(rows: pd.DataFrame, prediction: str) -> dict:
    if rows.empty:
        return {"n": 0}
    actual = rows.actual.to_numpy(dtype=float)
    predicted = rows[prediction].to_numpy(dtype=float)
    if (not np.isfinite(actual).all() or not np.isfinite(predicted).all()
            or (actual <= 0).any()):
        raise ValueError("Invalid point metric inputs")
    error = predicted - actual
    absolute = np.abs(error)
    relative = absolute / actual
    return {"n": int(len(rows)), "series": int(rows.series.nunique()),
            "origins": int(rows.forecast_origin.nunique()),
            "mae_php": float(absolute.mean()),
            "rmse_php": float(np.sqrt(np.square(error).mean())),
            "mape_pct": float(relative.mean() * 100),
            "bias_php": float(error.mean()),
            "within_5_php_pct": float((absolute <= 5).mean() * 100),
            "within_5_percent_pct": float((relative <= .05).mean() * 100)}


def summarize(rows: pd.DataFrame, prediction: str) -> dict:
    per_series = [metric(group, prediction) for _, group in rows.groupby("series", sort=True)]
    macro = {name: float(np.mean([item[name] for item in per_series]))
             for name in ("mae_php", "rmse_php", "mape_pct", "bias_php",
                          "within_5_php_pct", "within_5_percent_pct")}
    return {"pooled": metric(rows, prediction), "macro_equal_series": macro,
            "by_series": {series: metric(group, prediction)
                          for series, group in rows.groupby("series", sort=True)},
            "by_lead": {str(int(lead)): metric(group, prediction)
                        for lead, group in rows.groupby("lead", sort=True)},
            "days_1_2_or_month": metric(rows.loc[rows.lead.le(2)], prediction),
            "days_3_4_or_month": metric(rows.loc[rows.lead.ge(3)], prediction)}


def common_direct(rows: pd.DataFrame, path: Path, horizon: str,
                  strategy: str) -> tuple[dict, pd.DataFrame]:
    direct = pd.read_csv(path, float_precision="round_trip")
    prediction = f"candidate_{strategy}"
    required = {"series", "forecast_origin", "target_start", "target_end", "lead",
                "actual", prediction}
    if not required.issubset(direct):
        raise ValueError(f"Direct forecast lacks {sorted(required - set(direct))}")
    keys = ["series", "forecast_origin", "lead", "target_start", "target_end"]
    for frame in (rows, direct):
        for column in ("forecast_origin", "target_start", "target_end"):
            frame[column] = pd.to_datetime(frame[column]).dt.strftime("%Y-%m-%d")
    if direct.duplicated(keys).any():
        raise ValueError("Duplicate direct forecast keys")
    paired = rows.merge(direct[keys + ["actual", prediction]], on=keys,
                        how="inner", validate="one_to_one", suffixes=("_momentum", "_direct"))
    if paired.empty:
        raise ValueError("No common rows with selected direct candidate")
    if not np.isclose(paired.actual_momentum, paired.actual_direct, rtol=0, atol=1e-8).all():
        raise ValueError("Direct and momentum actuals disagree on common target keys")
    paired["actual"] = paired.actual_momentum
    paired["direct_point"] = paired[prediction]
    return {"n": int(len(paired)), "origins": int(paired.forecast_origin.nunique()),
            "momentum": summarize(paired, "momentum_point"),
            "persistence": summarize(paired, "persistence"),
            "direct_lightgbm": summarize(paired, "direct_point")}, paired


def run(targets_path: Path, source_path: Path, direct_root: Path,
        plan_path: Path, output_dir: Path) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite momentum result: {output_dir}")
    targets = pd.read_csv(targets_path, float_precision="round_trip")
    targets["forecast_origin"] = pd.to_datetime(targets.forecast_origin).dt.normalize()
    targets["target_start"] = pd.to_datetime(targets.target_start).dt.normalize()
    targets["target_end"] = pd.to_datetime(targets.target_end).dt.normalize()
    if (targets.target_end.max() > TARGET_CUTOFF
            or targets.target_end.max() >= HOLDOUT_START
            or targets.duplicated(KEYS).any()):
        raise ValueError("Target input reaches holdout or contains duplicate keys")
    raw = pd.DataFrame(json.loads(source_path.read_text(encoding="utf-8")))
    selection_path = direct_root / "selection_manifest.json"
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    if (selection.get("holdout_labels_used") is not False
            or selection.get("task_scope") != "objective"):
        raise ValueError("Direct comparator is not objective-scope, holdout-safe evidence")
    full, parameters, summaries, common, audit = [], {}, {}, {}, {}
    direct_paths = {"weekly": direct_root / "weekly/test_predictions.csv",
                    "monthly": direct_root / "monthly/test_predictions.csv"}
    for horizon in ("weekly", "monthly"):
        frame = targets.loc[targets.horizon.eq(horizon)].copy()
        feature = origin_features(raw, frame, horizon)
        frame = frame.merge(feature, on=["series", "forecast_origin"], how="left",
                            validate="many_to_one")
        if frame.return_1.isna().any() and frame.loc[
                frame.partition.eq("calibration"), "return_1"].isna().all():
            raise ValueError(f"No training momentum support for {horizon}")
        cal = frame.loc[frame.partition.eq("calibration")].copy()
        ev = frame.loc[frame.partition.eq("evaluation")].copy()
        if (ev.empty or cal.target_end.max() >= ev.forecast_origin.min()
                or ev.forecast_origin.min() < EVALUATION_START
                or ev.target_end.max() > TARGET_CUTOFF):
            raise ValueError(f"Nonchronological or invalid {horizon} split")
        params = fit_beta(cal, horizon)
        predicted = add_predictions(
            targets.loc[targets.horizon.eq(horizon)].copy(), feature, horizon, params["beta"])
        eval_rows = predicted.loc[predicted.partition.eq("evaluation")].copy()
        summaries[horizon] = {
            "fit": params,
            "calibration": {"targets": int(len(cal)),
                            "origins": int(cal.forecast_origin.nunique()),
                            "target_end_max": cal.target_end.max().date().isoformat(),
                            "momentum_signal_targets": int(cal.return_1.notna().sum())},
            "evaluation": {"targets": int(len(eval_rows)),
                           "origins": int(eval_rows.forecast_origin.nunique()),
                           "origin_min": eval_rows.forecast_origin.min().date().isoformat(),
                           "origin_max": eval_rows.forecast_origin.max().date().isoformat(),
                           "target_max": eval_rows.target_end.max().date().isoformat(),
                           "momentum_signal_targets": int(eval_rows.return_1.notna().sum()),
                           "metrics": {name: summarize(eval_rows, name)
                                       for name in ("persistence", "momentum_point")}},
        }
        strategy = selection["selected_strategy_by_horizon"][horizon]
        direct_result, direct_rows = common_direct(
            eval_rows.copy(), direct_paths[horizon], horizon, strategy)
        direct_result["selected_strategy"] = strategy
        summaries[horizon]["common_direct_test_origins"] = direct_result
        audit[horizon] = {"all_evaluation_rows": int(len(eval_rows)),
                          "direct_common_rows": int(len(direct_rows)),
                          "direct_common_origins": int(direct_rows.forecast_origin.nunique())}
        full.append(predicted)
        common[horizon] = direct_rows
        parameters[horizon] = params
    all_predictions = pd.concat(full, ignore_index=True)
    report = {
        "experiment": "equal_series_single_coefficient_period_momentum_vs_persistence",
        "target_rows_sha256": sha256(targets_path), "source_sha256": sha256(source_path),
        "plan_sha256": sha256(plan_path), "script_sha256": sha256(Path(__file__)),
        "direct_weekly_sha256": sha256(direct_paths["weekly"]),
        "direct_monthly_sha256": sha256(direct_paths["monthly"]),
        "direct_selection_manifest_sha256": sha256(selection_path),
        "preprocessing_contract": DataPreprocessor.preprocessing_contract(),
        "evaluation_previously_inspected": True, "holdout_labels_used": False,
        "production_promotion_permitted": False,
        "metrics_note": "All metrics are original PHP; MAPE is mean absolute error / positive actual; macro metrics average series equally.",
        "horizons": summaries,
    }
    output_dir.mkdir(parents=True)
    all_predictions.to_csv(output_dir / "all_period_predictions.csv", index=False)
    for horizon, paired in common.items():
        paired.to_csv(output_dir / f"{horizon}_direct_common.csv", index=False)
    (output_dir / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n",
                                             encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets", type=Path, default=TARGETS)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--direct-root", type=Path, default=DIRECT_ROOT)
    parser.add_argument("--plan", type=Path, default=PLAN)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.targets, args.source, args.direct_root, args.plan, args.output_dir)
    print(json.dumps({h: {"fit": result["fit"],
                          "persistence": result["evaluation"]["metrics"]["persistence"]["pooled"],
                          "momentum": result["evaluation"]["metrics"]["momentum_point"]["pooled"],
                          "direct_common": result["common_direct_test_origins"]["n"]}
                      for h, result in report["horizons"].items()}, indent=2))


if __name__ == "__main__":
    main()
