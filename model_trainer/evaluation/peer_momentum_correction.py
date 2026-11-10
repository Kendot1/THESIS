"""Research-only shared vegetable peer-momentum residual correction.

Fit on six earliest validation origins, select on seven later validation
origins, and open the reused historical test only if that screen passes.
No product-specific coefficient, arbitrary multiplier, or production write.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from evaluation.peer_momentum_diagnostic import evaluate as peer_diagnostic
from utils.metrics import compute_all_metrics


BANDS = ("days_1_7", "days_8_14")
KEY = ("series", "forecast_origin", "target_start", "target_end", "lead")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fit_coefficients(peer_rows: pd.DataFrame, fit_origins: list[pd.Timestamp]) -> dict[str, dict]:
    """Origin-equal-weight, zero-intercept OLS on pre-selection residuals."""
    fit = peer_rows.loc[peer_rows.forecast_origin.isin(fit_origins)]
    result = {}
    for band in BANDS:
        rows = fit.loc[fit.band.eq(band)].copy()
        if rows.empty or rows.forecast_origin.nunique() < 6:
            raise ValueError(f"Insufficient early-origin support: {band}")
        rows["origin_weight"] = 1 / rows.groupby("forecast_origin").series.transform("count")
        x = rows.peer_median_return3.to_numpy(dtype=float)
        y = rows.mean_relative_residual.to_numpy(dtype=float)
        weight = rows.origin_weight.to_numpy(dtype=float)
        valid = np.isfinite(x) & np.isfinite(y) & np.isfinite(weight)
        if valid.sum() < 30 or not np.square(x[valid]).dot(weight[valid]) > 0:
            raise ValueError(f"Insufficient variable peer momentum: {band}")
        beta = float(np.dot(weight[valid] * x[valid], y[valid])
                     / np.dot(weight[valid], np.square(x[valid])))
        result[band] = {
            "beta": beta,
            "fit_origins": int(rows.forecast_origin.nunique()),
            "fit_series_origin_rows": int(len(rows)),
            "latest_fit_origin": str(rows.forecast_origin.max().date()),
        }
    return result


def apply_correction(frame: pd.DataFrame, peer_rows: pd.DataFrame,
                     coefficients: dict[str, dict]) -> pd.DataFrame:
    frame = frame.copy()
    frame["forecast_origin"] = pd.to_datetime(frame.forecast_origin).dt.normalize()
    if frame.duplicated(list(KEY)).any():
        raise ValueError("Duplicate forecast keys")
    peer = peer_rows.loc[peer_rows.band.eq("days_1_7")]
    if peer.duplicated(["series", "forecast_origin"]).any():
        raise ValueError("Duplicate peer features")
    peer_map = {(row.series, row.forecast_origin): float(row.peer_median_return3)
                for row in peer.itertuples()}
    corrections = []
    for row in frame.itertuples():
        momentum = peer_map.get((row.series, row.forecast_origin))
        if row.product_category != "Vegetables" or momentum is None:
            corrections.append(0.0)
            continue
        band = "days_1_7" if int(row.lead) <= 7 else "days_8_14"
        corrections.append(float(row.anchor) * coefficients[band]["beta"] * momentum)
    frame["peer_correction_php"] = corrections
    frame["peer_corrected"] = np.maximum(
        0.01, frame.candidate_shared.to_numpy(dtype=float)
        + frame.peer_correction_php.to_numpy(dtype=float))
    return frame


def metrics(rows: pd.DataFrame, name: str) -> dict:
    actual = rows.actual.to_numpy(dtype=float)
    predicted = rows[name].to_numpy(dtype=float)
    result = compute_all_metrics(actual, predicted)
    if result["n"] != len(rows) or result["mape"] is None:
        raise ValueError("Metrics require identical finite positive target rows")
    return {
        "n": int(result["n"]),
        "mae_php": result["mae"],
        "rmse_php": result["rmse"],
        "mape_pct": result["mape"],
        "within_5_php_pct": result["within_5_php_accuracy_pct"],
        "bias_php": float(np.mean(predicted - actual)),
    }


def paired_metrics(rows: pd.DataFrame) -> dict:
    return {name: metrics(rows, name)
            for name in ("candidate_shared", "peer_corrected", "persistence")}


def selection_report(rows: pd.DataFrame) -> dict:
    vegetable = rows.loc[rows.product_category.eq("Vegetables")]
    result = {
        "all": paired_metrics(rows),
        "vegetables": paired_metrics(vegetable),
        "bands": {band: paired_metrics(rows.loc[
            rows.lead.between(1, 7) if band == "days_1_7"
            else rows.lead.between(8, 14)]) for band in BANDS},
    }
    result["by_series"] = {
        series: paired_metrics(group)
        for series, group in rows.groupby("series", sort=True)
    }
    result["by_lead"] = {
        str(int(lead)): paired_metrics(group)
        for lead, group in rows.groupby("lead", sort=True)
    }
    result["equal_series_macro"] = {
        method: {
            metric: float(np.mean([item[method][metric]
                                   for item in result["by_series"].values()]))
            for metric in ("mae_php", "rmse_php", "mape_pct", "within_5_php_pct", "bias_php")
        }
        for method in ("candidate_shared", "peer_corrected", "persistence")
    }
    result["error_reduction_vs_direct_pct"] = {
        metric: (
            (result["all"]["candidate_shared"][metric]
             - result["all"]["peer_corrected"][metric])
            / result["all"]["candidate_shared"][metric] * 100
            if result["all"]["candidate_shared"][metric] else None)
        for metric in ("mae_php", "rmse_php", "mape_pct")
    }
    result["series_mae_regressions_vs_direct"] = [
        series for series, item in result["by_series"].items()
        if item["peer_corrected"]["mae_php"] > item["candidate_shared"]["mae_php"]
    ]
    priority_regressions = []
    for series, group in rows.loc[rows.priority_product].groupby("series", sort=True):
        original = metrics(group, "candidate_shared")
        corrected = metrics(group, "peer_corrected")
        if corrected["mae_php"] > 1.10 * original["mae_php"]:
            priority_regressions.append(series)
    result["priority_mae_regressions_over_10pct"] = priority_regressions
    result["validation_selected"] = (
        all(result[scope]["peer_corrected"][metric]
            < result[scope]["candidate_shared"][metric]
            for scope in ("all", "vegetables")
            for metric in ("mae_php", "rmse_php", "mape_pct"))
        and result["all"]["peer_corrected"]["within_5_php_pct"]
            >= result["all"]["candidate_shared"]["within_5_php_pct"]
        and not priority_regressions
    )
    return result


def run(source_dir: Path, output_dir: Path) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite correction experiment: {output_dir}")
    manifest_path = source_dir / "selection_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest["task_scope"] != "objective"
            or manifest["selected_strategy_by_horizon"]["daily"] != "shared"
            or manifest["holdout_labels_used"] is not False):
        raise ValueError("Unexpected origin-independent base model evidence")
    validation_path = source_dir / "daily" / "validation_predictions.csv"
    validation = pd.read_csv(validation_path)
    _, peer_rows = peer_diagnostic(validation)
    origins = sorted(pd.to_datetime(validation.forecast_origin).dt.normalize().unique())
    if len(origins) != 13:
        raise ValueError("Expected exactly 13 frozen validation origins")
    fit_origins = origins[:6]
    selection_origins = origins[6:]
    if (pd.to_datetime(validation.loc[
            pd.to_datetime(validation.forecast_origin).isin(fit_origins), "target_end"]).max()
            >= selection_origins[0]):
        raise ValueError("Fitting targets have not closed before selection origins")
    coefficients = fit_coefficients(peer_rows, fit_origins)
    selected_rows = validation.loc[
        pd.to_datetime(validation.forecast_origin).isin(selection_origins)]
    selected_rows = apply_correction(selected_rows, peer_rows, coefficients)
    selected_metrics = selection_report(selected_rows)
    report = {
        "experiment": "shared_vegetable_peer_momentum_correction",
        "source_snapshot_sha256": manifest["source_snapshot_sha256"],
        "selection_manifest_sha256": sha256(manifest_path),
        "validation_predictions_sha256": sha256(validation_path),
        "script_sha256": sha256(Path(__file__)),
        "fit_origin_dates": [str(value.date()) for value in fit_origins],
        "selection_origin_dates": [str(value.date()) for value in selection_origins],
        "coefficients": coefficients,
        "selection": selected_metrics,
        "historical_test_reused": False,
        "holdout_labels_used": False,
        "production_promotion_permitted": False,
        "limitation": (
            "Base model early stopping used the full validation period; this correction "
            "is a historical diagnostic, not a pristine validation/test protocol. "
            "Immutable source-ingestion times are unavailable."),
    }
    output_dir.mkdir(parents=True)
    selected_rows[list(KEY) + ["actual", "anchor", "product_category",
                             "candidate_shared", "persistence", "peer_correction_php",
                             "peer_corrected"]].to_csv(
        output_dir / "selection_paired_predictions.csv", index=False)
    if selected_metrics["validation_selected"]:
        test_path = source_dir / "daily" / "test_predictions.csv"
        test = pd.read_csv(test_path)
        _, test_peer_rows = peer_diagnostic(
            test, first_origin_inclusive="2025-09-13",
            last_target_exclusive="2026-10-06")
        test_rows = apply_correction(test, test_peer_rows, coefficients)
        report["test_predictions_sha256"] = sha256(test_path)
        report["historical_test_reused"] = True
        report["test"] = selection_report(test_rows)
        test_rows[list(KEY) + ["actual", "anchor", "product_category",
                               "candidate_shared", "persistence", "peer_correction_php",
                               "peer_corrected"]].to_csv(
            output_dir / "test_paired_predictions.csv", index=False)
    else:
        report["test_not_opened_due_to_failed_validation_screen"] = True
    (output_dir / "report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report


def main() -> None:
    repository = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=repository /
                        "audits/foodcast_accuracy_20261017/relative5_test_confirmation_v2")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.source_dir, args.output_dir)
    print(json.dumps({"coefficients": report["coefficients"],
                      "selection": report["selection"],
                      "test": report.get("test")}, indent=2))


if __name__ == "__main__":
    main()
