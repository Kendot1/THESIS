"""Verify saved horizon models reproduce their final recorded test origin.

This is an artifact/inference consistency check, not a new accuracy evaluation.
It reads prediction columns only (not historical test actuals) and refuses a
source snapshot that reaches the sealed prospective holdout.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from data.preprocessor import DataPreprocessor
from evaluation.horizon_specific import (
    HOLDOUT_START,
    HorizonModelBundle,
    load_snapshot,
    sha256,
)


def verify_run(run_dir: Path) -> dict:
    run_dir = Path(run_dir).resolve()
    summary_path = run_dir / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    snapshot = Path(summary["source_snapshot"]).resolve()
    if not snapshot.is_file():
        raise FileNotFoundError(snapshot)
    source_sha = sha256(snapshot)
    if source_sha != summary.get("source_snapshot_sha256"):
        raise ValueError("Source snapshot SHA-256 does not match the experiment summary")

    raw = load_snapshot(snapshot)
    report_dates = pd.to_datetime(raw.report_date, errors="coerce").dropna()
    if report_dates.empty or report_dates.max().normalize() >= HOLDOUT_START:
        raise ValueError("Artifact verification snapshot reaches the sealed holdout")
    clean = DataPreprocessor().validate(raw)

    results = {}
    for horizon in ("daily", "weekly", "monthly"):
        horizon_dir = run_dir / horizon
        report = json.loads((horizon_dir / "report.json").read_text(encoding="utf-8"))
        strategy = report["selected_strategy"]
        test_origins = report.get("origins", {}).get("test", [])
        if not test_origins:
            raise ValueError(f"{horizon} report has no test origins")
        origin = pd.Timestamp(test_origins[-1]).normalize()

        bundle = HorizonModelBundle(horizon_dir / strategy)
        if bundle.horizon != horizon or bundle.strategy != strategy:
            raise ValueError(f"{horizon} artifact manifest does not match the experiment report")
        generated = bundle.forecast(clean, origin)
        prediction_column = f"candidate_{strategy}"
        predictions_path = horizon_dir / "test_predictions.csv"
        prediction_columns = pd.read_csv(predictions_path, nrows=0).columns
        origin_column = "forecast_origin" if "forecast_origin" in prediction_columns else "origin"
        expected = pd.read_csv(
            predictions_path,
            usecols=["series", origin_column, "target_start", prediction_column],
            parse_dates=[origin_column, "target_start"],
        )
        expected = expected.loc[expected[origin_column].eq(origin)].copy()
        if expected.empty:
            raise ValueError(f"No saved {horizon} predictions found for final origin {origin.date()}")
        if expected.duplicated(["series", "target_start"]).any():
            raise ValueError(f"Duplicate saved {horizon} rows at final origin")
        compared = expected.merge(
            generated[["series", "target_start", "predicted_price"]],
            on=["series", "target_start"],
            how="left",
            validate="one_to_one",
        )
        if compared.predicted_price.isna().any():
            missing = int(compared.predicted_price.isna().sum())
            raise ValueError(f"{horizon} artifact omitted {missing} saved prediction rows")
        difference = np.abs(
            compared[prediction_column].to_numpy(dtype=float)
            - compared.predicted_price.to_numpy(dtype=float)
        )
        max_difference = float(difference.max())
        if not np.isfinite(difference).all() or max_difference > 1e-9:
            raise ValueError(f"{horizon} artifact failed prediction round-trip: max delta {max_difference}")

        model_hashes = {
            key: sha256(bundle.model_dir / filename)
            for key, filename in bundle.manifest["model_files"].items()
        }
        results[horizon] = {
            "strategy": strategy,
            "manifest_schema_version": bundle.manifest.get("schema_version", 1),
            "forecast_origin": origin.date().isoformat(),
            "saved_prediction_rows": int(len(expected)),
            "generated_feature_rows": int(len(generated)),
            "matched_saved_rows": int(len(compared)),
            "max_absolute_prediction_delta_php": max_difference,
            "model_sha256": model_hashes,
            "production_activated": bool(bundle.manifest.get("production_activated", False)),
        }

    return {
        "verification": "passed",
        "purpose": "saved candidate artifact and inference round-trip; not an accuracy claim",
        "run_dir": str(run_dir),
        "source_snapshot_sha256": source_sha,
        "feature_pipeline_sha256": sha256(Path(__file__).with_name("horizon_specific.py")),
        "source_data_as_of": report_dates.max().date().isoformat(),
        "sealed_holdout_start": HOLDOUT_START.date().isoformat(),
        "holdout_labels_read": False,
        "horizons": results,
    }


def main() -> None:
    repository = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-dir", type=Path,
        default=repository / "audits/foodcast_accuracy_20261015/horizon_models_v2",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = verify_run(args.run_dir)
    serialized = json.dumps(report, indent=2, allow_nan=False)
    if args.output:
        output = args.output.resolve()
        if output.exists():
            raise FileExistsError(f"Refusing to overwrite verification report: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
