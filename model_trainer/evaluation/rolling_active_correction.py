"""Causal rolling bias correction for saved active daily forecast vintages.

At each origin, corrections use only earlier active forecast residuals whose
target dates have passed. This is an exploratory prequential evaluation on a
historical test window that has been reused by other research, not prospective
promotion evidence. No model or production pointer is changed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from evaluation.paired_daily_comparison import _metrics


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "audits/foodcast_accuracy_20261017/active_daily_paired_v2/paired_comparison/paired_predictions.csv"
DEFAULT_INPUT_REPORT = ROOT / "audits/foodcast_accuracy_20261017/active_daily_paired_v2/paired_comparison/report.json"
DEFAULT_OUTPUT_ROOT = ROOT / "audits/foodcast_accuracy_20261017/rolling_active_correction"
MIN_PRIOR_ORIGINS = 3
MIN_HISTORY_ROWS = 100


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {
        "series", "forecast_origin", "target_date", "lead", "actual_candidate",
        "ensemble", "candidate_shared", "persistence_active",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Paired forecasts are missing {sorted(missing)}")
    frame = frame.copy()
    frame["forecast_origin"] = pd.to_datetime(frame.forecast_origin, errors="coerce").dt.normalize()
    frame["target_date"] = pd.to_datetime(frame.target_date, errors="coerce").dt.normalize()
    frame["lead"] = pd.to_numeric(frame.lead, errors="coerce")
    if frame[["forecast_origin", "target_date", "lead"]].isna().any().any():
        raise ValueError("Forecast keys contain invalid origin, target date, or lead")
    if frame.duplicated(["series", "forecast_origin", "target_date", "lead"]).any():
        raise ValueError("Paired forecasts contain duplicate keys")
    if (frame.target_date <= frame.forecast_origin).any():
        raise ValueError("A daily target is not strictly after its forecast origin")
    for column in ("actual_candidate", "ensemble", "candidate_shared", "persistence_active"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.sort_values(["forecast_origin", "series", "lead"]).reset_index(drop=True)


def available_history(frame: pd.DataFrame, origin: pd.Timestamp) -> pd.DataFrame:
    """Use prior forecast vintages only after their daily target date has passed."""
    origin = pd.Timestamp(origin).normalize()
    return frame.loc[
        frame.forecast_origin.lt(origin) & frame.target_date.le(origin)
    ].copy()


def _bias_tables(history: pd.DataFrame) -> tuple[dict[int, float], dict[tuple[str, int], float]]:
    valid = history.loc[
        np.isfinite(history.actual_candidate)
        & history.actual_candidate.gt(0)
        & np.isfinite(history.ensemble)
    ].copy()
    if valid.empty:
        return {}, {}
    valid["residual"] = valid.ensemble - valid.actual_candidate
    global_bias = valid.groupby("lead", sort=True).residual.mean().to_dict()
    grouped = (valid.groupby(["series", "lead"], sort=True).residual
               .agg(["mean", "var", "count"]).reset_index())
    estimates: dict[tuple[str, int], float] = {}
    for lead, center_value in global_bias.items():
        center = float(center_value)
        stats = grouped.loc[
            grouped.lead.eq(lead) & grouped["count"].ge(2)
        ].copy()
        if stats.empty:
            continue
        degrees = int((stats["count"] - 1).sum())
        within_variance = (
            float(((stats["count"] - 1) * stats["var"].fillna(0)).sum() / degrees)
            if degrees else 0.0
        )
        between_variance = max(
            0.0,
            float(stats["mean"].var(ddof=1)
                  - np.mean(within_variance / stats["count"])),
        ) if len(stats) >= 2 else 0.0
        denominator = between_variance + within_variance / stats["count"]
        shrinkage = np.divide(
            between_variance, denominator.to_numpy(dtype=float),
            out=np.zeros(len(stats), dtype=float), where=denominator.to_numpy(dtype=float) > 0,
        )
        estimates.update({
            (str(row.series), int(row.lead)): float(center + weight * (row.mean - center))
            for row, weight in zip(stats.itertuples(index=False), shrinkage)
        })
    return {int(key): float(value) for key, value in global_bias.items()}, estimates


def rolling_correct(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Apply global-mean and empirical-Bayes residual corrections prequentially."""
    parts = []
    trace = []
    for origin in sorted(frame.forecast_origin.unique()):
        origin = pd.Timestamp(origin).normalize()
        current = frame.loc[frame.forecast_origin.eq(origin)].copy()
        history = available_history(frame, origin)
        prior_origins = int(history.forecast_origin.nunique())
        supported = prior_origins >= MIN_PRIOR_ORIGINS and len(history) >= MIN_HISTORY_ROWS
        global_bias, series_bias = _bias_tables(history) if supported else ({}, {})
        raw = current.ensemble.to_numpy(dtype=float)
        global_correction = current.lead.map(global_bias).fillna(0.0).to_numpy(dtype=float).copy()
        eb_correction = np.array([
            series_bias.get((str(series), int(lead)), global_bias.get(int(lead), 0.0))
            for series, lead in zip(current.series, current.lead)
        ], dtype=float)
        if not supported:
            global_correction[:] = 0.0
            eb_correction[:] = 0.0
        current["active_global_mean_bias_corrected"] = np.maximum(
            0.01, raw - global_correction
        )
        current["active_empirical_bayes_corrected"] = np.maximum(
            0.01, raw - eb_correction
        )
        current["calibration_rows"] = int(len(history)) if supported else 0
        current["calibration_origins"] = prior_origins if supported else 0
        current["calibration_applied"] = bool(supported)
        parts.append(current)
        trace.append({
            "forecast_origin": origin.date().isoformat(),
            "rows_scored": int(len(current)),
            "prior_target_rows_available": int(len(history)),
            "prior_forecast_origins_available": prior_origins,
            "correction_applied": bool(supported),
        })
    return pd.concat(parts, ignore_index=True), trace


def _summary(frame: pd.DataFrame, predictions: list[str]) -> dict:
    aggregate = {name: _metrics(frame, name) for name in predictions}
    by_series = {
        str(series): {name: _metrics(rows, name) for name in predictions}
        for series, rows in frame.groupby("series", sort=True)
    }
    macro = {}
    for name in predictions:
        rows = [item[name] for item in by_series.values() if item[name]["mae_php"] is not None]
        macro[name] = {
            key: float(np.mean([row[key] for row in rows])) if rows else None
            for key in ("mae_php", "rmse_php", "mape_pct", "within_5_percent_pct",
                        "within_5_php_pct", "bias_php")
        }
    by_lead = {
        str(int(lead)): {name: _metrics(rows, name) for name in predictions}
        for lead, rows in frame.groupby("lead", sort=True)
    }
    regressions = {
        candidate: {
            metric: sum(
                by_series[series][candidate][metric] > by_series[series]["ensemble"][metric]
                for series in by_series
                if by_series[series][candidate][metric] is not None
                and by_series[series]["ensemble"][metric] is not None
            )
            for metric in ("mae_php", "rmse_php", "mape_pct")
        }
        for candidate in predictions if candidate != "ensemble"
    }
    return {
        "n_rows": int(len(frame)),
        "series_count": int(frame.series.nunique()),
        "origins": sorted(frame.forecast_origin.dt.strftime("%Y-%m-%d").unique().tolist()),
        "aggregate": aggregate,
        "macro_series_equal_weight": macro,
        "by_lead": by_lead,
        "by_series": by_series,
        "per_series_regression_counts_vs_active": regressions,
    }


def run(input_path: Path = DEFAULT_INPUT, input_report_path: Path = DEFAULT_INPUT_REPORT,
        output_root: Path = DEFAULT_OUTPUT_ROOT) -> dict:
    input_path, input_report_path = Path(input_path).resolve(), Path(input_report_path).resolve()
    output_root = Path(output_root).resolve()
    output_dir = output_root / datetime.now(timezone.utc).strftime("run_%Y%m%dT%H%M%SZ")
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite rolling correction run {output_dir}")
    source_report = json.loads(input_report_path.read_text(encoding="utf-8"))
    if source_report.get("evaluation_status") != "historical_paired_diagnostic_not_prospective_holdout":
        raise ValueError("Input is not the declared historical paired daily diagnostic")
    if source_report.get("canonical_snapshot_sha256") != "1d61cb78c839efb54b677440d3b94daa8d82e339f5a7bed0d2b05a761f8dfba4":
        raise ValueError("Paired report references an unexpected source snapshot")
    frame = _load(input_path)
    corrected, trace = rolling_correct(frame)
    predictions = [
        "ensemble", "active_global_mean_bias_corrected",
        "active_empirical_bayes_corrected", "candidate_shared", "persistence_active",
    ]
    report = {
        "experiment": "causal_online_bias_correction_of_active_daily_ensemble",
        "evidence_status": "sequential_historical_diagnostic_not_prospective_or_promotion_evidence",
        "holdout_labels_used": False,
        "production_activated": False,
        "input": {
            "paired_predictions": {"path": str(input_path), "sha256": _sha256(input_path)},
            "paired_report": {"path": str(input_report_path), "sha256": _sha256(input_report_path)},
            "canonical_snapshot_sha256": source_report["canonical_snapshot_sha256"],
        },
        "configuration": {
            "minimum_prior_forecast_origins": MIN_PRIOR_ORIGINS,
            "minimum_prior_rows": MIN_HISTORY_ROWS,
            "availability_rule": "forecast_origin < current origin and target_date <= current origin",
            "global_correction": "per-lead mean of prior active prediction-minus-actual residuals",
            "series_correction": "per-series/lead empirical-Bayes mean residual shrunk toward prior global per-lead mean",
            "negative_price_floor_php": 0.01,
            "unsupported_history_behavior": "raw active forecast; no correction",
        },
        "availability_limit": (
            "Target-date completion is used as an availability proxy. The source snapshot has no immutable ingestion timestamps, "
            "so actual arrival before a simulated origin cannot be proven."
        ),
        "origin_calibration_trace": trace,
        "metrics": _summary(corrected, predictions),
        "test_reuse_caveat": (
            "The historical test origins have been reused by earlier research. This fixed, causal online rule does not fit on "
            "the current/future target rows, but the aggregate is development evidence only; prospective evaluation is still required."
        ),
    }
    output_dir.mkdir(parents=True, exist_ok=False)
    report["output_dir"] = str(output_dir)
    (output_dir / "report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    saved = corrected.copy()
    for column in ("forecast_origin", "target_date"):
        saved[column] = pd.to_datetime(saved[column]).dt.strftime("%Y-%m-%d")
    saved.to_csv(output_dir / "predictions.csv", index=False)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--input-report", type=Path, default=DEFAULT_INPUT_REPORT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    report = run(args.input, args.input_report, args.output_root)
    print(json.dumps({
        "rows": report["metrics"]["n_rows"],
        "origins": report["metrics"]["origins"],
        "metrics": report["metrics"]["aggregate"],
        "correction_trace": report["origin_calibration_trace"],
        "report": str(Path(report["output_dir"]) / "report.json"),
    }, indent=2))


if __name__ == "__main__":
    main()
