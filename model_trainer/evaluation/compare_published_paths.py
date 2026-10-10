"""Compare saved candidate paths with the active model on identical validation origins."""
import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.preprocessor import DataPreprocessor
from evaluation.horizon_audit import metrics
from features.builder import FeatureBuilder
from models.ensemble import EnsembleModel
from models.forecast_engine import ForecastEngine
from models.lightgbm_model import LightGBMModel
from models.lstm_model import LSTMModel
from models.model_store import ModelStore
from pipeline.prediction_writer import PredictionWriter
from pipeline.trainer import EVALUATION_ORIGIN_POLICY, TrainingPipeline


HORIZONS = ("daily", "weekly", "monthly")


def _load_engine(bundle, clean):
    builder = FeatureBuilder(bundle).load()
    featured = builder.transform(clean)
    lgbm = LightGBMModel(bundle)
    lgbm.load()
    lstm = LSTMModel(bundle)
    lstm.load()
    ensemble = EnsembleModel(bundle)
    ensemble.load()
    return ForecastEngine(lgbm, lstm, ensemble, builder), featured


def _published_rows(paths):
    output = []
    for (series, origin_text), group in paths.groupby(["series", "origin"], sort=True):
        group = group.sort_values("horizon")
        dates = pd.to_datetime(group.date).to_numpy()
        point = group.ensemble.to_numpy(dtype=float)
        actuals = dict(zip(pd.to_datetime(group.date).dt.date,
                           group.actual.to_numpy(dtype=float)))
        published = PredictionWriter._rows(
            "validation-product", dates, point, origin_text, {})
        path_dates = sorted(actuals)
        for row in published:
            horizon = row["forecast_horizon"]
            target = pd.Timestamp(row["prediction_date"]).date()
            if horizon == "daily":
                target_actuals = [actuals[target]] if target in actuals else []
                covered_days = 1
            else:
                start = pd.Timestamp(row["target_period_start"]).date()
                end = pd.Timestamp(row["target_period_end"]).date()
                covered = [day for day in path_dates if start <= day <= end]
                target_actuals = [actuals[day] for day in covered
                                  if math.isfinite(actuals[day]) and actuals[day] >= 0]
                covered_days = len(covered)
            target_actuals = [value for value in target_actuals
                              if math.isfinite(value) and value >= 0]
            if not target_actuals:
                continue
            if horizon == "daily":
                actual = target_actuals[0]
                period_days = 1
                partial = False
            else:
                actual = mean(target_actuals)
                period_days = int(row["period_days"])
                partial = (covered_days < period_days
                           or len(target_actuals) < covered_days)
            output.append({
                "series": str(series), "origin": str(origin_text)[:10],
                "date": target.isoformat(), "horizon": horizon,
                "forecast_step": int(row["forecast_step"]),
                "actual": actual, "ensemble": float(row["predicted_price"]),
                "covered_days": covered_days,
                "observed_days": len(target_actuals),
                "period_days": period_days,
                "partial_period": partial,
            })
    return output


def _metric_rows(rows):
    return metrics(rows)


def _by(rows, field):
    result = defaultdict(list)
    for row in rows:
        result[row[field]].append(row)
    return result


def _summarize(rows):
    by_horizon = {name: _metric_rows([row for row in rows if row["horizon"] == name])
                  for name in HORIZONS}
    by_step = {
        name: {str(step): _metric_rows(selected)
               for step, selected in sorted(_by(
                   [row for row in rows if row["horizon"] == name],
                   "forecast_step").items())}
        for name in HORIZONS
    }
    by_product = {
        name: {series: _metric_rows([row for row in rows
                                     if row["horizon"] == name and row["series"] == series])
               for series in sorted({row["series"] for row in rows
                                     if row["horizon"] == name})}
        for name in HORIZONS
    }
    worst = {
        name: sorted(({"series": series, **score}
                      for series, score in by_product[name].items()),
                     key=lambda score: score["rmse"] if score["rmse"] is not None else -1,
                     reverse=True)[:10]
        for name in HORIZONS
    }
    return {
        "overall": {name: by_horizon[name] for name in HORIZONS},
        "combined": _metric_rows(rows),
        "by_step": by_step,
        "by_product": by_product,
        "worst_ten_products_by_rmse": worst,
    }


def _assert_same_labels(candidate, active):
    keys = ["series", "origin", "date", "horizon"]
    left = candidate[keys + ["actual"]].copy()
    right = active[keys + ["actual"]].copy()
    left["origin"] = pd.to_datetime(left.origin).dt.strftime("%Y-%m-%d")
    right["origin"] = pd.to_datetime(right.origin).dt.strftime("%Y-%m-%d")
    left["date"] = pd.to_datetime(left.date).dt.strftime("%Y-%m-%d")
    right["date"] = pd.to_datetime(right.date).dt.strftime("%Y-%m-%d")
    left = left.sort_values(keys).reset_index(drop=True)
    right = right.sort_values(keys).reset_index(drop=True)
    if not left[keys].equals(right[keys]) or len(left) != len(right):
        raise ValueError("Candidate and active forecasts do not use identical path rows")
    for first, second in zip(left.actual.to_numpy(dtype=float),
                             right.actual.to_numpy(dtype=float)):
        if math.isfinite(first) != math.isfinite(second):
            raise ValueError("Candidate and active validation label coverage differs")
        if math.isfinite(first) and not math.isclose(first, second, rel_tol=0, abs_tol=1e-10):
            raise ValueError("Candidate and active validation actual labels differ")


def _partitions_from_metadata(clean, split_metadata, pipeline):
    partitions = {}
    assigned = pd.Series(False, index=clean.index)
    for name in ("train", "validation", "test"):
        bounds = split_metadata[name]
        start, end = pd.Timestamp(bounds["start"]), pd.Timestamp(bounds["end"])
        mask = clean.report_date.between(start, end)
        if (assigned & mask).any():
            raise ValueError("Candidate partition boundaries overlap")
        frame = clean.loc[mask].copy()
        if frame.empty or pipeline._partition_bounds(frame) != bounds:
            raise ValueError(f"Candidate {name} partition does not match its metadata")
        partitions[name] = frame
        assigned |= mask
    if not assigned.all():
        raise ValueError("Candidate split does not cover the supplied source snapshot")
    return partitions


def compare(candidate_run, snapshot, output, partition_name="validation"):
    candidate_run, snapshot, output = Path(candidate_run), Path(snapshot), Path(output)
    candidate_meta = json.loads((candidate_run / "metadata.json").read_text(encoding="utf-8"))
    raw = pd.DataFrame(json.loads(snapshot.read_text(encoding="utf-8")))
    pipeline = TrainingPipeline()
    fingerprint = pipeline._fingerprint(raw)
    if fingerprint != candidate_meta.get("data_fingerprint"):
        raise ValueError("Snapshot fingerprint does not match candidate provenance")

    settings = pipeline.cfg
    settings.evaluation_stride = int(candidate_meta["metrics"]["evaluation_stride_days"])
    if candidate_meta["metrics"].get("evaluation_origin_policy") != EVALUATION_ORIGIN_POLICY:
        raise ValueError("Candidate does not use the current evaluation-origin policy")
    active_run = pipeline.store.active_path()
    active_meta = json.loads((active_run / "metadata.json").read_text(encoding="utf-8"))
    if active_meta.get("data_fingerprint") != fingerprint:
        raise ValueError("Active and candidate bundles have different source snapshots")

    clean = pipeline.preprocessor.validate(raw)
    partitions = _partitions_from_metadata(clean, candidate_meta.get("split", {}), pipeline)
    if partition_name not in {"validation", "test"}:
        raise ValueError("Only chronological validation or development test can be compared")
    partition = partitions[partition_name]
    path_name = f"{partition_name}_paths.csv"

    active_engine, active_featured = _load_engine(active_run, clean)
    _, active_paths = pipeline._backtest(
        clean, active_featured, partition,
        active_engine, return_paths=True)
    active_paths["ensemble"] = active_engine.ensemble.predict_rows(
        active_paths.lstm.to_numpy(), active_paths.lgbm.to_numpy(),
        active_paths.horizon.to_numpy(), active_paths.anchor.to_numpy(),
        active_paths.series.to_numpy(), active_paths.moving_average7.to_numpy())
    candidate_paths = pd.read_csv(candidate_run / path_name)
    _assert_same_labels(candidate_paths, active_paths)

    baseline_rows = _published_rows(active_paths)
    candidate_rows = _published_rows(candidate_paths)
    baseline_keys = {(row["series"], row["origin"], row["horizon"], row["forecast_step"])
                     for row in baseline_rows}
    candidate_keys = {(row["series"], row["origin"], row["horizon"], row["forecast_step"])
                      for row in candidate_rows}
    if baseline_keys != candidate_keys:
        raise ValueError("Candidate and active published outputs are not directly comparable")

    results = {
        "active": _summarize(baseline_rows),
        "candidate": _summarize(candidate_rows),
    }
    confidence = candidate_meta.get("metrics", {}).get("product_confidence_by_identity", {})
    statuses = defaultdict(int)
    numeric = 0
    for product in confidence.values():
        for metric in product.get("confidence_by_horizon", {}).values():
            statuses[metric.get("evidence_status", "missing")] += 1
            numeric += isinstance(metric.get("confidence_score"), (int, float))
        for horizon_metrics in product.get("confidence_by_step", {}).values():
            for metric in horizon_metrics.values():
                statuses[metric.get("evidence_status", "missing")] += 1
                numeric += isinstance(metric.get("confidence_score"), (int, float))
    report = {
        "active_run": active_run.name,
        "candidate_run": candidate_run.name,
        "evaluation_partition": partition_name,
        "snapshot": str(snapshot.resolve()),
        "data_fingerprint": fingerprint,
        "source_observed_through": candidate_meta["metrics"].get(
            "source_data", {}).get("processed_through"),
        "evaluation_window": {
            "start": pd.Timestamp(partition.report_date.min()).date().isoformat(),
            "end": pd.Timestamp(partition.report_date.max()).date().isoformat(),
        },
        "evaluation_stride_days": settings.evaluation_stride,
        "evaluation_origin_policy": EVALUATION_ORIGIN_POLICY,
        "candidate_path_count": int(candidate_meta["metrics"].get(
            f"{partition_name}_path_samples", 0) / settings.monthly_horizon),
        "active_path_count": int(active_paths.groupby(["series", "origin"]).ngroups),
        "active_scored_rows": len(baseline_rows),
        "candidate_scored_rows": len(candidate_rows),
        "candidate_validation_confidence_status_counts": dict(statuses),
        "candidate_validation_confidence_numeric_count": int(numeric),
        "metrics": results,
        "metric_notes": {
            "within_10": "Absolute percentage error <= 10%; actuals below 1e-8 PHP excluded and counted.",
            "mae_rmse": "PHP scale; all finite nonnegative actuals.",
            "weekly_monthly": "PredictionWriter aggregation and centavo rounding; realized average over observed forecast-covered dates.",
            "partial_periods": "Retained and counted in each weekly/monthly metric group.",
            "holdout": "No frozen holdout actuals are read by this evaluation.",
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-run", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--partition", choices=("validation", "test"), default="validation")
    args = parser.parse_args()
    report = compare(args.candidate_run, args.snapshot, args.output, args.partition)
    print(json.dumps({"active_run": report["active_run"],
                      "candidate_run": report["candidate_run"],
                      "evaluation_partition": report["evaluation_partition"],
                      "metrics": {name: report["metrics"][name]["overall"]
                                  for name in ("active", "candidate")},
                      "confidence_status_counts": report[
                          "candidate_validation_confidence_status_counts"],
                      "report": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
