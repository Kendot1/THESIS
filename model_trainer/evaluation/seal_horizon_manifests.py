"""Add checksum-bound inference manifests beside legacy horizon artifacts.

The original experiment manifests remain untouched. New inference manifests
are sidecars that declare the feature/target contract and bind it to those
original manifests, model files, and evaluation records.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import lightgbm as lgb

from evaluation.horizon_specific import (
    CATEGORICAL_COLUMNS,
    HOLDOUT_START,
    MAX_INPUT_AGE_DAYS,
    SPECS,
    sha256,
)


def _model_schema(model_dir: Path, model_files: dict[str, str]) -> dict:
    columns = None
    categories = None
    for filename in model_files.values():
        path = model_dir / filename
        if not path.is_file():
            raise FileNotFoundError(path)
        model = lgb.Booster(model_file=str(path))
        model_columns = list(model.feature_name())
        embedded = model.pandas_categorical
        if (not model_columns or not embedded
                or len(embedded) != len(CATEGORICAL_COLUMNS)):
            raise ValueError(f"Model has no complete feature/category schema: {filename}")
        model_categories = {
            key: [str(value) for value in values]
            for key, values in zip(CATEGORICAL_COLUMNS, embedded)
        }
        if columns is None:
            columns, categories = model_columns, model_categories
        elif columns != model_columns or categories != model_categories:
            raise ValueError("Per-lead model files disagree on their inference schema")
    return {
        "columns": columns,
        "categorical_columns": list(CATEGORICAL_COLUMNS),
        "categories": categories,
    }


def seal_run(run_dir: Path) -> dict:
    run_dir = Path(run_dir).resolve()
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    profile = json.loads((run_dir / "dataset_profile.json").read_text(encoding="utf-8"))
    if summary.get("source_snapshot_sha256") != profile.get("snapshot_sha256"):
        raise ValueError("Dataset profile and experiment summary use different snapshots")
    if profile.get("raw_date_max") is None or profile["raw_date_max"] >= HOLDOUT_START.date().isoformat():
        raise ValueError("Candidate source snapshot reaches the sealed prospective holdout")

    result = {}
    for horizon, spec in SPECS.items():
        horizon_dir = run_dir / horizon
        report_path = horizon_dir / "report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        strategy = report.get("selected_strategy")
        model_dir = horizon_dir / str(strategy)
        parent_path = model_dir / "manifest.json"
        if not parent_path.is_file():
            raise FileNotFoundError(parent_path)
        if (model_dir / "inference_manifest.json").exists():
            raise FileExistsError(f"Refusing to overwrite inference manifest in {model_dir}")
        parent = json.loads(parent_path.read_text(encoding="utf-8"))
        if parent.get("horizon") != horizon or parent.get("strategy") != strategy:
            raise ValueError(f"{horizon} parent manifest does not match its report")
        if parent.get("source_snapshot_sha256") != summary["source_snapshot_sha256"]:
            raise ValueError(f"{horizon} model and report use different dataset snapshots")
        model_files = parent.get("model_files", {})
        expected_keys = ({"shared"} if strategy == "shared" else
                         {str(lead) for lead in range(1, spec.steps + 1)})
        if set(model_files) != expected_keys:
            raise ValueError(f"{horizon} model set does not cover the full horizon")
        schema = _model_schema(model_dir, model_files)
        test_origins = report.get("origins", {}).get("test", [])
        if not test_origins:
            raise ValueError(f"{horizon} report does not identify its test origins")

        target = {
            "frequency": spec.frequency,
            "target": (
                "observed price on each target calendar date" if spec.frequency == "daily"
                else "mean of valid observed prices within the target period"
            ),
            "week_boundary": "Monday through Sunday" if spec.frequency == "weekly" else None,
            "month_boundary": "calendar month" if spec.frequency == "monthly" else None,
            "minimum_coverage": spec.minimum_coverage,
        }
        manifest = {
            "schema_version": 2,
            "artifact_role": "candidate",
            "horizon": horizon,
            "strategy": strategy,
            "source_snapshot_sha256": summary["source_snapshot_sha256"],
            "source_data_as_of": profile["raw_date_max"],
            "steps": spec.steps,
            "target_definition": target,
            "selection": report.get("strategy_selection_policy"),
            "final_test_origin_used_for_round_trip": test_origins[-1],
            "feature_schema": schema,
            "input_contract": {
                "maximum_last_observation_age_days": MAX_INPUT_AGE_DAYS,
                "history_lags": list(spec.history_lags),
                "rolling_windows": list(spec.rolling_windows),
                "features_use_only_periods_ending_on_or_before_origin": True,
            },
            "prediction_transform": {
                "target": "actual / origin_anchor - 1",
                "prediction": "max(0.01, origin_anchor * (1 + predicted_relative_target))",
            },
            "holdout_start": HOLDOUT_START.date().isoformat(),
            "prospective_holdout_labels_read": False,
            "model_files": model_files,
            "model_sha256": {
                key: sha256(model_dir / filename)
                for key, filename in model_files.items()
            },
            "parent_manifest_file": "manifest.json",
            "parent_manifest_sha256": sha256(parent_path),
            "evaluation_report_sha256": sha256(report_path),
            "test_predictions_sha256": sha256(horizon_dir / "test_predictions.csv"),
            "production_activated": False,
        }
        path = model_dir / "inference_manifest.json"
        path.write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        result[horizon] = {
            "inference_manifest": str(path),
            "sha256": sha256(path),
            "model_count": len(model_files),
        }
    return {
        "status": "sealed",
        "run_dir": str(run_dir),
        "source_snapshot_sha256": summary["source_snapshot_sha256"],
        "horizons": result,
        "production_activated": False,
    }


def main() -> None:
    repository = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-dir", type=Path,
        default=repository / "audits/foodcast_accuracy_20261015/horizon_models_v2",
    )
    args = parser.parse_args()
    print(json.dumps(seal_run(args.run_dir), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
