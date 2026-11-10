"""Read-only weekly/monthly persistence interval support and calibration screen.

Never reads October 6+ holdout labels. Historical evaluation was reused in
prior model research, so results cannot independently promote production.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from data.preprocessor import DataPreprocessor, SERIES_KEY
from evaluation.horizon_specific import SPECS, build_period_panel, target_periods


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "audits/accuracy_goal_20261011/supabase_food_prices_through_20261005.json"
PLAN = ROOT / "audits/foodcast_accuracy_20261018/period_persistence_interval_plan.md"
ORIGIN_START = pd.Timestamp("2022-01-01")
EVAL_ORIGINS = {
    "weekly": pd.date_range("2026-04-05", "2026-08-30", freq="W-SUN"),
    "monthly": pd.date_range("2026-04-30", "2026-08-31", freq="ME"),
}
TARGET_CUTOFF = pd.Timestamp("2026-09-30")
HOLDOUT_START = pd.Timestamp("2026-10-06")
MAX_ANCHOR_AGE_DAYS = 7
MIN_CAL_ORIGINS = 20
LEVELS = (0.80, 0.95)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def eligible_anchor(history: pd.DataFrame, origin: pd.Timestamp) -> tuple[float, int] | None:
    """Latest completed valid period, never a future or partially observed row."""
    origin = pd.Timestamp(origin).normalize()
    eligible = history.loc[pd.to_datetime(history.period_end).le(origin)].sort_values("period_end")
    if eligible.empty:
        return None
    latest = eligible.iloc[-1]
    age = int((origin - pd.Timestamp(latest.last_observed_date)).days)
    point = float(latest.period_value)
    if age < 0 or age > MAX_ANCHOR_AGE_DAYS or not np.isfinite(point) or point <= 0:
        return None
    return point, age


def schedule(horizon: str) -> tuple[pd.DatetimeIndex, pd.DatetimeIndex]:
    if horizon not in EVAL_ORIGINS:
        raise ValueError("Only independent weekly/monthly periods are supported")
    evaluation = EVAL_ORIGINS[horizon]
    first = evaluation.min()
    if horizon == "weekly":
        calibration = pd.date_range(ORIGIN_START, first - pd.Timedelta(days=7), freq="W-SUN")
    else:
        calibration = pd.date_range(ORIGIN_START, first - pd.Timedelta(days=1), freq="ME")
    return calibration, evaluation


def build_period_predictions(panel: pd.DataFrame, horizon: str) -> tuple[pd.DataFrame, dict]:
    """Pair independent period targets with origin-known persistence points."""
    spec = SPECS[horizon]
    if spec.steps != (4 if horizon == "weekly" else 1):
        raise ValueError("Unexpected independent-horizon target count")
    calibration_origins, evaluation_origins = schedule(horizon)
    first_evaluation = evaluation_origins.min()
    rows = []
    potential_eval, ineligible_eval = 0, 0
    for identity, history in panel.groupby(SERIES_KEY, sort=True):
        history = history.sort_values("period_start").reset_index(drop=True)
        target_lookup = {pd.Timestamp(row.period_start): row
                         for row in history.itertuples(index=False)}
        series = "||".join(map(str, identity))
        for partition, origins in (("calibration", calibration_origins),
                                   ("evaluation", evaluation_origins)):
            for origin in origins:
                descriptors = target_periods(origin, spec)
                eligible_targets = []
                for descriptor in descriptors:
                    if descriptor["period_end"] > TARGET_CUTOFF:
                        continue
                    if (partition == "calibration"
                            and descriptor["period_end"] >= first_evaluation):
                        continue
                    target = target_lookup.get(descriptor["period_start"])
                    if target is not None:
                        eligible_targets.append((descriptor, target))
                if not eligible_targets:
                    continue
                anchor = eligible_anchor(history, origin)
                if partition == "evaluation":
                    potential_eval += len(eligible_targets)
                    if anchor is None:
                        ineligible_eval += len(eligible_targets)
                if anchor is None:
                    continue
                point, age = anchor
                for descriptor, target in eligible_targets:
                    rows.append({
                        "series": series, "horizon": horizon,
                        "partition": partition, "forecast_origin": origin,
                        "lead": int(descriptor["lead"]),
                        "target_start": descriptor["period_start"],
                        "target_end": descriptor["period_end"],
                        "actual": float(target.period_value),
                        "persistence": point,
                        "target_observed_days": int(target.observed_days),
                        "anchor_last_observed_age_days": age,
                    })
    result = pd.DataFrame(rows)
    if result.empty:
        raise ValueError(f"No eligible {horizon} period targets")
    keys = ["series", "forecast_origin", "horizon", "lead", "target_start", "target_end"]
    if (result.duplicated(keys).any()
            or result.target_end.max() > TARGET_CUTOFF
            or result.target_end.max() >= HOLDOUT_START
            or (result.target_start <= result.forecast_origin).any()
            or (result.target_observed_days < spec.minimum_coverage).any()
            or (result.anchor_last_observed_age_days > MAX_ANCHOR_AGE_DAYS).any()):
        raise ValueError("Period targets are duplicate, incomplete, stale, or not future")
    calibration = result.loc[result.partition.eq("calibration")]
    evaluation = result.loc[result.partition.eq("evaluation")]
    if (calibration.empty or evaluation.empty
            or calibration.target_end.max() >= evaluation.forecast_origin.min()):
        raise ValueError("Calibration labels overlap evaluation origins")
    audit = {"calibration_origins_scheduled": int(len(calibration_origins)),
             "evaluation_origins_scheduled": int(len(evaluation_origins)),
             "calibration_rows": int(len(calibration)),
             "evaluation_rows_eligible": int(len(evaluation)),
             "evaluation_valid_targets_before_anchor_screen": int(potential_eval),
             "evaluation_targets_without_fresh_completed_anchor": int(ineligible_eval),
             "calibration_last_target": calibration.target_end.max().date().isoformat(),
             "evaluation_first_origin": evaluation.forecast_origin.min().date().isoformat(),
             "evaluation_last_origin": evaluation.forecast_origin.max().date().isoformat(),
             "evaluation_last_target": evaluation.target_end.max().date().isoformat()}
    return result, audit


def radius(calibration: pd.DataFrame, level: float) -> dict | None:
    if not 0 < level < 1:
        raise ValueError("Nominal level must be between zero and one")
    if (calibration.duplicated(["forecast_origin"]).any()
            or calibration.duplicated(["target_start"]).any()):
        raise ValueError("Duplicate calibration origin or target period within series/lead")
    count = len(calibration)
    origin_count = calibration.forecast_origin.nunique()
    period_count = calibration.target_start.nunique()
    if min(origin_count, period_count) < MIN_CAL_ORIGINS:
        return None
    rank = int(math.ceil((count + 1) * level - 1e-12))
    if rank > count:
        return None
    scores = np.abs(calibration.actual.to_numpy(dtype=float)
                    - calibration.persistence.to_numpy(dtype=float))
    if not np.isfinite(scores).all():
        raise ValueError("Nonfinite calibration residual")
    return {"radius_php": float(np.sort(scores)[rank - 1]),
            "calibration_targets": int(count),
            "calibration_origins": int(origin_count),
            "calibration_target_periods": int(period_count), "rank": rank}


def score(rows: pd.DataFrame) -> dict:
    if rows.empty:
        return {"targets": 0, "series": 0, "coverage_pct": None,
                "mean_width_php": None, "mae_php": None, "rmse_php": None,
                "mape_pct": None, "bias_php": None}
    actual = rows.actual.to_numpy(dtype=float)
    point = rows.persistence.to_numpy(dtype=float)
    lower = rows.lower.to_numpy(dtype=float)
    upper = rows.upper.to_numpy(dtype=float)
    if (not np.isfinite(np.column_stack((actual, point, lower, upper))).all()
            or (actual <= 0).any() or (point <= 0).any()
            or (lower <= 0).any() or (upper < lower).any()):
        raise ValueError("Invalid scored period rows")
    residual = point - actual
    return {"targets": int(len(rows)), "series": int(rows.series.nunique()),
            "origins": int(rows.forecast_origin.nunique()),
            "target_periods": int(rows.target_start.nunique()),
            "coverage_pct": float(((actual >= lower) & (actual <= upper)).mean() * 100),
            "mean_width_php": float((upper - lower).mean()),
            "mae_php": float(np.abs(residual).mean()),
            "rmse_php": float(np.sqrt(np.square(residual).mean())),
            "mape_pct": float((np.abs(residual) / actual).mean() * 100),
            "bias_php": float(residual.mean())}


def evaluate(predictions: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    calibration = predictions.loc[predictions.partition.eq("calibration")]
    evaluation = predictions.loc[predictions.partition.eq("evaluation")]
    all_rows = []
    horizon_summary = {}
    for horizon in ("weekly", "monthly"):
        cal = calibration.loc[calibration.horizon.eq(horizon)]
        later = evaluation.loc[evaluation.horizon.eq(horizon)]
        unsupported = []
        for level in LEVELS:
            radii = {}
            for (series, lead), group in cal.groupby(["series", "lead"], sort=True):
                value = radius(group, level)
                if value is not None:
                    radii[(series, int(lead))] = value
            rows = later.copy()
            rows["nominal_level"] = level
            rows["radius_php"] = [radii.get((row.series, int(row.lead)), {}).get("radius_php", np.nan)
                                  for row in rows.itertuples()]
            missing = rows.loc[rows.radius_php.isna()]
            for (series, lead), group in missing.groupby(["series", "lead"]):
                earlier = cal.loc[cal.series.eq(series) & cal.lead.eq(lead)]
                unsupported.append({"series": series, "lead": int(lead),
                                    "level": level, "evaluation_targets": int(len(group)),
                                    "calibration_origins": int(earlier.forecast_origin.nunique()),
                                    "calibration_target_periods": int(earlier.target_start.nunique())})
            rows = rows.loc[rows.radius_php.notna()].copy()
            rows["lower"] = np.maximum(0.01, rows.persistence - rows.radius_php)
            rows["upper"] = rows.persistence + rows.radius_php
            all_rows.append(rows)
        horizon_rows = pd.concat(all_rows, ignore_index=True)
        horizon_rows = horizon_rows.loc[horizon_rows.horizon.eq(horizon)]
        levels = {}
        for level, rows in horizon_rows.groupby("nominal_level", sort=True):
            by_series = {series: score(group) for series, group in rows.groupby("series", sort=True)}
            by_lead = {str(int(lead)): score(group) for lead, group in rows.groupby("lead", sort=True)}
            levels[f"{level:.2f}"] = {
                "eligible_evaluation_targets": int(len(later)),
                "supported_targets": int(len(rows)),
                "unsupported_targets": int(len(later) - len(rows)),
                "pooled": score(rows),
                "equal_series_macro_coverage_pct": float(np.mean(
                    [item["coverage_pct"] for item in by_series.values()])),
                "equal_series_macro_width_php": float(np.mean(
                    [item["mean_width_php"] for item in by_series.values()])),
                "by_series": by_series, "by_lead": by_lead,
            }
        horizon_summary[horizon] = {"levels": levels, "unsupported_groups": unsupported}
    scored = pd.concat(all_rows, ignore_index=True)
    if (scored.empty or scored.duplicated(
            ["series", "horizon", "forecast_origin", "lead", "target_start", "nominal_level"]).any()):
        raise ValueError("Empty or duplicate interval output")
    return horizon_summary, scored


def run(source_path: Path, plan_path: Path, output_dir: Path) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite period interval audit: {output_dir}")
    raw = json.loads(source_path.read_text(encoding="utf-8"))
    clean = DataPreprocessor().validate(pd.DataFrame(raw))
    frames = []
    audits = {}
    for horizon in ("weekly", "monthly"):
        panel = build_period_panel(clean, SPECS[horizon])
        frame, audit = build_period_predictions(panel, horizon)
        frames.append(frame)
        audits[horizon] = audit
    predictions = pd.concat(frames, ignore_index=True)
    summary, scored = evaluate(predictions)
    report = {"experiment": "independent_weekly_monthly_persistence_interval_support",
              "source_sha256": sha256(source_path), "plan_sha256": sha256(plan_path),
              "script_sha256": sha256(Path(__file__)),
              "preprocessing_contract": DataPreprocessor.preprocessing_contract(),
              "minimum_observed_days_per_target": {
                  horizon: SPECS[horizon].minimum_coverage for horizon in ("weekly", "monthly")},
              "maximum_anchor_age_days": MAX_ANCHOR_AGE_DAYS,
              "target_cutoff": TARGET_CUTOFF.date().isoformat(),
              "holdout_labels_used": False, "production_promotion_permitted": False,
              "interval_guarantee": "empirical_only_dependent_periods_and_source_vintage_limits",
              "origin_audit": audits, "summary": summary}
    output_dir.mkdir(parents=True)
    predictions.to_csv(output_dir / "paired_period_targets.csv", index=False)
    scored.to_csv(output_dir / "scored_intervals.csv", index=False)
    (output_dir / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n",
                                             encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--plan", type=Path, default=PLAN)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.source, args.plan, args.output_dir)
    print(json.dumps({horizon: {"origin_audit": report["origin_audit"][horizon],
                               "levels": {level: {k: v for k, v in entry.items()
                                                  if k not in ("by_series", "by_lead")}
                                          for level, entry in section["levels"].items()},
                               "unsupported_group_count": len(section["unsupported_groups"])}
                      for horizon, section in report["summary"].items()}, indent=2))


if __name__ == "__main__":
    main()
