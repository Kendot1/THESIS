"""Train-only damped-trend screen for daily 14-step forecasts.

The global trend response is fit on labels ending no later than 2024-08-26.
Lookback selection uses the later validation forecasts only. After selection,
the selected rule is evaluated once on the saved active-production origins.
That historical test window has been reused by earlier research and is not
prospective promotion evidence. The sealed October holdout is never opened.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from data.preprocessor import DataPreprocessor, SERIES_KEY
from evaluation import horizon_specific as hs
from evaluation.paired_daily_comparison import (
    DEFAULT_ACTIVE, DEFAULT_CANDIDATE, _metrics, pair_forecasts,
)


ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "audits/accuracy_goal_20261011/supabase_food_prices_through_20261005.json"
DEFAULT_VALIDATION = ROOT / "audits/foodcast_accuracy_20261017/active_daily_paired_v2/daily/validation_predictions.csv"
DEFAULT_OUTPUT_ROOT = ROOT / "audits/foodcast_accuracy_20261017/damped_trend"
TRAIN_END = pd.Timestamp("2024-08-26")
VALIDATION_END = pd.Timestamp("2025-09-12")
TRAIN_ORIGIN_STRIDE_DAYS = 7
LOOKBACK_WINDOWS_DAYS = (3, 7, 14, 30)
MIN_OBSERVATIONS = 2


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _slope_at_origin(history: pd.DataFrame, origin: pd.Timestamp,
                     window_days: int) -> tuple[float, int]:
    """OLS price slope per calendar day from observed rows available by origin."""
    origin = pd.Timestamp(origin).normalize()
    end = pd.to_datetime(history.period_end, errors="coerce").dt.normalize()
    start = origin - pd.Timedelta(days=window_days - 1)
    rows = history.loc[end.between(start, origin)].copy()
    if rows.empty:
        return 0.0, 0
    dates = pd.to_datetime(rows.period_start, errors="coerce").dt.normalize()
    prices = pd.to_numeric(rows.period_value, errors="coerce").to_numpy(dtype=float)
    valid = dates.notna().to_numpy() & np.isfinite(prices) & (prices > 0)
    dates = dates.loc[valid]
    prices = prices[valid]
    if len(prices) < MIN_OBSERVATIONS:
        return 0.0, int(len(prices))
    x = (dates - origin).dt.days.to_numpy(dtype=float)
    x_centered = x - x.mean()
    denominator = float(np.dot(x_centered, x_centered))
    if denominator <= 0:
        return 0.0, int(len(prices))
    slope = float(np.dot(x_centered, prices - prices.mean()) / denominator)
    return slope, int(len(prices))


def _attach_slopes(frame: pd.DataFrame, history_index: dict,
                   window_days: int) -> pd.DataFrame:
    """Attach origin-only slopes; no target-period row participates."""
    required = {"forecast_origin", "series", "anchor", "lead", "last_observed_age_days"}
    if required - set(frame.columns):
        raise ValueError(f"Rows are missing trend inputs: {sorted(required - set(frame.columns))}")
    keys = frame[["forecast_origin", "series", *SERIES_KEY]].drop_duplicates()
    records = []
    for origin_value, category, product, variant, source_origin, unit, series in keys[
        ["forecast_origin", *SERIES_KEY, "series"]
    ].itertuples(index=False, name=None):
        origin = pd.Timestamp(origin_value).normalize()
        identity = tuple(map(str, (category, product, variant, source_origin, unit)))
        if identity not in history_index:
            raise ValueError(f"Missing origin history for series {series}")
        history = history_index[identity][0]
        slope, observations = _slope_at_origin(history, origin, window_days)
        records.append({
            "forecast_origin": origin,
            "series": str(series),
            "trend_slope_per_day": slope,
            "trend_observation_count": observations,
            "trend_available": observations >= MIN_OBSERVATIONS,
        })
    features = pd.DataFrame.from_records(records)
    result = frame.copy()
    result["forecast_origin"] = pd.to_datetime(result.forecast_origin).dt.normalize()
    result = result.merge(
        features, on=["forecast_origin", "series"], how="left", validate="many_to_one"
    )
    if result.trend_slope_per_day.isna().any():
        raise ValueError("Unable to construct origin-time trend features for every row")
    return result


def _fit_response(train: pd.DataFrame) -> dict:
    """Fit one non-product-specific LAD response to equal-series relative moves."""
    anchor = pd.to_numeric(train.anchor, errors="coerce").to_numpy(dtype=float)
    actual = pd.to_numeric(train.actual, errors="coerce").to_numpy(dtype=float)
    lead = pd.to_numeric(train.lead, errors="coerce").to_numpy(dtype=float)
    age = pd.to_numeric(train.last_observed_age_days, errors="coerce").to_numpy(dtype=float)
    slope = pd.to_numeric(train.trend_slope_per_day, errors="coerce").to_numpy(dtype=float)
    x = slope * (lead + age) / anchor
    y = actual / anchor - 1.0
    valid = (
        np.isfinite(anchor) & (anchor > 0) & np.isfinite(actual) & (actual > 0)
        & np.isfinite(x) & np.isfinite(y) & (np.abs(x) > 1e-12)
    )
    rows = train.loc[valid, ["series"]].copy()
    if rows.empty:
        return {"beta": 0.0, "fit_rows": 0, "fit_series": 0}
    x, y = x[valid], y[valid]
    series_counts = rows.series.value_counts()
    weights = np.abs(x) / rows.series.map(series_counts).to_numpy(dtype=float)
    ratios = y / x
    order = np.argsort(ratios, kind="mergesort")
    ratios, weights = ratios[order], weights[order]
    if not np.isfinite(weights).all() or weights.sum() <= 0:
        raise ValueError("Trend response weights are invalid")
    beta = float(ratios[np.searchsorted(np.cumsum(weights), weights.sum() / 2.0, side="left")])
    return {
        "beta": beta,
        "fit_rows": int(len(rows)),
        "fit_series": int(rows.series.nunique()),
        "fit_origins": int(train.loc[valid, "forecast_origin"].nunique()),
        "fit_objective": "equal-series mean absolute error of relative price movement",
        "estimator": "weighted median LAD coefficient through zero; row weight = abs(relative trend signal) / usable rows for that series",
    }


def _apply_response(frame: pd.DataFrame, beta: float, prediction_name: str) -> pd.DataFrame:
    result = frame.copy()
    anchor = pd.to_numeric(result.anchor, errors="coerce").to_numpy(dtype=float)
    lead = pd.to_numeric(result.lead, errors="coerce").to_numpy(dtype=float)
    age = pd.to_numeric(result.last_observed_age_days, errors="coerce").to_numpy(dtype=float)
    slope = pd.to_numeric(result.trend_slope_per_day, errors="coerce").to_numpy(dtype=float)
    prediction = anchor + beta * slope * (lead + age)
    result[prediction_name] = np.maximum(0.01, prediction)
    if not np.isfinite(result[prediction_name].to_numpy(dtype=float)).all():
        raise ValueError("Damped trend produced a nonfinite forecast")
    return result


def _metric_summary(frame: pd.DataFrame, predictions: list[str],
                    actual_column: str) -> dict:
    rows = frame.copy()
    rows["actual_candidate"] = pd.to_numeric(rows[actual_column], errors="coerce")
    aggregate = {name: _metrics(rows, name) for name in predictions}
    macro = {}
    for name in predictions:
        per_series = [_metrics(group, name) for _, group in rows.groupby("series", sort=True)]
        macro[name] = {
            field: (float(np.mean([item[field] for item in per_series if item[field] is not None]))
                    if any(item[field] is not None for item in per_series) else None)
            for field in ("mae_php", "rmse_php", "mape_pct", "within_5_percent_pct",
                          "within_5_php_pct", "bias_php")
        }
    return {
        "n_rows": int(len(rows)),
        "series_count": int(rows.series.nunique()),
        "forecast_origins": sorted(pd.to_datetime(rows.forecast_origin).dt.strftime("%Y-%m-%d").unique().tolist()),
        "aggregate": aggregate,
        "macro_series_equal_weight": macro,
    }


def _validation_scores(validation: pd.DataFrame, history_index: dict,
                       train_fits: dict[int, dict]) -> tuple[dict, dict]:
    result = {}
    variants = {}
    for window in LOOKBACK_WINDOWS_DAYS:
        rows = _attach_slopes(validation, history_index, window)
        beta = train_fits[window]
        name = f"damped_trend_{window}d"
        rows = _apply_response(rows, beta["beta"], name)
        variants[window] = (rows, beta)
        summary = _metric_summary(
            rows, [name, "candidate_shared", "persistence"], "actual"
        )
        result[str(window)] = {"response_fit_from_train_only": beta, **summary}
    selected_window = min(
        LOOKBACK_WINDOWS_DAYS,
        key=lambda window: (
            result[str(window)]["macro_series_equal_weight"][f"damped_trend_{window}d"]["mae_php"],
            result[str(window)]["macro_series_equal_weight"][f"damped_trend_{window}d"]["rmse_php"],
            result[str(window)]["macro_series_equal_weight"][f"damped_trend_{window}d"]["mape_pct"],
            window,
        ),
    )
    return {
        "variants": result,
        "selected_window_days": int(selected_window),
        "selection_rule": "lowest validation macro-series MAE; ties by macro RMSE, macro MAPE, then shorter lookback",
    }, variants


def _test_summary(test: pd.DataFrame, selected_window: int, beta: dict,
                  history_index: dict, pairing: dict) -> tuple[dict, pd.DataFrame]:
    anchor_column = "anchor_candidate" if "anchor_candidate" in test else "anchor"
    prepared = test.rename(columns={anchor_column: "anchor"}).copy()
    prepared = _attach_slopes(prepared, history_index, selected_window)
    prediction = f"damped_trend_{selected_window}d"
    prepared = _apply_response(prepared, beta["beta"], prediction)
    predictions = ["ensemble", "candidate_shared", "persistence_active", prediction]
    summary = _metric_summary(prepared, predictions, "actual_candidate")
    summary["by_lead"] = {
        str(int(lead)): _metric_summary(rows, predictions, "actual_candidate")["aggregate"]
        for lead, rows in prepared.groupby("lead", sort=True)
    }
    bands = {
        "days_1_7": prepared.lead.between(1, 7),
        "days_8_14": prepared.lead.between(8, 14),
    }
    summary["by_lead_band"] = {
        name: _metric_summary(prepared.loc[mask], predictions, "actual_candidate")
        for name, mask in bands.items()
    }
    summary["by_series"] = {
        str(series): {name: _metrics(rows.assign(actual_candidate=rows.actual_candidate), name)
                      for name in predictions}
        for series, rows in prepared.groupby("series", sort=True)
    }
    if "volatility_bucket" in prepared:
        summary["by_origin_volatility"] = {
            str(bucket): _metric_summary(rows, predictions, "actual_candidate")
            for bucket, rows in prepared.groupby("volatility_bucket", sort=True, dropna=False)
        }
    active_regressions = {}
    for metric in ("mae_php", "rmse_php", "mape_pct"):
        active_regressions[metric] = sum(
            summary["by_series"][series][prediction][metric]
            > summary["by_series"][series]["ensemble"][metric]
            for series in summary["by_series"]
            if summary["by_series"][series][prediction][metric] is not None
            and summary["by_series"][series]["ensemble"][metric] is not None
        )
    summary["selected_candidate_regressions_vs_active_by_series"] = active_regressions
    summary["error_reduction_pct_vs_active"] = {
        metric: float((summary["aggregate"]["ensemble"][metric]
                       - summary["aggregate"][prediction][metric])
                      / summary["aggregate"]["ensemble"][metric] * 100.0)
        for metric in ("mae_php", "rmse_php", "mape_pct")
    }
    summary["pairing"] = pairing
    return summary, prepared


def run(snapshot_path: Path = SNAPSHOT, active_path: Path = DEFAULT_ACTIVE,
        candidate_path: Path = DEFAULT_CANDIDATE,
        validation_path: Path = DEFAULT_VALIDATION,
        output_root: Path = DEFAULT_OUTPUT_ROOT) -> dict:
    snapshot_path, active_path, candidate_path, validation_path = map(
        lambda path: Path(path).resolve(),
        (snapshot_path, active_path, candidate_path, validation_path),
    )
    output_root = Path(output_root).resolve()
    output_dir = output_root / datetime.now(timezone.utc).strftime("run_%Y%m%dT%H%M%SZ")
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite experiment directory {output_dir}")

    raw = hs.load_snapshot(snapshot_path)
    report_dates = pd.to_datetime(raw.report_date, errors="coerce")
    if report_dates.isna().any() or report_dates.max().normalize() >= hs.HOLDOUT_START:
        raise ValueError("Input snapshot reaches or contains an invalid sealed-holdout date")
    clean = DataPreprocessor().validate(raw)
    if pd.Timestamp(clean.report_date.max()).normalize() >= hs.HOLDOUT_START:
        raise ValueError("Clean labels reach the sealed prospective holdout")
    source_hash = _sha256(snapshot_path)

    spec = hs.SPECS["daily"]
    history_index = hs.prepare_history_index(clean, spec)
    first = pd.Timestamp(clean.report_date.min()).normalize() + pd.Timedelta(days=30)
    training_origins = hs.origin_schedule(spec, first, TRAIN_END, TRAIN_ORIGIN_STRIDE_DAYS)
    train = hs.build_examples(clean, spec, training_origins, TRAIN_END, history_index)
    train = train.loc[
        train.forecast_origin.lt(TRAIN_END) & train.target_end.le(TRAIN_END)
    ].reset_index(drop=True)
    if train.empty or train.forecast_origin.max() >= TRAIN_END or train.target_end.max() > TRAIN_END:
        raise ValueError("Training targets cross the pre-registered training cutoff")

    validation = pd.read_csv(validation_path)
    validation_required = {
        "series", "forecast_origin", "target_start", "target_end", "lead", "actual",
        "anchor", "last_observed_age_days", "candidate_shared", "persistence", *SERIES_KEY,
    }
    missing = validation_required - set(validation.columns)
    if missing:
        raise ValueError(f"Validation forecasts are missing columns: {sorted(missing)}")
    validation["forecast_origin"] = pd.to_datetime(validation.forecast_origin, errors="coerce").dt.normalize()
    validation["target_end"] = pd.to_datetime(validation.target_end, errors="coerce").dt.normalize()
    validation["target_start"] = pd.to_datetime(validation.target_start, errors="coerce").dt.normalize()
    if validation[["forecast_origin", "target_end", "target_start"]].isna().any().any():
        raise ValueError("Validation data contains invalid dates")
    if validation.forecast_origin.min() <= TRAIN_END or validation.target_end.max() > VALIDATION_END:
        raise ValueError("Validation rows overlap training or exceed the declared validation period")
    if validation.duplicated(["series", "forecast_origin", "target_start", "lead"]).any():
        raise ValueError("Validation rows contain duplicate forecast keys")

    trained_variants = {}
    for window in LOOKBACK_WINDOWS_DAYS:
        train_window = _attach_slopes(train, history_index, window)
        trained_variants[window] = _fit_response(train_window)
    validation_result, _validation_variants = _validation_scores(
        validation, history_index, trained_variants
    )
    selected_window = validation_result["selected_window_days"]
    selected_beta = trained_variants[selected_window]

    # Only after the train-only fit and validation-only lookback selection do
    # we open historical test forecasts and their matched labels.
    active = pd.read_csv(active_path)
    candidate = pd.read_csv(candidate_path)
    paired, pairing = pair_forecasts(active, candidate)
    test_result, scored = _test_summary(
        paired, selected_window, selected_beta, history_index, pairing
    )

    report = {
        "output_dir": str(output_dir),
        "experiment": "daily14_global_damped_recent_trend",
        "evidence_status": "historical_development_test_not_prospective_or_promotion_evidence",
        "holdout_labels_used": False,
        "production_activated": False,
        "source_snapshot_sha256": source_hash,
        "source_snapshot_max_date": pd.Timestamp(clean.report_date.max()).date().isoformat(),
        "sources": {
            "snapshot": {"path": str(snapshot_path), "sha256": source_hash},
            "training_recipe": {
                "pipeline": str(Path(hs.__file__).resolve()),
                "sha256": _sha256(Path(hs.__file__).resolve()),
            },
            "validation_predictions": {
                "path": str(validation_path), "sha256": _sha256(validation_path),
            },
            "active_forecasts": {"path": str(active_path), "sha256": _sha256(active_path)},
            "direct_candidate_forecasts": {
                "path": str(candidate_path), "sha256": _sha256(candidate_path),
            },
        },
        "training": {
            "origin_start": pd.Timestamp(train.forecast_origin.min()).date().isoformat(),
            "origin_end_exclusive": TRAIN_END.date().isoformat(),
            "target_end_inclusive": pd.Timestamp(train.target_end.max()).date().isoformat(),
            "origin_stride_days": TRAIN_ORIGIN_STRIDE_DAYS,
            "rows": int(len(train)),
            "origins": int(train.forecast_origin.nunique()),
            "series": int(train.series.nunique()),
            "per_window_response_fits": {str(window): trained_variants[window]
                                         for window in LOOKBACK_WINDOWS_DAYS},
        },
        "model_definition": {
            "formula": "max(0.01, anchor + beta * OLS_slope_php_per_calendar_day * (lead + last_observed_age_days))",
            "slope_source": "observed daily target rows in the trailing calendar window ending at the forecast origin; no imputation",
            "minimum_slope_observations": MIN_OBSERVATIONS,
            "candidate_windows_days": list(LOOKBACK_WINDOWS_DAYS),
            "coefficient_scope": "one global beta per candidate window; no product-specific corrections",
            "coefficient_fit": "train-only weighted median LAD minimizing equal-series absolute relative movement error",
        },
        "validation_selection": validation_result,
        "selected_window_days": int(selected_window),
        "selected_train_fit": selected_beta,
        "historical_test": {
            **test_result,
            "window_start": min(test_result["forecast_origins"]),
            "window_end": max(test_result["forecast_origins"]),
            "reuse_caveat": (
                "The saved historical test outcomes have been used in earlier research. "
                "This one preselected candidate was not tuned on them, but results are "
                "diagnostic only and cannot establish prospective promotion eligibility."
            ),
        },
    }
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    saved = scored.copy()
    for column in ("forecast_origin", "target_date"):
        if column in saved:
            saved[column] = pd.to_datetime(saved[column]).dt.strftime("%Y-%m-%d")
    saved.to_csv(output_dir / "predictions.csv", index=False)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT)
    parser.add_argument("--active", type=Path, default=DEFAULT_ACTIVE)
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--validation", type=Path, default=DEFAULT_VALIDATION)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    report = run(args.snapshot, args.active, args.candidate, args.validation, args.output_root)
    print(json.dumps({
        "selected_window_days": report["selected_window_days"],
        "train_fit": report["selected_train_fit"],
        "test_rows": report["historical_test"]["n_rows"],
        "test_active": report["historical_test"]["aggregate"]["ensemble"],
        "test_selected_trend": report["historical_test"]["aggregate"][
            f"damped_trend_{report['selected_window_days']}d"
        ],
        "report": str(Path(report["output_dir"]) / "report.json"),
    }, indent=2))


if __name__ == "__main__":
    main()
