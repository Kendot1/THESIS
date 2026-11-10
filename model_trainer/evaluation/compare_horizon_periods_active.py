"""Pair direct weekly/monthly candidates with the incumbent published path.

The incumbent is replayed at the candidate's exact origins. Its daily ensemble
path is converted to period points with the same publisher aggregation used by
production. Candidate and incumbent are scored only on common complete target
periods and identical observed labels. This is historical development evidence,
not a promotion or prospective-holdout evaluation.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd

from config.settings import get_settings
from data.preprocessor import DataPreprocessor
from evaluation.compare_published_paths import _published_rows
from evaluation.horizon_specific import (
    HOLDOUT_START,
    SPECS,
    _metric,
    load_snapshot,
    sha256,
)
from features.builder import FeatureBuilder
from models.ensemble import EnsembleModel
from models.forecast_engine import ForecastEngine
from models.lightgbm_model import LightGBMModel
from models.lstm_model import LSTMModel
from models.model_store import ModelStore
from pipeline.trainer import TrainingPipeline
from utils.prices import round_price


def _metrics(frame: pd.DataFrame, prediction: str) -> dict:
    values = frame[["actual_candidate", prediction]].rename(
        columns={"actual_candidate": "actual", prediction: "prediction"})
    return _metric(values, "prediction")


def _group_metrics(frame: pd.DataFrame, prediction: str, group: str) -> dict:
    return {
        str(key): _metrics(rows, prediction)
        for key, rows in frame.groupby(group, sort=True, dropna=False)
    }


def compare(summary_path: Path, snapshot_path: Path, horizon: str,
            output_dir: Path) -> dict:
    if horizon not in {"weekly", "monthly"}:
        raise ValueError("This paired comparator supports weekly or monthly targets")
    summary_path = Path(summary_path).resolve()
    snapshot_path = Path(snapshot_path).resolve()
    output_dir = Path(output_dir).resolve()
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite paired comparison directory: {output_dir}")

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    expected_sha = summary.get("source_snapshot_sha256")
    if sha256(snapshot_path) != expected_sha:
        raise ValueError("Snapshot hash does not match the candidate experiment")
    run = summary["horizons"][horizon]
    origins = pd.DatetimeIndex(pd.to_datetime(run["origins"]["test"], errors="raise"))
    if origins.empty or origins.max() >= pd.Timestamp(summary["holdout_start"]):
        raise ValueError("Candidate origins are empty or reach the sealed prospective holdout")
    split = summary["splits"]

    candidate_path = summary_path.parent / horizon / "test_predictions.csv"
    candidate_report_path = summary_path.parent / horizon / "report.json"
    candidate_report = json.loads(candidate_report_path.read_text(encoding="utf-8"))
    strategy = run["selected_strategy"]
    prediction_column = f"candidate_{strategy}"
    candidate = pd.read_csv(candidate_path, usecols=[
        "series", "forecast_origin", "target_start", "target_end", "lead", "actual",
        "persistence", "seasonal_naive", prediction_column,
    ], parse_dates=["forecast_origin", "target_start", "target_end"])
    candidate = candidate.rename(columns={
        "target_start": "target_period_start",
        "target_end": "target_period_end",
        "lead": "forecast_step",
        "actual": "actual_candidate",
        prediction_column: "direct_candidate_raw",
    })
    candidate["forecast_origin"] = pd.to_datetime(candidate.forecast_origin).dt.normalize()
    candidate["direct_candidate"] = candidate.direct_candidate_raw.map(round_price)
    candidate["persistence"] = candidate.persistence.map(round_price)
    candidate["seasonal_naive"] = candidate.seasonal_naive.map(round_price)
    if candidate.duplicated([
            "series", "forecast_origin", "target_period_start", "target_period_end", "forecast_step"]).any():
        raise ValueError("Candidate contains duplicate target-period rows")

    raw = load_snapshot(snapshot_path)
    report_dates = pd.to_datetime(raw.report_date, errors="coerce").dropna()
    if report_dates.empty or report_dates.max().normalize() >= HOLDOUT_START:
        raise ValueError("Source snapshot reaches the sealed prospective holdout")
    clean = DataPreprocessor().validate(raw)
    test_start = pd.Timestamp(split["validation_end"]) + pd.Timedelta(days=1)
    test_end = pd.Timestamp(split["test_end"])
    partition = clean.loc[clean.report_date.between(test_start, test_end)].copy()
    if partition.empty:
        raise ValueError("Candidate test partition is empty")

    max_path_days = int((candidate.target_period_end - candidate.forecast_origin).dt.days.max())
    if max_path_days < 1:
        raise ValueError("Target periods do not extend beyond their forecast origins")

    active_dir = ModelStore().active_path()
    active_metadata = json.loads((active_dir / "metadata.json").read_text(encoding="utf-8"))
    builder = FeatureBuilder(active_dir).load()
    featured = builder.transform(clean)
    lgbm = LightGBMModel(active_dir)
    lgbm.load()
    lstm = LSTMModel(active_dir)
    lstm.load()
    ensemble = EnsembleModel(active_dir)
    ensemble.load()
    engine = ForecastEngine(lgbm, lstm, ensemble, builder)

    pipeline = TrainingPipeline.__new__(TrainingPipeline)
    pipeline.cfg = copy.copy(get_settings())
    pipeline.cfg.monthly_horizon = max_path_days
    pipeline.preprocessor = DataPreprocessor()
    _, active_paths = pipeline._backtest(
        clean, featured, partition, engine, return_paths=True,
        origin_dates=origins,
    )
    if "ensemble_path" not in active_paths:
        raise ValueError("Backtest did not preserve the incumbent's recursive ensemble path")
    active_paths["ensemble"] = active_paths["ensemble_path"].to_numpy(dtype=float)
    active_rows = pd.DataFrame(_published_rows(active_paths))
    if active_rows.empty:
        raise ValueError("The incumbent generated no published period rows")
    active_rows = active_rows.loc[active_rows.horizon.eq(horizon)].rename(columns={
        "horizon": "forecast_horizon",
        "origin": "forecast_origin",
        "ensemble": "active_published_path",
        "actual": "actual_active",
    })
    keys = ["series", "forecast_origin", "target_period_start", "target_period_end", "forecast_step"]
    active_rows["forecast_origin"] = pd.to_datetime(active_rows.forecast_origin).dt.normalize()
    active_rows["target_period_start"] = pd.to_datetime(active_rows.target_period_start).dt.normalize()
    active_rows["target_period_end"] = pd.to_datetime(active_rows.target_period_end).dt.normalize()
    candidate["target_period_start"] = pd.to_datetime(candidate.target_period_start).dt.normalize()
    candidate["target_period_end"] = pd.to_datetime(candidate.target_period_end).dt.normalize()
    matched = candidate.merge(
        active_rows[keys + ["active_published_path", "actual_active", "observed_days",
                            "covered_days", "period_days"]],
        on=keys, how="inner", validate="one_to_one",
    )
    if matched.empty:
        raise ValueError("No complete candidate and incumbent period targets matched")
    if not np.allclose(
            matched.actual_candidate.to_numpy(dtype=float),
            matched.actual_active.to_numpy(dtype=float), rtol=0, atol=1e-8,
            equal_nan=True):
        raise ValueError("Candidate and incumbent use different observed period labels")
    if not matched.covered_days.eq(matched.period_days).all():
        raise ValueError("Incumbent published path contains partial target periods")
    if matched.observed_days.lt(SPECS[horizon].minimum_coverage).any():
        raise ValueError("Matched actual target period violates minimum observation coverage")
    prediction_names = ["direct_candidate", "active_published_path", "persistence", "seasonal_naive"]
    if not np.isfinite(matched[prediction_names].to_numpy(dtype=float)).all():
        raise ValueError("Paired comparison contains a nonfinite forecast")

    overall = {name: _metrics(matched, name) for name in prediction_names}
    by_lead = {
        str(int(lead)): {name: _metrics(rows, name) for name in prediction_names}
        for lead, rows in matched.groupby("forecast_step", sort=True)
    }
    by_series = {
        name: _group_metrics(matched, name, "series") for name in prediction_names
    }
    series_delta = []
    for series, candidate_metric in by_series["direct_candidate"].items():
        active_metric = by_series["active_published_path"].get(series)
        if active_metric is not None:
            series_delta.append({
                "series": series,
                "candidate": candidate_metric,
                "active_published_path": active_metric,
                "mae_delta_php": candidate_metric["mae_php"] - active_metric["mae_php"],
                "rmse_delta_php": candidate_metric["rmse_php"] - active_metric["rmse_php"],
                "mape_delta_percentage_points": candidate_metric["mape_pct"] - active_metric["mape_pct"],
                "within_5_delta_percentage_points": (
                    candidate_metric["within_5_php_pct"] - active_metric["within_5_php_pct"]),
            })

    matched["forecast_origin"] = matched.forecast_origin.dt.strftime("%Y-%m-%d")
    matched["target_period_start"] = matched.target_period_start.dt.strftime("%Y-%m-%d")
    matched["target_period_end"] = matched.target_period_end.dt.strftime("%Y-%m-%d")
    output_dir.mkdir(parents=True, exist_ok=False)
    rows_path = output_dir / "matched_predictions.csv"
    matched.to_csv(rows_path, index=False)
    report = {
        "horizon": horizon,
        "active_run": active_dir.name,
        "active_data_fingerprint": active_metadata.get("data_fingerprint"),
        "candidate_strategy": strategy,
        "candidate_report_sha256": sha256(candidate_report_path),
        "candidate_test_predictions_sha256": sha256(candidate_path),
        "source_snapshot_sha256": expected_sha,
        "source_data_as_of": report_dates.max().date().isoformat(),
        "evaluation_window": {"start": str(test_start.date()), "end": str(test_end.date())},
        "forecast_origins": [origin.date().isoformat() for origin in origins],
        "active_model_policy": "fixed incumbent bundle; recursive daily forecasts using production path, rounded and aggregated by the production publisher",
        "candidate_fit_policy": "candidate refit causally at each origin; training target end no later than origin",
        "matched_rows": int(len(matched)),
        "candidate_rows": int(len(candidate)),
        "active_period_rows": int(len(active_rows)),
        "candidate_coverage_pct": float(len(matched) / len(candidate) * 100),
        "metric_policy": {
            "units": "original PHP price units",
            "mape": "positive actuals only; nonpositive actuals excluded",
            "bias": "prediction minus actual; negative indicates underprediction",
            "target": "same complete calendar target periods and observed labels",
            "candidate_rounding": "publisher-compatible two-decimal rounding before scoring",
        },
        "overall": overall,
        "by_forecast_step": by_lead,
        "by_series": by_series,
        "per_series_candidate_vs_active": series_delta,
        "prospective_holdout_labels_read": False,
        "production_activated": False,
        "matched_rows_file": rows_path.name,
        "accuracy_claim": "none; historical test window was previously used in development",
    }
    (output_dir / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return report


def main() -> None:
    repository = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path,
                        default=repository / "audits/foodcast_accuracy_20261015/horizon_models_v2/summary.json")
    parser.add_argument("--data", type=Path,
                        default=repository / "audits/accuracy_goal_20261011/supabase_food_prices_through_20261005.json")
    parser.add_argument("--horizon", choices=("weekly", "monthly"), required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = compare(args.summary, args.data, args.horizon, args.output_dir)
    print(json.dumps({
        "horizon": report["horizon"],
        "matched_rows": report["matched_rows"],
        "candidate_coverage_pct": report["candidate_coverage_pct"],
        "overall": report["overall"],
        "report": str(Path(args.output_dir).resolve() / "report.json"),
    }, indent=2))


if __name__ == "__main__":
    main()
