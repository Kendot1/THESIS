"""Compare the scaled peer correction with the active bundle at exact origins.

Both methods use a shared, target-truncated source snapshot. The saved active
validation file is opened only for point forecasts at two parity origins.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from data.preprocessor import DataPreprocessor
from evaluation import dense_active_interval_replay as active_replay
from features.builder import FeatureBuilder


ROOT = Path(__file__).resolve().parents[2]
RUN_ID = "20261001T025925Z_0661960a"
ACTIVE_BUNDLE = ROOT / "model_trainer" / "artifacts_v2" / "runs" / RUN_ID
ACTIVE_MANIFEST = ROOT / "model_trainer" / "artifacts_v2" / "manifest.json"
ACTIVE_SNAPSHOT = ROOT / "audits" / "accuracy_goal_20261011" / "supabase_food_prices_through_20261005.json"
EXPECTED_ACTIVE_SNAPSHOT_SHA256 = "1d61cb78c839efb54b677440d3b94daa8d82e339f5a7bed0d2b05a761f8dfba4"
ACTIVE_VALIDATION_FORECASTS = ACTIVE_BUNDLE / "validation_forecasts.csv"
VALIDATION_PARITY_ORIGINS = (pd.Timestamp("2024-08-26"), pd.Timestamp("2025-07-22"))
DIRECT_VALIDATION = ROOT / "audits" / "foodcast_accuracy_20261017" / "relative5_test_confirmation_v2" / "daily" / "validation_predictions.csv"
CANDIDATE_DIR = ROOT / "audits" / "foodcast_accuracy_20261018" / "peer_momentum_hierarchical_scaled_v1"
CANDIDATE_REPORT = CANDIDATE_DIR / "report.json"
CANDIDATE_PREDICTIONS = CANDIDATE_DIR / "paired_predictions.csv"
DEFAULT_OUTPUT = ROOT / "audits" / "foodcast_accuracy_20261018" / "peer_momentum_active_paired_v2"
HOLDOUT_START = pd.Timestamp("2026-10-06")
KEYS = ["series", "forecast_origin", "target_date", "lead"]
MODELS = ("active_ensemble", "direct_lgbm", "scaled_peer_correction", "persistence")
PRIORITY = ("chili||labuyo", "lettuce||romaine", "lettuce||green ice",
            "lettuce||iceberg", "bell pepper||red")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_target_rows(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["forecast_origin"] = pd.to_datetime(result.forecast_origin, errors="coerce").dt.normalize()
    result["target_date"] = pd.to_datetime(result.target_date, errors="coerce").dt.normalize()
    result["lead"] = pd.to_numeric(result.lead, errors="coerce")
    if result[KEYS].isna().any().any() or result.duplicated(KEYS).any():
        raise ValueError("Candidate has missing or duplicate exact forecast keys")
    if not result.lead.between(1, 14).all():
        raise ValueError("Candidate contains a lead outside the 14-day horizon")
    expected = result.forecast_origin + pd.to_timedelta(result.lead, unit="D")
    if not result.target_date.eq(expected).all():
        raise ValueError("Candidate target dates do not equal origin plus lead")
    if result.target_date.ge(HOLDOUT_START).any():
        raise ValueError("Candidate rows overlap the sealed prospective holdout")
    return result


def pair_candidate_to_active(candidate: pd.DataFrame, active: pd.DataFrame) -> pd.DataFrame:
    """Join full active point paths; use candidate labels for a shared sample."""
    candidate = validate_target_rows(candidate)
    active = active.copy()
    active["forecast_origin"] = pd.to_datetime(active.origin, errors="coerce").dt.normalize()
    active["target_date"] = pd.to_datetime(active.date, errors="coerce").dt.normalize()
    active["lead"] = pd.to_numeric(active.horizon, errors="coerce")
    if active[KEYS].isna().any().any() or active.duplicated(KEYS).any():
        raise ValueError("Active replay has missing or duplicate exact forecast keys")
    if active.target_date.ge(HOLDOUT_START).any():
        raise ValueError("Active replay rows overlap the sealed prospective holdout")
    if "ensemble_path" not in active:
        raise ValueError("Active replay is missing ensemble point forecasts")
    paired = candidate.merge(
        active[KEYS + ["ensemble_path"]], on=KEYS, how="left",
        indicator=True, validate="one_to_one",
    )
    if not paired._merge.eq("both").all():
        missing = int(paired._merge.ne("both").sum())
        raise ValueError(f"Active replay is missing {missing} candidate target keys")
    paired["actual"] = pd.to_numeric(paired.actual, errors="coerce")
    paired["active_ensemble"] = pd.to_numeric(paired.ensemble_path, errors="coerce")
    paired["direct_lgbm"] = pd.to_numeric(paired.candidate_shared, errors="coerce")
    paired["scaled_peer_correction"] = pd.to_numeric(paired.peer_corrected, errors="coerce")
    paired["persistence"] = pd.to_numeric(paired.persistence, errors="coerce")
    predictions = paired[list(KEYS) + ["actual", *MODELS, "product_category"]].copy()
    numeric = predictions[["actual", *MODELS]].to_numpy(float)
    if not np.isfinite(numeric).all() or predictions.actual.lt(0).any():
        raise ValueError("Paired predictions or actuals are invalid")
    return predictions.sort_values(KEYS).reset_index(drop=True)


def active_pair_coverage(candidate: pd.DataFrame, active: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Return exact common forecast keys and explicitly account for unsupported paths."""
    candidate = validate_target_rows(candidate)
    active = active.copy()
    active["forecast_origin"] = pd.to_datetime(active.origin, errors="coerce").dt.normalize()
    active["target_date"] = pd.to_datetime(active.date, errors="coerce").dt.normalize()
    active["lead"] = pd.to_numeric(active.horizon, errors="coerce")
    if active[KEYS].isna().any().any() or active.duplicated(KEYS).any():
        raise ValueError("Active replay has missing or duplicate exact forecast keys")
    if active.target_date.ge(HOLDOUT_START).any():
        raise ValueError("Active replay rows overlap the sealed prospective holdout")
    key_check = candidate[KEYS].merge(active[KEYS], on=KEYS, how="left", indicator=True,
                                      validate="one_to_one")
    missing = key_check.loc[key_check._merge.eq("left_only"), KEYS]
    common_keys = key_check.loc[key_check._merge.eq("both"), KEYS]
    common_candidate = candidate.merge(common_keys, on=KEYS, how="inner", validate="one_to_one")
    missing_by_series = missing.groupby("series", sort=True).size()
    return common_candidate, {
        "candidate_rows": int(len(candidate)),
        "active_forecasts_available": int(len(common_candidate)),
        "candidate_rows_without_active_forecast": int(len(missing)),
        "coverage_pct": float(len(common_candidate) / len(candidate) * 100.0) if len(candidate) else None,
        "series_without_active_forecast": {
            str(series): int(count) for series, count in missing_by_series.items()
        },
        "complete": bool(missing.empty),
    }


def compare_validation_points(replayed: pd.DataFrame, saved: pd.DataFrame) -> dict:
    """Measure source-vintage replay drift without loading saved actuals."""
    active_keys = ["series", "origin", "date", "horizon"]
    replayed = replayed.copy()
    saved = saved.copy()
    replayed["origin"] = pd.to_datetime(replayed.origin, errors="coerce").dt.normalize()
    replayed["date"] = pd.to_datetime(replayed.date, errors="coerce").dt.normalize()
    saved["origin"] = pd.to_datetime(saved.origin, errors="coerce").dt.normalize()
    saved["date"] = pd.to_datetime(saved.date, errors="coerce").dt.normalize()
    replayed["horizon"] = pd.to_numeric(replayed.horizon, errors="coerce")
    saved["horizon"] = pd.to_numeric(saved.horizon, errors="coerce")
    replayed = replayed.loc[
        replayed.origin.isin(VALIDATION_PARITY_ORIGINS)
        & pd.to_numeric(replayed.horizon, errors="coerce").between(1, 14),
                            active_keys + ["ensemble_path"]]
    saved = saved.loc[
        saved.origin.isin(VALIDATION_PARITY_ORIGINS)
        & pd.to_numeric(saved.horizon, errors="coerce").between(1, 14),
                      active_keys + ["ensemble"]]
    if replayed.duplicated(active_keys).any() or saved.duplicated(active_keys).any():
        raise ValueError("Duplicate validation parity forecast key")
    paired = replayed.merge(saved, on=active_keys, how="inner", validate="one_to_one")
    paired["difference_php"] = np.abs(
        pd.to_numeric(paired.ensemble_path, errors="coerce")
        - pd.to_numeric(paired.ensemble, errors="coerce"))
    differences = paired.difference_php.to_numpy(float)
    missing_saved = saved.merge(replayed[active_keys], on=active_keys, how="left", indicator=True)
    missing_replay = replayed.merge(saved[active_keys], on=active_keys, how="left", indicator=True)
    represented_origins = sorted(paired.origin.dropna().dt.strftime("%Y-%m-%d").unique())
    if len(paired) < 100 or len(represented_origins) != len(VALIDATION_PARITY_ORIGINS):
        raise ValueError("Insufficient active validation parity rows to assess replay drift")
    return {
        "origins": [value.strftime("%Y-%m-%d") for value in VALIDATION_PARITY_ORIGINS],
        "matched_rows": int(len(paired)),
        "replayed_rows": int(len(replayed)),
        "saved_rows": int(len(saved)),
        "matched_origins": represented_origins,
        "saved_keys_without_replay": int(missing_saved._merge.eq("left_only").sum()),
        "replay_keys_without_saved_reference": int(missing_replay._merge.eq("left_only").sum()),
        "max_abs_difference_php": float(differences.max()) if len(differences) else None,
        "mean_abs_difference_php": float(differences.mean()) if len(differences) else None,
        "rows_over_0_01_php": int(np.sum(differences > 0.01)),
        "tolerance_php": 0.01,
        "interpretation": "Source-vintage parity diagnostic; drift does not alter candidate scoring.",
    }


def _metric(rows: pd.DataFrame, prediction: str) -> dict:
    actual = rows.actual.to_numpy(float)
    predicted = rows[prediction].to_numpy(float)
    error = predicted - actual
    absolute = np.abs(error)
    positive = actual > 0
    return {
        "n": int(len(rows)),
        "mape_sample_count": int(positive.sum()),
        "zero_actual_count": int((actual == 0).sum()),
        "mae_php": float(absolute.mean()),
        "rmse_php": float(np.sqrt(np.mean(error ** 2))),
        "mape_pct": float(np.mean(absolute[positive] / actual[positive]) * 100.0)
        if positive.any() else None,
        "wape_pct": float(absolute.sum() / actual.sum() * 100.0)
        if actual.sum() > 0 else None,
        "bias_php": float(error.mean()),
        "within_5_php_pct": float(np.mean(absolute <= 5.0) * 100.0),
    }


def _macro(rows: pd.DataFrame, prediction: str) -> dict:
    product = [_metric(group, prediction) for _, group in rows.groupby("series", sort=True)]
    fields = ("mae_php", "rmse_php", "mape_pct", "wape_pct", "bias_php", "within_5_php_pct")
    return {field: float(np.mean([item[field] for item in product if item[field] is not None]))
            if any(item[field] is not None for item in product) else None
            for field in fields}


def score(rows: pd.DataFrame) -> dict:
    def scope(group: pd.DataFrame) -> dict:
        return {
            "n": int(len(group)),
            "series_count": int(group.series.nunique()),
            "pooled": {name: _metric(group, name) for name in MODELS},
            "macro_equal_series": {name: _macro(group, name) for name in MODELS},
        }
    by_series = {str(series): {name: _metric(group, name) for name in MODELS}
                 for series, group in rows.groupby("series", sort=True)}
    by_lead = {str(int(lead)): scope(group) for lead, group in rows.groupby("lead", sort=True)}
    active_error = by_series
    series_changes = {}
    for series, values in active_error.items():
        baseline = values["active_ensemble"]["mae_php"]
        candidate = values["scaled_peer_correction"]["mae_php"]
        series_changes[series] = (candidate - baseline) / baseline * 100.0 if baseline > 0 else None
    priority_regressions = [series for series, change in series_changes.items()
                            if any(token in series.casefold() for token in PRIORITY)
                            and change is not None and change > 10.0]
    result = {
        "all": scope(rows),
        "vegetables": scope(rows.loc[rows.product_category.eq("Vegetables")]),
        "by_series": by_series,
        "by_lead": by_lead,
        "series_mae_change_pct_candidate_vs_active": series_changes,
        "series_count_with_mae_regression": sum(value is not None and value > 0
                                                  for value in series_changes.values()),
        "series_count_with_mae_regression_over_10_pct": sum(value is not None and value > 10
                                                              for value in series_changes.values()),
        "priority_series_mae_regressions_over_10_pct": priority_regressions,
    }
    primary = ("mae_php", "rmse_php", "mape_pct")
    comparisons = []
    for name in ("all", "vegetables"):
        item = result[name]
        for aggregate in ("pooled", "macro_equal_series"):
            base = item[aggregate]["active_ensemble"]
            candidate = item[aggregate]["scaled_peer_correction"]
            comparisons.extend(candidate[key] < base[key] for key in primary)
        comparisons.append(item["pooled"]["scaled_peer_correction"]["within_5_php_pct"]
                          >= item["pooled"]["active_ensemble"]["within_5_php_pct"])
    result["active_comparison_gate_passed"] = bool(all(comparisons) and not priority_regressions)
    return result


def run_experiment(output_dir: Path = DEFAULT_OUTPUT) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing output directory: {output_dir}")
    active_manifest = json.loads(ACTIVE_MANIFEST.read_text(encoding="utf-8"))
    if active_manifest.get("active_run") != RUN_ID:
        raise ValueError(f"Active model pointer changed: {active_manifest.get('active_run')}")
    snapshot_hash = sha256(ACTIVE_SNAPSHOT)
    if snapshot_hash != EXPECTED_ACTIVE_SNAPSHOT_SHA256:
        raise ValueError("Shared source snapshot hash does not match audited provenance")
    candidate_report = json.loads(CANDIDATE_REPORT.read_text(encoding="utf-8"))
    if candidate_report.get("source_snapshot_sha256") != EXPECTED_ACTIVE_SNAPSHOT_SHA256:
        raise ValueError("Candidate and active replay source snapshots are not identical")
    selected = candidate_report.get("selected_hyperparameters", {})
    if (selected.get("selected_baseline_fallback") is not False
            or selected.get("shrinkage") != 0.1 or selected.get("scale") != 0.25):
        raise ValueError("Scaled candidate selection or parameters differ from the audited run")
    if candidate_report.get("historical_test_opened") is not False:
        raise ValueError("Candidate report indicates historical test data was opened")
    if sha256(DIRECT_VALIDATION) != candidate_report["source_validation"]["sha256"]:
        raise ValueError("Candidate source validation has changed since selection")
    candidate_frame = pd.read_csv(CANDIDATE_PREDICTIONS, parse_dates=[
        "forecast_origin", "target_start", "target_end",
    ])
    candidate_frame = candidate_frame.loc[
        candidate_frame.screen.eq("outer_validation_diagnostic")
    ].copy()
    candidate_frame = candidate_frame.rename(columns={"target_start": "target_date"})
    candidate_frame["lead"] = pd.to_numeric(candidate_frame.lead, errors="coerce")
    candidate_frame = validate_target_rows(candidate_frame)
    candidate_origins = sorted(candidate_frame.forecast_origin.unique())
    if len(candidate_origins) != 7:
        raise ValueError(f"Expected seven candidate gate origins, found {len(candidate_origins)}")
    if candidate_frame.target_date.ge(HOLDOUT_START).any():
        raise ValueError("Candidate evaluation touches the sealed holdout")

    source = json.loads(ACTIVE_SNAPSHOT.read_text(encoding="utf-8"))
    if isinstance(source, dict):
        source = source.get("rows", source.get("data"))
    raw = pd.DataFrame(source)
    if raw.empty:
        raise ValueError("Shared source snapshot is empty")
    raw["report_date"] = pd.to_datetime(raw.report_date, errors="coerce").dt.normalize()
    source_latest_date = raw.report_date.max()
    target_cutoff = candidate_frame.target_date.max()
    raw = raw.loc[raw.report_date.le(target_cutoff)].copy()
    if raw.empty or raw.report_date.max() > target_cutoff or target_cutoff >= HOLDOUT_START:
        raise ValueError("Target-truncated source snapshot is invalid or overlaps holdout")
    clean = DataPreprocessor().validate(raw)
    builder, engine = active_replay._load_engine(ACTIVE_BUNDLE)
    featured = builder.transform(clean)
    replay_origins = pd.DatetimeIndex(sorted(set(candidate_origins + list(VALIDATION_PARITY_ORIGINS))))
    original_parity_origins = active_replay.PARITY_ORIGINS
    try:
        active_replay.PARITY_ORIGINS = tuple(replay_origins)
        _, replay_paths = active_replay.replay_by_origin(clean, featured, engine, replay_origins)
    finally:
        active_replay.PARITY_ORIGINS = original_parity_origins

    saved_validation_points = pd.read_csv(
        ACTIVE_VALIDATION_FORECASTS,
        usecols=["series", "origin", "date", "horizon", "ensemble"],
        parse_dates=["origin", "date"],
    )
    parity_paths = replay_paths.loc[
        replay_paths.origin.isin(VALIDATION_PARITY_ORIGINS)
    ].copy()
    parity = compare_validation_points(parity_paths, saved_validation_points)
    candidate_paths = replay_paths.loc[
        pd.to_datetime(replay_paths.origin).dt.normalize().isin(candidate_origins)
    ].copy()
    common_candidate, coverage = active_pair_coverage(candidate_frame, candidate_paths)
    if common_candidate.empty:
        raise ValueError("Active bundle has no candidate target keys available for paired scoring")
    candidate_predictions = pair_candidate_to_active(common_candidate, candidate_paths)
    metrics = score(candidate_predictions)
    metrics["active_comparison_numeric_gate_passed"] = metrics["active_comparison_gate_passed"]
    metrics["active_comparison_gate_passed"] = bool(
        metrics["active_comparison_numeric_gate_passed"] and coverage["complete"]
    )

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir()
    candidate_hash = sha256(CANDIDATE_PREDICTIONS)
    report = {
        "experiment": "scaled_peer_correction_vs_common_input_active_ensemble",
        "active_run_id": RUN_ID,
        "active_manifest_sha256": sha256(ACTIVE_MANIFEST),
        "active_metadata_sha256": sha256(ACTIVE_BUNDLE / "metadata.json"),
        "active_source_snapshot": {
            "path": str(ACTIVE_SNAPSHOT.relative_to(ROOT)), "sha256": snapshot_hash,
            "shared_with_candidate": True,
            "source_latest_date": source_latest_date.date().isoformat(),
            "target_truncated_through": target_cutoff.date().isoformat(),
            "production_source_quality_exclusions_applied": True,
        },
        "candidate_report_sha256": sha256(CANDIDATE_REPORT),
        "candidate_predictions": {
            "path": str(CANDIDATE_PREDICTIONS.relative_to(ROOT)), "sha256": candidate_hash,
        },
        "candidate_source_validation_sha256": candidate_report["source_validation"]["sha256"],
        "candidate_parameters": selected,
        "candidate_origin_dates": [pd.Timestamp(value).date().isoformat()
                                   for value in candidate_origins],
        "candidate_targets": int(len(candidate_predictions)),
        "candidate_sample_coverage": coverage,
        "candidate_series": int(candidate_predictions.series.nunique()),
        "candidate_target_start": candidate_predictions.target_date.min().date().isoformat(),
        "candidate_target_end": candidate_predictions.target_date.max().date().isoformat(),
        "active_replay_parity": parity,
        "metrics": metrics,
        "historical_test_files_read": False,
        "historical_test_actuals_read": False,
        "sealed_prospective_holdout_read": False,
        "production_changed": False,
        "promotion_permitted": False,
        "independence_caveat": (
            "Candidate validation origins and active configuration have historical research/selection exposure; "
            "common-input exact-origin replay is a retrospective diagnostic, not prospective promotion evidence. "
            "Metrics use only exact keys with an active forecast; missing active paths are reported and fail the gate."
        ),
        "mape_policy": "positive actuals only for MAPE; zero actuals remain in PHP metrics",
        "macro_policy": "unweighted per-series macro; RMSE is calculated per series before averaging",
        "script_sha256": sha256(Path(__file__).resolve()),
    }
    candidate_predictions.to_csv(output_dir / "active_paired_predictions.csv", index=False)
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
        "parity": report["active_replay_parity"],
        "candidate_targets": report["candidate_targets"],
        "active_comparison_gate_passed": report["metrics"]["active_comparison_gate_passed"],
        "all_pooled": report["metrics"]["all"]["pooled"],
        "vegetable_pooled": report["metrics"]["vegetables"]["pooled"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
