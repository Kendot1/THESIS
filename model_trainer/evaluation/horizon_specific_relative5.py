"""Isolated horizon-specific run selecting strategy by validation Within-5%.

This changes only strategy selection. Feature construction, training windows,
model parameters, chronological cutoffs, and inference remain those of
``horizon_specific``. The historic test window is reported only as a reused
development diagnostic; it is not used to select the strategy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from evaluation import horizon_specific as pipeline
from utils.metrics import compute_all_metrics


_BASE_METRIC = pipeline._metric
_BASE_REPORT = pipeline._report_result
RELATIVE_TOLERANCE = 0.05

SELECTION_POLICY = (
    "Highest validation percentage of forecasts within 5% relative error; "
    "ties break by lower MAPE, then MAE, then RMSE."
)


def relative5_squared_hinge_grad_hess(y_true, y_pred, weight=None, group=None):
    """Squared hinge objective on forecast error relative to actual price.

    The model target is actual/anchor - 1. Therefore dividing the target-space
    residual by ``1 + y_true`` yields (forecast - actual)/actual exactly.
    """
    actual_relative_to_anchor = np.asarray(y_true, dtype=float).reshape(-1)
    predicted_relative_to_anchor = np.asarray(y_pred, dtype=float).reshape(-1)
    if (actual_relative_to_anchor.shape != predicted_relative_to_anchor.shape
            or not np.isfinite(actual_relative_to_anchor).all()
            or not np.isfinite(predicted_relative_to_anchor).all()):
        raise ValueError("Relative-5 objective inputs must be finite, aligned, and valid")
    if group is not None:
        raise ValueError("Relative-5 regression objective does not accept ranking groups")
    actual_scale = 1.0 + actual_relative_to_anchor
    if (not np.isfinite(actual_scale).all() or (actual_scale <= 0).any()):
        raise ValueError("Relative-5 objective requires positive actual-price scales")
    relative_error = (
        predicted_relative_to_anchor - actual_relative_to_anchor) / actual_scale
    margin = np.maximum(np.abs(relative_error) - RELATIVE_TOLERANCE, 0.0)
    gradient = 2.0 * margin * np.sign(relative_error) / actual_scale
    hessian = np.where(margin > 0.0, 2.0 / np.square(actual_scale), 1e-6)
    if weight is not None:
        sample_weight = np.asarray(weight, dtype=float).reshape(-1)
        if (sample_weight.shape != gradient.shape
                or not np.isfinite(sample_weight).all()
                or (sample_weight < 0).any()):
            raise ValueError("Relative-5 objective weights must be finite, aligned, and nonnegative")
        gradient *= sample_weight
        hessian = np.where(
            sample_weight > 0.0,
            np.maximum(hessian * sample_weight, 1e-12),
            0.0,
        )
    return gradient, hessian


def relative5_miss_pct(y_true, y_pred, anchors):
    """Publisher-scale relative-5% miss rate for anchor-relative predictions."""
    target = np.asarray(y_true, dtype=float).reshape(-1)
    prediction = np.asarray(y_pred, dtype=float).reshape(-1)
    anchor = np.asarray(anchors, dtype=float).reshape(-1)
    if (target.shape != prediction.shape or anchor.shape != target.shape
            or not np.isfinite(target).all() or not np.isfinite(prediction).all()
            or not np.isfinite(anchor).all() or (anchor <= 0).any()):
        raise ValueError("Relative-5 metric inputs must be finite, aligned, and positive")
    actual = anchor * (1.0 + target)
    predicted = np.maximum(0.01, anchor * (1.0 + prediction))
    if (not np.isfinite(actual).all() or (actual <= 0).any()):
        raise ValueError("Relative-5 metric requires positive actual prices")
    relative_error = np.abs(predicted - actual) / actual
    return float(np.mean(relative_error > 0.05) * 100.0)


def choose_strategy(validation_scores: dict[str, dict]) -> str:
    def key(name: str) -> tuple[float, float, float, float, str]:
        score = validation_scores[name]

        def lower_is_better(metric: str) -> float:
            value = score.get(metric)
            return float(value) if value is not None and math.isfinite(value) else math.inf

        hit_rate = score.get("within_5_percent_accuracy_pct")
        hit_rate = float(hit_rate) if hit_rate is not None and math.isfinite(hit_rate) else -math.inf
        return (
            -hit_rate,
            lower_is_better("mape_pct"),
            lower_is_better("mae_php"),
            lower_is_better("rmse_php"),
            name,
        )

    if not validation_scores:
        raise ValueError("No strategy validation scores were supplied")
    return min(validation_scores, key=key)


def _metric_with_relative_hit_rate(frame, prediction: str) -> dict:
    result = _BASE_METRIC(frame, prediction)
    metrics = compute_all_metrics(
        frame["actual"].to_numpy(dtype=float),
        frame[prediction].to_numpy(dtype=float),
    )
    result["within_5_percent_accuracy_pct"] = metrics["within_5_percent_accuracy_pct"]
    result["within_5_percent_count"] = metrics["within_5_percent_count"]
    result["within_5_percent_sample_count"] = metrics["within_5_percent_sample_count"]
    return result


def _report_with_selection_policy(result: dict) -> dict:
    report = _BASE_REPORT(result)
    report["strategy_selection_policy"] = SELECTION_POLICY
    return report


def run(args) -> dict:
    output_dir = Path(args.output_dir).resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Refusing to write experiment into a nonempty directory: {output_dir}")
    original_metric = pipeline._metric
    original_selector = pipeline._select_strategy
    original_report = pipeline._report_result
    pipeline._metric = _metric_with_relative_hit_rate
    pipeline._select_strategy = choose_strategy
    pipeline._report_result = _report_with_selection_policy
    try:
        summary = pipeline.run_cli(args)
    finally:
        pipeline._metric = original_metric
        pipeline._select_strategy = original_selector
        pipeline._report_result = original_report

    selection_path = output_dir / "selection_manifest.json"
    if selection_path.exists():
        raise FileExistsError(f"Refusing to overwrite selection manifest: {selection_path}")
    selection_manifest = {
        "experiment": "horizon_specific_relative5_strategy_selection",
        "selection_policy": SELECTION_POLICY,
        "training_pipeline": str(Path(pipeline.__file__).resolve()),
        "training_pipeline_sha256": hashlib.sha256(
            Path(pipeline.__file__).read_bytes()).hexdigest(),
        "experiment_script_sha256": hashlib.sha256(
            Path(__file__).read_bytes()).hexdigest(),
        "source_snapshot_sha256": summary["source_snapshot_sha256"],
        "holdout_labels_used": False,
        "task_scope": summary.get("task_scope"),
        "test_partition_scored": True,
        "test_end": summary.get("splits", {}).get("test_end"),
        "production_activated": False,
        "selected_strategy_by_horizon": {
            name: report["selected_strategy"]
            for name, report in summary["horizons"].items()
        },
    }
    selection_path.write_text(
        json.dumps(selection_manifest, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    repository = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data", type=Path,
        default=repository / "audits/accuracy_goal_20261011/supabase_food_prices_through_20261005.json",
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=repository / "audits/foodcast_accuracy_20261015/horizon_models_v4_relative5",
    )
    parser.add_argument("--train-end", default="2024-08-26")
    parser.add_argument("--validation-end", default="2025-09-12")
    parser.add_argument("--test-end", default="2026-09-30")
    parser.add_argument("--holdout-start", default=pipeline.HOLDOUT_START.date().isoformat())
    parser.add_argument("--daily-stride", type=int, default=30)
    parser.add_argument("--weekly-stride", type=int, default=4)
    parser.add_argument("--monthly-stride", type=int, default=1)
    parser.add_argument("--horizons", nargs="+", choices=("daily", "weekly", "monthly"),
                        default=("daily", "weekly", "monthly"))
    parser.add_argument(
        "--scope", choices=tuple(pipeline.HORIZON_SPEC_SCOPES), default="objective",
        help="Target lengths to evaluate; objective means daily 14, weekly 4, monthly 1.",
    )
    args = parser.parse_args()
    if min(args.daily_stride, args.weekly_stride, args.monthly_stride) < 1:
        raise ValueError("Origin strides must be positive")
    summary = run(args)
    for name, result in summary["horizons"].items():
        validation = result["validation"]["candidate_strategies"]
        selected = result["selected_strategy"]
        print(
            f"{name}: selected={selected}, "
            f"validation Within-5%={validation[selected]['within_5_percent_accuracy_pct']:.3f}%, "
            f"test MAPE={result['test']['candidate']['mape_pct']:.3f}%"
        )
    print(f"Detailed report: {Path(args.output_dir).resolve() / 'summary.json'}")


if __name__ == "__main__":
    main()
