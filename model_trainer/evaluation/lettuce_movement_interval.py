"""Frozen research screen for origin-movement-scaled active daily intervals.

Calibration uses only the earlier 27 origins. Later historical outcomes have
already been studied and cannot authorize production promotion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from data.preprocessor import DataPreprocessor
from evaluation.dense_active_interval_replay import origin_schedule
from evaluation.lettuce_origin_risk import (
    INTERVALS, LETUCES, MAX_LAST_AGE_DAYS, MIN_OBS, REPLAY, ROOT, SOURCE,
    WINDOW_DAYS, trailing_return,
)


LEVELS = (0.80, 0.95)
MIN_CALIBRATION_ORIGINS = 20
KEYS = ["series", "origin", "date", "horizon"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def origin_features(source: pd.DataFrame) -> pd.DataFrame:
    required = {"product_category", "product_name", "product_variant", "origin",
                "unit", "report_date", "observed_price", "is_observed"}
    if not required.issubset(source):
        raise ValueError("Source lacks observed-price provenance")
    source = source.loc[source.product_category.eq("Vegetables")
                        & source.product_name.eq("Lettuce")
                        & source.product_variant.isin(LETUCES)
                        & source.origin.eq("Local") & source.unit.eq("kg")]
    if set(source.product_variant.unique()) != set(LETUCES):
        raise ValueError("Archived source lacks a priority lettuce")
    calibration_origins, evaluation_origins = origin_schedule()
    records = []
    for variant, history in source.groupby("product_variant", sort=True):
        series = "||".join(("Vegetables", "Lettuce", variant, "Local", "kg"))
        for origin in calibration_origins.union(evaluation_origins):
            feature = trailing_return(history, origin)
            records.append({"series": series, "origin": origin, **feature})
    result = pd.DataFrame(records)
    if (result.duplicated(["series", "origin"]).any()
            or result.return_14d.isna().any()
            or (result.latest_observation > result.origin).any()):
        raise ValueError("Origin signal is missing, duplicate, or uses future prices")
    return result


def fit_movement_slope(calibration: pd.DataFrame) -> dict:
    """Within-series OLS of log mean relative absolute error on return."""
    required = {"series", "origin", "actual", "ensemble_path", "return_14d"}
    if calibration.empty or not required.issubset(calibration):
        raise ValueError("Missing calibration labels or features")
    if (not np.isfinite(calibration[["actual", "ensemble_path", "return_14d"]]
                        .to_numpy(dtype=float)).all()
            or (calibration[["actual", "ensemble_path"]] <= 0).any().any()):
        raise ValueError("Invalid calibration prices")
    rows = calibration.assign(
        relative_absolute_error=np.abs(calibration.actual - calibration.ensemble_path)
        / calibration.ensemble_path)
    grouped = rows.groupby(["series", "origin"], sort=True).agg(
        mean_relative_absolute_error=("relative_absolute_error", "mean"),
        return_14d=("return_14d", "first"),
        targets=("relative_absolute_error", "size"),
    ).reset_index()
    if (len(grouped) < 12 or (grouped.mean_relative_absolute_error <= 0).any()
            or grouped.groupby("series").origin.nunique().min() < 4):
        raise ValueError("Not enough positive, independent origin groups to fit scale")
    grouped["log_mae"] = np.log(grouped.mean_relative_absolute_error)
    x = grouped.return_14d - grouped.groupby("series").return_14d.transform("mean")
    y = grouped.log_mae - grouped.groupby("series").log_mae.transform("mean")
    denominator = float(np.dot(x, x))
    if denominator <= 0:
        raise ValueError("Origin movement has no within-series variation")
    beta = float(np.dot(x, y) / denominator)
    if not np.isfinite(beta):
        raise ValueError("Nonfinite fitted movement coefficient")
    return {"beta": beta, "fit_groups": int(len(grouped)),
            "fit_origins": int(grouped.origin.nunique()),
            "fit_series": int(grouped.series.nunique()),
            "fit_targets": int(len(rows)),
            "fit_method": "within-series OLS log(mean absolute relative error) on origin 14-day return"}


def normalized_radius(calibration: pd.DataFrame, beta: float,
                      level: float) -> dict | None:
    """Finite-sample order statistic with explicit origin support."""
    if not 0 < level < 1 or not np.isfinite(beta):
        raise ValueError("Invalid nominal level or movement coefficient")
    if calibration.duplicated(["origin"]).any():
        raise ValueError("Duplicate calibration origin for a series/lead")
    if (calibration.empty or calibration.origin.nunique() < MIN_CALIBRATION_ORIGINS):
        return None
    scale = np.exp(beta * calibration.return_14d.to_numpy(dtype=float))
    scores = np.abs(calibration.actual.to_numpy(dtype=float)
                    - calibration.ensemble_path.to_numpy(dtype=float)) / scale
    if not np.isfinite(scores).all() or (scale <= 0).any():
        raise ValueError("Nonfinite normalized residual score")
    rank = math.ceil((len(scores) + 1) * level - 1e-12)
    if rank > len(scores):
        return None
    return {"radius": float(np.sort(scores)[rank - 1]),
            "calibration_targets": int(len(scores)),
            "calibration_origins": int(calibration.origin.nunique()),
            "order_rank": int(rank)}


def metrics(rows: pd.DataFrame, prefix: str) -> dict:
    if rows.empty:
        return {"targets": 0, "origins": 0, "coverage_pct": None,
                "mean_width_php": None, "upper_miss_pct": None,
                "lower_miss_pct": None}
    actual = rows.actual.to_numpy(dtype=float)
    lower = rows[f"{prefix}_lower"].to_numpy(dtype=float)
    upper = rows[f"{prefix}_upper"].to_numpy(dtype=float)
    if (not np.isfinite(np.column_stack((actual, lower, upper))).all()
            or (lower <= 0).any() or (upper < lower).any()):
        raise ValueError("Invalid interval score rows")
    return {"targets": int(len(rows)), "origins": int(rows.origin.nunique()),
            "coverage_pct": float(((actual >= lower) & (actual <= upper)).mean() * 100),
            "mean_width_php": float((upper - lower).mean()),
            "upper_miss_pct": float((actual > upper).mean() * 100),
            "lower_miss_pct": float((actual < lower).mean() * 100)}


def assert_eval_parity(selected: pd.DataFrame, replay: pd.DataFrame) -> None:
    """Require identical active points and truths on every supported key."""
    one_level = selected.loc[np.isclose(selected.nominal_level, LEVELS[0])]
    comparison = one_level.merge(
        replay[KEYS + ["actual", "ensemble_path"]], on=KEYS, how="left",
        validate="one_to_one", suffixes=("_interval", "_replay"))
    if (len(comparison) != len(one_level)
            or comparison.actual_replay.isna().any()
            or not np.isclose(comparison.actual_interval, comparison.actual_replay,
                              rtol=0, atol=1e-8).all()
            or not np.isclose(comparison.point, comparison.ensemble_path,
                              rtol=0, atol=1e-8).all()):
        raise ValueError("Interval rows do not match archived active replay points/actuals")


def evaluate(source: pd.DataFrame, replay: pd.DataFrame,
             intervals: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    features = origin_features(source)
    calibration_origins, evaluation_origins = origin_schedule()
    replay = replay.copy()
    replay["origin"] = pd.to_datetime(replay.origin).dt.normalize()
    replay["date"] = pd.to_datetime(replay.date).dt.normalize()
    if replay.duplicated(KEYS).any():
        raise ValueError("Duplicate replay targets")
    calibration = replay.loc[replay.origin.isin(calibration_origins)
                             & replay.series.isin(features.series)].copy()
    if (calibration.empty or calibration.date.max() >= evaluation_origins.min()
            or not calibration.date.gt(calibration.origin).all()):
        raise ValueError("Calibration target dates overlap evaluation")
    calibration = calibration.merge(features, on=["series", "origin"], how="left",
                                    validate="many_to_one")
    if calibration.return_14d.isna().any():
        raise ValueError("Calibration lacks origin signals")
    fit = fit_movement_slope(calibration)

    intervals = intervals.copy()
    intervals["origin"] = pd.to_datetime(intervals.origin).dt.normalize()
    intervals["date"] = pd.to_datetime(intervals.date).dt.normalize()
    if (intervals.duplicated(KEYS + ["nominal_level"]).any()
            or not intervals.origin.isin(evaluation_origins).all()
            or not intervals.date.gt(intervals.origin).all()
            or intervals.date.max() >= pd.Timestamp("2026-10-06")):
        raise ValueError("Intervals contain duplicate, wrong-period, or holdout rows")
    selected = intervals.loc[intervals.series.isin(features.series)
                             & intervals.nominal_level.isin(LEVELS)].copy()
    selected = selected.merge(features, on=["series", "origin"], how="left",
                              validate="many_to_one")
    if selected.empty or selected.return_14d.isna().any():
        raise ValueError("Evaluation rows lack origin signals")
    if (selected.groupby(KEYS).nominal_level.nunique() != len(LEVELS)).any():
        raise ValueError("80% and 95% evaluation rows differ")
    assert_eval_parity(selected, replay)

    radius_by_group = {}
    unsupported = []
    for level in LEVELS:
        for (series, lead), group in calibration.groupby(["series", "horizon"], sort=True):
            radius = normalized_radius(group, fit["beta"], level)
            if radius is None:
                unsupported.append({"series": series, "lead": int(lead),
                                    "level": level, "calibration_origins": int(group.origin.nunique())})
            else:
                radius_by_group[(series, int(lead), level)] = radius
    selected["radius"] = [radius_by_group.get((row.series, int(row.horizon),
                                               float(row.nominal_level)), {}).get("radius", np.nan)
                          for row in selected.itertuples()]
    supported = selected.loc[selected.radius.notna()].copy()
    if supported.empty:
        raise ValueError("No candidate intervals have calibration support")
    scale = np.exp(fit["beta"] * supported.return_14d.to_numpy(dtype=float))
    half_width = supported.radius.to_numpy(dtype=float) * scale
    if not np.isfinite(half_width).all():
        raise ValueError("Nonfinite candidate interval width")
    supported["candidate_lower"] = np.maximum(0.01, supported.point - half_width)
    supported["candidate_upper"] = supported.point + half_width
    if (supported.candidate_lower > supported.candidate_upper).any():
        raise ValueError("Malformed candidate bound")
    supported["quarter"] = supported.date.dt.to_period("Q").astype(str)

    summary = {"fit": fit, "selected_target_rows": int(len(selected)),
               "candidate_supported_rows": int(len(supported)),
               "unsupported_groups": unsupported, "levels": {}}
    for level in LEVELS:
        block = supported.loc[np.isclose(supported.nominal_level, level)].copy()
        reference = selected.loc[np.isclose(selected.nominal_level, level)]
        result = {"reference_targets": int(len(reference)), "common_targets": int(len(block)),
                  "reference_fixed_all_rows": metrics(reference, "fixed"),
                  "reference_expanding_all_rows": metrics(reference, "expanding"),
                  "common_pooled": {name: metrics(block, name)
                                    for name in ("candidate", "fixed", "expanding")},
                  "by_series": {}, "by_lead": {}, "by_quarter": {}}
        for label, field in (("by_series", "series"), ("by_lead", "horizon"),
                             ("by_quarter", "quarter")):
            for key, group in block.groupby(field, sort=True):
                result[label][str(key)] = {name: metrics(group, name)
                                           for name in ("candidate", "fixed", "expanding")}
        summary["levels"][f"{level:.2f}"] = result
    return summary, supported


def run(source_path: Path, replay_path: Path, intervals_path: Path,
        plan_path: Path, output_dir: Path) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite research result: {output_dir}")
    source = DataPreprocessor().validate(
        pd.DataFrame(json.loads(source_path.read_text(encoding="utf-8"))),
        apply_source_quality_exclusions=False)
    replay = pd.read_csv(replay_path, float_precision="round_trip")
    intervals = pd.read_csv(intervals_path, float_precision="round_trip")
    summary, scored = evaluate(source, replay, intervals)
    report = {
        "experiment": "calibration_fit_origin_movement_scaled_lettuce_interval",
        "source_sha256": sha256(source_path), "replay_sha256": sha256(replay_path),
        "intervals_sha256": sha256(intervals_path), "plan_sha256": sha256(plan_path),
        "script_sha256": sha256(Path(__file__)),
        "window_days": WINDOW_DAYS, "minimum_observations": MIN_OBS,
        "maximum_last_age_days": MAX_LAST_AGE_DAYS,
        "nominal_levels": list(LEVELS), "minimum_calibration_origins": MIN_CALIBRATION_ORIGINS,
        "historical_evaluation_previously_inspected": True,
        "holdout_labels_used": False, "production_promotion_permitted": False,
        "formal_conformal_coverage_guarantee": False,
        "summary": summary,
    }
    output_dir.mkdir(parents=True)
    scored.to_csv(output_dir / "matched_intervals.csv", index=False)
    (output_dir / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n",
                                             encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--replay", type=Path, default=REPLAY)
    parser.add_argument("--intervals", type=Path, default=INTERVALS)
    parser.add_argument("--plan", type=Path, default=ROOT /
                        "audits/foodcast_accuracy_20261018/lettuce_movement_interval_plan.md")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.source, args.replay, args.intervals, args.plan, args.output_dir)
    print(json.dumps({"fit": report["summary"]["fit"],
                      "unsupported_groups": report["summary"]["unsupported_groups"],
                      "pooled": {level: values["common_pooled"]
                                 for level, values in report["summary"]["levels"].items()}}, indent=2))


if __name__ == "__main__":
    main()
