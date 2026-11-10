"""Research screen for a shrinkage-based vegetable peer-momentum correction.

The first three validation origins fit series and pooled slopes; the next three
choose shrinkage; the first six then refit coefficients for a seven-origin
outer validation screen. The saved test partition is never opened.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from evaluation.peer_momentum_diagnostic import evaluate as peer_diagnostic


ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIR = ROOT / "audits" / "foodcast_accuracy_20261017" / "relative5_test_confirmation_v2"
VALIDATION_PATH = SOURCE_DIR / "daily" / "validation_predictions.csv"
MANIFEST_PATH = SOURCE_DIR / "selection_manifest.json"
PLAN_PATH = ROOT / "audits" / "foodcast_accuracy_20261018" / "peer_momentum_hierarchical_plan.md"
DEFAULT_OUTPUT = ROOT / "audits" / "foodcast_accuracy_20261018" / "peer_momentum_hierarchical_v1"
HOLDOUT_START = pd.Timestamp("2026-10-06")
LAMBDA_GRID = (0.0, 0.00001, 0.00003, 0.0001, 0.0003,
               0.001, 0.003, 0.01, 0.03, 0.1)
BANDS = ((1, 7, "days_1_7"), (8, 14, "days_8_14"))
KEYS = ["series", "forecast_origin", "target_start", "target_end", "lead"]
PRIORITY = ("chili||labuyo", "lettuce||romaine", "lettuce||green ice",
            "lettuce||iceberg", "bell pepper||red")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _path_label(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(resolved)


def load_validation(path: Path) -> tuple[pd.DataFrame, dict]:
    frame = pd.read_csv(path)
    required = set(KEYS) | {
        "forecast_origin", "product_category", "actual", "anchor",
        "candidate_shared", "persistence", "priority_product", "period_days",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Validation input missing columns: {sorted(missing)}")
    frame["forecast_origin"] = pd.to_datetime(frame.forecast_origin, errors="coerce").dt.normalize()
    frame["target_start"] = pd.to_datetime(frame.target_start, errors="coerce").dt.normalize()
    frame["target_end"] = pd.to_datetime(frame.target_end, errors="coerce").dt.normalize()
    frame["lead"] = pd.to_numeric(frame.lead, errors="coerce")
    for column in ("actual", "anchor", "candidate_shared", "persistence", "period_days"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if frame[KEYS].isna().any().any() or frame.duplicated(KEYS).any():
        raise ValueError("Validation forecast keys are missing or duplicated")
    if not frame.lead.between(1, 14).all():
        raise ValueError("Daily input contains leads outside 1-14")
    expected = frame.forecast_origin + pd.to_timedelta(frame.lead, unit="D")
    if not frame.target_start.eq(expected).all() or not frame.target_end.eq(frame.target_start).all():
        raise ValueError("Daily targets do not align with origin and lead")
    if not frame.period_days.eq(1).all():
        raise ValueError("Input is not a one-calendar-day target panel")
    if frame.target_end.ge(HOLDOUT_START).any():
        raise ValueError("Validation input overlaps the sealed prospective holdout")
    numeric = frame[["actual", "anchor", "candidate_shared", "persistence"]].to_numpy(float)
    if not np.isfinite(numeric).all() or frame.actual.lt(0).any() or frame.anchor.le(0).any():
        raise ValueError("Validation input has invalid labels or point forecasts")
    category_counts = frame.groupby("series").product_category.nunique()
    if category_counts.gt(1).any():
        raise ValueError("A forecast series maps to multiple product categories")
    return frame.sort_values(KEYS).reset_index(drop=True), {
        "path": _path_label(path),
        "sha256": sha256(path),
        "rows": int(len(frame)),
        "series_count": int(frame.series.nunique()),
        "origin_dates": [date.date().isoformat() for date in sorted(frame.forecast_origin.unique())],
        "target_start": frame.target_start.min().date().isoformat(),
        "target_end": frame.target_end.max().date().isoformat(),
    }


def split_origins(frame: pd.DataFrame) -> dict[str, list[pd.Timestamp]]:
    origins = sorted(pd.to_datetime(frame.forecast_origin).dt.normalize().unique())
    if len(origins) != 13:
        raise ValueError(f"Expected 13 frozen validation origins, found {len(origins)}")
    result = {
        "inner_fit": list(origins[:3]),
        "shrinkage_tune": list(origins[3:6]),
        "outer_fit": list(origins[:6]),
        "outer_gate": list(origins[6:]),
    }
    for fit_name, score_name in (("inner_fit", "shrinkage_tune"),
                                 ("outer_fit", "outer_gate")):
        fit_end = frame.loc[frame.forecast_origin.isin(result[fit_name]), "target_end"].max()
        score_start = min(result[score_name])
        if fit_end >= score_start:
            raise ValueError(f"{fit_name} target periods overlap {score_name}")
    return result


def add_peer_categories(frame: pd.DataFrame, peers: pd.DataFrame) -> pd.DataFrame:
    categories = frame.groupby("series").product_category.first()
    result = peers.copy()
    result["forecast_origin"] = pd.to_datetime(result.forecast_origin).dt.normalize()
    result["product_category"] = result.series.map(categories)
    if result.product_category.isna().any():
        raise ValueError("Peer feature contains a series absent from the input panel")
    if result.duplicated(["series", "forecast_origin", "band"]).any():
        raise ValueError("Peer features contain duplicate series/origin/band keys")
    return result


def _fit_rows(peers: pd.DataFrame, origins: list[pd.Timestamp], band: str) -> pd.DataFrame:
    rows = peers.loc[
        peers.forecast_origin.isin(origins)
        & peers.band.eq(band)
        & peers.product_category.eq("Vegetables")
        & peers.peer_count.ge(5)
    ].copy()
    rows["x"] = pd.to_numeric(rows.peer_median_return3, errors="coerce")
    rows["y"] = pd.to_numeric(rows.mean_relative_residual, errors="coerce")
    rows = rows.loc[np.isfinite(rows.x) & np.isfinite(rows.y)].copy()
    if rows.empty:
        raise ValueError(f"No supported vegetable peer rows for {band}")
    counts = rows.groupby("forecast_origin").series.transform("nunique")
    rows["weight"] = 1.0 / counts
    return rows


def fit_hierarchical(peers: pd.DataFrame, origins: list[pd.Timestamp],
                     shrinkage: float, min_series_origins: int = 3) -> dict:
    """Fit per-series weighted slopes shrunk toward one shared slope per band."""
    if shrinkage < 0:
        raise ValueError("Shrinkage must be nonnegative")
    coefficients = {}
    for _, _, band in BANDS:
        rows = _fit_rows(peers, origins, band)
        x, y, w = (rows[column].to_numpy(float) for column in ("x", "y", "weight"))
        global_denominator = float(np.dot(w, x * x))
        if global_denominator <= 0:
            raise ValueError(f"Peer momentum has no variation for {band}")
        global_beta = float(np.dot(w, x * y) / global_denominator)
        by_series = {}
        for series, group in rows.groupby("series", sort=True):
            sx = group.x.to_numpy(float)
            sy = group.y.to_numpy(float)
            sw = group.weight.to_numpy(float)
            sxx = float(np.dot(sw, sx * sx))
            sxy = float(np.dot(sw, sx * sy))
            n_origins = int(group.forecast_origin.nunique())
            if n_origins < min_series_origins or sxx <= 0:
                beta = global_beta
            else:
                beta = (sxy + shrinkage * global_beta) / (sxx + shrinkage)
            by_series[str(series)] = {
                "beta": float(beta),
                "fit_origins": n_origins,
                "unshrunk_sxx": sxx,
                "used_global_fallback": bool(n_origins < min_series_origins or sxx <= 0),
            }
        coefficients[band] = {
            "global_beta": global_beta,
            "supported_series": int(len(by_series)),
            "fit_rows": int(len(rows)),
            "fit_origins": int(rows.forecast_origin.nunique()),
            "series": by_series,
        }
    return coefficients


def apply_correction(frame: pd.DataFrame, peers: pd.DataFrame,
                     coefficients: dict) -> pd.DataFrame:
    result = frame.copy()
    feature_rows = peers.loc[peers.peer_count.ge(5)].copy()
    feature_key = ["series", "forecast_origin", "band"]
    if feature_rows.duplicated(feature_key).any():
        raise ValueError("Duplicate supported peer feature")
    feature_map = {
        (row.series, row.forecast_origin, row.band): float(row.peer_median_return3)
        for row in feature_rows.itertuples()
        if pd.notna(row.peer_median_return3)
    }
    categories = result.groupby("series").product_category.first().to_dict()
    corrections = []
    supported = []
    for row in result.itertuples():
        band = "days_1_7" if int(row.lead) <= 7 else "days_8_14"
        x = feature_map.get((row.series, row.forecast_origin, band))
        eligible = categories[row.series] == "Vegetables" and x is not None
        if eligible:
            beta_record = coefficients[band]["series"].get(row.series)
            beta = beta_record["beta"] if beta_record else coefficients[band]["global_beta"]
            corrections.append(float(row.anchor) * float(beta) * x)
        else:
            corrections.append(0.0)
        supported.append(bool(eligible))
    result["peer_feature_supported"] = supported
    result["peer_correction_php"] = corrections
    result["peer_corrected"] = np.maximum(
        0.01, result.candidate_shared.to_numpy(float)
        + result.peer_correction_php.to_numpy(float))
    return result


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
    metrics = [_metric(group, prediction) for _, group in rows.groupby("series", sort=True)]
    fields = ("mae_php", "rmse_php", "mape_pct", "wape_pct", "bias_php", "within_5_php_pct")
    return {field: float(np.mean([item[field] for item in metrics if item[field] is not None]))
            if any(item[field] is not None for item in metrics) else None
            for field in fields}


def score(rows: pd.DataFrame) -> dict:
    if rows.empty:
        raise ValueError("Cannot score an empty partition")
    def scope_metrics(group: pd.DataFrame) -> dict:
        return {
            "n": int(len(group)),
            "series_count": int(group.series.nunique()),
            "models": {name: _metric(group, name)
                       for name in ("candidate_shared", "peer_corrected", "persistence")},
            "macro_equal_series": {name: _macro(group, name)
                                    for name in ("candidate_shared", "peer_corrected", "persistence")},
        }
    by_series = {str(series): {
        name: _metric(group, name)
        for name in ("candidate_shared", "peer_corrected", "persistence")
    } for series, group in rows.groupby("series", sort=True)}
    by_lead = {str(int(lead)): scope_metrics(group)
               for lead, group in rows.groupby("lead", sort=True)}
    per_series_mae_changes = {
        series: (values["peer_corrected"]["mae_php"] - values["candidate_shared"]["mae_php"])
        / values["candidate_shared"]["mae_php"] * 100.0
        if values["candidate_shared"]["mae_php"] > 0 else None
        for series, values in by_series.items()
    }
    priority_regressions = [series for series, change in per_series_mae_changes.items()
                            if any(token in series.casefold() for token in PRIORITY)
                            and change is not None and change > 10.0]
    result = {
        "all": scope_metrics(rows),
        "vegetables": scope_metrics(rows.loc[rows.product_category.eq("Vegetables")]),
        "by_series": by_series,
        "by_lead": by_lead,
        "series_mae_change_pct_candidate_vs_direct": per_series_mae_changes,
        "series_count_with_mae_regression": sum(value is not None and value > 0
                                                  for value in per_series_mae_changes.values()),
        "series_count_with_mae_regression_over_10_pct": sum(value is not None and value > 10
                                                              for value in per_series_mae_changes.values()),
        "priority_series_mae_regressions_over_10_pct": priority_regressions,
    }
    gate_conditions = []
    for scope in ("all", "vegetables"):
        base = result[scope]["models"]["candidate_shared"]
        candidate = result[scope]["models"]["peer_corrected"]
        gate_conditions.extend(candidate[key] < base[key]
                               for key in ("mae_php", "rmse_php", "mape_pct"))
    gate_conditions.append(
        result["all"]["models"]["peer_corrected"]["within_5_php_pct"]
        >= result["all"]["models"]["candidate_shared"]["within_5_php_pct"]
    )
    gate_conditions.append(not priority_regressions)
    result["promotion_screen_passed"] = bool(all(gate_conditions))
    return result


def _macro_vegetable_mae(rows: pd.DataFrame) -> float:
    vegetables = rows.loc[rows.product_category.eq("Vegetables")]
    return float(np.mean([_metric(group, "peer_corrected")["mae_php"]
                          for _, group in vegetables.groupby("series", sort=True)]))


def run_experiment(source_dir: Path = SOURCE_DIR, output_dir: Path = DEFAULT_OUTPUT) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing output directory: {output_dir}")
    manifest_path = source_dir / "selection_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("task_scope") != "objective"
            or manifest.get("selected_strategy_by_horizon", {}).get("daily") != "shared"
            or manifest.get("holdout_labels_used") is not False):
        raise ValueError("Unexpected or holdout-contaminated source selection manifest")
    validation_path = source_dir / "daily" / "validation_predictions.csv"
    validation, validation_meta = load_validation(validation_path)
    origins = split_origins(validation)
    _, peer_rows = peer_diagnostic(validation)
    peer_rows = add_peer_categories(validation, peer_rows)
    if peer_rows.forecast_origin.ge(HOLDOUT_START).any():
        raise ValueError("Peer features overlap the sealed prospective holdout")

    inner_fit = fit_hierarchical(peer_rows, origins["inner_fit"], shrinkage=0.0)
    tuning_rows = validation.loc[validation.forecast_origin.isin(origins["shrinkage_tune"])]
    tuning_scores = []
    for shrinkage in LAMBDA_GRID:
        candidate = apply_correction(
            tuning_rows, peer_rows, fit_hierarchical(peer_rows, origins["inner_fit"], shrinkage))
        tuning_scores.append({
            "shrinkage": shrinkage,
            "vegetable_macro_mae_php": _macro_vegetable_mae(candidate),
            "metrics": score(candidate),
        })
    best_loss = min(item["vegetable_macro_mae_php"] for item in tuning_scores)
    best_options = [item for item in tuning_scores
                    if np.isclose(item["vegetable_macro_mae_php"], best_loss,
                                  rtol=0.0, atol=1e-12)]
    selected = max(best_options, key=lambda item: item["shrinkage"])
    chosen_shrinkage = float(selected["shrinkage"])

    outer_coefficients = fit_hierarchical(peer_rows, origins["outer_fit"], chosen_shrinkage)
    gate_rows = validation.loc[validation.forecast_origin.isin(origins["outer_gate"])]
    gate_predictions = apply_correction(gate_rows, peer_rows, outer_coefficients)
    gate_metrics = score(gate_predictions)
    tuning_predictions = apply_correction(
        tuning_rows, peer_rows, fit_hierarchical(peer_rows, origins["inner_fit"], chosen_shrinkage))
    source_meta = {
        "validation": validation_meta,
        "selection_manifest": {
            "path": _path_label(manifest_path), "sha256": sha256(manifest_path),
        },
        "plan": {"path": _path_label(PLAN_PATH), "sha256": sha256(PLAN_PATH)},
        "peer_diagnostic_script": {
            "path": _path_label(Path(__file__).with_name("peer_momentum_diagnostic.py")),
            "sha256": sha256(Path(__file__).with_name("peer_momentum_diagnostic.py")),
        },
    }
    report = {
        "experiment": "hierarchical_shrunk_vegetable_peer_momentum_correction",
        "source_snapshot_sha256": manifest.get("source_snapshot_sha256"),
        "source_files": source_meta,
        "script_sha256": sha256(Path(__file__).resolve()),
        "target_definition": "observed daily targets at leads 1-14; target date equals origin plus lead",
        "inner_fit_origins": [pd.Timestamp(date).date().isoformat() for date in origins["inner_fit"]],
        "shrinkage_tune_origins": [pd.Timestamp(date).date().isoformat() for date in origins["shrinkage_tune"]],
        "outer_fit_origins": [pd.Timestamp(date).date().isoformat() for date in origins["outer_fit"]],
        "outer_gate_origins": [pd.Timestamp(date).date().isoformat() for date in origins["outer_gate"]],
        "shrinkage_grid": list(LAMBDA_GRID),
        "selected_shrinkage": chosen_shrinkage,
        "inner_tuning_scores": [{
            "shrinkage": item["shrinkage"],
            "vegetable_macro_mae_php": item["vegetable_macro_mae_php"],
            "all_pooled": item["metrics"]["all"]["models"],
            "vegetable_pooled": item["metrics"]["vegetables"]["models"],
        } for item in tuning_scores],
        "inner_fit_coefficients": inner_fit,
        "outer_fit_coefficients": outer_coefficients,
        "tuning_metrics": score(tuning_predictions),
        "outer_gate_metrics": gate_metrics,
        "mape_policy": "mean absolute percentage error on positive actuals; zero actuals remain in PHP metrics",
        "macro_policy": "unweighted mean of per-series metrics; per-series RMSE is computed before averaging",
        "historical_test_opened": False,
        "sealed_prospective_holdout_read": False,
        "production_changed": False,
        "promotion_permitted": False,
        "base_model_selection_caveat": (
            "The saved base model's early stopping used a broader validation period; "
            "these reused historical rows are diagnostic only, even if the candidate screen passes."
        ),
    }
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir()
    predictions = pd.concat([
        tuning_predictions.assign(screen="inner_shrinkage_tune"),
        gate_predictions.assign(screen="outer_validation_gate"),
    ], ignore_index=True)
    keep = KEYS + ["actual", "anchor", "product_category", "candidate_shared",
                   "persistence", "peer_feature_supported", "peer_correction_php",
                   "peer_corrected", "screen"]
    predictions[keep].sort_values(KEYS).to_csv(output_dir / "paired_predictions.csv", index=False)
    (output_dir / "report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=SOURCE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    report = run_experiment(args.source_dir, args.output_dir)
    gate = report["outer_gate_metrics"]
    print(json.dumps({
        "output_dir": str(args.output_dir),
        "selected_shrinkage": report["selected_shrinkage"],
        "promotion_screen_passed": gate["promotion_screen_passed"],
        "all_models": gate["all"]["models"],
        "vegetable_models": gate["vegetables"]["models"],
        "series_regressions": gate["series_count_with_mae_regression"],
        "series_regressions_over_10pct": gate["series_count_with_mae_regression_over_10_pct"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
