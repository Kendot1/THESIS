"""Historical, validation-only per-series switch between direct and persistence.

This is a research diagnostic on a previously reused test partition. It does
not fit a new model, calibrate intervals, or permit production promotion.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from utils.metrics import compute_all_metrics


HORIZONS = ("daily", "weekly", "monthly")
KEY = ("series", "forecast_origin", "target_start", "target_end", "lead")
MIN_VALIDATION_ORIGINS = 6


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_predictions(path: Path, prediction: str) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = set(KEY) | {"actual", "persistence", prediction, "priority_product"}
    if not required.issubset(frame):
        raise ValueError(f"Missing columns in {path}: {sorted(required - set(frame))}")
    if frame.empty or frame.duplicated(list(KEY)).any():
        raise ValueError(f"Empty or duplicate prediction keys in {path}")
    for column in ("actual", "persistence", prediction):
        values = pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float)
        if not np.isfinite(values).all() or (values <= 0).any():
            raise ValueError(f"Invalid {column} values in {path}")
    if (pd.to_datetime(frame.target_start) <= pd.to_datetime(frame.forecast_origin)).any():
        raise ValueError(f"Nonfuture target in {path}")
    if (pd.to_datetime(frame.target_end) < pd.to_datetime(frame.target_start)).any():
        raise ValueError(f"Reversed target period in {path}")
    return frame


def select_series(validation: pd.DataFrame, prediction: str) -> dict[str, dict]:
    """Switch only with six earlier origins and strictly better MAE and RMSE."""
    result = {}
    for series, group in validation.groupby("series", sort=True):
        actual = group.actual.to_numpy(dtype=float)
        candidate = group[prediction].to_numpy(dtype=float)
        persistence = group.persistence.to_numpy(dtype=float)
        candidate_mae = float(np.mean(np.abs(candidate - actual)))
        persistence_mae = float(np.mean(np.abs(persistence - actual)))
        candidate_rmse = float(np.sqrt(np.mean(np.square(candidate - actual))))
        persistence_rmse = float(np.sqrt(np.mean(np.square(persistence - actual))))
        origins = int(group.forecast_origin.nunique())
        use_candidate = (
            origins >= MIN_VALIDATION_ORIGINS
            and candidate_mae < persistence_mae
            and candidate_rmse < persistence_rmse
        )
        result[series] = {
            "use_candidate": bool(use_candidate),
            "validation_rows": int(len(group)),
            "validation_origins": origins,
            "candidate_mae_php": candidate_mae,
            "candidate_rmse_php": candidate_rmse,
            "persistence_mae_php": persistence_mae,
            "persistence_rmse_php": persistence_rmse,
        }
    return result


def metrics(frame: pd.DataFrame, prediction: str) -> dict:
    actual = frame.actual.to_numpy(dtype=float)
    predicted = frame[prediction].to_numpy(dtype=float)
    result = compute_all_metrics(actual, predicted)
    return {
        "n": int(result["n"]),
        "mae_php": result["mae"],
        "rmse_php": result["rmse"],
        "mape_pct": result["mape"],
        "within_5_php_pct": result["within_5_php_accuracy_pct"],
        "bias_php": float(np.mean(predicted - actual)),
    }


def comparisons(frame: pd.DataFrame) -> dict:
    scores = {name: metrics(frame, name) for name in ("gated", "candidate", "persistence")}
    scores["error_reduction_vs_persistence_pct"] = {
        key: (scores["persistence"][key] - scores["gated"][key])
        / scores["persistence"][key] * 100
        if scores["persistence"][key] else None
        for key in ("mae_php", "rmse_php", "mape_pct")
    }
    return scores


def evaluate(validation: pd.DataFrame, test: pd.DataFrame, prediction: str) -> tuple[dict, pd.DataFrame]:
    if pd.to_datetime(validation.target_end).max() >= pd.to_datetime(test.forecast_origin).min():
        raise ValueError("Validation target periods must close before first test origin")
    decisions = select_series(validation, prediction)
    evaluated = test.copy()
    evaluated["candidate"] = evaluated[prediction]
    switches = evaluated.series.map({key: row["use_candidate"] for key, row in decisions.items()})
    evaluated["gated"] = np.where(switches.fillna(False).to_numpy(dtype=bool),
                                  evaluated[prediction], evaluated.persistence)
    by_series = {}
    for series, group in evaluated.groupby("series", sort=True):
        by_series[series] = {
            "choice": "direct" if decisions.get(series, {}).get("use_candidate") else "persistence",
            "validation_support": decisions.get(series),
            "priority_product": bool(group.priority_product.iloc[0]),
            "test": comparisons(group),
        }
    by_lead = {str(int(lead)): comparisons(group)
               for lead, group in evaluated.groupby("lead", sort=True)}
    pooled = comparisons(evaluated)
    pooled["macro_equal_series"] = {
        method: {
            metric: float(np.mean([row["test"][method][metric] for row in by_series.values()]))
            for metric in ("mae_php", "rmse_php", "mape_pct", "within_5_php_pct", "bias_php")
        }
        for method in ("gated", "candidate", "persistence")
    }
    return {
        "selection_policy": (
            "Per series, choose direct only if at least six validation origins and "
            "both validation MAE and RMSE strictly improve on persistence; "
            "otherwise choose persistence. No test outcomes inform choices."
        ),
        "validation_end": str(pd.to_datetime(validation.target_end).max().date()),
        "test_first_origin": str(pd.to_datetime(test.forecast_origin).min().date()),
        "test_last_target": str(pd.to_datetime(test.target_end).max().date()),
        "validation_series": len(decisions),
        "test_series": len(by_series),
        "direct_series": sum(row["choice"] == "direct" for row in by_series.values()),
        "test_only_series": sum(series not in decisions for series in by_series),
        "pooled": pooled,
        "by_lead": by_lead,
        "by_series": by_series,
    }, evaluated


def run(input_dir: Path, output_dir: Path) -> dict:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Refusing nonempty output directory: {output_dir}")
    manifest_path = input_dir / "selection_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("task_scope") != "objective" or manifest.get("holdout_labels_used") is not False:
        raise ValueError("Input experiment must be 14/4/1 and exclude sealed holdout")
    report = {
        "date": "2026-10-18",
        "source_experiment": str(input_dir.resolve()),
        "source_snapshot_sha256": manifest["source_snapshot_sha256"],
        "selection_manifest_sha256": digest(manifest_path),
        "script_sha256": digest(Path(__file__)),
        "production_promotion_permitted": False,
        "limitations": (
            "Previously reused historical test; models were refitted across its origins; "
            "validation-only switches are not prospectively confirmed. No intervals."
        ),
        "horizons": {},
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    for horizon in HORIZONS:
        selected = manifest["selected_strategy_by_horizon"][horizon]
        prediction = f"candidate_{selected}"
        validation_path = input_dir / horizon / "validation_predictions.csv"
        test_path = input_dir / horizon / "test_predictions.csv"
        validation = checked_predictions(validation_path, prediction)
        test = checked_predictions(test_path, prediction)
        if pd.to_datetime(test.target_end).max() >= pd.Timestamp("2026-10-06"):
            raise ValueError("Test would reach sealed holdout")
        result, rows = evaluate(validation, test, prediction)
        result["input_sha256"] = {
            "validation": digest(validation_path), "test": digest(test_path)
        }
        result["selected_direct_strategy"] = selected
        report["horizons"][horizon] = result
        rows[list(KEY) + ["actual", "persistence", prediction, "gated"]].to_csv(
            output_dir / f"{horizon}_paired_predictions.csv", index=False)
    (output_dir / "report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report


def main() -> None:
    repository = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path,
                        default=repository / "audits/foodcast_accuracy_20261017/relative5_test_confirmation_v2")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.input_dir, args.output_dir)
    for name, horizon in report["horizons"].items():
        metric = horizon["pooled"]["error_reduction_vs_persistence_pct"]
        print(f"{name}: {horizon['direct_series']}/{horizon['test_series']} direct; "
              f"MAE {metric['mae_php']:+.2f}%, RMSE {metric['rmse_php']:+.2f}%, "
              f"MAPE {metric['mape_pct']:+.2f}% vs persistence")


if __name__ == "__main__":
    main()
