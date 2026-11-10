"""Research-only product-adaptive active/persistence blend.

Only previously elapsed 14-day paths and observed target rows can update the
weight. Historical test reuse and missing immutable source vintages prohibit
promotion even if retrospective metrics improve.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from data.preprocessor import DataPreprocessor
from evaluation.causal_daily_blend import fit_mae_grid
from evaluation.dense_active_interval_replay import HOLDOUT_START, KEYS, origin_schedule
from evaluation.dense_point_baseline import _score, origin_known_persistence


RECENT_COMPLETE_ORIGINS = 8
MIN_PRODUCT_TARGETS = 40
PRIORITY_NAMES = ("Bell Pepper||Red", "Chili||Labuyo", "Lettuce||Green Ice",
                  "Lettuce||Iceberg", "Lettuce||Romaine")
METHODS = ("active", "persistence", "expanding_mae", "product_recent8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def completed_history(history: pd.DataFrame, series: str, origin: pd.Timestamp
                      ) -> pd.DataFrame:
    """Most recent eight distinct origins whose full target window has ended."""
    origin = pd.Timestamp(origin).normalize()
    eligible = history.loc[
        history.series.eq(series)
        & history.origin.add(pd.Timedelta(days=14)).lt(origin)
        & history.date.lt(origin)
    ].copy()
    if eligible.empty:
        return eligible
    origins = eligible.origin.drop_duplicates().sort_values().tail(RECENT_COMPLETE_ORIGINS)
    return eligible.loc[eligible.origin.isin(origins)]


def _sufficient(rows: pd.DataFrame) -> bool:
    return (len(rows) >= MIN_PRODUCT_TARGETS
            and rows.origin.nunique() >= RECENT_COMPLETE_ORIGINS)


def product_weights(calibration: pd.DataFrame, global_fallback: float) -> dict:
    """Pre-evaluation product weights; sparse series inherit pooled weight."""
    result = {}
    for series, rows in calibration.groupby("series", sort=True):
        supported = _sufficient(rows)
        result[str(series)] = {
            "weight": fit_mae_grid(rows) if supported else global_fallback,
            "source": "product_calibration" if supported else "pooled_calibration_fallback",
            "target_count": int(len(rows)),
            "origin_count": int(rows.origin.nunique()),
        }
    return result


def make_candidate(calibration: pd.DataFrame, evaluation: pd.DataFrame,
                   *, global_fallback: float) -> tuple[pd.DataFrame, dict]:
    if (calibration.empty or evaluation.empty
            or calibration.date.max() >= evaluation.date.min()
            or evaluation.date.max() >= HOLDOUT_START
            or calibration.duplicated(KEYS).any()
            or evaluation.duplicated(KEYS).any()):
        raise ValueError("Product blend input overlaps or reaches sealed holdout")
    fixed = product_weights(calibration, global_fallback)
    history = pd.concat([calibration, evaluation], ignore_index=True)
    parts, weights = [], []
    for origin, current in evaluation.groupby("origin", sort=True):
        current = current.copy()
        current["product_recent8"] = np.nan
        for series, rows in current.groupby("series", sort=True):
            recent = completed_history(history, series, origin)
            if _sufficient(recent):
                weight = fit_mae_grid(recent)
                source = "recent_completed_product_origins"
            else:
                fallback = fixed.get(str(series))
                weight = fallback["weight"] if fallback else global_fallback
                source = fallback["source"] if fallback else "pooled_calibration_fallback"
            current.loc[rows.index, "product_recent8"] = (
                weight * rows.ensemble_path.to_numpy(dtype=float)
                + (1 - weight) * rows.persistence.to_numpy(dtype=float))
            weights.append({
                "origin": pd.Timestamp(origin).date().isoformat(),
                "series": str(series), "active_weight": float(weight),
                "weight_source": source,
                "eligible_target_count": int(len(recent)),
                "eligible_complete_origin_count": int(recent.origin.nunique()),
                "latest_eligible_target_date": (
                    recent.date.max().date().isoformat() if not recent.empty else None),
            })
        parts.append(current)
    scored = pd.concat(parts, ignore_index=True)
    if (len(scored) != len(evaluation) or scored.duplicated(KEYS).any()
            or scored.product_recent8.isna().any()
            or not np.isfinite(scored.product_recent8.to_numpy(dtype=float)).all()):
        raise ValueError("Product blend rows are missing or misaligned")
    return scored, {"fixed_product_calibration": fixed,
                    "by_origin_product": weights}


def summarize(scored: pd.DataFrame) -> dict:
    def metrics(rows: pd.DataFrame) -> dict:
        return {method: _score(rows, "ensemble_path" if method == "active" else method)
                for method in METHODS}

    pooled = metrics(scored)
    products = {str(series): metrics(rows)
                for series, rows in scored.groupby("series", sort=True)}
    macro = {
        method: {metric: float(np.mean([group[method][metric]
                                        for group in products.values()]))
                 for metric in ("mae", "rmse", "mape", "within_5_php_accuracy_pct")}
        for method in METHODS}
    priority = {series: groups for series, groups in products.items()
                if any(name in series for name in PRIORITY_NAMES)}
    candidate = "product_recent8"
    pooled_better_both = all(
        pooled[candidate][metric] < min(pooled["active"][metric],
                                        pooled["persistence"][metric])
        for metric in ("mae", "rmse", "mape"))
    macro_no_regression = all(
        macro[candidate][metric] <= min(macro["active"][metric],
                                        macro["persistence"][metric])
        for metric in ("mae", "rmse", "mape"))
    priority_no_major_regression = all(
        groups[candidate]["mae"] <= 1.10 * min(groups[ref]["mae"]
                                                for ref in ("active", "persistence"))
        for groups in priority.values())
    product_regressions = sum(
        groups[candidate]["mae"] > 1.10 * min(groups[ref]["mae"]
                                                for ref in ("active", "persistence"))
        for groups in products.values())
    broad_nonregression = product_regressions <= max(1, int(0.10 * len(products)))
    within5_ok = pooled[candidate]["within_5_php_accuracy_pct"] >= (
        max(pooled[ref]["within_5_php_accuracy_pct"]
            for ref in ("active", "persistence")) - 0.5)
    blocks = {
        "days_1_7": metrics(scored.loc[scored.horizon.le(7)]),
        "days_8_14": metrics(scored.loc[scored.horizon.ge(8)]),
    }
    blocks_ok = all(
        groups[candidate]["mae"] <= 1.05 * min(groups[ref]["mae"]
                                                for ref in ("active", "persistence"))
        for groups in blocks.values())
    screen = {
        "pooled_mae_rmse_mape_better_than_both": pooled_better_both,
        "macro_mae_rmse_mape_no_worse_than_both": macro_no_regression,
        "priority_mae_within_10pct_of_better_reference": priority_no_major_regression,
        "products_over_10pct_mae_regression_vs_better_reference": product_regressions,
        "at_most_10pct_products_majorly_regress": broad_nonregression,
        "within_php5_rate_within_half_point_of_better_reference": within5_ok,
        "both_lead_blocks_mae_within_5pct_of_better_reference": blocks_ok,
        "research_screen_passed": bool(pooled_better_both and macro_no_regression
                                       and priority_no_major_regression
                                       and broad_nonregression and within5_ok
                                       and blocks_ok),
        "production_promotion_permitted": False,
    }
    return {
        "sample_count": int(len(scored)),
        "origin_count": int(scored.origin.nunique()),
        "product_count": len(products),
        "pooled": pooled,
        "macro_equal_product": macro,
        "by_product": products,
        "by_lead": {str(int(lead)): metrics(rows)
                    for lead, rows in scored.groupby("horizon", sort=True)},
        "lead_blocks": blocks,
        "research_screen": screen,
    }


def run(blend_dir: Path, replay_dir: Path, source: Path, output_dir: Path) -> dict:
    blend_dir, replay_dir, source, output_dir = map(
        Path, (blend_dir, replay_dir, source, output_dir))
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite product-blend output: {output_dir}")
    parent = json.loads((blend_dir / "report.json").read_text(encoding="utf-8"))
    replay = json.loads((replay_dir / "report.json").read_text(encoding="utf-8"))
    if (parent.get("source_sha256") != _sha256(source)
            or parent.get("replay_report_sha256") != _sha256(replay_dir / "report.json")
            or parent.get("holdout_labels_used") is not False
            or replay.get("saved_active_forecast_parity_passed") is not True):
        raise ValueError("Product blend requires verified exact-vintage parent evidence")
    raw = json.loads(source.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw = raw.get("rows", raw.get("data"))
    raw = pd.DataFrame(raw)
    if pd.to_datetime(raw.report_date, errors="coerce").max() >= HOLDOUT_START:
        raise ValueError("Product blend source enters prospective holdout")
    clean = DataPreprocessor().validate(raw, apply_source_quality_exclusions=False)
    replay_path = replay_dir / "replay_observed_targets.csv"
    observed = pd.read_csv(replay_path, float_precision="round_trip")
    calibration_origins, evaluation_origins = origin_schedule()
    observed["origin"] = pd.to_datetime(observed.origin).dt.normalize()
    observed["date"] = pd.to_datetime(observed.date).dt.normalize()
    calibration = origin_known_persistence(
        observed.loc[observed.origin.isin(calibration_origins)], clean)
    evaluation_path = blend_dir / "paired_targets.csv"
    evaluation = pd.read_csv(evaluation_path, float_precision="round_trip")
    evaluation["origin"] = pd.to_datetime(evaluation.origin).dt.normalize()
    evaluation["date"] = pd.to_datetime(evaluation.date).dt.normalize()
    if (len(calibration) != replay["calibration_scored_targets"]
            or len(evaluation) != replay["evaluation_scored_targets"]
            or not evaluation.origin.isin(evaluation_origins).all()
            or evaluation.duplicated(KEYS).any()):
        raise ValueError("Product-blend comparison does not match parent samples")
    expected = origin_known_persistence(
        observed.loc[observed.origin.isin(evaluation_origins)], clean)
    checked = evaluation.merge(
        expected[KEYS + ["actual", "ensemble_path", "persistence"]],
        on=KEYS, how="inner", suffixes=("_parent", "_replay"),
        validate="one_to_one")
    if len(checked) != len(evaluation) or any(
        not np.allclose(checked[f"{name}_parent"], checked[f"{name}_replay"],
                        rtol=0, atol=1e-9)
        for name in ("actual", "ensemble_path", "persistence")
    ):
        raise ValueError("Parent target values differ from parity-clean replay")
    global_fallback = parent["weights"]["fixed"]["pooled_mae_weight"]
    scored, weights = make_candidate(
        calibration, evaluation, global_fallback=global_fallback)
    summary = summarize(scored)
    for method in ("active", "persistence", "expanding_mae"):
        for metric in ("mae", "rmse", "mape"):
            if not np.isclose(summary["pooled"][method][metric],
                              parent["summary"]["pooled"][method][metric],
                              rtol=0, atol=1e-9):
                raise ValueError("Parent reference metrics were not reproduced")
    report = {
        "experiment": "product_recent_completed_origin_active_persistence_blend",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "script_sha256": _sha256(Path(__file__)),
        "parent_blend_report_sha256": _sha256(blend_dir / "report.json"),
        "parent_evaluation_sha256": _sha256(evaluation_path),
        "replay_report_sha256": _sha256(replay_dir / "report.json"),
        "source_sha256": _sha256(source),
        "recent_complete_origins": RECENT_COMPLETE_ORIGINS,
        "minimum_product_target_rows": MIN_PRODUCT_TARGETS,
        "origin_availability_rule": "prior_origin + 14 calendar days < current_origin",
        "calibration_source": "observed historical active-versus-persistence errors only",
        "historical_test_reused_for_development": True,
        "holdout_labels_used": False,
        "production_promotion_permitted": False,
        "source_availability_caveat": (
            "Report dates are known, but immutable historical source-ingestion "
            "or publication timestamps are not. Overlapping 14-day paths remain dependent."
        ),
        "weights": weights,
        "summary": summary,
    }
    output_dir.mkdir(parents=True)
    scored.to_csv(output_dir / "paired_targets.csv", index=False)
    (output_dir / "report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blend-dir", type=Path, required=True)
    parser.add_argument("--replay-dir", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.blend_dir, args.replay_dir, args.source, args.output_dir)
    summary = report["summary"]
    print(json.dumps({"pooled": {name: {
        key: values[key] for key in ("mae", "rmse", "mape", "within_5_php_accuracy_pct")}
        for name, values in summary["pooled"].items()},
        "research_screen": summary["research_screen"]}, indent=2))


if __name__ == "__main__":
    main()
