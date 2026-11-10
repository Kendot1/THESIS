"""Report acceptance and relative-error metrics on saved historical outputs.

This is a reporting diagnostic only. It does not select a model, read the
sealed prospective holdout, or change any production artifact.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from utils.metrics import compute_all_metrics


HORIZONS = ("daily", "weekly", "monthly")
REQUIRED_WITHIN_5_PERCENT_ACCURACY_PCT = 95.0
RUN_MATCH_KEYS = ("series", "forecast_origin", "target_start", "target_end", "lead")


def _score(frame: pd.DataFrame, actual: str, prediction: str) -> dict:
    pairs = frame[[actual, prediction]].dropna()
    metrics = compute_all_metrics(
        pairs[actual].to_numpy(dtype=float),
        pairs[prediction].to_numpy(dtype=float),
    )
    within_5_percent_accuracy = metrics["within_5_percent_accuracy_pct"]
    secondary_shortfalls = {
        "mae_php": max(0.0, metrics["mae"] - 5.0),
        "rmse_php": max(0.0, metrics["rmse"] - 5.0),
        "mape_pct": max(0.0, metrics["mape"] - 5.0)
        if metrics["mape"] is not None else None,
    }
    meets_secondary_targets = (
        metrics["mae"] <= 5.0 and metrics["rmse"] <= 5.0
        and metrics["mape"] is not None and metrics["mape"] <= 5.0
    )
    return {
        "n": metrics["n"],
        "within_5_php_count": metrics["within_5_php_count"],
        "within_5_php_sample_count": metrics["within_5_php_sample_count"],
        "within_5_php_accuracy_pct": metrics["within_5_php_accuracy_pct"],
        "within_5_php_tolerance": metrics["within_5_php_tolerance"],
        "within_5_percent_count": metrics["within_5_percent_count"],
        "within_5_percent_sample_count": metrics["within_5_percent_sample_count"],
        "within_5_percent_accuracy_pct": metrics["within_5_percent_accuracy_pct"],
        "prediction_success": metrics["prediction_success"],
        "success_tolerance": metrics["success_tolerance"],
        "required_within_5_percent_accuracy_pct": REQUIRED_WITHIN_5_PERCENT_ACCURACY_PCT,
        "primary_target_shortfall_pp": (
            max(0.0, REQUIRED_WITHIN_5_PERCENT_ACCURACY_PCT - within_5_percent_accuracy)
            if within_5_percent_accuracy is not None else None
        ),
        "secondary_threshold_shortfall": secondary_shortfalls,
        "meets_primary_target": (
            within_5_percent_accuracy is not None
            and within_5_percent_accuracy >= REQUIRED_WITHIN_5_PERCENT_ACCURACY_PCT
        ),
        "meets_secondary_targets": meets_secondary_targets,
        "meets_all_user_thresholds": (
            within_5_percent_accuracy is not None
            and within_5_percent_accuracy >= REQUIRED_WITHIN_5_PERCENT_ACCURACY_PCT
            and meets_secondary_targets
        ),
        "within_10_count": metrics["within_10_count"],
        "within_10_sample_count": metrics["within_10_sample_count"],
        "within_10_accuracy_pct": metrics["within_10_accuracy_pct"],
        "mae_php": metrics["mae"],
        "rmse_php": metrics["rmse"],
        "mape_pct": metrics["mape"],
    }


def _paired_scores(
    frame: pd.DataFrame,
    actual: str,
    predictions: dict[str, str],
) -> dict:
    common = frame[[actual, *predictions.values()]].dropna()
    return {
        "matched_rows": int(len(common)),
        "models": {
            name: _score(common, actual, column)
            for name, column in predictions.items()
        },
    }


def _strategy_scores(frame: pd.DataFrame) -> dict:
    required = {"actual", "persistence", "candidate_shared", "candidate_per_lead"}
    missing = required - set(frame.columns)
    if missing:
        return {
            "available": False,
            "reason": "Only the selected candidate strategy was fit on this split",
        }
    common = frame[[
        "actual", "persistence", "candidate_shared", "candidate_per_lead",
    ]].dropna()
    return {
        "available": True,
        "matched_rows": int(len(common)),
        "models": {
            "shared": _score(common, "actual", "candidate_shared"),
            "per_lead": _score(common, "actual", "candidate_per_lead"),
            "persistence": _score(common, "actual", "persistence"),
        },
    }


def _grouped_scores(
    frame: pd.DataFrame,
    group_column: str,
    actual: str,
    predictions: dict[str, str],
) -> dict:
    common = frame[[group_column, actual, *predictions.values()]].dropna()
    report = {}
    for value, group in common.groupby(group_column, sort=True):
        report[str(value)] = {
            name: _score(group, actual, column)
            for name, column in predictions.items()
        }
    return report


def compare_candidate_runs(reference_dir: Path, candidate_dir: Path) -> dict:
    """Compare candidate runs on identical observed test targets only."""
    reference_summary = json.loads(
        (reference_dir / "summary.json").read_text(encoding="utf-8"))
    candidate_summary = json.loads(
        (candidate_dir / "summary.json").read_text(encoding="utf-8"))
    comparison = {}
    for horizon in HORIZONS:
        reference_strategy = reference_summary["horizons"][horizon]["selected_strategy"]
        candidate_strategy = candidate_summary["horizons"][horizon]["selected_strategy"]
        reference_frame = pd.read_csv(reference_dir / horizon / "test_predictions.csv")
        candidate_frame = pd.read_csv(candidate_dir / horizon / "test_predictions.csv")
        reference_column = f"candidate_{reference_strategy}"
        candidate_column = f"candidate_{candidate_strategy}"
        left = reference_frame[[*RUN_MATCH_KEYS, "actual", "persistence", reference_column]]
        right = candidate_frame[[*RUN_MATCH_KEYS, "actual", "persistence", candidate_column]]
        matched = left.merge(
            right, on=list(RUN_MATCH_KEYS), how="inner",
            suffixes=("_reference", "_candidate"), validate="one_to_one")
        reference_prediction_column = (
            f"{reference_column}_reference"
            if reference_column == candidate_column else reference_column)
        candidate_prediction_column = (
            f"{candidate_column}_candidate"
            if reference_column == candidate_column else candidate_column)
        if matched.empty:
            raise ValueError(f"Candidate runs have no matched {horizon} targets")
        if not np.allclose(
                matched["actual_reference"], matched["actual_candidate"],
                rtol=0, atol=1e-10):
            raise ValueError(f"Candidate runs disagree on matched {horizon} actual labels")
        if not np.allclose(
                matched["persistence_reference"], matched["persistence_candidate"],
                rtol=0, atol=1e-10):
            raise ValueError(f"Candidate runs disagree on matched {horizon} persistence")
        score_frame = pd.DataFrame({
            "actual": matched["actual_reference"],
            "reference": matched[reference_prediction_column],
            "candidate": matched[candidate_prediction_column],
            "persistence": matched["persistence_reference"],
        })
        score_frame = score_frame.dropna()
        comparison[horizon] = {
            "reference_strategy": reference_strategy,
            "candidate_strategy": candidate_strategy,
            "reference_test_rows": int(len(reference_frame)),
            "candidate_test_rows": int(len(candidate_frame)),
            "matched_rows": int(len(score_frame)),
            "paired_models": _paired_scores(
                score_frame,
                "actual",
                {"reference_candidate": "reference", "new_candidate": "candidate",
                 "persistence": "persistence"},
            ),
        }
    return {
        "reference_run": str(reference_dir),
        "candidate_run": str(candidate_dir),
        "join_keys": list(RUN_MATCH_KEYS),
        "selection_or_promotion": False,
        "comparison": comparison,
        "warning": "The historical test windows were reused in development; this paired comparison is diagnostic only.",
    }


def build_report(candidate_dir: Path, baseline_validation: Path) -> dict:
    summary_path = candidate_dir / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    active_validation = pd.read_csv(baseline_validation)

    horizons = {}
    for horizon in HORIZONS:
        definition = summary["horizons"][horizon]
        strategy = definition["selected_strategy"]
        candidate_column = f"candidate_{strategy}"
        horizon_dir = candidate_dir / horizon
        splits = {}
        for split in ("validation", "test"):
            frame = pd.read_csv(horizon_dir / f"{split}_predictions.csv")
            comparable = frame.dropna(subset=[candidate_column, "actual", "persistence"])
            splits[split] = {
                "candidate_strategy": strategy,
                "candidate_vs_persistence_same_rows": _paired_scores(
                    comparable,
                    "actual",
                    {"candidate": candidate_column, "persistence": "persistence"},
                ),
                "shared_vs_per_lead_vs_persistence_same_rows": _strategy_scores(frame),
                "by_lead": _grouped_scores(
                    comparable, "lead", "actual",
                    {"candidate": candidate_column, "persistence": "persistence"},
                ),
                "by_series": _grouped_scores(
                    comparable, "series", "actual",
                    {"candidate": candidate_column, "persistence": "persistence"},
                ),
            }
        horizons[horizon] = splits

    active_prediction_paths = {
        "daily": candidate_dir / "active_daily" / "matched_predictions.csv",
        "weekly": candidate_dir / "active_period_weekly" / "matched_predictions.csv",
        "monthly": candidate_dir / "active_period_monthly" / "matched_predictions.csv",
    }
    has_active_replay = all(path.is_file() for path in active_prediction_paths.values())
    if has_active_replay:
        daily_path = pd.read_csv(active_prediction_paths["daily"])
        weekly_path = pd.read_csv(active_prediction_paths["weekly"])
        monthly_path = pd.read_csv(active_prediction_paths["monthly"])

    matched_active = {
        "daily": {
            "actual": "actual",
            "step": "lead",
            "predictions": {"direct_candidate": "candidate", "active_ensemble": "ensemble",
                            "persistence": "persistence"},
            "frame": daily_path,
        },
        "weekly": {
            "actual": "actual_candidate",
            "step": "forecast_step",
            "predictions": {"direct_candidate": "direct_candidate",
                            "active_published_path": "active_published_path",
                            "persistence": "persistence"},
            "frame": weekly_path,
        },
        "monthly": {
            "actual": "actual_candidate",
            "step": "forecast_step",
            "predictions": {"direct_candidate": "direct_candidate",
                            "active_published_path": "active_published_path",
                            "persistence": "persistence"},
            "frame": monthly_path,
        },
    } if has_active_replay else {}

    matched_active_scores = {
        "daily": _paired_scores(
            daily_path,
            "actual",
            {"direct_candidate": "candidate", "active_ensemble": "ensemble",
             "persistence": "persistence"},
        ),
        "weekly": _paired_scores(
            weekly_path,
            "actual_candidate",
            {"direct_candidate": "direct_candidate",
             "active_published_path": "active_published_path",
             "persistence": "persistence"},
        ),
        "monthly": _paired_scores(
            monthly_path,
            "actual_candidate",
            {"direct_candidate": "direct_candidate",
             "active_published_path": "active_published_path",
             "persistence": "persistence"},
        ),
    } if has_active_replay else {
        "available": False,
        "reason": "No matched incumbent published-path replay is stored with this run.",
    }
    matched_active_slices = {
        horizon: {
            "by_lead_or_period_step": _grouped_scores(
                item["frame"], item["step"], item["actual"], item["predictions"]),
            "by_series": _grouped_scores(
                item["frame"], "series", item["actual"], item["predictions"]),
        }
        for horizon, item in matched_active.items()
    } if has_active_replay else {"available": False}

    return {
        "primary_user_target": {
            "metric": "percentage of forecast rows with absolute percentage error <= 5%",
            "required_accuracy_pct": 95.0,
            "note": "Zero and near-zero actuals are excluded from the relative-error denominator.",
        },
        "reported_metrics": [
            "within_5_php_accuracy_pct",
            "within_5_percent_accuracy_pct",
            "within_10_accuracy_pct",
            "mae_php",
            "rmse_php",
            "mape_pct",
        ],
        "metric_implementation": "model_trainer.utils.metrics.compute_all_metrics",
        "user_stated_secondary_thresholds": {
            "mae_php_max": 5.0,
            "rmse_php_max": 5.0,
            "mape_pct_max": 5.0,
        },
        "near_zero_actual_policy": "excluded from relative-error denominator per shared metric implementation",
        "selection_or_promotion": False,
        "sealed_holdout_labels_read": False,
        "source_snapshot_sha256": summary["source_snapshot_sha256"],
        "active_app_validation_snapshot": {
            "model_run_id": "20261001T025925Z_0661960a",
            "score": _score(active_validation, "actual", "ensemble"),
            "expected_snapshot_within_10_pct": 83.24049090434329,
            "expected_snapshot_within_5_percent_pct": 69.80154930803377,
        },
        "candidate_by_horizon": horizons,
        "matched_active_published_path": matched_active_scores,
        "matched_active_by_lead_and_series": matched_active_slices,
        "warning": (
            "Historical validation/test windows were used in development; these "
            "results are diagnostics, not fresh promotion evidence."
        ),
    }


def main() -> None:
    repository = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidate-dir", type=Path,
        default=repository / "audits/foodcast_accuracy_20261015/horizon_models_v3",
    )
    parser.add_argument(
        "--baseline-validation", type=Path,
        default=repository / "model_trainer/artifacts_v2/runs/20261001T025925Z_0661960a/validation_forecasts.csv",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--reference-dir", type=Path)
    args = parser.parse_args()

    report = build_report(args.candidate_dir, args.baseline_validation)
    if args.reference_dir:
        report["paired_candidate_run_comparison"] = compare_candidate_runs(
            args.reference_dir.resolve(), args.candidate_dir.resolve())
    serialized = json.dumps(report, indent=2, allow_nan=False)
    if args.output:
        output = args.output.resolve()
        if output.exists():
            raise FileExistsError(f"Refusing to overwrite within-10 report: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
