"""Joint nested selection of peer-correction shrinkage and amplitude.

The source validation window has substantial prior research exposure. This
script records a reproducible diagnostic only; it never reads test labels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from evaluation.peer_momentum_diagnostic import evaluate as peer_diagnostic
from evaluation.peer_momentum_hierarchical_correction import (
    LAMBDA_GRID,
    PLAN_PATH as HIERARCHICAL_PLAN,
    SOURCE_DIR,
    add_peer_categories,
    apply_correction,
    fit_hierarchical,
    load_validation,
    score,
    sha256,
    split_origins,
)


ROOT = Path(__file__).resolve().parents[2]
PLAN_PATH = ROOT / "audits" / "foodcast_accuracy_20261018" / "peer_momentum_hierarchical_scaled_plan.md"
DEFAULT_OUTPUT = ROOT / "audits" / "foodcast_accuracy_20261018" / "peer_momentum_hierarchical_scaled_v1"
SCALE_GRID = (0.0, 0.125, 0.25, 0.375, 0.5, 0.75, 1.0)
PRIMARY = ("mae_php", "rmse_php", "mape_pct")
SCOPES = ("all", "vegetables")


def apply_scale(frame: pd.DataFrame, scale: float) -> pd.DataFrame:
    """Apply a frozen scalar to the learned PHP correction, not to the point."""
    if not 0.0 <= scale <= 1.0:
        raise ValueError("Correction scale must be in [0, 1]")
    result = frame.copy()
    result["peer_corrected"] = np.maximum(
        0.01,
        result.candidate_shared.to_numpy(float)
        + scale * result.peer_correction_php.to_numpy(float),
    )
    result["correction_scale"] = float(scale)
    return result


def passes_accuracy_gates(metrics: dict) -> bool:
    """Require all pooled/macro errors to improve and within-5 not to fall."""
    for scope in SCOPES:
        result = metrics[scope]
        base = result["models"]["candidate_shared"]
        candidate = result["models"]["peer_corrected"]
        base_macro = result["macro_equal_series"]["candidate_shared"]
        candidate_macro = result["macro_equal_series"]["peer_corrected"]
        if not all(candidate[key] < base[key] for key in PRIMARY):
            return False
        if not all(candidate_macro[key] < base_macro[key] for key in PRIMARY):
            return False
        if candidate["within_5_php_pct"] < base["within_5_php_pct"]:
            return False
    return True


def choose_tuning_candidate(candidates: list[dict]) -> dict:
    """Pick the best gate-passing inner candidate; conservative tie-breaks."""
    eligible = [item for item in candidates if item["passes_accuracy_gates"]]
    if not eligible:
        return {"shrinkage": 0.0, "scale": 0.0, "selected_baseline_fallback": True}
    winner = min(eligible, key=lambda item: (
        item["vegetable_macro_mae_php"], -item["shrinkage"], item["scale"],
    ))
    return {
        "shrinkage": float(winner["shrinkage"]),
        "scale": float(winner["scale"]),
        "selected_baseline_fallback": False,
        "vegetable_macro_mae_php": float(winner["vegetable_macro_mae_php"]),
    }


def _compact(metrics: dict) -> dict:
    result = {}
    for scope in SCOPES:
        item = metrics[scope]
        result[scope] = {
            "n": item["n"],
            "series_count": item["series_count"],
            "pooled": item["models"],
            "macro_equal_series": item["macro_equal_series"],
        }
    return result


def _fit_and_score(train_rows: pd.DataFrame, peer_rows: pd.DataFrame,
                   score_rows: pd.DataFrame, shrinkage: float, scale: float) -> dict:
    coefficients = fit_hierarchical(
        peer_rows, sorted(train_rows.forecast_origin.unique()), shrinkage)
    candidate = apply_correction(score_rows, peer_rows, coefficients)
    candidate = apply_scale(candidate, scale)
    return candidate


def _final_screen(metrics: dict) -> dict:
    priority_ok = not metrics["priority_series_mae_regressions_over_10_pct"]
    accuracy_ok = passes_accuracy_gates(metrics)
    return {
        "accuracy_gates_passed": bool(accuracy_ok),
        "priority_product_gate_passed": bool(priority_ok),
        "all_numeric_screens_passed": bool(accuracy_ok and priority_ok),
        "promotion_permitted": False,
        "promotion_reason": "Historical validation has prior selection and model-development exposure.",
    }


def run_experiment(source_dir: Path = SOURCE_DIR, output_dir: Path = DEFAULT_OUTPUT) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing output directory: {output_dir}")
    manifest_path = source_dir / "selection_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("task_scope") != "objective"
            or manifest.get("selected_strategy_by_horizon", {}).get("daily") != "shared"
            or manifest.get("holdout_labels_used") is not False):
        raise ValueError("Unexpected or holdout-contaminated source manifest")
    validation_path = source_dir / "daily" / "validation_predictions.csv"
    validation, validation_meta = load_validation(validation_path)
    origins = split_origins(validation)
    _, peer_rows = peer_diagnostic(validation)
    peer_rows = add_peer_categories(validation, peer_rows)

    inner_train = validation.loc[validation.forecast_origin.isin(origins["inner_fit"])]
    inner_tune = validation.loc[validation.forecast_origin.isin(origins["shrinkage_tune"])]
    evaluations = []
    tuning_predictions = {}
    for shrinkage in LAMBDA_GRID:
        for scale in SCALE_GRID:
            candidate = _fit_and_score(inner_train, peer_rows, inner_tune, shrinkage, scale)
            metrics = score(candidate)
            key = (float(shrinkage), float(scale))
            tuning_predictions[key] = candidate
            evaluations.append({
                "shrinkage": float(shrinkage),
                "scale": float(scale),
                "passes_accuracy_gates": passes_accuracy_gates(metrics),
                "vegetable_macro_mae_php": metrics["vegetables"]["macro_equal_series"][
                    "peer_corrected"]["mae_php"],
                "metrics": _compact(metrics),
            })
    selected = choose_tuning_candidate(evaluations)
    chosen_lambda, chosen_scale = selected["shrinkage"], selected["scale"]
    selected_tuning = tuning_predictions.get((chosen_lambda, chosen_scale))
    if selected_tuning is None:
        selected_tuning = apply_scale(inner_tune.assign(peer_correction_php=0.0), 0.0)
    tuning_metrics = score(selected_tuning)

    outer_train = validation.loc[validation.forecast_origin.isin(origins["outer_fit"])]
    outer_gate = validation.loc[validation.forecast_origin.isin(origins["outer_gate"])]
    gate_predictions = _fit_and_score(
        outer_train, peer_rows, outer_gate, chosen_lambda, chosen_scale)
    gate_metrics = score(gate_predictions)
    final_screen = _final_screen(gate_metrics)

    helper_path = Path(__file__).with_name("peer_momentum_hierarchical_correction.py")
    diagnostic_path = Path(__file__).with_name("peer_momentum_diagnostic.py")
    report = {
        "experiment": "scaled_hierarchical_vegetable_peer_momentum_correction",
        "source_snapshot_sha256": manifest.get("source_snapshot_sha256"),
        "source_validation": validation_meta,
        "source_manifest": {"path": str(manifest_path), "sha256": sha256(manifest_path)},
        "source_plan": {"path": str(HIERARCHICAL_PLAN), "sha256": sha256(HIERARCHICAL_PLAN)},
        "plan": {"path": str(PLAN_PATH), "sha256": sha256(PLAN_PATH)},
        "helper_sha256": sha256(helper_path),
        "peer_diagnostic_sha256": sha256(diagnostic_path),
        "script_sha256": sha256(Path(__file__).resolve()),
        "inner_fit_origins": [pd.Timestamp(date).date().isoformat() for date in origins["inner_fit"]],
        "shrinkage_tune_origins": [pd.Timestamp(date).date().isoformat() for date in origins["shrinkage_tune"]],
        "outer_fit_origins": [pd.Timestamp(date).date().isoformat() for date in origins["outer_fit"]],
        "outer_gate_origins": [pd.Timestamp(date).date().isoformat() for date in origins["outer_gate"]],
        "shrinkage_grid": list(LAMBDA_GRID),
        "scale_grid": list(SCALE_GRID),
        "selected_hyperparameters": selected,
        "inner_tuning_candidates": evaluations,
        "inner_tuning_metrics": tuning_metrics,
        "outer_gate_metrics": gate_metrics,
        "outer_gate_screen": final_screen,
        "historical_test_opened": False,
        "sealed_prospective_holdout_read": False,
        "production_changed": False,
        "mape_policy": "MAPE uses positive actuals only; zero actuals remain in PHP-unit metrics",
        "macro_policy": "unweighted mean of per-series MAE/RMSE/MAPE; RMSE averaged after per-series calculation",
        "independence_caveat": (
            "Outer validation dates and the preliminary scale trend were viewed in prior research. "
            "These metrics are retrospective diagnostics and do not qualify promotion."
        ),
    }
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir()
    frames = []
    if not selected["selected_baseline_fallback"]:
        frames.append(selected_tuning.assign(screen="inner_shrinkage_scale_tune"))
    frames.append(gate_predictions.assign(screen="outer_validation_diagnostic"))
    keep = ["series", "forecast_origin", "target_start", "target_end", "lead",
            "actual", "anchor", "product_category", "candidate_shared", "persistence",
            "peer_feature_supported", "peer_correction_php", "correction_scale",
            "peer_corrected", "screen"]
    pd.concat(frames, ignore_index=True)[keep].sort_values(
        ["series", "forecast_origin", "target_start", "target_end", "lead"]
    ).to_csv(output_dir / "paired_predictions.csv", index=False)
    (output_dir / "report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=SOURCE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    report = run_experiment(args.source_dir, args.output_dir)
    print(json.dumps({
        "output_dir": str(args.output_dir),
        "selected_hyperparameters": report["selected_hyperparameters"],
        "outer_gate_screen": report["outer_gate_screen"],
        "all_pooled": report["outer_gate_metrics"]["all"]["models"],
        "vegetable_pooled": report["outer_gate_metrics"]["vegetables"]["models"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
