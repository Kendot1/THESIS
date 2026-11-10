"""Origin-available exploratory screen of residual correction and blending.

This diagnostic uses saved horizon validation predictions. Calibration labels
are restricted to target periods ending before each forecast origin, but the
underlying models were early-stopped on the full validation window. Therefore
the results are not an independent out-of-sample estimate and cannot qualify a
candidate for promotion. It does not train or promote a production model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUTS = {
    "daily14": ROOT / "audits/foodcast_accuracy_20261016/relative_hinge_lightgbm/run_20261016T162106Z/daily_validation_predictions.csv",
    "weekly4": ROOT / "audits/foodcast_accuracy_20261016/relative_hinge_lightgbm/run_20261016T163714Z/weekly_validation_predictions.csv",
    "monthly1": ROOT / "audits/foodcast_accuracy_20261016/relative_hinge_lightgbm/run_20261016T163714Z/monthly_validation_predictions.csv",
}
DEFAULT_OUTPUT = ROOT / "audits/foodcast_accuracy_20261017/rolling_calibration"
WEIGHT_GRID = (0.0, 0.25, 0.5, 0.75, 1.0)
MIN_PRIOR_ORIGINS = 3
MIN_HISTORY_ROWS = 100
MIN_LEAD_ROWS = 30


def _read_predictions(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {
        "forecast_origin", "target_end", "series", "lead", "actual",
        "v5_selected", "candidate_selected", "persistence",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{path} is missing required columns: {sorted(missing)}")
    frame = frame.copy()
    frame["forecast_origin"] = pd.to_datetime(frame.forecast_origin, errors="coerce").dt.normalize()
    frame["target_end"] = pd.to_datetime(frame.target_end, errors="coerce").dt.normalize()
    for column in ("lead", "actual", "v5_selected", "candidate_selected", "persistence"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if frame[["forecast_origin", "target_end"]].isna().any().any():
        raise ValueError(f"{path} has invalid origin or target-end dates")
    if frame.duplicated(["series", "forecast_origin", "lead"]).any():
        raise ValueError(f"{path} has duplicate series/origin/lead rows")
    return frame


def available_history(frame: pd.DataFrame, origin: pd.Timestamp) -> pd.DataFrame:
    """Rows passing the target-end availability proxy; future targets are excluded."""
    origin = pd.Timestamp(origin).normalize()
    return frame.loc[
        frame.forecast_origin.lt(origin) & frame.target_end.le(origin)
    ].copy()


def _valid_rows(frame: pd.DataFrame, prediction: str) -> pd.DataFrame:
    values = frame[["actual", prediction]].to_numpy(dtype=float)
    mask = np.isfinite(values).all(axis=1) & (values[:, 0] > 0)
    return frame.loc[mask].copy()


def _fit_mae_weight(history: pd.DataFrame, prediction: str) -> float:
    history = _valid_rows(history, prediction)
    if history.empty:
        return 1.0
    actual = history.actual.to_numpy(dtype=float)
    model = history[prediction].to_numpy(dtype=float)
    persistence = history.persistence.to_numpy(dtype=float)
    losses = [np.mean(np.abs(actual - (weight * model + (1.0 - weight) * persistence)))
              for weight in WEIGHT_GRID]
    return float(WEIGHT_GRID[int(np.argmin(losses))])


def rolling_blend(frame: pd.DataFrame) -> pd.DataFrame:
    """Fit per-lead model/persistence weights using only previously knowable labels."""
    output = []
    for origin in sorted(frame.forecast_origin.unique()):
        history = _valid_rows(available_history(frame, origin), "candidate_selected")
        if (history.forecast_origin.nunique() < MIN_PRIOR_ORIGINS
                or len(history) < MIN_HISTORY_ROWS):
            continue
        current = frame.loc[frame.forecast_origin.eq(origin)].copy()
        for lead, rows in current.groupby("lead", sort=True):
            lead_history = history.loc[history.lead.eq(lead)]
            if (lead_history.forecast_origin.nunique() >= MIN_PRIOR_ORIGINS
                    and len(lead_history) >= MIN_LEAD_ROWS):
                fit_rows = lead_history
                fit_scope = "lead"
            else:
                fit_rows = history
                fit_scope = "pooled_horizons"
            weight = _fit_mae_weight(fit_rows, "candidate_selected")
            part = rows.copy()
            part["blend_weight"] = weight
            part["blend_fit_scope"] = fit_scope
            part["calibration_rows"] = int(len(fit_rows))
            part["calibration_origins"] = int(fit_rows.forecast_origin.nunique())
            part["rolling_blend"] = (
                weight * part.candidate_selected
                + (1.0 - weight) * part.persistence
            )
            output.append(part)
    return pd.concat(output, ignore_index=True) if output else frame.iloc[0:0].copy()


def rolling_bias_correction(frame: pd.DataFrame) -> pd.DataFrame:
    """Apply global or empirical-Bayes series/lead bias learned causally."""
    output = []
    for origin in sorted(frame.forecast_origin.unique()):
        history = _valid_rows(available_history(frame, origin), "v5_selected")
        if (history.forecast_origin.nunique() < MIN_PRIOR_ORIGINS
                or len(history) < MIN_HISTORY_ROWS):
            continue
        history["residual"] = history.v5_selected - history.actual
        grouped = (history.groupby(["series", "lead"], sort=True).residual
                   .agg(["mean", "var", "count"]).reset_index())
        global_bias = history.groupby("lead").residual.mean().to_dict()
        corrections = []
        for lead in sorted(history.lead.unique()):
            lead_history = history.loc[history.lead.eq(lead)]
            stats = grouped.loc[
                grouped.lead.eq(lead) & grouped["count"].ge(2)
            ].copy()
            if len(stats) >= 2:
                degrees = int((stats["count"] - 1).sum())
                within_variance = (
                    float(((stats["count"] - 1) * stats["var"].fillna(0)).sum() / degrees)
                    if degrees else 0.0
                )
                between_variance = max(
                    0.0,
                    float(stats["mean"].var(ddof=1)
                          - np.mean(within_variance / stats["count"])),
                )
            else:
                within_variance = 0.0
                between_variance = 0.0
            center = float(global_bias[lead])
            denominator = between_variance + within_variance / stats["count"]
            shrinkage = np.divide(
                between_variance, denominator,
                out=np.zeros(len(stats), dtype=float), where=denominator.to_numpy() > 0,
            )
            stats["bias_estimate"] = center + shrinkage * (stats["mean"] - center)
            stats["global_bias"] = center
            corrections.append(stats[["series", "lead", "bias_estimate", "global_bias"]])
        if not corrections:
            continue
        correction = pd.concat(corrections, ignore_index=True)
        current = frame.loc[frame.forecast_origin.eq(origin)].merge(
            correction, on=["series", "lead"], how="left", validate="one_to_one"
        )
        current["global_bias"] = current.lead.map(global_bias)
        current["bias_estimate"] = current.bias_estimate.fillna(current.global_bias)
        current["global_bias_corrected"] = current.v5_selected - current.global_bias
        current["empirical_bayes_corrected"] = current.v5_selected - current.bias_estimate
        current["calibration_rows"] = int(len(history))
        current["calibration_origins"] = int(history.forecast_origin.nunique())
        output.append(current)
    return pd.concat(output, ignore_index=True) if output else frame.iloc[0:0].copy()


def metrics(frame: pd.DataFrame, prediction: str) -> dict:
    valid = _valid_rows(frame, prediction)
    if valid.empty:
        return {"n": 0, "mae_php": None, "rmse_php": None, "mape_pct": None,
                "within_5_percent_pct": None, "within_5_php_pct": None, "bias_php": None}
    actual = valid.actual.to_numpy(dtype=float)
    error = valid[prediction].to_numpy(dtype=float) - actual
    absolute = np.abs(error)
    return {
        "n": int(len(valid)),
        "mae_php": float(absolute.mean()),
        "rmse_php": float(np.sqrt(np.mean(error ** 2))),
        "mape_pct": float(np.mean(absolute / actual) * 100.0),
        "within_5_percent_pct": float(np.mean(absolute / actual <= 0.05) * 100.0),
        "within_5_php_pct": float(np.mean(absolute <= 5.0) * 100.0),
        "bias_php": float(error.mean()),
    }


def _metrics_by(frame: pd.DataFrame, predictions: list[str], group: str) -> dict:
    result = {}
    for label, rows in frame.groupby(group, dropna=False, sort=True):
        result[str(label)] = {prediction: metrics(rows, prediction) for prediction in predictions}
    return result


def _summarize(frame: pd.DataFrame, predictions: list[str]) -> dict:
    series_metrics = _metrics_by(frame, predictions, "series")
    macro = {}
    for prediction in predictions:
        values = [row[prediction] for row in series_metrics.values()
                  if row[prediction]["mae_php"] is not None]
        macro[prediction] = {
            key: float(np.mean([row[key] for row in values])) if values else None
            for key in ("mae_php", "rmse_php", "mape_pct", "within_5_percent_pct",
                        "within_5_php_pct", "bias_php")
        }
    return {
        "n": int(len(frame)),
        "forecast_origins": sorted(frame.forecast_origin.dt.strftime("%Y-%m-%d").unique().tolist()),
        "aggregate": {prediction: metrics(frame, prediction) for prediction in predictions},
        "macro_series": macro,
        "by_lead": _metrics_by(frame, predictions, "lead"),
        "by_series": series_metrics,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_screen(paths: dict[str, Path], output_dir: Path) -> dict:
    report = {
        "experiment": "causal_online_blending_and_bias_correction",
        "evidence_status": "development_validation_only_not_for_promotion",
        "selection_caveat": (
            "The saved base models were early-stopped using the full validation window being analyzed, "
            "so their predictions are not independent out-of-sample evidence. The rolling correction "
            "uses only residual labels whose target periods ended before each forecast origin, but "
            "that origin-availability rule does not remove the base-model validation reuse. "
            "Treat all results as exploratory only, not leakage-safe promotion evidence."
        ),
        "configuration": {
            "weight_grid": list(WEIGHT_GRID),
            "weight_objective": "minimum historical MAE in PHP; ties choose the smaller model weight",
            "minimum_prior_origins": MIN_PRIOR_ORIGINS,
            "minimum_history_rows": MIN_HISTORY_ROWS,
            "minimum_lead_rows": MIN_LEAD_ROWS,
            "availability_rule": "forecast_origin < current origin and target_end <= current origin",
            "bias_estimator": "per-lead global residual mean and empirical-Bayes series/lead shrinkage",
        },
        "horizons": {},
        "sources": {},
    }
    prediction_parts = []
    for name, path in paths.items():
        frame = _read_predictions(path)
        report["sources"][name] = {"path": str(path), "sha256": _sha256(path), "rows": int(len(frame))}
        blend = rolling_blend(frame)
        if not blend.empty:
            blend_summary = _summarize(
                blend, ["v5_selected", "candidate_selected", "persistence", "rolling_blend"]
            )
            blend["horizon_name"] = name
            blend["experiment_part"] = "rolling_blend"
            blend["rolling_bias"] = np.nan
            prediction_parts.append(blend)
        else:
            blend_summary = {"n": 0, "forecast_origins": [], "aggregate": {}, "macro_series": {},
                             "by_lead": {}, "by_series": {}}
        bias = rolling_bias_correction(frame)
        if not bias.empty:
            bias_summary = _summarize(
                bias, ["v5_selected", "global_bias_corrected", "empirical_bayes_corrected"]
            )
            bias["horizon_name"] = name
            bias["experiment_part"] = "rolling_bias"
            bias["rolling_blend"] = np.nan
            prediction_parts.append(bias)
        else:
            bias_summary = {"n": 0, "forecast_origins": [], "aggregate": {}, "macro_series": {},
                             "by_lead": {}, "by_series": {}}
        report["horizons"][name] = {"rolling_blend": blend_summary, "rolling_bias": bias_summary}
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    if prediction_parts:
        pd.concat(prediction_parts, ignore_index=True, sort=False).to_csv(
            output_dir / "predictions.csv", index=False
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--daily", type=Path, default=DEFAULT_INPUTS["daily14"])
    parser.add_argument("--weekly", type=Path, default=DEFAULT_INPUTS["weekly4"])
    parser.add_argument("--monthly", type=Path, default=DEFAULT_INPUTS["monthly1"])
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    paths = {"daily14": args.daily, "weekly4": args.weekly, "monthly1": args.monthly}
    report = run_screen(paths, args.output)
    for name, result in report["horizons"].items():
        blend = result["rolling_blend"]["aggregate"]
        bias = result["rolling_bias"]["aggregate"]
        print(f"{name}: blend n={result['rolling_blend']['n']} "
              f"MAE={blend.get('rolling_blend', {}).get('mae_php')} "
              f"RMSE={blend.get('rolling_blend', {}).get('rmse_php')} "
              f"bias-corrected n={result['rolling_bias']['n']} "
              f"EB MAE={bias.get('empirical_bayes_corrected', {}).get('mae_php')}")
    print(f"Saved {args.output / 'report.json'} and {args.output / 'predictions.csv'}")


if __name__ == "__main__":
    main()
