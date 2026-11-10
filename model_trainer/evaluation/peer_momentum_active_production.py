"""Compare a historical candidate with the active model and serving fallback.

This reproduces the prediction writer's as-of preprocessing and per-series
history-shortfall persistence fallback without instantiating a database client
or publishing forecasts. Historical validation is diagnostic only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from config.settings import get_settings
from data.preprocessor import DataPreprocessor, SERIES_KEY
from evaluation import dense_active_interval_replay as active_replay
from evaluation.peer_momentum_active_paired import (
    ACTIVE_BUNDLE,
    ACTIVE_MANIFEST,
    ACTIVE_SNAPSHOT,
    CANDIDATE_DIR,
    CANDIDATE_PREDICTIONS,
    CANDIDATE_REPORT,
    DIRECT_VALIDATION,
    EXPECTED_ACTIVE_SNAPSHOT_SHA256,
    HOLDOUT_START,
    KEYS,
    PRIORITY,
    RUN_ID,
    VALIDATION_PARITY_ORIGINS,
    _macro,
    _metric,
    compare_validation_points,
    sha256,
    validate_target_rows,
)
from features.builder import FeatureBuilder
from pipeline.prediction_writer import (
    PredictionWriter,
)


ROOT = Path(__file__).resolve().parents[2]
MODEL_ONLY_DIR = ROOT / "audits" / "foodcast_accuracy_20261018" / "peer_momentum_active_paired_v2"
MODEL_ONLY_PREDICTIONS = MODEL_ONLY_DIR / "active_paired_predictions.csv"
MODEL_ONLY_REPORT = MODEL_ONLY_DIR / "report.json"
DEFAULT_OUTPUT = ROOT / "audits" / "foodcast_accuracy_20261018" / "peer_momentum_active_production_v1"
MODEL_NAMES = ("active_production", "direct_lgbm", "scaled_peer_correction", "persistence")
DAILY_EVALUATION_DAYS = 7


def point_path_rows(series: str, origin: pd.Timestamp, dates, points,
                    source: str) -> pd.DataFrame:
    """Validate and encode the active seven-day daily evaluation path."""
    origin = pd.Timestamp(origin).normalize()
    dates = pd.to_datetime(dates, errors="coerce").normalize()
    values = np.asarray(points, dtype=float).reshape(-1)
    expected = pd.date_range(origin + pd.Timedelta(days=1), periods=DAILY_EVALUATION_DAYS, freq="D")
    if (len(dates) != DAILY_EVALUATION_DAYS
            or len(values) != DAILY_EVALUATION_DAYS
            or not dates.equals(expected)
            or not np.isfinite(values).all()):
        raise ValueError("Daily evaluation path must contain 7 finite consecutive daily targets")
    return pd.DataFrame({
        "series": str(series),
        "origin": origin,
        "date": dates,
        "horizon": np.arange(1, DAILY_EVALUATION_DAYS + 1, dtype=int),
        "ensemble_path": values,
        "forecast_source": str(source),
    })


def persistence_fallback_path(series: str, origin: pd.Timestamp,
                              history: pd.DataFrame) -> pd.DataFrame:
    """Use the same flat last-price fallback as PredictionWriter, without confidence."""
    dates, points = PredictionWriter._persistence_fallback(
        None, history, DAILY_EVALUATION_DAYS)
    return point_path_rows(series, origin, dates, points, "persistence_fallback")


def _load_candidate() -> tuple[pd.DataFrame, list[pd.Timestamp], dict]:
    report = json.loads(CANDIDATE_REPORT.read_text(encoding="utf-8"))
    selected = report.get("selected_hyperparameters", {})
    if (report.get("source_snapshot_sha256") != EXPECTED_ACTIVE_SNAPSHOT_SHA256
            or report.get("historical_test_opened") is not False
            or selected.get("selected_baseline_fallback") is not False
            or selected.get("shrinkage") != 0.1
            or selected.get("scale") != 0.25
            or sha256(DIRECT_VALIDATION) != report["source_validation"]["sha256"]):
        raise ValueError("Candidate provenance, test-data guard, or selected parameters changed")
    frame = pd.read_csv(CANDIDATE_PREDICTIONS, parse_dates=[
        "forecast_origin", "target_start", "target_end",
    ])
    frame = frame.loc[frame.screen.eq("outer_validation_diagnostic")].copy()
    frame = frame.rename(columns={"target_start": "target_date"})
    frame["lead"] = pd.to_numeric(frame.lead, errors="coerce")
    frame = validate_target_rows(frame)
    origins = sorted(pd.Timestamp(value).normalize() for value in frame.forecast_origin.unique())
    if len(origins) != 7:
        raise ValueError(f"Expected seven candidate outer origins, found {len(origins)}")
    return frame, origins, report


def _asof_daily_inputs(clean: pd.DataFrame, origin: pd.Timestamp,
                       max_fill_days: int) -> pd.DataFrame:
    available = clean.loc[pd.to_datetime(clean.report_date).le(origin)].copy()
    if available.empty:
        raise ValueError(f"No source history is available by forecast origin {origin.date()}")
    return PredictionWriter._extend_inputs_to_origin(available, origin, max_fill_days)


def replay_production_origins(clean: pd.DataFrame, origins: list[pd.Timestamp],
                              builder, engine) -> tuple[pd.DataFrame, dict]:
    """Mirror PredictionWriter's model batch and history-shortfall fallback."""
    max_fill_days = int(get_settings().max_fill_days)
    path_frames = []
    origin_audit = {}
    for origin in sorted(set(pd.Timestamp(value).normalize() for value in origins)):
        daily = _asof_daily_inputs(clean, origin, max_fill_days)
        category_daily = FeatureBuilder.category_return_history(daily)
        category_daily["category_return"] = category_daily.category_return.fillna(0.0)
        market_groups = {
            str(category): group for category, group
            in category_daily.groupby("product_category", sort=False)
        }
        product_daily = FeatureBuilder.product_return_history(daily)
        product_daily["product_return"] = product_daily.product_return.fillna(0.0)
        product_groups = {
            tuple(map(str, key)): group for key, group
            in product_daily.groupby(SERIES_KEY[:3], sort=False)
        }

        prepared, prepared_meta = [], []
        fallbacks, unavailable = [], []
        for key, series in daily.groupby(SERIES_KEY, sort=True):
            series_name = "||".join(map(str, key))
            if series.empty or not np.isfinite(float(series.price_index.iloc[-1])):
                last_observed = series.loc[series.is_observed, "report_date"]
                unavailable.append({
                    "series": series_name,
                    "reason": "no observed price within max_fill_days of forecast origin",
                    "last_observed_date": (pd.Timestamp(last_observed.max()).date().isoformat()
                                           if not last_observed.empty else None),
                })
                continue

            category = str(key[0])
            market = market_groups.get(category)
            market_history = ([] if market is None else market.loc[
                pd.to_datetime(market.report_date).le(origin),
                "category_return"].to_numpy(dtype=float).tolist())
            product_market = product_groups.get(tuple(map(str, key[:3])))
            product_history = ([] if product_market is None else product_market.loc[
                pd.to_datetime(product_market.report_date).le(origin),
                "product_return"].to_numpy(dtype=float).tolist())
            try:
                item = engine._prepare(series, None, market_history, product_history)
                prepared.append(item)
                prepared_meta.append((series_name, series))
            except (ValueError, FileNotFoundError) as exc:
                if not PredictionWriter._is_history_shortfall(exc):
                    raise
                fallback = persistence_fallback_path(series_name, origin, series)
                path_frames.append(fallback)
                fallbacks.append({"series": series_name, "reason": str(exc)})

        if prepared:
            forecasts = engine.forecast_many(prepared, DAILY_EVALUATION_DAYS)
            if len(forecasts) != len(prepared_meta):
                raise ValueError("Production model replay lost prepared series")
            for (series_name, _), forecast in zip(prepared_meta, forecasts):
                path_frames.append(point_path_rows(
                    series_name, origin, forecast.dates, forecast.point, "active_ensemble"))

        origin_audit[origin.date().isoformat()] = {
            "model_series": int(len(prepared_meta)),
            "persistence_fallback_series": int(len(fallbacks)),
            "unavailable_series": int(len(unavailable)),
            "fallback_details": fallbacks,
            "unavailable_details": unavailable,
        }
        print(f"Replayed serving path {origin.date()}: model={len(prepared_meta)}, "
              f"fallback={len(fallbacks)}, unavailable={len(unavailable)}", flush=True)
    if not path_frames:
        raise ValueError("Production-path replay generated no forecasts")
    paths = pd.concat(path_frames, ignore_index=True)
    if paths.duplicated(["series", "origin", "date", "horizon"]).any():
        raise ValueError("Production-path replay generated duplicate point keys")
    return paths, origin_audit


def _rename_active_model_keys(value):
    if isinstance(value, dict):
        return {
            ("active_production" if key == "active_ensemble" else key):
            _rename_active_model_keys(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_rename_active_model_keys(item) for item in value]
    return value


def score_production(rows: pd.DataFrame) -> dict:
    """Use the established scorer while labeling ensemble/fallback as production."""
    from evaluation.peer_momentum_active_paired import score

    scoring_rows = rows.copy()
    scoring_rows["active_ensemble"] = scoring_rows.active_production
    return _rename_active_model_keys(score(scoring_rows))


def run_experiment(output_dir: Path = DEFAULT_OUTPUT) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing output directory: {output_dir}")
    active_manifest = json.loads(ACTIVE_MANIFEST.read_text(encoding="utf-8"))
    if active_manifest.get("active_run") != RUN_ID:
        raise ValueError(f"Active model pointer changed: {active_manifest.get('active_run')}")
    snapshot_hash = sha256(ACTIVE_SNAPSHOT)
    if snapshot_hash != EXPECTED_ACTIVE_SNAPSHOT_SHA256:
        raise ValueError("Shared input source snapshot hash changed")

    candidate, candidate_origins, candidate_report = _load_candidate()
    target_cutoff = candidate.target_date.max().normalize()
    parity_origins = list(VALIDATION_PARITY_ORIGINS)
    replay_origins = sorted(set(candidate_origins + parity_origins))

    raw_payload = json.loads(ACTIVE_SNAPSHOT.read_text(encoding="utf-8"))
    if isinstance(raw_payload, dict):
        raw_payload = raw_payload.get("rows", raw_payload.get("data"))
    raw = pd.DataFrame(raw_payload)
    raw["report_date"] = pd.to_datetime(raw.report_date, errors="coerce").dt.normalize()
    source_latest = raw.report_date.max()
    raw = raw.loc[raw.report_date.le(target_cutoff)].copy()
    if raw.empty or raw.report_date.max() > target_cutoff or target_cutoff >= HOLDOUT_START:
        raise ValueError("Source must be non-empty, target-truncated, and pre-holdout")
    clean = DataPreprocessor().validate(raw)
    builder, engine = active_replay._load_engine(ACTIVE_BUNDLE)
    production_paths, origin_audit = replay_production_origins(
        clean, replay_origins, builder, engine)

    parity_paths = production_paths.loc[
        production_paths.origin.isin(parity_origins),
        ["series", "origin", "date", "horizon", "ensemble_path"],
    ].copy()
    saved_validation_points = pd.read_csv(
        ACTIVE_BUNDLE / "validation_forecasts.csv",
        usecols=["series", "origin", "date", "horizon", "ensemble"],
        parse_dates=["origin", "date"],
    )
    parity = compare_validation_points(parity_paths, saved_validation_points)

    candidate_paths = production_paths.loc[
        production_paths.origin.isin(candidate_origins)
    ].copy()
    active = candidate_paths.copy()
    active["forecast_origin"] = active.origin
    active["target_date"] = active.date
    active["lead"] = active.horizon
    candidate["forecast_origin"] = pd.to_datetime(candidate.forecast_origin).dt.normalize()
    candidate["target_date"] = pd.to_datetime(candidate.target_date).dt.normalize()
    candidate["lead"] = pd.to_numeric(candidate.lead, errors="coerce")
    active["forecast_origin"] = pd.to_datetime(active.forecast_origin).dt.normalize()
    active["target_date"] = pd.to_datetime(active.target_date).dt.normalize()
    active["lead"] = pd.to_numeric(active.lead, errors="coerce")
    coverage = candidate[KEYS].merge(
        active[KEYS], on=KEYS, how="left", indicator=True, validate="one_to_one")
    missing_keys = coverage.loc[coverage._merge.eq("left_only"), KEYS]
    paired_keys = coverage.loc[coverage._merge.eq("both"), KEYS]
    candidate_common = candidate.merge(paired_keys, on=KEYS, how="inner", validate="one_to_one")
    coverage_report = {
        "candidate_rows": int(len(candidate)),
        "active_production_forecasts_available": int(len(paired_keys)),
        "candidate_rows_without_active_production_forecast": int(len(missing_keys)),
        "coverage_pct": float(len(paired_keys) / len(candidate) * 100.0),
        "complete": bool(missing_keys.empty),
        "uncovered_by_series": {str(key): int(value)
                                 for key, value in missing_keys.groupby("series").size().items()},
    }
    if candidate_common.empty:
        raise ValueError("Production-path replay has no exact candidate target keys")

    active_for_pairing = active.rename(columns={"forecast_source": "active_forecast_source"})
    # Reuse the shared key/metric code; this column now represents exactly the
    # serving behavior (active ensemble where prepared, writer fallback otherwise).
    active_for_pairing["ensemble_path"] = pd.to_numeric(
        active_for_pairing.ensemble_path, errors="coerce")
    paired = candidate_common.merge(
        active_for_pairing[KEYS + ["ensemble_path", "active_forecast_source"]],
        on=KEYS, how="left", validate="one_to_one")
    paired["actual"] = pd.to_numeric(paired.actual, errors="coerce")
    paired["active_production"] = pd.to_numeric(paired.ensemble_path, errors="coerce")
    paired["direct_lgbm"] = pd.to_numeric(paired.candidate_shared, errors="coerce")
    paired["scaled_peer_correction"] = pd.to_numeric(paired.peer_corrected, errors="coerce")
    paired["persistence"] = pd.to_numeric(paired.persistence, errors="coerce")
    numeric = paired[["actual", *MODEL_NAMES]].to_numpy(dtype=float)
    if not np.isfinite(numeric).all() or paired.actual.lt(0).any():
        raise ValueError("Production-paired predictions or labels are invalid")

    metrics = score_production(paired)
    metrics["active_comparison_numeric_gate_passed"] = metrics["active_comparison_gate_passed"]
    metrics["active_comparison_gate_passed"] = bool(
        metrics["active_comparison_numeric_gate_passed"] and coverage_report["complete"])
    source_metrics = {
        str(source): {
            "n": int(len(group)),
            "active_production": _metric(group, "active_production"),
            "scaled_peer_correction": _metric(group, "scaled_peer_correction"),
            "persistence": _metric(group, "persistence"),
        }
        for source, group in paired.groupby("active_forecast_source", sort=True)
    }
    metrics["active_production_by_forecast_source"] = source_metrics

    output = paired[[*KEYS, "actual", *MODEL_NAMES, "active_forecast_source",
                     "product_category"]].copy().sort_values(KEYS).reset_index(drop=True)
    report = {
        "experiment": "scaled_peer_correction_vs_active_production_serving_path",
        "active_run_id": RUN_ID,
        "active_manifest_sha256": sha256(ACTIVE_MANIFEST),
        "active_metadata_sha256": sha256(ACTIVE_BUNDLE / "metadata.json"),
        "active_source_snapshot": {
            "path": str(ACTIVE_SNAPSHOT.relative_to(ROOT)),
            "sha256": snapshot_hash,
            "shared_with_candidate": True,
            "source_latest_date": source_latest.date().isoformat(),
            "target_truncated_through": target_cutoff.date().isoformat(),
            "production_preprocessing_and_asof_fill": True,
        },
        "candidate_report_sha256": sha256(CANDIDATE_REPORT),
        "candidate_predictions_sha256": sha256(CANDIDATE_PREDICTIONS),
        "candidate_source_validation_sha256": candidate_report["source_validation"]["sha256"],
        "candidate_parameters": candidate_report["selected_hyperparameters"],
        "candidate_origin_dates": [date.date().isoformat() for date in candidate_origins],
        "candidate_target_start": candidate.target_date.min().date().isoformat(),
        "candidate_target_end": target_cutoff.date().isoformat(),
        "production_replay_origin_audit": origin_audit,
        "candidate_sample_coverage": coverage_report,
        "validation_point_parity": parity,
        "metrics": metrics,
        "forecast_source_counts_on_scored_rows": {
            str(key): int(value) for key, value
            in paired.active_forecast_source.value_counts().items()
        },
        "historical_test_files_read": False,
        "historical_test_actuals_read": False,
        "sealed_prospective_holdout_read": False,
        "production_changed": False,
        "promotion_permitted": False,
        "independence_caveat": (
            "Candidate outer-validation origins and candidate correction selection have prior research exposure. "
            "This is a production-path historical diagnostic, not independent promotion evidence."
        ),
        "mape_policy": "positive actuals only for MAPE; zero actuals remain in PHP-unit metrics",
        "macro_policy": "unweighted per-series macro; RMSE is calculated per series before averaging",
        "replay_dependencies": {
            str(path.relative_to(ROOT)): sha256(path) for path in (
                Path(__file__).resolve(),
                Path(__file__).with_name("peer_momentum_active_paired.py"),
                Path(__file__).parents[1] / "pipeline" / "prediction_writer.py",
                Path(__file__).parents[1] / "models" / "forecast_engine.py",
                Path(__file__).parents[1] / "data" / "preprocessor.py",
            )
        },
    }
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir()
    output.to_csv(output_dir / "active_production_paired_predictions.csv", index=False)
    (output_dir / "report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    report = run_experiment(args.output_dir)
    print(json.dumps({
        "output_dir": str(args.output_dir),
        "validation_point_parity": report["validation_point_parity"],
        "coverage": report["candidate_sample_coverage"],
        "forecast_sources": report["forecast_source_counts_on_scored_rows"],
        "active_comparison_gate_passed": report["metrics"]["active_comparison_gate_passed"],
        "all_pooled": report["metrics"]["all"]["pooled"],
        "vegetable_pooled": report["metrics"]["vegetables"]["pooled"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
