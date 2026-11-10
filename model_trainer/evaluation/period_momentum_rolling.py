"""Re-score the frozen period-momentum point rule on fixed calendar windows."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from evaluation.period_momentum_point import OUTPUT_ROOT, fit_beta, metric, summarize


ROOT = Path(__file__).resolve().parents[2]
INPUT = OUTPUT_ROOT / "period_momentum_point_v1/all_period_predictions.csv"
PLAN = OUTPUT_ROOT / "period_momentum_rolling_plan.md"
WINDOWS = {
    "weekly": [
        ("2023", "2023-01-08", "2023-12-31"),
        ("2024", "2024-01-07", "2024-12-29"),
        ("2025", "2025-01-05", "2025-12-28"),
        ("2026Q1", "2026-01-04", "2026-03-29"),
        ("2026Q2Q3", "2026-04-05", "2026-08-30"),
    ],
    "monthly": [
        ("2023", "2023-01-31", "2023-12-31"),
        ("2024", "2024-01-31", "2024-12-31"),
        ("2025", "2025-01-31", "2025-12-31"),
        ("2026Q1", "2026-01-31", "2026-03-31"),
        ("2026AprAug", "2026-04-30", "2026-08-31"),
    ],
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def split_window(horizon_rows: pd.DataFrame, start: str | pd.Timestamp,
                 end: str | pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame]:
    start, end = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()
    calibration = horizon_rows.loc[
        horizon_rows.target_end.lt(start) & horizon_rows.forecast_origin.lt(start)
    ].copy()
    evaluation = horizon_rows.loc[
        horizon_rows.forecast_origin.between(start, end, inclusive="both")
    ].copy()
    if (calibration.empty or evaluation.empty
            or calibration.target_end.max() >= evaluation.forecast_origin.min()
            or evaluation.target_end.max() >= pd.Timestamp("2026-10-06")
            or evaluation.duplicated(
                ["series", "forecast_origin", "lead", "target_start", "target_end"]).any()):
        raise ValueError("Invalid calibration/evaluation split")
    return calibration, evaluation


def run(input_path: Path, plan_path: Path, output_dir: Path) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite rolling score: {output_dir}")
    frame = pd.read_csv(input_path, float_precision="round_trip")
    for column in ("forecast_origin", "target_start", "target_end"):
        frame[column] = pd.to_datetime(frame[column]).dt.normalize()
    scored, report_windows = [], {}
    for horizon, windows in WINDOWS.items():
        horizon_rows = frame.loc[frame.horizon.eq(horizon)].copy()
        for label, start_text, end_text in windows:
            start, end = pd.Timestamp(start_text), pd.Timestamp(end_text)
            try:
                calibration, evaluation = split_window(horizon_rows, start, end)
            except ValueError as exc:
                raise ValueError(f"Invalid calibration/evaluation split: {horizon} {label}") from exc
            fit = fit_beta(calibration, horizon)
            x = evaluation.return_1.to_numpy(dtype=float)
            if horizon == "weekly":
                x = x * evaluation.lead.to_numpy(dtype=float)
            response = np.where(np.isfinite(x), fit["beta"] * x, 0.0)
            evaluation["momentum_point"] = np.maximum(
                0.01, evaluation.persistence.to_numpy(dtype=float) * (1.0 + response))
            evaluation["momentum_applied"] = np.isfinite(evaluation.return_1)
            evaluation["rolling_window"] = label
            if not np.isfinite(evaluation.momentum_point).all():
                raise ValueError("Nonfinite rolling momentum forecast")
            base = summarize(evaluation, "persistence")
            candidate = summarize(evaluation, "momentum_point")
            product_changes = []
            for series, method in candidate["by_series"].items():
                baseline = base["by_series"][series]["mae_php"]
                change = ((baseline - method["mae_php"]) / baseline * 100
                          if baseline > 0 else 0.0)
                product_changes.append({"series": series,
                                        "error_reduction_mae_pct": float(change),
                                        "persistence_mae_php": baseline,
                                        "momentum_mae_php": method["mae_php"]})
            report_windows[f"{horizon}_{label}"] = {
                "horizon": horizon, "label": label,
                "evaluation_origin_start": evaluation.forecast_origin.min().date().isoformat(),
                "evaluation_origin_end": evaluation.forecast_origin.max().date().isoformat(),
                "calibration_targets": int(len(calibration)),
                "calibration_origins": int(calibration.forecast_origin.nunique()),
                "calibration_last_target": calibration.target_end.max().date().isoformat(),
                "evaluation_targets": int(len(evaluation)),
                "evaluation_origins": int(evaluation.forecast_origin.nunique()),
                "signal_support_pct": float(evaluation.momentum_applied.mean() * 100),
                "fit": fit,
                "persistence": base,
                "momentum": candidate,
                "products_with_over_10pct_mae_deterioration": int(
                    sum(item["error_reduction_mae_pct"] < -10 for item in product_changes)),
                "product_changes": product_changes,
            }
            scored.append(evaluation)
    result = pd.concat(scored, ignore_index=True)
    report = {"experiment": "fixed_rule_period_momentum_rolling_calendar_windows",
              "input_sha256": sha256(input_path), "plan_sha256": sha256(plan_path),
              "script_sha256": sha256(Path(__file__)),
              "window_outcomes_previously_seen_in_other_research": True,
              "holdout_labels_used": False, "production_promotion_permitted": False,
              "windows": report_windows}
    output_dir.mkdir(parents=True)
    result.to_csv(output_dir / "rolling_predictions.csv", index=False)
    (output_dir / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n",
                                             encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=INPUT)
    parser.add_argument("--plan", type=Path, default=PLAN)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.input, args.plan, args.output_dir)
    print(json.dumps({name: {"beta": item["fit"]["beta"],
                             "targets": item["evaluation_targets"],
                             "persistence": item["persistence"]["pooled"],
                             "momentum": item["momentum"]["pooled"],
                             "macro_persistence": item["persistence"]["macro_equal_series"],
                             "macro_momentum": item["momentum"]["macro_equal_series"],
                             "products_over_10pct_worse": item[
                                 "products_with_over_10pct_mae_deterioration"]}
                      for name, item in report["windows"].items()}, indent=2))


if __name__ == "__main__":
    main()
