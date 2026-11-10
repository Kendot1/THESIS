"""Paired 14-day comparison of a direct candidate with the active bundle.

The candidate and incumbent are evaluated on the candidate's exact origins and
observed targets. The candidate is refit causally at each origin; the active
bundle is kept fixed, matching the current production artifact's behavior.
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
from evaluation.horizon_specific import _metric, load_snapshot, sha256
from features.builder import FeatureBuilder
from models.ensemble import EnsembleModel
from models.forecast_engine import ForecastEngine
from models.lightgbm_model import LightGBMModel
from models.lstm_model import LSTMModel
from models.model_store import ModelStore
from pipeline.trainer import TrainingPipeline


PREDICTIONS = {
    "active_ensemble": "ensemble",
    "active_lstm": "lstm",
    "active_lightgbm": "lgbm",
    "persistence": "persistence",
    "seasonal_naive_7": "seasonal7",
    "moving_average_7": "moving_average7",
}


def _metric_for(frame: pd.DataFrame, prediction: str) -> dict:
    values = frame[["actual", prediction]].rename(columns={prediction: "prediction"})
    return _metric(values, "prediction")


def _summarize_groups(frame: pd.DataFrame, prediction: str, group: str) -> list[dict]:
    rows = []
    for key, subset in frame.groupby(group, sort=True, dropna=False):
        rows.append({group: str(key), **_metric_for(subset, prediction)})
    return rows


def compare(summary_path: Path, snapshot_path: Path, output_dir: Path) -> dict:
    summary_path = Path(summary_path).resolve()
    snapshot_path = Path(snapshot_path).resolve()
    output_dir = Path(output_dir).resolve()
    report_path = output_dir / "report.json"
    rows_path = output_dir / "matched_predictions.csv"
    if report_path.exists() or rows_path.exists():
        raise FileExistsError(f"Refusing to overwrite paired comparison: {output_dir}")

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    expected_sha = summary.get("source_snapshot_sha256")
    if sha256(snapshot_path) != expected_sha:
        raise ValueError("Snapshot hash does not match the candidate experiment")
    horizon = summary["horizons"]["daily"]
    split = summary["splits"]
    origins = pd.to_datetime(horizon["origins"]["test"], errors="raise")
    holdout_start = pd.Timestamp(summary["holdout_start"])
    if origins.max() >= holdout_start:
        raise ValueError("Candidate origins reach the sealed prospective holdout")

    candidate_path = summary_path.parent / "daily" / "test_predictions.csv"
    candidate = pd.read_csv(candidate_path)
    strategy = horizon["selected_strategy"]
    candidate_prediction = f"candidate_{strategy}"
    required = {"series", "forecast_origin", "target_start", "lead", "actual", candidate_prediction}
    if not required.issubset(candidate.columns):
        raise ValueError(f"Candidate rows are missing columns: {sorted(required - set(candidate.columns))}")
    candidate["forecast_origin"] = pd.to_datetime(
        candidate.forecast_origin, errors="raise").dt.normalize()
    candidate["date"] = pd.to_datetime(candidate.target_start, errors="raise").dt.normalize()

    raw = load_snapshot(snapshot_path)
    clean = DataPreprocessor().validate(raw)
    test_start, test_end = pd.Timestamp(split["validation_end"]) + pd.Timedelta(days=1), pd.Timestamp(split["test_end"])
    partition = clean.loc[clean.report_date.between(test_start, test_end)].copy()
    if partition.empty:
        raise ValueError("The candidate test partition is empty")

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
    pipeline.cfg.monthly_horizon = int(horizon["target_definition"]["steps"])
    pipeline.preprocessor = DataPreprocessor()
    _, active_paths = pipeline._backtest(
        clean, featured, partition, engine, return_paths=True,
        origin_dates=origins,
    )
    active_paths["ensemble"] = ensemble.predict_rows(
        active_paths.lstm.to_numpy(dtype=float),
        active_paths.lgbm.to_numpy(dtype=float),
        active_paths.horizon.to_numpy(dtype=int),
        active_paths.anchor.to_numpy(dtype=float),
        active_paths.series.to_numpy(),
        active_paths.moving_average7.to_numpy(dtype=float),
    )
    active_paths["origin"] = pd.to_datetime(active_paths.origin).dt.normalize()
    active_paths["date"] = pd.to_datetime(active_paths.date).dt.normalize()
    active_paths["forecast_origin"] = active_paths.origin

    keys = ["series", "forecast_origin", "date"]
    candidate_view = candidate[
        ["series", "forecast_origin", "date", "lead", "actual", candidate_prediction]
    ].rename(columns={
        "actual": "candidate_actual",
        candidate_prediction: "candidate",
    })
    selected_active = active_paths[keys + ["actual", "horizon", *PREDICTIONS.values()]].copy()
    matched = candidate_view.merge(
        selected_active, on=keys, how="inner", suffixes=("_candidate", "_active"),
        validate="one_to_one",
    )
    if matched.empty:
        raise ValueError("No candidate and active forecast rows matched")
    if not np.allclose(
            matched.candidate_actual.to_numpy(dtype=float),
            matched.actual.to_numpy(dtype=float),
            rtol=0, atol=1e-10, equal_nan=True):
        raise ValueError("Candidate and active predictions use different actual labels")
    matched = matched.loc[
        np.isfinite(matched.actual.to_numpy(dtype=float))
    ].copy()
    matched = matched.rename(columns={"horizon": "active_lead"})

    prediction_columns = {"direct_candidate": "candidate", **PREDICTIONS}
    overall = {
        name: _metric_for(matched, column)
        for name, column in prediction_columns.items()
    }
    by_lead = {
        str(lead): {
            name: _metric_for(group, column)
            for name, column in prediction_columns.items()
        }
        for lead, group in matched.groupby("lead", sort=True)
    }
    by_series = {
        name: _summarize_groups(matched, column, "series")
        for name, column in prediction_columns.items()
    }
    active_series = {row["series"]: row for row in by_series["active_ensemble"]}
    candidate_series = by_series["direct_candidate"]
    paired_series = []
    for row in candidate_series:
        baseline = active_series.get(row["series"])
        if baseline is None:
            continue
        paired_series.append({
            "series": row["series"],
            "candidate": row,
            "active_ensemble": baseline,
            "mae_delta_php": row["mae_php"] - baseline["mae_php"],
            "rmse_delta_php": row["rmse_php"] - baseline["rmse_php"],
            "mape_delta_percentage_points": row["mape_pct"] - baseline["mape_pct"],
        })

    matched["forecast_origin"] = matched.forecast_origin.dt.strftime("%Y-%m-%d")
    matched["date"] = matched.date.dt.strftime("%Y-%m-%d")
    output_dir.mkdir(parents=True, exist_ok=True)
    matched.to_csv(rows_path, index=False)
    report = {
        "active_run": active_dir.name,
        "active_data_fingerprint": active_metadata.get("data_fingerprint"),
        "candidate_experiment": str(summary_path),
        "source_snapshot_sha256": expected_sha,
        "test_window": {"start": str(test_start.date()), "end": str(test_end.date())},
        "forecast_origins": [str(pd.Timestamp(origin).date()) for origin in origins],
        "candidate_refit_policy": "causal expanding fit at each origin; target_end <= origin",
        "active_model_policy": "fixed active bundle, replayed at the same origins",
        "matched_rows": int(len(matched)),
        "candidate_rows": int(len(candidate)),
        "matched_coverage_pct": float(len(matched) / len(candidate) * 100),
        "metric_policy": {
            "price_units": "PHP in original units",
            "mape": "positive actuals only; nonpositive actuals excluded",
            "bias": "prediction minus actual; negative indicates underprediction",
            "scope": "identical series, origins, dates, and actual labels",
        },
        "overall": overall,
        "by_lead": by_lead,
        "by_series": by_series,
        "per_series_candidate_vs_active": paired_series,
        "production_activated": False,
        "matched_rows_file": rows_path.name,
    }
    report_path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True,
                        help="Completed horizon experiment summary.json")
    parser.add_argument("--data", type=Path, required=True,
                        help="Exact input snapshot used for the experiment")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = compare(args.summary, args.data, args.output_dir)
    print(json.dumps({
        "active_run": report["active_run"],
        "matched_rows": report["matched_rows"],
        "matched_coverage_pct": report["matched_coverage_pct"],
        "metrics": report["overall"],
        "report": str(Path(args.output_dir).resolve() / "report.json"),
    }, indent=2))


if __name__ == "__main__":
    main()
