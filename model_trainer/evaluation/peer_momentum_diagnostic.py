"""Historical check for origin-known cross-vegetable momentum.

Exploratory and non-promotable: only 13 independent origins per partition
exist, test dates have been reused, and source-ingestion timestamps are
unavailable. No model is fitted here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pearson(left, right) -> float | None:
    x, y = np.asarray(left, dtype=float), np.asarray(right, dtype=float)
    valid = np.isfinite(x) & np.isfinite(y)
    if valid.sum() < 4 or np.std(x[valid]) == 0 or np.std(y[valid]) == 0:
        return None
    return float(np.corrcoef(x[valid], y[valid])[0, 1])


def evaluate(frame: pd.DataFrame, *,
             first_origin_inclusive: str = "2024-08-27",
             last_target_exclusive: str = "2025-09-13") -> tuple[dict, pd.DataFrame]:
    required = {"series", "product_category", "forecast_origin", "target_end",
                "lead", "last_observed_age_days", "return_3", "anchor",
                "actual", "candidate_shared"}
    if frame.empty or not required.issubset(frame):
        raise ValueError(f"Empty or missing validation columns: {sorted(required - set(frame))}")
    frame = frame.copy()
    frame["forecast_origin"] = pd.to_datetime(frame.forecast_origin).dt.normalize()
    frame["target_end"] = pd.to_datetime(frame.target_end).dt.normalize()
    if (frame.duplicated(["series", "forecast_origin", "target_end", "lead"]).any()
            or frame.forecast_origin.min() < pd.Timestamp(first_origin_inclusive)
            or frame.forecast_origin.max() >= pd.Timestamp(last_target_exclusive)
            or frame.target_end.max() >= pd.Timestamp(last_target_exclusive)
            or (frame.target_end <= frame.forecast_origin).any()
            or not np.isfinite(frame[["anchor", "actual", "candidate_shared"]]
                               .to_numpy(dtype=float)).all()
            or (frame[["anchor", "actual", "candidate_shared"]] <= 0).any().any()):
        raise ValueError("Invalid, overlapping, or post-validation target rows")
    feature_columns = ["product_category", "return_3", "last_observed_age_days", "anchor"]
    if (frame.groupby(["series", "forecast_origin"], sort=False)[feature_columns]
            .nunique(dropna=False).gt(1).any().any()):
        raise ValueError("Origin features vary across forecast leads")
    origin_features = frame.drop_duplicates(["series", "forecast_origin"])
    vegetables = origin_features.loc[origin_features.product_category.eq("Vegetables")]
    peers = vegetables.loc[vegetables.last_observed_age_days.le(1)
                           & np.isfinite(vegetables.return_3.to_numpy(dtype=float))]
    peer_values = {}
    for origin, group in peers.groupby("forecast_origin", sort=True):
        for row in vegetables.loc[vegetables.forecast_origin.eq(origin)].itertuples():
            others = group.loc[group.series.ne(row.series), "return_3"].to_numpy(dtype=float)
            if len(others) >= 5:
                peer_values[(row.series, origin)] = (float(np.median(others)), int(len(others)))
    frame = frame.loc[frame.product_category.eq("Vegetables")].copy()
    frame["peer_median_return3"] = [
        peer_values.get((row.series, row.forecast_origin), (np.nan, 0))[0]
        for row in frame.itertuples()]
    frame["peer_count"] = [
        peer_values.get((row.series, row.forecast_origin), (np.nan, 0))[1]
        for row in frame.itertuples()]
    frame["relative_residual"] = (frame.actual - frame.candidate_shared) / frame.anchor
    frame["absolute_error_php"] = np.abs(frame.actual - frame.candidate_shared)
    grouped = []
    for (series, origin), group in frame.groupby(["series", "forecast_origin"], sort=True):
        for label, mask in (("days_1_7", group.lead.between(1, 7)),
                            ("days_8_14", group.lead.between(8, 14))):
            block = group.loc[mask]
            if block.empty:
                continue
            grouped.append({
                "series": series, "forecast_origin": origin, "band": label,
                "n": int(len(block)), "peer_count": int(block.peer_count.iloc[0]),
                "peer_median_return3": float(block.peer_median_return3.iloc[0]),
                "own_return3": float(block.return_3.iloc[0]),
                "mean_relative_residual": float(block.relative_residual.mean()),
                "mae_php": float(block.absolute_error_php.mean()),
            })
    rows = pd.DataFrame(grouped)
    rows = rows.loc[rows.peer_count.ge(5) & np.isfinite(rows.peer_median_return3)]
    if rows.empty:
        raise ValueError("No origin-known peer support")
    summary = {}
    for band, block in rows.groupby("band", sort=True):
        by_origin = block.groupby("forecast_origin", sort=True).agg(
            series_count=("series", "nunique"),
            peer_momentum=("peer_median_return3", "mean"),
            mean_relative_residual=("mean_relative_residual", "mean"),
            mean_mae_php=("mae_php", "mean"),
        ).reset_index()
        summary[band] = {
            "origin_count": int(len(by_origin)),
            "series_origin_count": int(len(block)),
            "series_count": int(block.series.nunique()),
            "origin_level_peer_vs_residual_pearson": _pearson(
                by_origin.peer_momentum, by_origin.mean_relative_residual),
            "series_origin_peer_vs_residual_pearson_descriptive_only": _pearson(
                block.peer_median_return3, block.mean_relative_residual),
            "series_origin_own_vs_residual_pearson_descriptive_only": _pearson(
                block.own_return3, block.mean_relative_residual),
            "origin_metrics": [{
                "forecast_origin": row.forecast_origin.date().isoformat(),
                "series_count": int(row.series_count),
                "peer_momentum": float(row.peer_momentum),
                "mean_relative_residual": float(row.mean_relative_residual),
                "mean_mae_php": float(row.mean_mae_php),
            } for row in by_origin.itertuples()],
        }
    return summary, rows


def run(source_dir: Path, output_dir: Path, *, partition: str = "validation") -> dict:
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite diagnostic: {output_dir}")
    if partition not in {"validation", "test"}:
        raise ValueError("Only pre-holdout validation or historical test is supported")
    manifest_path = source_dir / "selection_manifest.json"
    source_path = source_dir / "daily" / f"{partition}_predictions.csv"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest["task_scope"] != "objective"
            or manifest["selected_strategy_by_horizon"]["daily"] != "shared"
            or manifest["holdout_labels_used"] is not False):
        raise ValueError("Unexpected selected daily validation experiment")
    boundaries = ({"first_origin_inclusive": "2024-08-27",
                   "last_target_exclusive": "2025-09-13"}
                  if partition == "validation" else
                  {"first_origin_inclusive": "2025-09-13",
                   "last_target_exclusive": "2026-10-06"})
    summary, rows = evaluate(pd.read_csv(source_path), **boundaries)
    report = {
        "experiment": "origin_known_peer_vegetable_momentum_diagnostic",
        "partition": partition,
        "period_boundaries": boundaries,
        "source_snapshot_sha256": manifest["source_snapshot_sha256"],
        "selection_manifest_sha256": sha256(manifest_path),
        "predictions_sha256": sha256(source_path),
        "script_sha256": sha256(Path(__file__)),
        "test_partition_accessed": partition == "test",
        "historical_test_reused": partition == "test",
        "holdout_labels_used": False,
        "model_fitted": False,
        "production_promotion_permitted": False,
        "source_availability_limitation": (
            "Report-date availability is reconstructed; immutable ingestion times are absent."),
        "summary": summary,
    }
    output_dir.mkdir(parents=True)
    rows.to_csv(output_dir / "origin_series_diagnostic.csv", index=False)
    (output_dir / "report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report


def main() -> None:
    repository = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=repository /
                        "audits/foodcast_accuracy_20261017/relative5_test_confirmation_v2")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--partition", choices=("validation", "test"),
                        default="validation")
    args = parser.parse_args()
    report = run(args.source_dir, args.output_dir, partition=args.partition)
    print(json.dumps({key: {name: value for name, value in item.items()
                            if name != "origin_metrics"}
                      for key, item in report["summary"].items()}, indent=2))


if __name__ == "__main__":
    main()
