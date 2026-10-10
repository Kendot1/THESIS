"""Audit product confidence on denser origins inside a sealed validation window.

This is an offline diagnostic. It reuses a candidate's saved held-out validation
actuals, replays its unchanged model at weekly origins within that same window,
and uses the production confidence scoring formula. It never reads test or final
holdout outcomes and does not edit or activate a model bundle.
"""
import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from statistics import mean

import numpy as np
import pandas as pd

REPLAY_PARITY_TOLERANCE_PHP = 0.01

from data.preprocessor import DataPreprocessor, SERIES_KEY
from evaluation.product_confidence import (
    HORIZONS, MIN_ORIGINS, MIN_SAMPLES, _empty_metric, score_metrics,
)
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


def _load_engine(bundle):
    builder = FeatureBuilder(bundle).load()
    lgbm, lstm, ensemble = LightGBMModel(bundle), LSTMModel(bundle), EnsembleModel(bundle)
    lgbm.load()
    lstm.load()
    ensemble.load()
    return builder, ForecastEngine(lgbm, lstm, ensemble, builder)


def _score(rows):
    valid, invalid = [], 0
    for row in rows:
        try:
            actual, predicted = float(row["actual"]), float(row["ensemble"])
        except (KeyError, TypeError, ValueError):
            invalid += 1
            continue
        if not math.isfinite(actual) or not math.isfinite(predicted) or actual < 0:
            invalid += 1
            continue
        valid.append((actual, predicted, bool(row.get("partial_period", False))))
    errors = [abs(predicted - actual) for actual, predicted, _ in valid]
    eligible = [(actual, predicted) for actual, predicted, _ in valid if actual >= 1e-8]
    apes = [abs(predicted - actual) / actual for actual, predicted in eligible]
    hits = sum(ape <= 0.10 for ape in apes)
    return {
        "n": len(valid), "within_10_count": hits,
        "percentage_n": len(apes),
        "within_10_pct": hits / len(apes) * 100 if apes else None,
        "mae": mean(errors) if errors else None,
        "rmse": math.sqrt(mean(error * error for error in errors)) if errors else None,
        "mape": mean(apes) * 100 if apes else None,
        "excluded_near_zero": len(valid) - len(apes),
        "excluded_invalid": invalid,
        "partial_periods": sum(partial for _, _, partial in valid),
    }


def replay(bundle, snapshot, output, stride_days=7):
    bundle, snapshot, output = Path(bundle), Path(snapshot), Path(output)
    metadata = json.loads((bundle / "metadata.json").read_text(encoding="utf-8"))
    ensemble_meta = json.loads((bundle / "ensemble.json").read_text(encoding="utf-8"))
    calibration = ensemble_meta.get("calibration", {})
    if (calibration.get("scope") != "held_out_from_ensemble_fit"
            or calibration.get("base_model_scope") != "calibration_excluded_from_early_stopping"):
        raise ValueError("Candidate has no held-out validation calibration provenance")
    if type(stride_days) is not int or stride_days < 1:
        raise ValueError("stride_days must be a positive integer")

    target_start = date.fromisoformat(calibration["start"][:10])
    target_end = date.fromisoformat(calibration["end"][:10])
    first_origin = target_start - timedelta(days=1)
    last_origin = target_end - timedelta(days=30)
    if last_origin < first_origin:
        raise ValueError("Held-out calibration window is shorter than 30 forecast days")

    validation = pd.read_csv(bundle / "validation_forecasts.csv")
    validation["origin_dt"] = pd.to_datetime(validation.origin).dt.date
    validation["date_dt"] = pd.to_datetime(validation.date).dt.date
    heldout = validation[
        (validation.origin_dt >= first_origin)
        & (validation.date_dt >= target_start)
        & (validation.date_dt <= target_end)
    ].copy()
    if len(heldout) != int(calibration.get("sample_count", -1)):
        raise ValueError("Saved held-out validation rows do not match calibration provenance")

    actual_map, saved_predictions = {}, {}
    for row in heldout.itertuples():
        label_key = (str(row.series), row.date_dt)
        actual_value = float(row.actual)
        previous = actual_map.get(label_key)
        if previous is not None and not math.isclose(previous, actual_value, rel_tol=0, abs_tol=1e-8):
            raise ValueError("Conflicting saved held-out actuals for a series/date")
        actual_map[label_key] = actual_value
        saved_predictions[(str(row.series), row.origin_dt, row.date_dt)] = float(row.ensemble)

    origin_set = set(pd.date_range(first_origin, last_origin, freq=f"{stride_days}D").date)
    # Include the original held-out origins for direct replay parity checks.
    origin_set.update(
        origin for origin in validation.loc[
            (validation.origin_dt >= first_origin)
            & (validation.origin_dt <= last_origin), "origin_dt"].unique())
    origins = [pd.Timestamp(origin) for origin in sorted(origin_set)]

    raw = pd.DataFrame(json.loads(snapshot.read_text(encoding="utf-8")))
    clean = DataPreprocessor().validate(raw)
    builder, engine = _load_engine(bundle)
    featured = builder.transform(clean)
    market_daily = FeatureBuilder.category_return_history(clean)
    market_daily["category_return"] = market_daily.category_return.fillna(0.0)
    market_histories = {}
    for category, group in market_daily.groupby("product_category", sort=False):
        dates = pd.to_datetime(group.report_date)
        for origin in origins:
            market_histories[(str(category), origin)] = group.loc[
                dates <= origin, "category_return"].to_numpy(dtype=float).tolist()

    feature_groups = {key: group for key, group in featured.groupby(SERIES_KEY, sort=False)}
    cases, contexts = [], []
    supported_series = {series for series, _ in actual_map}
    for key, series in clean.groupby(SERIES_KEY, sort=True):
        series = series.sort_values("report_date")
        name = "||".join(map(str, key))
        if name not in supported_series:
            continue
        for origin in origins:
            history = series[series.report_date <= origin]
            try:
                case = engine._prepare(
                    history, feature_groups[key],
                    market_histories.get((str(key[0]), origin), []))
            except (KeyError, ValueError):
                continue
            if not np.isfinite(history.price_index.to_numpy(dtype=float)).any():
                continue
            cases.append(case)
            contexts.append((tuple(key), origin))

    paths = engine.forecast_many(cases, 30)
    scored_rows, parity, output_counts, output_counts_by_step = [], [], Counter(), Counter()
    missing_actual, open_periods = Counter(), Counter()
    for path, (key, origin) in zip(paths, contexts):
        series = "||".join(map(str, key))
        published = PredictionWriter._rows("audit-product", path.dates, path.point, origin, {})
        daily = [row for row in published if row["forecast_horizon"] == "daily"]
        daily_dates = [pd.Timestamp(row["prediction_date"]).date() for row in daily]
        for row in published:
            horizon = row["forecast_horizon"]
            step = int(row["forecast_step"])
            if horizon == "daily":
                output_counts[(series, horizon)] += 1
                output_counts_by_step[(series, horizon, step)] += 1
                continue
            period_end = date.fromisoformat(row["target_period_end"])
            if period_end > target_end:
                open_periods[horizon] += 1
                continue
            output_counts[(series, horizon)] += 1
            output_counts_by_step[(series, horizon, step)] += 1
        for index, row in enumerate(daily):
            target = daily_dates[index]
            identity = (series, origin.date(), target)
            if identity in saved_predictions:
                delta = abs(float(path.point[index]) - saved_predictions[identity])
                parity.append(delta)
            actual = actual_map.get((series, target))
            if actual is None:
                missing_actual["daily"] += 1
                continue
            scored_rows.append({
                "series": series, "origin": origin.date().isoformat(),
                "date": target.isoformat(), "available_date": target.isoformat(),
                "horizon": "daily", "forecast_step": index + 1,
                "actual": actual, "ensemble": float(row["predicted_price"]),
                "covered_days": 1, "observed_days": 1, "period_days": 1,
                "partial_period": False,
            })
        for row in published:
            horizon = row["forecast_horizon"]
            if horizon == "daily":
                continue
            period_start = date.fromisoformat(row["target_period_start"])
            period_end = date.fromisoformat(row["target_period_end"])
            if period_end > target_end:
                continue
            covered = [day for day in daily_dates if period_start <= day <= period_end]
            actuals = [actual_map[(series, day)] for day in covered
                       if (series, day) in actual_map]
            if not actuals:
                missing_actual[horizon] += 1
                continue
            scored_rows.append({
                "series": series, "origin": origin.date().isoformat(),
                "date": period_end.isoformat(), "available_date": period_end.isoformat(),
                "horizon": horizon, "forecast_step": int(row["forecast_step"]),
                "target_period_start": period_start.isoformat(),
                "target_period_end": period_end.isoformat(),
                "actual": mean(actuals), "ensemble": float(row["predicted_price"]),
                "covered_days": len(covered), "observed_days": len(actuals),
                "period_days": int(row["period_days"]),
                "partial_period": (len(covered) < int(row["period_days"])
                                   or len(actuals) < len(covered)),
            })

    identities = sorted({row["series"] for row in scored_rows} |
                        {str(series) for series in validation.series.unique()})
    products = {tuple(series.split("||")): series for series in identities}
    result = {product: {
        "confidence_by_horizon": {
            name: _empty_metric(bundle, lead) for lead, name in HORIZONS.items()},
        "confidence_by_step": {name: {} for name in HORIZONS.values()},
    } for product in products.values()}
    for product in result.values():
        for metric in product["confidence_by_horizon"].values():
            metric["evidence_status"] = "insufficient_data"

    daily_all, daily_steps = defaultdict(list), defaultdict(list)
    sample_groups = defaultdict(list)
    for row in scored_rows:
        actual, predicted = float(row["actual"]), float(row["ensemble"])
        if (actual < 1e-8 or predicted <= 0 or not math.isfinite(actual)
                or not math.isfinite(predicted)):
            continue
        product, horizon = row["series"], row["horizon"]
        origin = date.fromisoformat(row["origin"])
        available = date.fromisoformat(row["available_date"])
        error = abs(predicted - actual)
        ape = error / actual * 100
        sample = (origin, available, error, ape, available)
        daily_all[(product, horizon)].append(sample)
        daily_steps[(product, horizon, int(row["forecast_step"]))].append(sample)
        sample_groups[(product, horizon)].append(row)

    metric_groups = []
    for (product, horizon), samples in daily_all.items():
        metric_groups.append((result[product]["confidence_by_horizon"][horizon], samples))
    for (product, horizon, step), samples in daily_steps.items():
        lead = {"daily": 1, "weekly": 7, "monthly": 30}[horizon]
        metric = _empty_metric(bundle, lead, step)
        metric["evidence_status"] = "insufficient_data"
        result[product]["confidence_by_step"][horizon][step] = metric
        metric_groups.append((metric, samples))
    score_metrics(metric_groups)

    replay_fidelity_pass = (
        len(parity) == len(heldout) and bool(parity)
        and max(parity) <= REPLAY_PARITY_TOLERANCE_PHP)
    if not replay_fidelity_pass:
        # Do not expose numeric confidence scores when the historical replay
        # cannot reproduce the sealed candidate predictions from its source.
        for product in result.values():
            for metric in product["confidence_by_horizon"].values():
                metric["confidence_score"] = None
                metric["confidence_level"] = "Insufficient data"
                metric["evidence_status"] = "unverified_provenance"
            for steps in product["confidence_by_step"].values():
                for metric in steps.values():
                    metric["confidence_score"] = None
                    metric["confidence_level"] = "Insufficient data"
                    metric["evidence_status"] = "unverified_provenance"

    # Report evidence coverage separately from the conditional error score.
    # Sparse labels cannot be hidden by a high MAPE-based reliability score.
    for product, details in result.items():
        for horizon, metric in details["confidence_by_horizon"].items():
            opportunities = output_counts[(product, horizon)]
            selected = sample_groups[(product, horizon)]
            metric["forecast_opportunities"] = opportunities
            metric["observed_outcome_coverage"] = (
                len(selected) / opportunities if opportunities else 0.0)
            if horizon in ("weekly", "monthly") and selected:
                metric["mean_observed_days_per_period"] = mean(
                    row["observed_days"] for row in selected)
                metric["mean_observed_fraction_of_covered_days"] = mean(
                    row["observed_days"] / row["covered_days"]
                    for row in selected if row["covered_days"])
                metric["mean_forecast_fraction_of_calendar_period"] = mean(
                    row["covered_days"] / row["period_days"]
                    for row in selected if row["period_days"])
        for horizon, steps in details["confidence_by_step"].items():
            for step, metric in steps.items():
                opportunities = output_counts_by_step[(product, horizon, int(step))]
                selected = [row for row in sample_groups[(product, horizon)]
                            if int(row["forecast_step"]) == int(step)]
                metric["forecast_opportunities"] = opportunities
                metric["observed_outcome_coverage"] = (
                    len(selected) / opportunities if opportunities else 0.0)

    output.parent.mkdir(parents=True, exist_ok=True)
    columns = sorted({key for row in scored_rows for key in row})
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(scored_rows)
    confidence_metrics = [metric for product in result.values()
                          for metric in product["confidence_by_horizon"].values()]
    confidence_metrics.extend(metric for product in result.values()
                              for horizon in product["confidence_by_step"].values()
                              for metric in horizon.values())
    report = {
        "candidate_model": bundle.name,
        "validation_window": metadata.get("split", {}).get("validation"),
        "ensemble_calibration": calibration,
        "heldout_target_window": {"start": target_start.isoformat(),
                                  "end": target_end.isoformat()},
        "origin_stride_days": stride_days,
        "origins": [origin.date().isoformat() for origin in origins],
        "source_snapshot": str(snapshot),
        "source_snapshot_sha256": _sha256(snapshot),
        "model_metadata_sha256": _sha256(bundle / "metadata.json"),
        "validation_forecasts_sha256": _sha256(bundle / "validation_forecasts.csv"),
        "forecast_paths": len(paths),
        "saved_calibration_rows": len(heldout),
        "saved_prediction_parity": {
            "matched_rows": len(parity),
            "within_half_cent": sum(value < 0.0051 for value in parity),
            "mean_abs_difference_php": mean(parity) if parity else None,
            "max_abs_difference_php": max(parity) if parity else None,
            "rows_over_half_cent": sum(value >= 0.0051 for value in parity),
        },
        "replay_fidelity_gate": {
            "passed": replay_fidelity_pass,
            "maximum_allowed_point_difference_php": REPLAY_PARITY_TOLERANCE_PHP,
            "numeric_confidence_scores_permitted": replay_fidelity_pass,
        },
        "scored_rows": {horizon: sum(row["horizon"] == horizon for row in scored_rows)
                        for horizon in ("daily", "weekly", "monthly")},
        "unscored_no_actual": dict(missing_actual),
        "open_periods_past_calibration_end": dict(open_periods),
        "confidence_evidence_status": dict(Counter(
            metric["evidence_status"] for metric in confidence_metrics)),
        "numeric_confidence_metrics": sum(
            isinstance(metric.get("confidence_score"), (int, float))
            for metric in confidence_metrics),
        "minimum_evidence": {"samples": MIN_SAMPLES, "distinct_origins": MIN_ORIGINS},
        "product_confidence": result,
        "interpretation": (
            "Offline diagnostic only; not written to the candidate bundle or API. "
            "Weekly/monthly prices use the publisher's full-path aggregation, while "
            "outcomes use only saved observed validation labels through the sealed "
            "calibration end. Coverage ratios are reported alongside scores."),
    }
    report_path = output.with_suffix(".json")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stride-days", type=int, default=7)
    args = parser.parse_args()
    report = replay(args.bundle, args.snapshot, args.output, args.stride_days)
    print(json.dumps({key: report[key] for key in (
        "candidate_model", "origins", "saved_prediction_parity", "scored_rows",
        "confidence_evidence_status", "numeric_confidence_metrics")}, indent=2))


if __name__ == "__main__":
    main()
