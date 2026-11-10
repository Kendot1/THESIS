"""Historical fixed-model interval replay; never reads the prospective holdout.

Weekly origins provide more distinct active-model forecast vintages than the
saved monthly backtest. Calibration and evaluation are separated by target date.
The historical test period has been reused in research, so this is a diagnostic,
not final promotion evidence or a production calibration update.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from data.preprocessor import DataPreprocessor, SERIES_KEY
from evaluation.interval_calibration import (
    calibrate_residual_interval, interval_from_calibration, interval_metrics,
)
from features.builder import FeatureBuilder
from models.ensemble import EnsembleModel
from models.forecast_engine import ForecastEngine
from models.lightgbm_model import LightGBMModel
from models.lstm_model import LSTMModel


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BUNDLE = ROOT / "model_trainer/artifacts_v2/runs/20261001T025925Z_0661960a"
DEFAULT_SNAPSHOT = ROOT / "audits/accuracy_goal_20261011/supabase_food_prices_through_20261005.json"
DEFAULT_OUTPUT = ROOT / "audits/foodcast_accuracy_20261017/dense_active_interval_replay_weekday_aligned"
HOLDOUT_START = pd.Timestamp("2026-10-06")
TEST_START = pd.Timestamp("2025-09-13")
TEST_END = pd.Timestamp("2026-09-30")
CALIBRATION_START = pd.Timestamp("2025-09-12")
CALIBRATION_LAST_ORIGIN = pd.Timestamp("2026-03-15")
EVALUATION_START = pd.Timestamp("2026-04-03")
EVALUATION_LAST_ORIGIN = pd.Timestamp("2026-09-16")
FORECAST_DAYS = 14
ORIGIN_STRIDE_DAYS = 7
PARITY_ORIGINS = (pd.Timestamp("2025-09-12"), pd.Timestamp("2026-08-08"))
KEYS = ["series", "origin", "date", "horizon"]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def origin_schedule() -> tuple[pd.DatetimeIndex, pd.DatetimeIndex]:
    calibration = pd.date_range(
        CALIBRATION_START, CALIBRATION_LAST_ORIGIN, freq=f"{ORIGIN_STRIDE_DAYS}D")
    evaluation = pd.date_range(
        EVALUATION_START, EVALUATION_LAST_ORIGIN, freq=f"{ORIGIN_STRIDE_DAYS}D")
    if (calibration.empty or evaluation.empty
            or calibration.min() + pd.Timedelta(days=1) < TEST_START
            or calibration[0].weekday() != evaluation[0].weekday()
            or calibration.max() + pd.Timedelta(days=FORECAST_DAYS) >= EVALUATION_START
            or evaluation.max() + pd.Timedelta(days=FORECAST_DAYS) > TEST_END
            or TEST_END >= HOLDOUT_START):
        raise ValueError("Calibration/evaluation target windows are not disjoint or pre-holdout")
    return calibration, evaluation


def _load_engine(bundle: Path) -> tuple[FeatureBuilder, ForecastEngine]:
    builder = FeatureBuilder(bundle).load()
    lgbm, lstm, ensemble = LightGBMModel(bundle), LSTMModel(bundle), EnsembleModel(bundle)
    lgbm.load()
    lstm.load()
    ensemble.load()
    return builder, ForecastEngine(lgbm, lstm, ensemble, builder)


def parity_details(paths: pd.DataFrame, saved: pd.DataFrame) -> dict:
    """Compare only the daily leads replayed by this 14-day experiment."""
    replay = paths.loc[paths.origin.isin(PARITY_ORIGINS), KEYS + ["ensemble_path"]].copy()
    reference = saved.loc[
        saved.origin.isin(PARITY_ORIGINS) & saved.horizon.between(1, FORECAST_DAYS),
        KEYS + ["ensemble"],
    ].copy()
    if replay.duplicated(KEYS).any() or reference.duplicated(KEYS).any():
        raise ValueError("Duplicate replay/reference forecast key")
    paired = replay.merge(reference, on=KEYS, how="inner", validate="one_to_one")
    paired["difference_php"] = np.abs(paired.ensemble_path - paired.ensemble)
    differences = paired.difference_php.to_numpy(dtype=float)
    missing = reference.merge(replay[KEYS], on=KEYS, how="left", indicator=True)
    missing = missing.loc[missing._merge.eq("left_only")]
    mismatched = paired.loc[paired.difference_php.gt(0.01)]
    affected = (mismatched.groupby(["series", "origin"], sort=True)
                .difference_php.agg(["count", "max"]).reset_index()
                .sort_values(["count", "max"], ascending=False).head(20))
    affected["origin"] = affected.origin.dt.strftime("%Y-%m-%d")
    largest = paired.nlargest(10, "difference_php").copy()
    for column in ("origin", "date"):
        largest[column] = pd.to_datetime(largest[column]).dt.strftime("%Y-%m-%d")
    result = {
        "matched_rows": int(len(paired)),
        "replay_rows": int(len(replay)),
        "saved_rows": int(len(reference)),
        "matched_origins": int(paired.origin.nunique()),
        "max_abs_difference_php": float(differences.max()) if len(differences) else None,
        "mean_abs_difference_php": float(differences.mean()) if len(differences) else None,
        "nonfinite_difference_rows": int((~np.isfinite(differences)).sum()),
        "rows_over_tolerance": int(np.sum(differences > 0.01)),
        "affected_series_origins": affected.to_dict(orient="records"),
        "saved_keys_without_replay": missing[KEYS].assign(
            origin=lambda x: x.origin.dt.strftime("%Y-%m-%d"),
            date=lambda x: x.date.dt.strftime("%Y-%m-%d"),
        ).to_dict(orient="records"),
        "largest_differences": largest.to_dict(orient="records"),
        "tolerance_php": 0.01,
    }
    return result


def parity_check(paths: pd.DataFrame, saved: pd.DataFrame) -> dict:
    """Require exact-key replay agreement before interpreting dense forecasts."""
    result = parity_details(paths, saved)
    differences_ok = result["max_abs_difference_php"] is not None and (
        result["max_abs_difference_php"] <= result["tolerance_php"])
    if (result["matched_rows"] < 100
            or result["matched_rows"] != result["saved_rows"]
            or result["matched_origins"] != len(PARITY_ORIGINS)
            or result["nonfinite_difference_rows"]
            or not differences_ok):
        raise ValueError(f"Active-model forecast parity failed: {result}")
    return result


def replay_by_origin(clean: pd.DataFrame, featured: pd.DataFrame,
                     engine: ForecastEngine, origins: pd.DatetimeIndex
                     ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Replay one forecast origin at a time to bound case/state memory."""
    series_data = {}
    feature_groups = {key: group for key, group in featured.groupby(SERIES_KEY, sort=False)}
    for key, group in clean.groupby(SERIES_KEY, sort=True):
        series = group.sort_values("report_date")
        series_data[key] = (series, series.set_index("report_date").observed_price)
    category_daily = FeatureBuilder.category_return_history(clean)
    category_daily["category_return"] = category_daily.category_return.fillna(0.0)
    category_histories = {
        str(category): group.sort_values("report_date")
        for category, group in category_daily.groupby("product_category", sort=False)
    }
    product_daily = FeatureBuilder.product_return_history(clean)
    product_daily["product_return"] = product_daily.product_return.fillna(0.0)
    product_histories = {
        tuple(map(str, key)): group.sort_values("report_date")
        for key, group in product_daily.groupby(SERIES_KEY[:3], sort=False)
    }
    scored_rows, parity_rows = [], []
    for index, origin in enumerate(origins, start=1):
        origin = pd.Timestamp(origin)
        market_at_origin = {
            category: group.loc[group.report_date.le(origin), "category_return"].to_list()
            for category, group in category_histories.items()
        }
        product_at_origin = {
            key: group.loc[group.report_date.le(origin), "product_return"].to_list()
            for key, group in product_histories.items()
        }
        cases, contexts = [], []
        for key, (series, actual) in series_data.items():
            history = series.loc[series.report_date.le(origin)]
            if history.empty:
                continue
            try:
                prepared = engine._prepare(
                    history, feature_groups[key],
                    market_at_origin.get(str(key[0]), []),
                    product_at_origin.get(tuple(map(str, key[:3])), []),
                )
            except ValueError:
                continue
            cases.append(prepared)
            contexts.append(("||".join(map(str, key)), actual))
        paths = engine.forecast_many(cases, FORECAST_DAYS)
        for path, (series, actual) in zip(paths, contexts):
            if pd.Timestamp(path.dates[0]) != origin + pd.Timedelta(days=1):
                continue
            for lead, (date, point) in enumerate(zip(path.dates, path.point), start=1):
                date = pd.Timestamp(date)
                record = {
                    "series": series, "origin": origin, "date": date,
                    "horizon": lead, "ensemble_path": float(point),
                }
                if origin in PARITY_ORIGINS:
                    parity_rows.append(record)
                truth = actual.get(date, np.nan)
                if np.isfinite(truth):
                    scored_rows.append({**record, "actual": float(truth)})
        if index % 10 == 0 or index == len(origins):
            print(f"Replayed {index}/{len(origins)} origins", flush=True)
    if not scored_rows or not parity_rows:
        raise ValueError("Replay has no observed targets or parity forecasts")
    return pd.DataFrame(scored_rows), pd.DataFrame(parity_rows)


def score_intervals(calibration: pd.DataFrame, evaluation: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    """Calibrate by series/lead on earlier origins and score later targets."""
    if calibration.empty or evaluation.empty:
        raise ValueError("Calibration and evaluation both require observed targets")
    calibration = calibration.copy()
    evaluation = evaluation.copy()
    for frame in (calibration, evaluation):
        frame["origin"] = pd.to_datetime(frame.origin).dt.normalize()
        frame["date"] = pd.to_datetime(frame.date).dt.normalize()
        if frame.duplicated(KEYS).any():
            raise ValueError("Duplicate daily forecast target key")
        if (frame.date <= frame.origin).any() or frame.horizon.lt(1).any() or frame.horizon.gt(14).any():
            raise ValueError("Invalid daily forecast origin, date, or lead")
    if calibration.date.max() >= evaluation.date.min():
        raise ValueError("Calibration target dates overlap evaluation targets")
    summary = {}
    scored = []
    for level in (0.80, 0.95):
        parts = []
        supported = 0
        for (series, lead), earlier in calibration.groupby(["series", "horizon"], sort=True):
            bounds = calibrate_residual_interval(
                earlier.actual, earlier.ensemble_path, origins=earlier.origin,
                nominal_level=level,
            )
            if bounds is None:
                continue
            later = evaluation.loc[
                evaluation.series.eq(series) & evaluation.horizon.eq(lead)
            ].copy()
            if later.empty:
                continue
            interval = [interval_from_calibration(point, bounds)
                        for point in later.ensemble_path.to_numpy(dtype=float)]
            later["lower"] = [pair[0] if pair else np.nan for pair in interval]
            later["upper"] = [pair[1] if pair else np.nan for pair in interval]
            later["nominal_level"] = level
            later["calibration_origins"] = bounds["origin_count"]
            later["calibration_rows"] = bounds["sample_count"]
            parts.append(later)
            supported += 1
        if parts:
            level_rows = pd.concat(parts, ignore_index=True)
            pooled = interval_metrics(level_rows.actual, level_rows.lower,
                                      level_rows.upper, nominal_level=level)
            by_series = {
                str(series): interval_metrics(rows.actual, rows.lower, rows.upper,
                                              nominal_level=level)
                for series, rows in level_rows.groupby("series", sort=True)
            }
            by_lead = {
                str(int(lead)): interval_metrics(rows.actual, rows.lower, rows.upper,
                                                 nominal_level=level)
                for lead, rows in level_rows.groupby("horizon", sort=True)
            }
            scored.append(level_rows)
        else:
            pooled = interval_metrics([], [], [], nominal_level=level)
            by_series, by_lead = {}, {}
        summary[f"{level:.2f}"] = {
            "pooled": pooled,
            "supported_series_leads": supported,
            "supported_series": len(by_series),
            "by_series": by_series,
            "by_lead": by_lead,
        }
    return summary, pd.concat(scored, ignore_index=True) if scored else pd.DataFrame()


def run(bundle: Path, snapshot: Path, output: Path, *, parity_only: bool = False,
        source_drift_diagnostic: bool = False,
        legacy_source_quality: bool = False) -> dict:
    bundle, snapshot, output = Path(bundle), Path(snapshot), Path(output)
    if output.exists() and not parity_only:
        raise FileExistsError(f"Refusing to overwrite replay output: {output}")
    calibration_origins, evaluation_origins = origin_schedule()
    source = json.loads(snapshot.read_text(encoding="utf-8"))
    if isinstance(source, dict):
        source = source.get("rows", source.get("data"))
    raw = pd.DataFrame(source)
    if raw.empty or pd.to_datetime(raw.report_date, errors="coerce").max() >= HOLDOUT_START:
        raise ValueError("Source snapshot is empty or reaches the sealed holdout")
    # The archived active bundle predates the three source-quality exclusions.
    # Legacy mode is for exact model-vintage replay only; new training keeps
    # the documented exclusions enabled.
    clean = DataPreprocessor().validate(
        raw, apply_source_quality_exclusions=not legacy_source_quality)
    builder, engine = _load_engine(bundle)
    featured = builder.transform(clean)
    all_origins = (pd.DatetimeIndex(PARITY_ORIGINS) if parity_only else
                   pd.DatetimeIndex(sorted(set(calibration_origins)
                                           | set(evaluation_origins) | set(PARITY_ORIGINS))))
    observed, parity_paths = replay_by_origin(clean, featured, engine, all_origins)
    saved = pd.read_csv(bundle / "test_forecasts.csv", parse_dates=["origin", "date"])
    if parity_only:
        return {"parity_diagnostic": parity_details(parity_paths, saved)}
    parity = parity_details(parity_paths, saved)
    try:
        parity_check(parity_paths, saved)
        parity_passed = True
    except ValueError:
        if not source_drift_diagnostic:
            raise
        parity_passed = False
    earlier = observed.loc[observed.origin.isin(calibration_origins)].copy()
    later = observed.loc[observed.origin.isin(evaluation_origins)].copy()
    levels, scored = score_intervals(earlier, later)
    if not parity_passed:
        for level in levels.values():
            for metrics in [level["pooled"], *level["by_series"].values(),
                            *level["by_lead"].values()]:
                metrics["empirical_coverage_status"] = metrics["reliability_status"]
                metrics["reliability_status"] = "limited_source_vintage_mismatch"
    report = {
        "experiment": "dense_fixed_active_daily_prediction_intervals",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "model_run_id": bundle.name,
        "model_metadata_sha256": _sha256(bundle / "metadata.json"),
        "saved_test_forecasts_sha256": _sha256(bundle / "test_forecasts.csv"),
        "source_snapshot_sha256": _sha256(snapshot),
        "legacy_source_quality_replay": bool(legacy_source_quality),
        "script_sha256": _sha256(Path(__file__)),
        "holdout_labels_used": False,
        "historical_test_reused_for_development": True,
        "immutable_ingestion_vintages_available": False,
        "forecast_days": FORECAST_DAYS,
        "origin_stride_days": ORIGIN_STRIDE_DAYS,
        "origin_weekday": CALIBRATION_START.day_name(),
        "calibration_origin_dates": [date.date().isoformat() for date in calibration_origins],
        "evaluation_origin_dates": [date.date().isoformat() for date in evaluation_origins],
        "calibration_scored_targets": int(len(earlier)),
        "evaluation_scored_targets": int(len(later)),
        "parity": parity,
        "saved_active_forecast_parity_passed": parity_passed,
        "production_interval_claim_permitted": False,
        "levels": levels,
        "interpretation": (
            "Fixed active model trained/selected before these historical test origins. "
            "Only report-date availability can be reconstructed; source ingestion times are absent. "
            "Weekly origins cause overlapping 14-day targets and dependent errors. "
            "No production interval or model is changed; historical test reuse bars final promotion claims. "
            "Legacy source-quality mode reproduces the archived model's pre-exclusion "
            "input semantics and is not a recommendation to undo verified quality flags. "
            "When saved parity fails, these are active-weight/current-snapshot diagnostics, "
            "not exact reproductions of archived production forecasts."
        ),
    }
    output.mkdir(parents=True)
    observed.to_csv(output / "replay_observed_targets.csv", index=False)
    scored.to_csv(output / "scored_intervals.csv", index=False)
    (output / "report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--parity-only", action="store_true")
    parser.add_argument("--source-drift-diagnostic", action="store_true")
    parser.add_argument("--legacy-source-quality", action="store_true")
    args = parser.parse_args()
    report = run(args.bundle, args.snapshot, args.output,
                 parity_only=args.parity_only,
                 source_drift_diagnostic=args.source_drift_diagnostic,
                 legacy_source_quality=args.legacy_source_quality)
    if args.parity_only:
        print(json.dumps(report, indent=2))
        return
    print(json.dumps({"parity": report["parity"],
                      "saved_active_forecast_parity_passed": report["saved_active_forecast_parity_passed"],
                      "calibration_origins": len(report["calibration_origin_dates"]),
                      "evaluation_origins": len(report["evaluation_origin_dates"]),
                      "levels": {name: value["pooled"] for name, value in report["levels"].items()}},
                     indent=2))


if __name__ == "__main__":
    main()
