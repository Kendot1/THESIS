"""Research-only daily active/persistence blends selected on prior outcomes.

The active model and source are replayed exactly, but the historical test has
already been inspected. These results can diagnose recursive error and inform
a future preregistered candidate; they cannot authorize production promotion.
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
from evaluation.dense_active_interval_replay import HOLDOUT_START, KEYS, origin_schedule
from evaluation.dense_point_baseline import _score, origin_known_persistence


WEIGHT_GRID = tuple(round(i / 10, 1) for i in range(11))
MIN_LEAD_ORIGINS = 8
MIN_LEAD_ROWS = 100
PRIORITY_NAMES = ("Bell Pepper||Red", "Chili||Labuyo", "Lettuce||Green Ice",
                  "Lettuce||Iceberg", "Lettuce||Romaine")
ERROR_NAMES = ("mae", "rmse", "mape")
METHODS = ("active", "persistence", "fixed_mae", "fixed_mse", "expanding_mae")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _blended(frame: pd.DataFrame, weight: float) -> np.ndarray:
    return (weight * frame.ensemble_path.to_numpy(dtype=float)
            + (1 - weight) * frame.persistence.to_numpy(dtype=float))


def _support(frame: pd.DataFrame) -> dict:
    return {"target_count": int(len(frame)),
            "origin_count": int(frame.origin.nunique())}


def _supported(frame: pd.DataFrame) -> bool:
    return len(frame) >= MIN_LEAD_ROWS and frame.origin.nunique() >= MIN_LEAD_ORIGINS


def fit_mae_grid(frame: pd.DataFrame) -> float:
    """Choose a predeclared convex weight by MAE; break ties conservatively."""
    if frame.empty:
        raise ValueError("Cannot fit a blend on empty calibration")
    actual = frame.actual.to_numpy(dtype=float)
    if not np.isfinite(actual).all():
        raise ValueError("Calibration actuals must be finite")
    choices = []
    for weight in WEIGHT_GRID:
        predicted = _blended(frame, weight)
        error = predicted - actual
        mae = float(np.mean(np.abs(error)))
        rmse = float(np.sqrt(np.mean(error ** 2)))
        mape = float(np.mean(np.abs(error) / actual)) if (actual > 0).all() else float("inf")
        choices.append((mae, rmse, mape, abs(1 - weight), weight))
    return float(min(choices)[-1])


def fit_mse(frame: pd.DataFrame) -> float:
    """Closed-form, clipped MSE-optimal convex weight."""
    if frame.empty:
        raise ValueError("Cannot fit a blend on empty calibration")
    delta = (frame.ensemble_path - frame.persistence).to_numpy(dtype=float)
    target = (frame.actual - frame.persistence).to_numpy(dtype=float)
    denominator = float(np.dot(delta, delta))
    if not np.isfinite(denominator) or denominator <= 1e-12:
        return 1.0
    return float(np.clip(np.dot(delta, target) / denominator, 0.0, 1.0))


def select_fixed_weights(calibration: pd.DataFrame) -> dict:
    """Fit each lead on calibration only; absent leads use one pooled weight."""
    if (calibration.empty or calibration.date.max() >= HOLDOUT_START
            or calibration.duplicated(KEYS).any()):
        raise ValueError("Invalid or holdout calibration rows")
    global_mae = fit_mae_grid(calibration)
    global_mse = fit_mse(calibration)
    by_lead = {}
    for lead in range(1, 15):
        rows = calibration.loc[calibration.horizon.eq(lead)]
        supported = _supported(rows)
        by_lead[str(lead)] = {
            "mae_weight": fit_mae_grid(rows) if supported else global_mae,
            "mse_weight": fit_mse(rows) if supported else global_mse,
            "weight_source": "lead_calibration" if supported else "pooled_calibration_fallback",
            **_support(rows),
        }
    return {"pooled_mae_weight": global_mae,
            "pooled_mse_weight": global_mse,
            "by_lead": by_lead}


def eligible_at_origin(calibration: pd.DataFrame, evaluation: pd.DataFrame,
                       origin: pd.Timestamp) -> pd.DataFrame:
    """Observed outcomes must be from older origins and dated by this origin."""
    origin = pd.Timestamp(origin).normalize()
    history = pd.concat([calibration, evaluation], ignore_index=True)
    return history.loc[(history.origin < origin) & (history.date <= origin)].copy()


def make_candidates(calibration: pd.DataFrame, evaluation: pd.DataFrame
                    ) -> tuple[pd.DataFrame, dict]:
    """Emit identical evaluation keys for all candidate and reference paths."""
    if (calibration.empty or evaluation.empty
            or calibration.date.max() >= evaluation.date.min()
            or evaluation.date.max() >= HOLDOUT_START
            or calibration.duplicated(KEYS).any()
            or evaluation.duplicated(KEYS).any()):
        raise ValueError("Calibration/evaluation keys overlap or enter holdout")
    fixed = select_fixed_weights(calibration)
    parts = []
    weight_history = []
    for origin, current in evaluation.groupby("origin", sort=True):
        available = eligible_at_origin(calibration, evaluation, origin)
        if available.empty or available.date.max() > origin:
            raise ValueError("Future target reached expanding blend selection")
        current = current.copy()
        current["active"] = current.ensemble_path
        current["fixed_mae"] = np.nan
        current["fixed_mse"] = np.nan
        current["expanding_mae"] = np.nan
        for lead, rows in current.groupby("horizon", sort=True):
            key = str(int(lead))
            selected = fixed["by_lead"][key]
            historical_lead = available.loc[available.horizon.eq(lead)]
            if _supported(historical_lead):
                expanding_weight = fit_mae_grid(historical_lead)
                source = "prior_observed_lead"
            else:
                expanding_weight = fixed["pooled_mae_weight"]
                source = "pooled_calibration_fallback"
            current.loc[rows.index, "fixed_mae"] = _blended(rows, selected["mae_weight"])
            current.loc[rows.index, "fixed_mse"] = _blended(rows, selected["mse_weight"])
            current.loc[rows.index, "expanding_mae"] = _blended(rows, expanding_weight)
            weight_history.append({
                "origin": pd.Timestamp(origin).date().isoformat(),
                "lead": int(lead),
                "fixed_mae_weight": selected["mae_weight"],
                "fixed_mse_weight": selected["mse_weight"],
                "expanding_mae_weight": expanding_weight,
                "expanding_weight_source": source,
                "eligible_lead_targets": int(len(historical_lead)),
                "eligible_lead_origins": int(historical_lead.origin.nunique()),
                "latest_eligible_target_date": (
                    historical_lead.date.max().date().isoformat()
                    if not historical_lead.empty else None),
            })
        parts.append(current)
    scored = pd.concat(parts, ignore_index=True)
    if (len(scored) != len(evaluation) or scored.duplicated(KEYS).any()
            or scored[list(METHODS)].isna().any().any()):
        raise ValueError("Candidate rows are missing or misaligned")
    return scored, {"fixed": fixed, "by_origin_lead": weight_history}


def _group_metrics(rows: pd.DataFrame) -> dict:
    return {name: _score(rows, "ensemble_path" if name == "active" else name)
            for name in METHODS}


def _error_reduction(candidate: float, baseline: float) -> float | None:
    return float((baseline - candidate) / baseline * 100) if baseline else None


def _research_screen(summary: dict, name: str) -> dict:
    """Predeclared conservative screen; passing still cannot promote a model."""
    pooled = summary["pooled"]
    macro = summary["macro_equal_product"]
    names = [series for series in summary["by_product"]
             if any(label in series for label in PRIORITY_NAMES)]
    pooled_both = all(
        pooled[name][metric] < min(pooled["active"][metric],
                                   pooled["persistence"][metric])
        for metric in ERROR_NAMES)
    macro_both = all(
        macro[name][metric] <= min(macro["active"][metric],
                                   macro["persistence"][metric])
        for metric in ERROR_NAMES)
    priority_ok = all(
        summary["by_product"][series][name]["mae"]
        <= 1.10 * min(summary["by_product"][series][ref]["mae"]
                      for ref in ("active", "persistence"))
        for series in names)
    lead_blocks_ok = all(
        summary["lead_blocks"][block][name]["mae"]
        <= 1.05 * min(summary["lead_blocks"][block][ref]["mae"]
                      for ref in ("active", "persistence"))
        for block in ("days_1_7", "days_8_14"))
    hit_rate_ok = pooled[name]["within_5_php_accuracy_pct"] >= (
        max(pooled[ref]["within_5_php_accuracy_pct"]
            for ref in ("active", "persistence")) - 0.5)
    return {
        "pooled_all_three_errors_better_than_both": pooled_both,
        "macro_all_three_errors_no_worse_than_both": macro_both,
        "priority_mae_within_10pct_of_better_reference": priority_ok,
        "both_lead_blocks_mae_within_5pct_of_better_reference": lead_blocks_ok,
        "within_php5_rate_within_half_point_of_better_reference": hit_rate_ok,
        "priority_series_screened": names,
        "research_screen_passed": bool(pooled_both and macro_both and priority_ok
                                       and lead_blocks_ok and hit_rate_ok),
        "production_promotion_permitted": False,
    }


def summarize(scored: pd.DataFrame) -> dict:
    if scored.empty or scored.duplicated(KEYS).any():
        raise ValueError("Scored comparison is empty or has duplicate keys")
    products = {str(series): _group_metrics(rows)
                for series, rows in scored.groupby("series", sort=True)}
    macro = {
        name: {metric: float(np.mean([item[name][metric]
                                      for item in products.values()]))
               for metric in (*ERROR_NAMES, "within_5_php_accuracy_pct",
                              "mean_signed_error_php")}
        for name in METHODS}
    pooled = _group_metrics(scored)
    result = {
        "evaluation_target_count": int(len(scored)),
        "evaluation_origin_count": int(scored.origin.nunique()),
        "product_count": len(products),
        "evaluation_origin_start": scored.origin.min().date().isoformat(),
        "evaluation_origin_end": scored.origin.max().date().isoformat(),
        "evaluation_target_start": scored.date.min().date().isoformat(),
        "evaluation_target_end": scored.date.max().date().isoformat(),
        "pooled": pooled,
        "macro_equal_product": macro,
        "by_product": products,
        "by_lead": {str(int(lead)): _group_metrics(rows)
                    for lead, rows in scored.groupby("horizon", sort=True)},
        "lead_blocks": {
            "days_1_7": _group_metrics(scored.loc[scored.horizon.le(7)]),
            "days_8_14": _group_metrics(scored.loc[scored.horizon.ge(8)]),
        },
        "error_reduction_vs_active_pct": {
            name: {metric: _error_reduction(pooled[name][metric],
                                            pooled["active"][metric])
                   for metric in ERROR_NAMES}
            for name in METHODS if name != "active"
        },
        "error_reduction_vs_persistence_pct": {
            name: {metric: _error_reduction(pooled[name][metric],
                                            pooled["persistence"][metric])
                   for metric in ERROR_NAMES}
            for name in METHODS if name != "persistence"
        },
    }
    result["research_screens"] = {
        name: _research_screen(result, name)
        for name in METHODS if name not in {"active", "persistence"}}
    return result


def run(replay_dir: Path, source: Path, output_dir: Path) -> dict:
    replay_dir, source, output_dir = map(Path, (replay_dir, source, output_dir))
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite blend output: {output_dir}")
    replay_report = json.loads((replay_dir / "report.json").read_text(encoding="utf-8"))
    if (replay_report.get("saved_active_forecast_parity_passed") is not True
            or replay_report.get("legacy_source_quality_replay") is not True
            or replay_report.get("source_snapshot_sha256") != _sha256(source)
            or replay_report.get("holdout_labels_used") is not False):
        raise ValueError("Blend requires the exact-vintage parity-clean replay")
    raw = json.loads(source.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw = raw.get("rows", raw.get("data"))
    raw = pd.DataFrame(raw)
    if pd.to_datetime(raw.report_date, errors="coerce").max() >= HOLDOUT_START:
        raise ValueError("Blend source enters sealed prospective holdout")
    clean = DataPreprocessor().validate(raw, apply_source_quality_exclusions=False)
    replay_path = replay_dir / "replay_observed_targets.csv"
    observed = pd.read_csv(replay_path, float_precision="round_trip")
    observed["origin"] = pd.to_datetime(observed.origin).dt.normalize()
    observed["date"] = pd.to_datetime(observed.date).dt.normalize()
    if (observed.duplicated(KEYS).any()
            or not observed.date.eq(observed.origin
                                    + pd.to_timedelta(observed.horizon, unit="D")).all()):
        raise ValueError("Replay has invalid daily target alignment")
    calibration_origins, evaluation_origins = origin_schedule()
    observed = observed.loc[observed.origin.isin(calibration_origins.append(evaluation_origins))]
    paired = origin_known_persistence(observed, clean)
    calibration = paired.loc[paired.origin.isin(calibration_origins)]
    evaluation = paired.loc[paired.origin.isin(evaluation_origins)]
    if (len(calibration) != replay_report["calibration_scored_targets"]
            or len(evaluation) != replay_report["evaluation_scored_targets"]):
        raise ValueError("Blend does not match replay evaluation sample")
    scored, weight_history = make_candidates(calibration, evaluation)
    summary = summarize(scored)
    report = {
        "experiment": "causal_daily_active_persistence_convex_blend",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "script_sha256": _sha256(Path(__file__)),
        "replay_report_sha256": _sha256(replay_dir / "report.json"),
        "replay_targets_sha256": _sha256(replay_path),
        "source_sha256": _sha256(source),
        "weight_grid": list(WEIGHT_GRID),
        "minimum_lead_origins": MIN_LEAD_ORIGINS,
        "minimum_lead_rows": MIN_LEAD_ROWS,
        "weight_convention": "weight * active + (1-weight) * persistence",
        "training_target_availability": "target_date <= current_origin; earlier forecast origin only",
        "historical_test_reused_for_development": True,
        "holdout_labels_used": False,
        "production_promotion_permitted": False,
        "availability_caveat": (
            "Historical source report dates, not immutable ingestion/publication vintages, "
            "govern origin-known labels. Weekly-origin 14-day windows overlap."
        ),
        "weights": weight_history,
        "summary": summary,
    }
    output_dir.mkdir(parents=True)
    scored.to_csv(output_dir / "paired_targets.csv", index=False)
    (output_dir / "report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay-dir", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.replay_dir, args.source, args.output_dir)
    print(json.dumps({"pooled": report["summary"]["pooled"],
                      "research_screens": report["summary"]["research_screens"]}, indent=2))


if __name__ == "__main__":
    main()
