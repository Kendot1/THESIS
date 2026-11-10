"""Score a parity-clean active daily replay against origin-known persistence."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from data.preprocessor import DataPreprocessor, SERIES_KEY
from evaluation.dense_active_interval_replay import HOLDOUT_START, KEYS, origin_schedule
from utils.metrics import compute_all_metrics


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def origin_known_persistence(replay: pd.DataFrame, clean: pd.DataFrame) -> pd.DataFrame:
    """Attach each series' most recent observed price on/before forecast origin."""
    replay = replay.copy()
    replay["origin"] = pd.to_datetime(replay.origin).dt.normalize()
    replay["date"] = pd.to_datetime(replay.date).dt.normalize()
    if replay.empty or replay.duplicated(KEYS).any():
        raise ValueError("Replay is empty or has duplicate forecast keys")
    history = clean.loc[clean.is_observed & clean.observed_price.notna(),
                        SERIES_KEY + ["report_date", "observed_price"]].copy()
    history["series"] = history[SERIES_KEY].astype(str).agg("||".join, axis=1)
    history = history[["series", "report_date", "observed_price"]]
    history = history.rename(columns={"report_date": "origin",
                                      "observed_price": "persistence"})
    if history.duplicated(["series", "origin"]).any():
        raise ValueError("Duplicate observed series-date history")
    out = pd.merge_asof(
        replay.sort_values("origin"), history.sort_values("origin"),
        on="origin", by="series", direction="backward", allow_exact_matches=True)
    if out.persistence.isna().any():
        raise ValueError("Forecast has no origin-known persistence anchor")
    if (out.date <= out.origin).any():
        raise ValueError("Forecast target is not after origin")
    return out.sort_values(KEYS).reset_index(drop=True)


def _score(rows: pd.DataFrame, prediction: str) -> dict:
    result = compute_all_metrics(rows.actual, rows[prediction])
    result["mean_signed_error_php"] = float(
        np.mean(rows[prediction].to_numpy(dtype=float)
                - rows.actual.to_numpy(dtype=float)))
    return result


def score(replay: pd.DataFrame, clean: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    _, evaluation_origins = origin_schedule()
    rows = replay.loc[pd.to_datetime(replay.origin).isin(evaluation_origins)].copy()
    if rows.empty or pd.to_datetime(rows.date).max() >= HOLDOUT_START:
        raise ValueError("No eligible pre-holdout evaluation targets")
    rows = origin_known_persistence(rows, clean)
    if (not np.isfinite(rows.actual.to_numpy(dtype=float)).all()
            or not np.isfinite(rows.ensemble_path.to_numpy(dtype=float)).all()):
        raise ValueError("Scored replay contains nonfinite actuals or predictions")
    products = {}
    for series, subset in rows.groupby("series", sort=True):
        products[str(series)] = {
            "active": _score(subset, "ensemble_path"),
            "persistence": _score(subset, "persistence"),
        }
    macro = {}
    for model in ("active", "persistence"):
        macro[model] = {
            name: float(np.mean([item[model][name] for item in products.values()]))
            for name in ("mae", "rmse", "mape", "within_5_php_accuracy_pct",
                         "mean_signed_error_php")
        }
    report = {
        "evaluation_origin_count": int(rows.origin.nunique()),
        "evaluation_target_count": int(len(rows)),
        "product_count": len(products),
        "evaluation_origin_start": rows.origin.min().date().isoformat(),
        "evaluation_origin_end": rows.origin.max().date().isoformat(),
        "evaluation_target_start": rows.date.min().date().isoformat(),
        "evaluation_target_end": rows.date.max().date().isoformat(),
        "pooled": {
            "active": _score(rows, "ensemble_path"),
            "persistence": _score(rows, "persistence"),
        },
        "macro_equal_product": macro,
        "by_product": products,
        "by_lead": {
            str(int(lead)): {
                "active": _score(subset, "ensemble_path"),
                "persistence": _score(subset, "persistence"),
            }
            for lead, subset in rows.groupby("horizon", sort=True)
        },
    }
    return report, rows


def run(replay_dir: Path, source: Path, output_dir: Path) -> dict:
    replay_dir, source, output_dir = map(Path, (replay_dir, source, output_dir))
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite point-baseline output: {output_dir}")
    replay_report = json.loads((replay_dir / "report.json").read_text(encoding="utf-8"))
    if (replay_report.get("saved_active_forecast_parity_passed") is not True
            or replay_report.get("legacy_source_quality_replay") is not True
            or replay_report.get("source_snapshot_sha256") != _sha256(source)
            or replay_report.get("holdout_labels_used") is not False):
        raise ValueError("Point baseline requires the exact-vintage parity-clean replay")
    raw = json.loads(source.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw = raw.get("rows", raw.get("data"))
    raw = pd.DataFrame(raw)
    if pd.to_datetime(raw.report_date, errors="coerce").max() >= HOLDOUT_START:
        raise ValueError("Source enters sealed prospective holdout")
    clean = DataPreprocessor().validate(raw, apply_source_quality_exclusions=False)
    replay_path = replay_dir / "replay_observed_targets.csv"
    observed = pd.read_csv(replay_path, float_precision="round_trip")
    comparison, rows = score(observed, clean)
    report = {
        "experiment": "dense_active_point_vs_origin_known_persistence",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "script_sha256": _sha256(Path(__file__)),
        "replay_report_sha256": _sha256(replay_dir / "report.json"),
        "replay_targets_sha256": _sha256(replay_path),
        "source_sha256": _sha256(source),
        "holdout_labels_used": False,
        "historical_test_reused_for_development": True,
        "production_promotion_permitted": False,
        "availability_caveat": (
            "Persistence uses last report-date-observed price on/before origin. "
            "Immutable source-ingestion vintages are unavailable; overlapping "
            "14-day targets from weekly origins are dependent."
        ),
        "comparison": comparison,
    }
    output_dir.mkdir(parents=True)
    rows.to_csv(output_dir / "paired_targets.csv", index=False)
    (output_dir / "report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay-dir", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    report = run(args.replay_dir, args.source, args.output_dir)
    print(json.dumps({"pooled": report["comparison"]["pooled"],
                      "macro": report["comparison"]["macro_equal_product"]}, indent=2))


if __name__ == "__main__":
    main()
