"""Causal seasonal-naive references for independent weekly/monthly forecasts.

This research-only screen compares exact prior-season period means with
completed-period persistence on identical saved target keys. It never opens
the sealed prospective holdout or changes production artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from data.preprocessor import DataPreprocessor, SERIES_KEY
from evaluation.horizon_specific import SPECS, build_period_panel


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "audits/accuracy_goal_20261011/supabase_food_prices_through_20261005.json"
TARGETS = ROOT / "audits/foodcast_accuracy_20261018/period_persistence_intervals_v3/paired_period_targets.csv"
PLAN = ROOT / "audits/foodcast_accuracy_20261018/period_seasonal_naive_plan.md"
TARGET_CUTOFF = pd.Timestamp("2026-09-30")
HOLDOUT_START = pd.Timestamp("2026-10-06")
KEYS = ["series", "forecast_origin", "horizon", "lead", "target_start", "target_end"]
METRICS = ("mae_php", "rmse_php", "mape_pct", "within_5_php_pct",
           "within_5_percent_pct")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def seasonal_period_start(target_start: pd.Timestamp, horizon: str) -> pd.Timestamp:
    """Return exactly 52 weeks or 12 calendar months before the target."""
    start = pd.Timestamp(target_start).normalize()
    if horizon == "weekly":
        return start - pd.Timedelta(days=364)
    if horizon == "monthly":
        return (start - pd.DateOffset(months=12)).normalize()
    raise ValueError("Seasonal period baseline supports weekly and monthly only")


def attach_seasonal(targets: pd.DataFrame, panel: pd.DataFrame,
                    horizon: str) -> pd.DataFrame:
    """Attach a causal same-season value, falling back to persistence if absent."""
    if horizon not in ("weekly", "monthly"):
        raise ValueError("Only weekly/monthly seasonality is supported")
    required_targets = set(KEYS + ["actual", "persistence", "partition"])
    required_panel = set(SERIES_KEY + ["period_start", "period_end",
                                       "last_observed_date", "period_value",
                                       "observed_days"])
    if not required_targets.issubset(targets) or not required_panel.issubset(panel):
        raise ValueError("Seasonal baseline input schema is incomplete")

    rows = targets.copy()
    for column in ("forecast_origin", "target_start", "target_end"):
        rows[column] = pd.to_datetime(rows[column], errors="raise").dt.normalize()
    rows["lead"] = pd.to_numeric(rows.lead, errors="raise").astype(int)
    if rows.horizon.ne(horizon).any() or rows.duplicated(KEYS).any():
        raise ValueError("Wrong horizon or duplicate target keys")
    if (rows.target_start.le(rows.forecast_origin).any()
            or rows.target_end.le(rows.forecast_origin).any()
            or rows.target_end.gt(TARGET_CUTOFF).any()
            or rows.target_end.ge(HOLDOUT_START).any()):
        raise ValueError("Target rows are not future or reach the sealed holdout")
    if horizon == "weekly":
        valid_periods = (rows.target_start.dt.weekday.eq(0)
                         & rows.target_end.eq(rows.target_start + pd.Timedelta(days=6)))
    else:
        valid_periods = (rows.target_start.dt.day.eq(1)
                         & rows.target_end.eq(rows.target_start + pd.offsets.MonthEnd(0)))
    if not valid_periods.all():
        raise ValueError("Target rows do not use full calendar periods")
    if not np.isfinite(rows[["actual", "persistence"]].to_numpy(dtype=float)).all():
        raise ValueError("Non-finite actual or persistence point")
    if (rows.actual.le(0).any() or rows.persistence.le(0).any()):
        raise ValueError("Period prices must be positive")

    history = panel.copy()
    history["series"] = history[SERIES_KEY].astype(str).agg("||".join, axis=1)
    for column in ("period_start", "period_end", "last_observed_date"):
        history[column] = pd.to_datetime(history[column], errors="raise").dt.normalize()
    if history.duplicated(["series", "period_start"]).any():
        raise ValueError("Duplicate source period keys")
    lookup = {}
    for item in history.itertuples(index=False):
        lookup[(str(item.series), pd.Timestamp(item.period_start))] = (
            float(item.period_value), pd.Timestamp(item.period_end),
            pd.Timestamp(item.last_observed_date), int(item.observed_days))

    seasonal_values, seasonal_starts, support, reasons = [], [], [], []
    for row in rows.itertuples(index=False):
        prior_start = seasonal_period_start(row.target_start, horizon)
        item = lookup.get((str(row.series), prior_start))
        usable = False
        reason = "no_valid_prior_season"
        value = np.nan
        if item is not None:
            value, period_end, last_observed, observed_days = item
            expected_end = (prior_start + pd.Timedelta(days=6) if horizon == "weekly"
                            else prior_start + pd.offsets.MonthEnd(0))
            if period_end != expected_end:
                raise ValueError("Prior seasonal row is not a full calendar period")
            if last_observed < prior_start or last_observed > period_end:
                raise ValueError("Prior seasonal observation date is outside its period")
            if observed_days < SPECS[horizon].minimum_coverage:
                reason = "insufficient_prior_season_observations"
                value = np.nan
            elif period_end > row.forecast_origin or last_observed > row.forecast_origin:
                reason = "prior_season_not_completed_at_origin"
                value = np.nan
            else:
                usable = np.isfinite(value) and value > 0
                reason = "supported" if usable else "invalid_prior_season_price"
        seasonal_values.append(value)
        seasonal_starts.append(prior_start)
        support.append(usable)
        reasons.append(reason)
    rows["seasonal_period_start"] = seasonal_starts
    rows["seasonal_value"] = seasonal_values
    rows["seasonal_supported"] = support
    rows["seasonal_support_reason"] = reasons
    rows["seasonal_naive_point"] = np.where(
        rows.seasonal_supported, rows.seasonal_value, rows.persistence)
    if not np.isfinite(rows.seasonal_naive_point.to_numpy(dtype=float)).all():
        raise ValueError("Seasonal candidate contains non-finite points")
    return rows


def metric(rows: pd.DataFrame, prediction: str) -> dict:
    if rows.empty:
        return {"n": 0}
    actual = rows.actual.to_numpy(dtype=float)
    predicted = rows[prediction].to_numpy(dtype=float)
    if (not np.isfinite(actual).all() or not np.isfinite(predicted).all()
            or (actual <= 0).any()):
        raise ValueError("Invalid original-PHP metric inputs")
    error = predicted - actual
    absolute = np.abs(error)
    relative = absolute / actual
    return {
        "n": int(len(rows)), "series": int(rows.series.nunique()),
        "origins": int(rows.forecast_origin.nunique()),
        "target_periods": int(rows.target_start.nunique()),
        "mae_php": float(absolute.mean()),
        "rmse_php": float(np.sqrt(np.square(error).mean())),
        "mape_pct": float(relative.mean() * 100),
        "wape_pct": float(absolute.sum() / actual.sum() * 100),
        "bias_php": float(error.mean()),
        "within_5_php_pct": float((absolute <= 5).mean() * 100),
        "within_5_percent_pct": float((relative <= .05).mean() * 100),
    }


def summarize(rows: pd.DataFrame, prediction: str) -> dict:
    by_series = {series: metric(group, prediction)
                 for series, group in rows.groupby("series", sort=True)}
    by_lead = {str(int(lead)): metric(group, prediction)
               for lead, group in rows.groupby("lead", sort=True)}
    macro = {name: float(np.mean([value[name] for value in by_series.values()]))
             for name in ("mae_php", "rmse_php", "mape_pct", "wape_pct",
                          "within_5_php_pct", "within_5_percent_pct")} if by_series else {}
    return {"pooled": metric(rows, prediction), "macro_equal_series": macro,
            "by_series": by_series, "by_lead": by_lead}


def error_reduction(baseline: dict, candidate: dict) -> dict:
    result = {}
    for name in ("mae_php", "rmse_php", "mape_pct"):
        before, after = baseline.get(name), candidate.get(name)
        result[name] = (None if before is None or before == 0 or after is None
                        else float((before - after) / before * 100))
    return result


def compare(rows: pd.DataFrame) -> dict:
    seasonal_only = rows.loc[rows.seasonal_supported].copy()
    base_all = summarize(rows, "persistence")
    season_all = summarize(rows, "seasonal_naive_point")
    base_supported = summarize(seasonal_only, "persistence")
    season_supported = summarize(seasonal_only, "seasonal_value")
    regressions = []
    for series, baseline in base_supported["by_series"].items():
        candidate = season_supported["by_series"][series]
        if candidate["mae_php"] > baseline["mae_php"] * 1.10:
            regressions.append(series)
    return {
        "targets": int(len(rows)),
        "seasonal_supported_targets": int(len(seasonal_only)),
        "seasonal_support_pct": float(rows.seasonal_supported.mean() * 100) if len(rows) else None,
        "fallback_targets": int((~rows.seasonal_supported).sum()),
        "persistence_all_rows": base_all,
        "seasonal_with_persistence_fallback_all_rows": season_all,
        "all_row_error_reduction_pct": error_reduction(base_all["pooled"], season_all["pooled"]),
        "persistence_supported_rows": base_supported,
        "seasonal_only_supported_rows": season_supported,
        "supported_row_error_reduction_pct": error_reduction(
            base_supported["pooled"], season_supported["pooled"]),
        "supported_series_mae_regressions_over_10pct": regressions,
        "supported_series_mae_regression_count_over_10pct": len(regressions),
    }


def run(source_path: Path, targets_path: Path, plan_path: Path,
        output_dir: Path) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite seasonal-naive results: {output_dir}")
    raw = json.loads(source_path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw = raw.get("rows", raw.get("data", raw))
    source = pd.DataFrame(raw)
    source_dates = pd.to_datetime(source.report_date, errors="coerce").dropna()
    if source_dates.empty or source_dates.max().normalize() >= HOLDOUT_START:
        raise ValueError("Source snapshot reaches the sealed prospective holdout")
    targets = pd.read_csv(targets_path, float_precision="round_trip")
    targets["forecast_origin"] = pd.to_datetime(targets.forecast_origin).dt.normalize()
    targets["target_start"] = pd.to_datetime(targets.target_start).dt.normalize()
    targets["target_end"] = pd.to_datetime(targets.target_end).dt.normalize()
    if targets.duplicated(KEYS).any() or targets.target_end.max() > TARGET_CUTOFF:
        raise ValueError("Duplicate target keys or targets beyond historical cutoff")
    if targets.target_end.max() >= HOLDOUT_START:
        raise ValueError("Target input reaches the sealed prospective holdout")

    clean = DataPreprocessor().validate(source)
    scored_parts, horizon_reports = [], {}
    for horizon in ("weekly", "monthly"):
        subset = targets.loc[targets.horizon.eq(horizon)].copy()
        if subset.empty:
            raise ValueError(f"No {horizon} target rows")
        panel = build_period_panel(clean, SPECS[horizon])
        scored = attach_seasonal(subset, panel, horizon)
        scored_parts.append(scored)
        partitions = {
            str(name): compare(group)
            for name, group in scored.groupby("partition", sort=True)
        }
        years = {
            str(int(name)): compare(group)
            for name, group in scored.groupby(scored.target_end.dt.year, sort=True)
        }
        horizon_reports[horizon] = {
            "period_definition": {
                "weekly": "prior full Monday-Sunday period exactly 364 days before target; >=4 observed days",
                "monthly": "prior full calendar month 12 months before target; >=15 observed days",
            }[horizon],
            "partition_results": partitions,
            "target_year_results": years,
        }
    predictions = pd.concat(scored_parts, ignore_index=True)
    if predictions.duplicated(KEYS).any() or predictions.target_end.max() > TARGET_CUTOFF:
        raise ValueError("Output target keys or dates failed final checks")
    report = {
        "experiment": "weekly_monthly_same_season_naive_vs_completed_period_persistence",
        "source_sha256": sha256(source_path), "targets_sha256": sha256(targets_path),
        "plan_sha256": sha256(plan_path),
        "script_sha256": sha256(Path(__file__)),
        "preprocessing_contract": DataPreprocessor.preprocessing_contract(),
        "source_report_date_max": source_dates.max().normalize().date().isoformat(),
        "target_cutoff": TARGET_CUTOFF.date().isoformat(),
        "holdout_labels_used": False, "production_promotion_permitted": False,
        "retrospective_reuse_note": "Saved calibration/evaluation origins are historical and have been used in prior research; no result is pristine prospective confirmation.",
        "metrics_note": "Original-PHP pooled and equal-series macro metrics; MAPE uses positive observed period means. Seasonal-only scores are paired against persistence on identical supported rows. The all-row seasonal result falls back to persistence when a prior season is missing.",
        "horizons": horizon_reports,
    }
    output_dir.mkdir(parents=True)
    predictions.to_csv(output_dir / "seasonal_predictions.csv", index=False)
    (output_dir / "report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--targets", type=Path, default=TARGETS)
    parser.add_argument("--plan", type=Path, default=PLAN)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.source, args.targets, args.plan, args.output_dir)
    print(json.dumps({h: {partition: {
        "targets": item["targets"],
        "seasonal_support_pct": item["seasonal_support_pct"],
        "persistence_mae_rmse_mape": [
            item["persistence_all_rows"]["pooled"].get(key)
            for key in ("mae_php", "rmse_php", "mape_pct")],
        "seasonal_with_fallback_mae_rmse_mape": [
            item["seasonal_with_persistence_fallback_all_rows"]["pooled"].get(key)
            for key in ("mae_php", "rmse_php", "mape_pct")],
        "seasonal_supported_error_reduction_pct": item["supported_row_error_reduction_pct"],
    } for partition, item in section["partition_results"].items()}
        for h, section in report["horizons"].items()}, indent=2))


if __name__ == "__main__":
    main()
