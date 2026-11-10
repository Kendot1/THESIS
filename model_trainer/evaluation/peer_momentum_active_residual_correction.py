"""Nested screen for peer-momentum correction of active production residuals.

Historical-validation diagnostic only. The active engine and writer fallback
are replayed without a database client; no model is promoted or published.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from data.preprocessor import DataPreprocessor
from evaluation import dense_active_interval_replay as active_replay
from evaluation.peer_momentum_active_production import (
    ACTIVE_SNAPSHOT,
    replay_production_origins,
)
from evaluation.peer_momentum_active_paired import (
    ACTIVE_BUNDLE,
    ACTIVE_MANIFEST,
    CANDIDATE_PREDICTIONS,
    CANDIDATE_REPORT,
    EXPECTED_ACTIVE_SNAPSHOT_SHA256,
    HOLDOUT_START,
    KEYS,
    PRIORITY,
    RUN_ID,
    _macro,
    _metric,
    sha256,
    validate_target_rows,
)
from evaluation.peer_momentum_diagnostic import evaluate as peer_diagnostic
from evaluation.peer_momentum_hierarchical_correction import (
    SOURCE_DIR,
    add_peer_categories,
    fit_hierarchical,
    load_validation,
    split_origins,
)
from evaluation.peer_momentum_scaled_correction import SCALE_GRID
from features.builder import FeatureBuilder


ROOT = Path(__file__).resolve().parents[2]
VALIDATION_PATH = SOURCE_DIR / "daily" / "validation_predictions.csv"
ACTIVE_PRODUCTION_DIR = ROOT / "audits" / "foodcast_accuracy_20261018" / "peer_momentum_active_production_v1"
ACTIVE_PRODUCTION_PREDICTIONS = ACTIVE_PRODUCTION_DIR / "active_production_paired_predictions.csv"
ACTIVE_PRODUCTION_REPORT = ACTIVE_PRODUCTION_DIR / "report.json"
PLAN_PATH = ROOT / "audits" / "foodcast_accuracy_20261018" / "active_residual_peer_correction_plan.md"
DEFAULT_OUTPUT = ROOT / "audits" / "foodcast_accuracy_20261018" / "active_residual_peer_correction_v1"
LAMBDA_GRID = (0.0, 1e-5, 3e-5, 1e-4, 3e-4, 1e-3, 3e-3, 1e-2, 3e-2, 1e-1)
PRIMARY = ("mae_php", "rmse_php", "mape_pct")
SCOPES = ("all", "vegetables")
MODEL_COLUMNS = ("active_production", "direct_lgbm", "peer_corrected", "persistence")


def apply_active_correction(rows: pd.DataFrame, peer_features: pd.DataFrame,
                            coefficients: dict, scale: float) -> pd.DataFrame:
    """Apply a fitted origin-known peer correction to the active point path."""
    if not 0.0 <= float(scale) <= 1.0:
        raise ValueError("Correction scale must be in [0, 1]")
    result = rows.copy()
    feature_rows = peer_features.loc[peer_features.peer_count.ge(5)].copy()
    feature_keys = ["series", "forecast_origin", "band"]
    if feature_rows.duplicated(feature_keys).any():
        raise ValueError("Peer features contain duplicate series/origin/band keys")
    feature_map = {
        (row.series, pd.Timestamp(row.forecast_origin), row.band): float(row.peer_median_return3)
        for row in feature_rows.itertuples()
        if pd.notna(row.peer_median_return3) and np.isfinite(float(row.peer_median_return3))
    }
    category_by_series = result.groupby("series").product_category.first().to_dict()
    correction = []
    supported = []
    for row in result.itertuples():
        band = "days_1_7" if int(row.lead) <= 7 else "days_8_14"
        x = feature_map.get((row.series, pd.Timestamp(row.forecast_origin), band))
        eligible = category_by_series[row.series] == "Vegetables" and x is not None
        if eligible:
            record = coefficients[band]["series"].get(row.series)
            beta = record["beta"] if record else coefficients[band]["global_beta"]
            correction.append(float(row.anchor) * float(beta) * float(x))
        else:
            correction.append(0.0)
        supported.append(bool(eligible))
    result["peer_correction_php"] = correction
    result["peer_feature_supported"] = supported
    result["correction_scale"] = float(scale)
    result["peer_corrected"] = np.maximum(
        0.01, result.active_production.to_numpy(float) + float(scale) * np.asarray(correction))
    return result


def active_residual_peer_rows(peer_features: pd.DataFrame,
                              production_rows: pd.DataFrame) -> pd.DataFrame:
    """Replace direct-LGBM residual targets with active-production residuals."""
    rows = production_rows.copy()
    rows["band"] = np.where(rows.lead.le(7), "days_1_7", "days_8_14")
    rows["active_relative_residual"] = (
        rows.actual.to_numpy(float) - rows.active_production.to_numpy(float)
    ) / rows.anchor.to_numpy(float)
    residuals = (rows.groupby(["series", "forecast_origin", "band"], sort=True)
                 .agg(mean_relative_residual=("active_relative_residual", "mean"),
                      active_rows=("actual", "size"))
                 .reset_index())
    fit_rows = peer_features.drop(
        columns=["mean_relative_residual", "mae_php"], errors="ignore"
    ).merge(residuals, on=["series", "forecast_origin", "band"],
            how="inner", validate="one_to_one")
    return fit_rows


def _scope(rows: pd.DataFrame) -> dict:
    return {
        "n": int(len(rows)),
        "series_count": int(rows.series.nunique()),
        "pooled": {name: _metric(rows, name) for name in MODEL_COLUMNS},
        "macro_equal_series": {name: _macro(rows, name) for name in MODEL_COLUMNS},
    }


def _metrics(rows: pd.DataFrame) -> dict:
    bands = {}
    for name, mask in (("days_1_7", rows.lead.between(1, 7)),
                       ("days_8_14", rows.lead.between(8, 14))):
        block = rows.loc[mask]
        if not block.empty:
            bands[name] = _scope(block)
    result = {
        "all": _scope(rows),
        "vegetables": _scope(rows.loc[rows.product_category.eq("Vegetables")]),
        "by_lead_band": bands,
        "by_lead": {str(int(lead)): _scope(group)
                    for lead, group in rows.groupby("lead", sort=True)},
        "by_series": {str(series): {name: _metric(group, name) for name in MODEL_COLUMNS}
                      for series, group in rows.groupby("series", sort=True)},
    }
    changes = {}
    for series, values in result["by_series"].items():
        baseline = values["active_production"]["mae_php"]
        candidate = values["peer_corrected"]["mae_php"]
        changes[series] = ((baseline - candidate) / baseline * 100.0
                           if baseline > 0 else None)
    result["series_mae_error_reduction_pct_candidate_vs_active"] = changes
    result["series_count_with_mae_regression"] = sum(
        value is not None and value < 0 for value in changes.values())
    result["series_count_with_mae_regression_over_10_pct"] = sum(
        value is not None and value < -10 for value in changes.values())
    result["priority_series_mae_regressions_over_10_pct"] = [
        series for series, value in changes.items()
        if any(token in series.casefold() for token in PRIORITY)
        and value is not None and value < -10
    ]
    return result


def gate(metrics: dict) -> dict:
    failures = []
    for scope in SCOPES:
        result = metrics[scope]
        for aggregate in ("pooled", "macro_equal_series"):
            base = result[aggregate]["active_production"]
            candidate = result[aggregate]["peer_corrected"]
            for metric in PRIMARY:
                if not candidate[metric] < base[metric]:
                    failures.append(f"{scope}.{aggregate}.{metric}")
        for aggregate in ("pooled", "macro_equal_series"):
            base = result[aggregate]["active_production"]["within_5_php_pct"]
            candidate = result[aggregate]["peer_corrected"]["within_5_php_pct"]
            if candidate < base:
                failures.append(f"{scope}.{aggregate}.within_5_php_pct")
    second_week = metrics["by_lead_band"]["days_8_14"]["pooled"]
    for metric in PRIMARY:
        base = second_week["active_production"][metric]
        candidate = second_week["peer_corrected"][metric]
        if candidate > base:
            failures.append(f"days_8_14.mean_{metric}")
    priority = metrics["priority_series_mae_regressions_over_10_pct"]
    if priority:
        failures.append("priority_product_mae_regression_over_10_pct")
    return {"passed": not failures, "failures": failures}


def _selected_candidate(candidates: list[dict]) -> dict:
    eligible = [item for item in candidates if item["gate"]["passed"]]
    if not eligible:
        return {"shrinkage": 0.0, "scale": 0.0,
                "selected_active_baseline_fallback": True,
                "selection_reason": "No tuning configuration passed all active-production gates."}
    winner = min(eligible, key=lambda item: (
        item["metrics"]["vegetables"]["macro_equal_series"]["peer_corrected"]["mae_php"],
        item["scale"], -item["shrinkage"],
    ))
    return {"shrinkage": float(winner["shrinkage"]),
            "scale": float(winner["scale"]),
            "selected_active_baseline_fallback": False,
            "selection_reason": "Best vegetable macro MAE among configurations passing all tuning gates."}


def _load_outer_validation(validation: pd.DataFrame, source_report: dict) -> pd.DataFrame:
    validation = validation.copy()
    if "target_date" not in validation:
        validation["target_date"] = pd.to_datetime(validation.target_start).dt.normalize()
    validation["forecast_origin"] = pd.to_datetime(validation.forecast_origin).dt.normalize()
    validation["target_date"] = pd.to_datetime(validation.target_date).dt.normalize()
    validation["lead"] = pd.to_numeric(validation.lead, errors="coerce")
    if source_report.get("active_run_id") != RUN_ID:
        raise ValueError("Saved outer active production replay points at a different model")
    outer_origins = pd.to_datetime(source_report["candidate_origin_dates"]).normalize()
    outer = pd.read_csv(ACTIVE_PRODUCTION_PREDICTIONS, parse_dates=[
        "forecast_origin", "target_date",
    ])
    outer = outer[[*KEYS, "active_production", "active_forecast_source"]]
    joined = validation.loc[
        validation.forecast_origin.isin(outer_origins)
    ].merge(outer, on=KEYS, how="left", indicator=True, validate="one_to_one")
    if not joined._merge.eq("both").all():
        raise ValueError("Outer active production rows do not exactly cover the candidate gate")
    return joined.drop(columns="_merge")


def run_experiment(output_dir: Path = DEFAULT_OUTPUT) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing output directory: {output_dir}")
    candidate_report = json.loads(CANDIDATE_REPORT.read_text(encoding="utf-8"))
    if (candidate_report.get("historical_test_opened") is not False
            or candidate_report.get("source_snapshot_sha256") != EXPECTED_ACTIVE_SNAPSHOT_SHA256
            or sha256(VALIDATION_PATH) != candidate_report["source_validation"]["sha256"]):
        raise ValueError("Validation source provenance or historical-test guard changed")
    active_report = json.loads(ACTIVE_PRODUCTION_REPORT.read_text(encoding="utf-8"))
    source_snapshot_hash = sha256(ACTIVE_SNAPSHOT)
    if (source_snapshot_hash != EXPECTED_ACTIVE_SNAPSHOT_SHA256
            or active_report.get("active_run_id") != RUN_ID
            or active_report.get("sealed_prospective_holdout_read") is not False):
        raise ValueError("Active production replay provenance changed")

    validation, validation_info = load_validation(VALIDATION_PATH)
    if validation_info["sha256"] != candidate_report["source_validation"]["sha256"]:
        raise ValueError("The nested validation screen differs from the candidate's frozen source")
    splits = split_origins(validation)
    _, peer_features = peer_diagnostic(validation)
    peer_features = add_peer_categories(validation, peer_features)
    peer_features["forecast_origin"] = pd.to_datetime(peer_features.forecast_origin).dt.normalize()

    origins_to_replay = splits["inner_fit"] + splits["shrinkage_tune"]
    raw_payload = json.loads(ACTIVE_SNAPSHOT.read_text(encoding="utf-8"))
    if isinstance(raw_payload, dict):
        raw_payload = raw_payload.get("rows", raw_payload.get("data"))
    raw = pd.DataFrame(raw_payload)
    raw["report_date"] = pd.to_datetime(raw.report_date, errors="coerce").dt.normalize()
    target_cutoff = validation.target_end.max().normalize()
    raw = raw.loc[raw.report_date.le(target_cutoff)].copy()
    if raw.empty or target_cutoff >= HOLDOUT_START:
        raise ValueError("Inputs must be non-empty and truncated before the sealed holdout")
    clean = DataPreprocessor().validate(raw)
    builder, engine = active_replay._load_engine(ACTIVE_BUNDLE)
    inner_paths, inner_origin_audit = replay_production_origins(
        clean, [pd.Timestamp(value) for value in origins_to_replay], builder, engine)

    inner_paths = inner_paths.rename(columns={
        "origin": "forecast_origin", "date": "target_date",
        "horizon": "lead", "ensemble_path": "active_production",
        "forecast_source": "active_forecast_source",
    })
    inner_paths["forecast_origin"] = pd.to_datetime(inner_paths.forecast_origin).dt.normalize()
    inner_paths["target_date"] = pd.to_datetime(inner_paths.target_date).dt.normalize()
    inner_paths["lead"] = pd.to_numeric(inner_paths.lead, errors="coerce")
    validation["target_date"] = pd.to_datetime(validation.target_start).dt.normalize()
    validation["forecast_origin"] = pd.to_datetime(validation.forecast_origin).dt.normalize()
    validation["lead"] = pd.to_numeric(validation.lead, errors="coerce")
    inner_validation = validation.loc[
        validation.forecast_origin.isin(origins_to_replay)
    ].copy()
    inner_join = inner_validation.merge(
        inner_paths[[*KEYS, "active_production", "active_forecast_source"]],
        on=KEYS, how="left", indicator=True, validate="one_to_one")
    inner_coverage = {
        "candidate_rows": int(len(inner_validation)),
        "active_rows_available": int(inner_join._merge.eq("both").sum()),
        "rows_unavailable": int(inner_join._merge.ne("both").sum()),
        "coverage_pct": float(inner_join._merge.eq("both").mean() * 100.0),
        "complete": bool(inner_join._merge.eq("both").all()),
    }
    inner_scored = inner_join.loc[inner_join._merge.eq("both")].drop(columns="_merge").copy()
    if inner_scored.empty:
        raise ValueError("No exact active-production rows available on fit/tune origins")

    active_peer_features = active_residual_peer_rows(peer_features, inner_scored)
    if active_peer_features.empty:
        raise ValueError("No origin-known peer rows with paired active residuals")
    tuning_rows = inner_scored.loc[
        inner_scored.forecast_origin.isin(splits["shrinkage_tune"])
    ].copy()
    tuning_rows["direct_lgbm"] = tuning_rows.candidate_shared
    fit_peer_rows = active_peer_features.loc[
        active_peer_features.forecast_origin.isin(splits["inner_fit"])
    ].copy()
    if tuning_rows.empty or fit_peer_rows.empty:
        raise ValueError("Chronological fit and tune partitions must both have active paired rows")

    tuning_candidates = []
    for shrinkage in LAMBDA_GRID:
        coefficients = fit_hierarchical(
            fit_peer_rows, splits["inner_fit"], float(shrinkage))
        for scale in SCALE_GRID:
            scored = apply_active_correction(
                tuning_rows, peer_features, coefficients, float(scale))
            metrics = _metrics(scored)
            compact = {
                scope: {
                    "n": metrics[scope]["n"],
                    "series_count": metrics[scope]["series_count"],
                    "pooled": metrics[scope]["pooled"],
                    "macro_equal_series": metrics[scope]["macro_equal_series"],
                }
                for scope in SCOPES
            }
            compact["by_lead_band"] = metrics["by_lead_band"]
            compact["series_count_with_mae_regression"] = metrics[
                "series_count_with_mae_regression"]
            compact["series_count_with_mae_regression_over_10_pct"] = metrics[
                "series_count_with_mae_regression_over_10_pct"]
            compact["priority_series_mae_regressions_over_10_pct"] = metrics[
                "priority_series_mae_regressions_over_10_pct"]
            tuning_candidates.append({
                "shrinkage": float(shrinkage),
                "scale": float(scale),
                "gate": gate(metrics),
                "metrics": compact,
            })
    selected = _selected_candidate(tuning_candidates)

    outer_active = _load_outer_validation(validation, active_report)
    outer_origins = splits["outer_gate"]
    outer_peer_rows = active_residual_peer_rows(peer_features, pd.concat(
        [inner_scored, outer_active], ignore_index=True))
    fit_origins = splits["outer_fit"]
    outer_fit_peers = outer_peer_rows.loc[
        outer_peer_rows.forecast_origin.isin(fit_origins)
    ].copy()
    if selected["selected_active_baseline_fallback"]:
        coefficients = None
        outer_scored = outer_active.copy()
        outer_scored["peer_correction_php"] = 0.0
        outer_scored["peer_feature_supported"] = False
        outer_scored["correction_scale"] = 0.0
        outer_scored["peer_corrected"] = outer_scored.active_production
    else:
        coefficients = fit_hierarchical(
            outer_fit_peers, fit_origins, selected["shrinkage"])
        outer_scored = apply_active_correction(
            outer_active, peer_features, coefficients, selected["scale"])
    outer_scored = outer_scored.copy()
    outer_scored["direct_lgbm"] = outer_scored.candidate_shared
    outer_metrics = _metrics(outer_scored)
    outer_gate = gate(outer_metrics)
    lead_bands = {}
    for name, mask in (("days_1_7", outer_scored.lead.between(1, 7)),
                       ("days_8_14", outer_scored.lead.between(8, 14))):
        lead_bands[name] = _scope(outer_scored.loc[mask])

    report = {
        "experiment": "nested_peer_momentum_correction_of_active_production_residuals",
        "active_run_id": RUN_ID,
        "active_manifest_sha256": sha256(ACTIVE_MANIFEST),
        "active_metadata_sha256": sha256(ACTIVE_BUNDLE / "metadata.json"),
        "active_production_replay_report_sha256": sha256(ACTIVE_PRODUCTION_REPORT),
        "active_production_replay_predictions_sha256": sha256(ACTIVE_PRODUCTION_PREDICTIONS),
        "candidate_report_sha256": sha256(CANDIDATE_REPORT),
        "validation_source": validation_info,
        "source_snapshot_sha256": source_snapshot_hash,
        "source_target_cutoff": target_cutoff.date().isoformat(),
        "inner_fit_origins": [pd.Timestamp(value).date().isoformat() for value in splits["inner_fit"]],
        "shrinkage_tune_origins": [pd.Timestamp(value).date().isoformat() for value in splits["shrinkage_tune"]],
        "outer_fit_origins": [pd.Timestamp(value).date().isoformat() for value in splits["outer_fit"]],
        "outer_gate_origins": [pd.Timestamp(value).date().isoformat() for value in outer_origins],
        "inner_active_coverage": inner_coverage,
        "inner_origin_audit": inner_origin_audit,
        "shrinkage_grid": list(LAMBDA_GRID),
        "scale_grid": list(SCALE_GRID),
        "tuning_candidates": tuning_candidates,
        "selected_hyperparameters": selected,
        "selected_coefficients": coefficients,
        "outer_gate_metrics": outer_metrics,
        "outer_gate_by_lead_band": lead_bands,
        "outer_gate": {
            "numeric_and_priority_gates_passed": bool(outer_gate["passed"]),
            "failures": outer_gate["failures"],
            "coverage_complete": bool(len(outer_scored) == len(outer_active)),
            "promotion_permitted": False,
        },
        "production_changed": False,
        "historical_test_files_read": False,
        "historical_test_actuals_read": False,
        "sealed_prospective_holdout_read": False,
        "confidence_or_intervals_changed": False,
        "independence_caveat": (
            "Validation periods, peer-correction exploration, and active-model configuration have prior research exposure. "
            "This is a nested historical diagnostic, not prospective promotion evidence."
        ),
        "mape_policy": "positive actuals only; zero actuals retained in PHP metrics",
        "macro_policy": "unweighted mean of per-series metrics; per-series RMSE is averaged after calculation",
        "script_sha256": sha256(Path(__file__).resolve()),
        "plan_sha256": sha256(PLAN_PATH),
    }
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir()
    keep = [*KEYS, "actual", "anchor", "product_category", "active_production",
            "active_forecast_source", "direct_lgbm", "peer_corrected", "persistence",
            "peer_correction_php", "peer_feature_supported", "correction_scale"]
    outer_scored[keep].sort_values(KEYS).to_csv(
        output_dir / "outer_gate_paired_predictions.csv", index=False)
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
        "selected_hyperparameters": report["selected_hyperparameters"],
        "inner_active_coverage": report["inner_active_coverage"],
        "outer_gate": report["outer_gate"],
        "outer_pooled": report["outer_gate_metrics"]["all"]["pooled"],
        "outer_vegetable_pooled": report["outer_gate_metrics"]["vegetables"]["pooled"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
