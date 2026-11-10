"""Read-only origin-known lettuce run-up versus active interval upper misses.

Uses the exact-active-vintage archived source and interval replay. Historical
test outcomes have been reused; this diagnostic cannot promote a model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from data.preprocessor import DataPreprocessor, SERIES_KEY
from evaluation.dense_active_interval_replay import origin_schedule


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "audits/confidence_20261002/training_snapshot.json"
INTERVALS = ROOT / "audits/foodcast_accuracy_20261017/prequential_interval_exact_vintage/paired_intervals.csv"
REPLAY = ROOT / "audits/foodcast_accuracy_20261017/dense_active_interval_replay_exact_vintage/replay_observed_targets.csv"
LETUCES = ("Green Ice", "Iceberg", "Romaine")
WINDOW_DAYS = 14
MIN_OBS = 5
MAX_LAST_AGE_DAYS = 2


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def trailing_return(observations: pd.DataFrame, origin: pd.Timestamp) -> dict:
    """Return first-to-last price movement using observed, origin-known rows."""
    origin = pd.Timestamp(origin).normalize()
    date = pd.to_datetime(observations.report_date).dt.normalize()
    price = pd.to_numeric(observations.observed_price, errors="coerce")
    window = (date.between(origin - pd.Timedelta(days=WINDOW_DAYS - 1), origin)
              & observations.is_observed.fillna(False).astype(bool)
              & np.isfinite(price) & price.gt(0))
    rows = observations.loc[window, ["report_date", "observed_price"]].sort_values("report_date")
    if rows.report_date.duplicated().any():
        raise ValueError("Duplicate observed price date")
    count = len(rows)
    last_date = pd.Timestamp(rows.report_date.iloc[-1]) if count else pd.NaT
    last_age = int((origin - last_date).days) if count else None
    supported = count >= MIN_OBS and last_age <= MAX_LAST_AGE_DAYS
    return {
        "observation_count": int(count),
        "latest_observation": last_date,
        "last_age_days": last_age,
        "return_14d": float(rows.observed_price.iloc[-1] / rows.observed_price.iloc[0] - 1)
        if supported else np.nan,
    }


def evaluate(source: pd.DataFrame, intervals: pd.DataFrame,
             replay: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    required = {"series", "origin", "date", "horizon", "actual", "point",
                "nominal_level", "expanding_lower", "expanding_upper",
                "fixed_lower", "fixed_upper"}
    if intervals.empty or not required.issubset(intervals):
        raise ValueError("Missing interval replay columns")
    scored = intervals.loc[np.isclose(intervals.nominal_level, 0.95)].copy()
    scored["origin"] = pd.to_datetime(scored.origin).dt.normalize()
    scored["date"] = pd.to_datetime(scored.date).dt.normalize()
    calibration_origins, evaluation_origins = origin_schedule()
    if (scored.duplicated(["series", "origin", "date", "horizon"]).any()
            or not scored.origin.isin(evaluation_origins).all()
            or not scored.date.gt(scored.origin).all()
            or not scored.date.lt(pd.Timestamp("2026-10-06")).all()):
        raise ValueError("Intervals have duplicate, wrong-schedule, or holdout rows")
    needed = set(SERIES_KEY + ["report_date", "observed_price", "is_observed"])
    if not needed.issubset(source):
        raise ValueError("Source lacks causal observed-price provenance")
    lettuce = source.loc[source.product_category.eq("Vegetables")
                         & source.product_name.eq("Lettuce")
                         & source.product_variant.isin(LETUCES)
                         & source.origin.eq("Local") & source.unit.eq("kg")]
    if set(lettuce.product_variant.unique()) != set(LETUCES):
        raise ValueError("Archived source lacks a priority lettuce")
    features = []
    for variant, history in lettuce.groupby("product_variant"):
        for origin in calibration_origins.union(evaluation_origins):
            feature = trailing_return(history, origin)
            features.append({"series": "||".join(("Vegetables", "Lettuce", variant,
                                                    "Local", "kg")),
                             "origin": origin, **feature})
    features = pd.DataFrame(features)
    if (features.latest_observation.notna()
            & features.latest_observation.gt(features.origin)).any():
        raise AssertionError("Future price reached origin risk feature")
    calibration = features.loc[features.origin.isin(calibration_origins)]
    supported_cal = calibration.loc[calibration.return_14d.notna()]
    if supported_cal.empty:
        raise ValueError("No pre-evaluation origin signal")
    median_by_origin = supported_cal.groupby("origin").return_14d.median()
    threshold = float(median_by_origin.median())

    calibration_rows = replay.copy()
    if not {"series", "origin", "date", "horizon", "actual", "ensemble_path"}.issubset(calibration_rows):
        raise ValueError("Missing archived calibration replay columns")
    calibration_rows["origin"] = pd.to_datetime(calibration_rows.origin).dt.normalize()
    calibration_rows["date"] = pd.to_datetime(calibration_rows.date).dt.normalize()
    calibration_rows = calibration_rows.loc[
        calibration_rows.origin.isin(calibration_origins)
        & calibration_rows.series.isin(set(features.series))].copy()
    if (calibration_rows.empty
            or calibration_rows.duplicated(["series", "origin", "date", "horizon"]).any()
            or calibration_rows.date.max() >= evaluation_origins.min()
            or not calibration_rows.date.gt(calibration_rows.origin).all()):
        raise ValueError("Calibration replay is empty, overlapping, or duplicated")
    calibration_rows = calibration_rows.merge(
        features, on=["series", "origin"], how="left", validate="many_to_one")
    if calibration_rows.return_14d.isna().any():
        raise ValueError("Calibration rows lack origin-known returns")

    target_series = set(features.series)
    scored = scored.loc[scored.series.isin(target_series)].copy()
    scored = scored.merge(features, on=["series", "origin"], how="left", validate="many_to_one")
    if scored.empty or scored.return_14d.isna().any():
        raise ValueError("Evaluation lettuce interval rows lack origin signals")
    scored["upper_miss"] = scored.actual.gt(scored.expanding_upper)
    scored["fixed_upper_miss"] = scored.actual.gt(scored.fixed_upper)
    scored["covered"] = scored.actual.between(scored.expanding_lower, scored.expanding_upper)
    scored["width_php"] = scored.expanding_upper - scored.expanding_lower
    scored["high_runup"] = scored.return_14d.gt(threshold)
    by_origin = scored.groupby("origin").agg(
        median_return_14d=("return_14d", "median"),
        upper_miss_rate=("upper_miss", "mean"),
        coverage=("covered", "mean"),
        sample_count=("covered", "size"),
    ).reset_index()
    def origin_correlation(frame: pd.DataFrame, point_column: str) -> float | None:
        frame = frame.copy()
        frame["positive_relative_residual"] = np.maximum(
            0.0, (frame.actual - frame[point_column]) / frame[point_column])
        origin_rows = frame.groupby("origin").agg(
            median_return=("return_14d", "median"),
            mean_positive_residual=("positive_relative_residual", "mean"))
        x = origin_rows.median_return.to_numpy(dtype=float)
        y = origin_rows.mean_positive_residual.to_numpy(dtype=float)
        return float(np.corrcoef(x, y)[0, 1]) if len(x) >= 4 and x.std() and y.std() else None

    x = by_origin.median_return_14d.to_numpy(dtype=float)
    y = by_origin.upper_miss_rate.to_numpy(dtype=float)
    correlation = float(np.corrcoef(x, y)[0, 1]) if len(x) >= 4 and x.std() and y.std() else None

    def metrics(frame: pd.DataFrame) -> dict:
        return {
            "targets": int(len(frame)), "origins": int(frame.origin.nunique()),
            "upper_miss_rate_pct": float(frame.upper_miss.mean() * 100),
            "coverage_pct": float(frame.covered.mean() * 100),
            "mean_width_php": float(frame.width_php.mean()),
            "median_origin_return_pct": float(frame.return_14d.median() * 100),
        }

    summary = {
        "calibration_origin_count": int(len(calibration_origins)),
        "calibration_supported_origin_count": int(len(median_by_origin)),
        "calibration_median_runup_threshold_pct": threshold * 100,
        "calibration_median_return_vs_positive_residual_pearson": origin_correlation(
            calibration_rows, "ensemble_path"),
        "evaluation_median_return_vs_positive_residual_pearson": origin_correlation(
            scored, "point"),
        "evaluation": metrics(scored),
        "high_runup": metrics(scored.loc[scored.high_runup]),
        "low_runup": metrics(scored.loc[~scored.high_runup]),
        "by_series": {series: metrics(group) for series, group in scored.groupby("series")},
        "origin_median_runup_vs_upper_miss_pearson": correlation,
        "origin_metrics": [{"origin": row.origin.date().isoformat(),
                            "median_return_14d_pct": float(row.median_return_14d * 100),
                            "upper_miss_rate_pct": float(row.upper_miss_rate * 100),
                            "coverage_pct": float(row.coverage * 100),
                            "targets": int(row.sample_count)}
                           for row in by_origin.itertuples()],
    }
    return summary, scored


def run(source_path: Path, intervals_path: Path, replay_path: Path,
        output_dir: Path) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite diagnostic: {output_dir}")
    source = DataPreprocessor().validate(pd.DataFrame(json.loads(source_path.read_text(encoding="utf-8"))),
                                         apply_source_quality_exclusions=False)
    summary, scored = evaluate(
        source, pd.read_csv(intervals_path, float_precision="round_trip"),
        pd.read_csv(replay_path, float_precision="round_trip"))
    report = {
        "experiment": "origin_known_lettuce_runup_vs_active_95pct_upper_miss",
        "source_sha256": sha256(source_path),
        "intervals_sha256": sha256(intervals_path),
        "replay_sha256": sha256(replay_path),
        "script_sha256": sha256(Path(__file__)),
        "source_quality_contract": "legacy-active-vintage; no later exclusions",
        "window_calendar_days": WINDOW_DAYS,
        "minimum_observed_days": MIN_OBS,
        "maximum_last_observed_age_days": MAX_LAST_AGE_DAYS,
        "historical_test_reused": True,
        "holdout_labels_used": False,
        "production_promotion_permitted": False,
        "summary": summary,
    }
    output_dir.mkdir(parents=True)
    scored.to_csv(output_dir / "lettuce_interval_rows.csv", index=False)
    (output_dir / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n",
                                             encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--intervals", type=Path, default=INTERVALS)
    parser.add_argument("--replay", type=Path, default=REPLAY)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.source, args.intervals, args.replay, args.output_dir)
    print(json.dumps({k: v for k, v in report["summary"].items()
                      if k not in ("by_series", "origin_metrics")}, indent=2))


if __name__ == "__main__":
    main()
