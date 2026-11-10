"""Train-only global shrinkage of prior-season period values toward persistence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "audits/foodcast_accuracy_20261018/period_seasonal_naive_v2/seasonal_predictions.csv"
INPUT_REPORT = ROOT / "audits/foodcast_accuracy_20261018/period_seasonal_naive_v2/report.json"
DIRECT_ROOT = ROOT / "audits/foodcast_accuracy_20261018/period_momentum_point_v1"
PLAN = ROOT / "audits/foodcast_accuracy_20261018/period_seasonal_shrink_plan.md"
TARGET_CUTOFF = pd.Timestamp("2026-09-30")
HOLDOUT_START = pd.Timestamp("2026-10-06")
KEYS = ["series", "forecast_origin", "horizon", "lead", "target_start", "target_end"]
METRICS = ("mae_php", "rmse_php", "mape_pct", "wape_pct", "bias_php",
           "within_5_php_pct", "within_5_percent_pct")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fit_beta(calibration: pd.DataFrame) -> dict:
    required = {"series", "actual", "persistence", "seasonal_value",
                "seasonal_supported"}
    if calibration.empty or not required.issubset(calibration):
        raise ValueError("Calibration rows are empty or incomplete")
    supported = calibration.loc[calibration.seasonal_supported].copy()
    if supported.empty:
        raise ValueError("No supported prior-season values in calibration")
    anchor = supported.persistence.to_numpy(dtype=float)
    season = supported.seasonal_value.to_numpy(dtype=float)
    actual = supported.actual.to_numpy(dtype=float)
    x = season / anchor - 1.0
    y = actual / anchor - 1.0
    valid = (np.isfinite(x) & np.isfinite(y) & (anchor > 0)
             & np.isfinite(season) & (season > 0) & (np.abs(x) > 1e-12))
    supported = supported.loc[valid].copy()
    x, y = x[valid], y[valid]
    if supported.empty:
        raise ValueError("No nonzero seasonal movements in calibration")
    counts = supported.series.value_counts()
    weights = np.abs(x) / supported.series.map(counts).to_numpy(dtype=float)
    ratios = y / x
    order = np.argsort(ratios, kind="mergesort")
    ratios, weights = ratios[order], weights[order]
    if not np.isfinite(ratios).all() or not np.isfinite(weights).all() or weights.sum() <= 0:
        raise ValueError("Invalid equal-series seasonal shrink fit")
    beta = float(ratios[np.searchsorted(np.cumsum(weights), weights.sum() / 2,
                                        side="left")])
    return {
        "beta": beta, "fit_targets": int(len(supported)),
        "fit_series": int(supported.series.nunique()),
        "fit_origins": int(supported.forecast_origin.nunique()),
        "minimum_origins_per_series": int(supported.groupby("series").forecast_origin.nunique().min()),
        "median_origins_per_series": float(supported.groupby("series").forecast_origin.nunique().median()),
        "method": "equal-series weighted median LAD of relative target residual / relative seasonal displacement",
    }


def add_candidate(rows: pd.DataFrame, beta: float) -> pd.DataFrame:
    required = {"persistence", "seasonal_value", "seasonal_supported"}
    if not required.issubset(rows) or not np.isfinite(beta):
        raise ValueError("Candidate rows or fitted coefficient are invalid")
    result = rows.copy()
    supported = result.seasonal_supported.to_numpy(dtype=bool)
    anchor = result.persistence.to_numpy(dtype=float)
    seasonal = result.seasonal_value.to_numpy(dtype=float)
    displacement = seasonal / anchor - 1.0
    response = np.where(supported & np.isfinite(displacement), beta * displacement, 0.0)
    result["seasonal_shrink_point"] = np.maximum(0.01, anchor * (1.0 + response))
    result["seasonal_shrink_applied"] = supported & np.isfinite(displacement)
    if not np.isfinite(result.seasonal_shrink_point.to_numpy(dtype=float)).all():
        raise ValueError("Seasonal-shrink forecast is non-finite")
    return result


def metric(rows: pd.DataFrame, prediction: str) -> dict:
    if rows.empty:
        return {"n": 0}
    actual = rows.actual.to_numpy(dtype=float)
    predicted = rows[prediction].to_numpy(dtype=float)
    if (not np.isfinite(actual).all() or not np.isfinite(predicted).all()
            or (actual <= 0).any()):
        raise ValueError("Invalid original-PHP metrics")
    error = predicted - actual
    absolute = np.abs(error)
    relative = absolute / actual
    return {
        "n": int(len(rows)), "series": int(rows.series.nunique()),
        "origins": int(rows.forecast_origin.nunique()),
        "target_periods": int(rows.target_start.nunique()),
        "mae_php": float(absolute.mean()),
        "rmse_php": float(np.sqrt(np.square(error).mean())),
        "mape_pct": float(relative.mean() * 100),
        "wape_pct": float(absolute.sum() / actual.sum() * 100),
        "bias_php": float(error.mean()),
        "within_5_php_pct": float((absolute <= 5).mean() * 100),
        "within_5_percent_pct": float((relative <= .05).mean() * 100),
    }


def summarize(rows: pd.DataFrame, prediction: str) -> dict:
    by_series = {series: metric(group, prediction)
                 for series, group in rows.groupby("series", sort=True)}
    by_lead = {str(int(lead)): metric(group, prediction)
               for lead, group in rows.groupby("lead", sort=True)}
    macro = {name: float(np.mean([entry[name] for entry in by_series.values()]))
             for name in METRICS} if by_series else {}
    return {"pooled": metric(rows, prediction), "macro_equal_series": macro,
            "by_series": by_series, "by_lead": by_lead}


def compare(rows: pd.DataFrame) -> dict:
    supported = rows.loc[rows.seasonal_supported].copy()
    persistence_all = summarize(rows, "persistence")
    shrink_all = summarize(rows, "seasonal_shrink_point")
    persistence_supported = summarize(supported, "persistence")
    shrink_supported = summarize(supported, "seasonal_shrink_point")
    reductions = {}
    for sample, base, candidate in (
            ("all_rows", persistence_all, shrink_all),
            ("supported_rows", persistence_supported, shrink_supported)):
        reductions[sample] = {}
        for name in ("mae_php", "rmse_php", "mape_pct"):
            before = base["pooled"].get(name)
            after = candidate["pooled"].get(name)
            reductions[sample][name] = (None if before is None or before == 0 or after is None
                                        else float((before - after) / before * 100))
    regressions = {}
    for series, base in persistence_all["by_series"].items():
        candidate = shrink_all["by_series"][series]
        regressions[series] = {
            "mae_change_pct": float((candidate["mae_php"] - base["mae_php"])
                                     / base["mae_php"] * 100)
            if base["mae_php"] > 0 else None,
            "rmse_change_pct": float((candidate["rmse_php"] - base["rmse_php"])
                                      / base["rmse_php"] * 100)
            if base["rmse_php"] > 0 else None,
        }
    return {
        "targets": int(len(rows)),
        "seasonal_supported_targets": int(len(supported)),
        "seasonal_support_pct": float(rows.seasonal_supported.mean() * 100) if len(rows) else None,
        "persistence_all_rows": persistence_all,
        "shrink_all_rows": shrink_all,
        "persistence_supported_rows": persistence_supported,
        "shrink_supported_rows": shrink_supported,
        "error_reduction_pct": reductions,
        "per_series_error_change_pct": regressions,
        "series_mae_regressions_over_10pct": [
            series for series, values in regressions.items()
            if values["mae_change_pct"] is not None and values["mae_change_pct"] > 10],
    }


def compare_direct(rows: pd.DataFrame, direct: pd.DataFrame) -> dict:
    required = set(KEYS + ["actual", "direct_point"])
    if not required.issubset(direct) or direct.duplicated(KEYS).any():
        raise ValueError("Direct-model input lacks exact unique comparison keys")
    paired = rows.merge(direct[KEYS + ["actual", "direct_point"]], on=KEYS,
                        how="inner", validate="one_to_one", suffixes=("_shrink", "_direct"))
    if paired.empty or not np.allclose(paired.actual_shrink, paired.actual_direct,
                                       rtol=0, atol=1e-8):
        raise ValueError("No exact direct-model match or actual labels disagree")
    paired["actual"] = paired.actual_shrink
    summaries = {
        name: summarize(paired, column)
        for name, column in (("persistence", "persistence"),
                             ("seasonal_shrink", "seasonal_shrink_point"),
                             ("direct_lightgbm", "direct_point"))
    }
    direct_scores = summaries["direct_lightgbm"]["pooled"]
    shrink_scores = summaries["seasonal_shrink"]["pooled"]
    reductions = {
        name: (None if direct_scores[name] == 0 else
               float((direct_scores[name] - shrink_scores[name])
                     / direct_scores[name] * 100))
        for name in ("mae_php", "rmse_php", "mape_pct")
    }
    return {"targets": int(len(paired)),
            "origins": int(paired.forecast_origin.nunique()),
            "series": int(paired.series.nunique()),
            "metrics": summaries,
            "seasonal_shrink_error_reduction_vs_direct_pct": reductions}


def validate_rows(rows: pd.DataFrame, horizon: str) -> pd.DataFrame:
    if horizon not in ("weekly", "monthly"):
        raise ValueError("Only weekly/monthly targets are permitted")
    subset = rows.loc[rows.horizon.eq(horizon)].copy()
    if subset.empty or subset.duplicated(KEYS).any():
        raise ValueError("Missing horizon rows or duplicate forecast keys")
    for column in ("forecast_origin", "target_start", "target_end"):
        subset[column] = pd.to_datetime(subset[column], errors="raise").dt.normalize()
    subset["seasonal_supported"] = subset.seasonal_supported.astype(str).str.lower().eq("true")
    if (subset.target_end.gt(TARGET_CUTOFF).any()
            or subset.target_end.ge(HOLDOUT_START).any()
            or subset.target_start.le(subset.forecast_origin).any()
            or subset.target_end.le(subset.forecast_origin).any()):
        raise ValueError("Target dates reach holdout or are not future to origin")
    if not subset.partition.isin(["calibration", "evaluation"]).all():
        raise ValueError("Unknown calibration/evaluation partition")
    if not np.isfinite(subset[["actual", "persistence"]].to_numpy(dtype=float)).all():
        raise ValueError("Invalid actual or persistence point")
    if subset.actual.le(0).any() or subset.persistence.le(0).any():
        raise ValueError("Period prices must be positive")
    calibration = subset.loc[subset.partition.eq("calibration")]
    evaluation = subset.loc[subset.partition.eq("evaluation")]
    if (calibration.empty or evaluation.empty
            or calibration.target_end.max() >= evaluation.forecast_origin.min()):
        raise ValueError("Calibration targets overlap or follow evaluation origins")
    return subset


def run(input_path: Path, input_report_path: Path, direct_root: Path,
        plan_path: Path, output_dir: Path) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite seasonal-shrink results: {output_dir}")
    input_report = json.loads(input_report_path.read_text(encoding="utf-8"))
    if (input_report.get("holdout_labels_used") is not False
            or input_report.get("production_promotion_permitted") is not False
            or input_report.get("source_report_date_max", "9999") >= "2026-10-06"):
        raise ValueError("Input seasonal-naive audit is not holdout-safe")
    raw = pd.read_csv(input_path, float_precision="round_trip")
    full_predictions, horizon_results = [], {}
    direct_hashes = {}
    for horizon in ("weekly", "monthly"):
        subset = validate_rows(raw, horizon)
        calibration = subset.loc[subset.partition.eq("calibration")]
        evaluation = subset.loc[subset.partition.eq("evaluation")]
        fit = fit_beta(calibration)
        predicted = add_candidate(subset, fit["beta"])
        evaluation = predicted.loc[predicted.partition.eq("evaluation")].copy()
        supported_calibration = calibration.loc[calibration.seasonal_supported]
        direct_path = direct_root / f"{horizon}_direct_common.csv"
        direct = pd.read_csv(direct_path, float_precision="round_trip")
        for column in ("forecast_origin", "target_start", "target_end"):
            direct[column] = pd.to_datetime(direct[column], errors="raise").dt.normalize()
        direct["lead"] = pd.to_numeric(direct.lead, errors="raise").astype(int)
        direct_hashes[horizon] = sha256(direct_path)
        horizon_results[horizon] = {
            "fit": fit,
            "calibration": {
                "targets": int(len(calibration)),
                "seasonally_supported_targets": int(len(supported_calibration)),
                "origins": int(calibration.forecast_origin.nunique()),
                "latest_target_end": calibration.target_end.max().date().isoformat(),
            },
            "evaluation": {
                "first_origin": evaluation.forecast_origin.min().date().isoformat(),
                "last_origin": evaluation.forecast_origin.max().date().isoformat(),
                "latest_target_end": evaluation.target_end.max().date().isoformat(),
                "metrics": compare(evaluation),
                "common_direct_lightgbm": compare_direct(evaluation, direct),
            },
        }
        full_predictions.append(predicted)
    predictions = pd.concat(full_predictions, ignore_index=True)
    if predictions.duplicated(KEYS).any() or predictions.target_end.max() > TARGET_CUTOFF:
        raise ValueError("Final output has duplicate or post-cutoff targets")
    report = {
        "experiment": "train_only_equal_series_lad_global_seasonal_shrink_vs_persistence",
        "input_sha256": sha256(input_path),
        "input_audit_report_sha256": sha256(input_report_path),
        "direct_common_file_sha256": direct_hashes,
        "source_sha256": input_report["source_sha256"],
        "targets_sha256": input_report["targets_sha256"],
        "upstream_plan_sha256": input_report["plan_sha256"],
        "plan_sha256": sha256(plan_path),
        "script_sha256": sha256(Path(__file__)),
        "holdout_labels_used": False, "production_promotion_permitted": False,
        "retrospective_reuse_note": "The historical evaluation rows have been used in prior research and are not independent prospective confirmation.",
        "metric_note": "Original-PHP pooled/equal-series metrics; MAPE uses positive actual period means. The same rows compare seasonal shrink and persistence.",
        "horizons": horizon_results,
    }
    output_dir.mkdir(parents=True)
    predictions.to_csv(output_dir / "seasonal_shrink_predictions.csv", index=False)
    (output_dir / "report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=INPUT)
    parser.add_argument("--input-report", type=Path, default=INPUT_REPORT)
    parser.add_argument("--direct-root", type=Path, default=DIRECT_ROOT)
    parser.add_argument("--plan", type=Path, default=PLAN)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.input, args.input_report, args.direct_root,
                 args.plan, args.output_dir)
    print(json.dumps({horizon: {
        "beta": entry["fit"]["beta"],
        "calibration_targets": entry["calibration"]["targets"],
        "evaluation": {
            "targets": entry["evaluation"]["metrics"]["targets"],
            "error_reduction_pct": entry["evaluation"]["metrics"]["error_reduction_pct"],
            "persistence_mae_rmse_mape": [entry["evaluation"]["metrics"][
                "persistence_all_rows"]["pooled"][key]
                for key in ("mae_php", "rmse_php", "mape_pct")],
            "shrink_mae_rmse_mape": [entry["evaluation"]["metrics"][
                "shrink_all_rows"]["pooled"][key]
                for key in ("mae_php", "rmse_php", "mape_pct")],
            "common_direct_targets": entry["evaluation"]["common_direct_lightgbm"]["targets"],
            "common_direct_error_reduction_pct": entry["evaluation"][
                "common_direct_lightgbm"]["seasonal_shrink_error_reduction_vs_direct_pct"],
        },
    } for horizon, entry in report["horizons"].items()}, indent=2))


if __name__ == "__main__":
    main()
