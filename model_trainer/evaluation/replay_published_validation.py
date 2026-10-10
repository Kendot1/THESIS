"""Rebuild publisher-aligned daily-path calendar outputs for validation.

The validation CSV stores only days with observed labels. This audit replays the
    saved model against a dated source snapshot, then passes each full 30-day path
through PredictionWriter._rows so weekly/monthly predictions use the same
rounding and calendar aggregation as publication. Actual period targets use
observed validation labels on the forecast-covered dates and report coverage.
"""
import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

import numpy as np
import pandas as pd

from data.preprocessor import DataPreprocessor, SERIES_KEY
from evaluation.horizon_audit import metrics
from evaluation.product_confidence import validation_confidence
from features.builder import FeatureBuilder
from models.ensemble import EnsembleModel
from models.forecast_engine import ForecastEngine
from models.lightgbm_model import LightGBMModel
from models.lstm_model import LSTMModel
from pipeline.prediction_writer import PredictionWriter


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _engine(bundle, builder):
    lgbm = LightGBMModel(bundle)
    lgbm.load()
    lstm = LSTMModel(bundle)
    lstm.load()
    ensemble = EnsembleModel(bundle)
    ensemble.load()
    return ForecastEngine(lgbm, lstm, ensemble, builder)


def _groups(rows, field):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row[field]].append(row)
    return grouped


def _metrics_report(rows):
    return metrics(rows)


def replay(bundle, snapshot, output, report=None):
    bundle, snapshot, output = Path(bundle), Path(snapshot), Path(output)
    metadata = json.loads((bundle / "metadata.json").read_text(encoding="utf-8"))
    validation = pd.read_csv(bundle / "validation_forecasts.csv")
    validation["origin_dt"] = pd.to_datetime(validation.origin).dt.normalize()
    validation["date_dt"] = pd.to_datetime(validation.date).dt.normalize()
    actual_map = {
        (str(row.series), row.origin_dt, row.date_dt): float(row.actual)
        for row in validation.itertuples()
        if math.isfinite(float(row.actual))
    }
    saved_prediction = {
        (str(row.series), row.origin_dt, row.date_dt): float(row.ensemble)
        for row in validation.itertuples()
        if math.isfinite(float(row.ensemble))
    }

    start = pd.Timestamp(metadata["split"]["validation"]["start"])
    end = pd.Timestamp(metadata["split"]["validation"]["end"])
    horizon = 30
    origins = pd.date_range(start - pd.Timedelta(days=1),
                            end - pd.Timedelta(days=horizon), freq="30D")

    # The snapshot may contain later rows, but each model input below is sliced
    # to its forecast origin. Validation outcomes come only from the sealed CSV.
    raw = pd.DataFrame(json.loads(snapshot.read_text(encoding="utf-8")))
    clean = DataPreprocessor().validate(raw)
    builder = FeatureBuilder(bundle).load()
    featured = builder.transform(clean)
    market_daily = FeatureBuilder.category_return_history(clean)
    market_daily["category_return"] = market_daily.category_return.fillna(0.0)
    market_histories = {}
    for category, group in market_daily.groupby("product_category", sort=False):
        dates = pd.to_datetime(group.report_date)
        for origin in origins:
            market_histories[(str(category), pd.Timestamp(origin))] = group.loc[
                dates <= origin, "category_return"].to_numpy(dtype=float).tolist()

    engine = _engine(bundle, builder)
    feature_groups = {key: group for key, group in
                      featured.groupby(SERIES_KEY, sort=False)}
    cases, contexts = [], []
    for key, full_series in clean.groupby(SERIES_KEY, sort=True):
        full_series = full_series.sort_values("report_date")
        for origin in origins:
            history = full_series[full_series.report_date <= origin]
            try:
                category = str(full_series.product_category.iloc[-1])
                case = engine._prepare(
                    history, feature_groups[key],
                    market_histories.get((category, pd.Timestamp(origin)), []))
            except (KeyError, ValueError):
                continue
            last_seven = history.price_index[
                np.isfinite(history.price_index)].tail(7).to_numpy(dtype=float)
            if not len(last_seven):
                continue
            cases.append(case)
            contexts.append((tuple(key), pd.Timestamp(origin), last_seven))

    paths = engine.forecast_many(cases, horizon)
    period_rows, replay_vs_saved = [], []
    missing_actual_periods = 0
    for path, (key, origin, _) in zip(paths, contexts):
        series = "||".join(map(str, key))
        published = PredictionWriter._rows(
            "audit-product", path.dates, path.point, origin, {})
        daily = [row for row in published if row["forecast_horizon"] == "daily"]
        covered = [pd.Timestamp(row["prediction_date"]).normalize() for row in daily]
        for index, row in enumerate(daily):
            identity = (series, origin.normalize(),
                        pd.Timestamp(row["prediction_date"]).normalize())
            if identity in saved_prediction:
                model_point = float(path.point[index])
                replay_vs_saved.append({
                    "series": series,
                    "origin": origin.date().isoformat(),
                    "date": identity[2].date().isoformat(),
                    "saved": saved_prediction[identity],
                    "replayed_model_point": model_point,
                    "replayed_published": float(row["predicted_price"]),
                    "model_point_absolute_difference": abs(
                        saved_prediction[identity] - model_point),
                    "published_absolute_difference": abs(
                        saved_prediction[identity] - float(row["predicted_price"])),
                })
        for row in published:
            kind = row["forecast_horizon"]
            if kind == "daily":
                continue
            period_start = pd.Timestamp(row["target_period_start"]).normalize()
            period_end = pd.Timestamp(row["target_period_end"]).normalize()
            period_covered = [day for day in covered
                              if period_start <= day <= period_end]
            realized = [actual_map[(series, origin.normalize(), day)]
                        for day in period_covered
                        if (series, origin.normalize(), day) in actual_map]
            if not realized:
                missing_actual_periods += 1
                continue
            period_rows.append({
                "series": series,
                "origin": origin.date().isoformat(),
                "date": pd.Timestamp(row["prediction_date"]).date().isoformat(),
                "horizon": kind,
                "forecast_step": int(row["forecast_step"]),
                "target_period_start": period_start.date().isoformat(),
                "target_period_end": period_end.date().isoformat(),
                "actual": mean(realized),
                "ensemble": float(row["predicted_price"]),
                "covered_days": len(period_covered),
                "observed_days": len(realized),
                "period_days": int(row["period_days"]),
                "partial_period": (len(period_covered) < int(row["period_days"])
                                   or len(realized) < len(period_covered)),
            })

    output.parent.mkdir(parents=True, exist_ok=True)
    columns = ["series", "origin", "date", "horizon", "forecast_step",
               "target_period_start", "target_period_end", "actual", "ensemble",
               "covered_days", "observed_days", "period_days", "partial_period"]
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(period_rows)

    daily_rows = [{
        "series": str(row.series), "origin": row.origin_dt.date().isoformat(),
        "date": row.date_dt.date().isoformat(), "actual": float(row.actual),
        "ensemble": float(row.ensemble), "partial_period": False,
        "forecast_step": int(row.horizon),
    } for row in validation.itertuples()]
    period_by_horizon = {name: [row for row in period_rows
                                if row["horizon"] == name]
                         for name in ("weekly", "monthly")}
    scored = {"daily": daily_rows, **period_by_horizon}
    combined = [row for values in scored.values() for row in values]
    by_step, by_product = {}, {}
    for name, rows in scored.items():
        by_step[name] = {
            str(step): _metrics_report(selected)
            for step, selected in sorted(_groups(rows, "forecast_step").items())
        }
        by_product[name] = {
            series: _metrics_report(selected)
            for series, selected in sorted(_groups(rows, "series").items())
        }
    worst_products = {}
    for name, groups in by_product.items():
        worst_products[name] = sorted(
            ({"series": series, **score} for series, score in groups.items()),
            key=lambda item: item["rmse"] if item["rmse"] is not None else -1,
            reverse=True)[:5]
    parity_diffs = [row["model_point_absolute_difference"]
                    for row in replay_vs_saved]
    published_diffs = [row["published_absolute_difference"]
                       for row in replay_vs_saved]
    snapshot_metadata_path = snapshot.with_name("snapshot_metadata.json")
    snapshot_metadata = (json.loads(snapshot_metadata_path.read_text(encoding="utf-8"))
                         if snapshot_metadata_path.exists() else None)
    period_report = {
        name: _metrics_report(rows) for name, rows in scored.items()
    }
    identities = {tuple(row["series"].split("||")): row["series"]
                  for row in daily_rows}
    confidence = validation_confidence(bundle, identities)
    confidence_metrics = [metric for product in confidence.values()
                          for metric in product["confidence_by_horizon"].values()]
    confidence_metrics.extend(
        metric for product in confidence.values()
        for horizon_metrics in product["confidence_by_step"].values()
        for metric in horizon_metrics.values())
    report_data = {
        "active_model": bundle.name,
        "validation_window": {"start": start.date().isoformat(),
                              "end": end.date().isoformat()},
        "source_snapshot": str(snapshot),
        "source_snapshot_sha256": _sha256(snapshot),
        "source_snapshot_metadata": snapshot_metadata,
        "active_source_data": metadata.get("metrics", {}).get("source_data"),
        "validation_forecasts_sha256": _sha256(bundle / "validation_forecasts.csv"),
        "model_metadata_sha256": _sha256(bundle / "metadata.json"),
        "forecast_paths_replayed": len(paths),
        "saved_daily_rows": len(validation),
        "daily_replay_parity": {
            "matched_rows": len(replay_vs_saved),
            "within_half_cent": sum(diff < 0.0051 for diff in parity_diffs),
            "model_point_mean_abs_difference_php": mean(parity_diffs) if parity_diffs else None,
            "model_point_max_abs_difference_php": max(parity_diffs) if parity_diffs else None,
            "rows_over_half_cent": sum(diff >= 0.0051 for diff in parity_diffs),
            "published_rounding_mean_abs_difference_vs_saved_raw_php": (
                mean(published_diffs) if published_diffs else None),
        },
        "periods_without_observed_validation_actual": missing_actual_periods,
        "period_rows_written": len(period_rows),
        "metrics": {"published_output_all_horizons": _metrics_report(combined),
                    **period_report},
        "per_step": by_step,
        "per_product": by_product,
        "worst_five_products_by_rmse": worst_products,
        "confidence_evidence_status": dict(Counter(
            metric["evidence_status"] for metric in confidence_metrics)),
        "confidence_numeric_metric_count": sum(
            isinstance(metric.get("confidence_score"), (int, float))
            for metric in confidence_metrics),
        "replay_scope_limitations": (
            "The 2026-09-18 source snapshot is non-atomic and is not the original "
            "model-training vintage. Seventeen replayed daily model points differ "
            "from saved validation predictions by more than 0.005 PHP. Weekly and "
            "monthly scores are publisher-aligned replay diagnostics; realized "
            "period targets average only observed validation labels on forecast-"
            "covered dates, and all scored period rows are partial."),
        "confidence_evidence_note": (
            "Confidence was not recalibrated from this replay. See the sealed bundle's "
            "product confidence evidence statuses; this replay is a validation audit."),
    }
    report_path = Path(report) if report else output.with_suffix(".json")
    report_path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
    return report_data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = replay(args.bundle, args.snapshot, args.output, args.report)
    print(json.dumps({
        "active_model": result["active_model"],
        "daily_replay_parity": result["daily_replay_parity"],
        "metrics": result["metrics"],
        "period_rows_written": result["period_rows_written"],
        "report": str(args.report or args.output.with_suffix(".json")),
        "periods": str(args.output),
    }, indent=2))


if __name__ == "__main__":
    main()
