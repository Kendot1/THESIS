"""Causal, horizon-specific forecasting experiments.

This module is intentionally separate from the production v2 bundle.  It builds
three target tables from observed labels only:

* daily: the next 7 observed calendar dates;
* weekly: the next four completed Monday--Sunday period means;
* monthly: the next completed calendar-month mean.

All origin features are computed from periods ending no later than the origin.
The CLI refuses a source snapshot that reaches the sealed prospective holdout.
Candidate models are written below the requested output directory and are never
activated or published by this module.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import lightgbm as lgb
import numpy as np
import pandas as pd

from config.settings import get_settings
from data.preprocessor import DataPreprocessor, SERIES_KEY
from utils.prices import round_price


HOLDOUT_START = pd.Timestamp("2026-10-06")
MAX_INPUT_AGE_DAYS = get_settings().max_fill_days
PRIORITY_PRODUCTS = (
    "Chili Labuyo", "Romaine Lettuce", "Green Ice", "Iceberg",
    "Bell Pepper Red",
)
PRIORITY_IDENTITY_PARTS = (
    ("chili", "labuyo"), ("lettuce", "romaine"), ("lettuce", "green ice"),
    ("lettuce", "iceberg"), ("bell pepper", "red"),
)
CATEGORICAL_COLUMNS = ("product_category", "product_name", "product_variant", "origin", "unit")


@dataclass(frozen=True)
class HorizonSpec:
    name: str
    steps: int
    frequency: str
    minimum_coverage: int
    seasonal_periods: int
    history_lags: tuple[int, ...]
    rolling_windows: tuple[int, ...]


SPECS = {
    "daily": HorizonSpec("daily", 7, "daily", 1, 7, (1, 2, 3, 7, 14, 30), (3, 7, 14, 30)),
    "weekly": HorizonSpec("weekly", 4, "weekly", 4, 52, (1, 2, 3, 4, 8, 12), (3, 6, 12)),
    "monthly": HorizonSpec("monthly", 1, "monthly", 15, 12, (1, 2, 3, 6, 12), (3, 6, 12)),
}
LEGACY_SPECS = {
    # Historical experiment runs used a 14-day daily path. Keep that shape
    # available only to replay their explicitly legacy manifests.
    "daily": HorizonSpec("daily", 14, "daily", 1, 7, (1, 2, 3, 7, 14, 30), (3, 7, 14, 30)),
    "weekly": HorizonSpec("weekly", 7, "weekly", 4, 52, (1, 2, 3, 4, 8, 12), (3, 6, 12)),
    "monthly": HorizonSpec("monthly", 3, "monthly", 15, 12, (1, 2, 3, 6, 12), (3, 6, 12)),
}
HORIZON_SPEC_SCOPES = {
    "objective": SPECS,
    "detailed_phases": LEGACY_SPECS,
}
# Exact, previously recorded feature-pipeline versions. Keep this registry
# narrow: a hash is compatible only with the step counts used by that run.
COMPATIBLE_PIPELINE_STEP_COUNTS = {
    "a5f421ace7ed362afca09db853760411013fcc63e801ed750d44cf286f4adecc": {
        "daily": 14, "weekly": 7, "monthly": 3,
    },
    "ffbdb0d9352155bada73b92ec4b54a44240cb1092b7b0eeb5cc5b631361db193": {
        "daily": 14, "weekly": 4, "monthly": 1,
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_snapshot(path: Path) -> pd.DataFrame:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("rows", data.get("data", data))
    frame = pd.DataFrame(data)
    if frame.empty:
        raise ValueError("Snapshot contains no rows")
    return frame


def _month_end(start: pd.Timestamp) -> pd.Timestamp:
    return (start + pd.offsets.MonthEnd(0)).normalize()


def _period_bounds(date: pd.Timestamp, frequency: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    date = pd.Timestamp(date).normalize()
    if frequency == "daily":
        return date, date
    if frequency == "weekly":
        start = date - pd.Timedelta(days=int(date.weekday()))
        return start, start + pd.Timedelta(days=6)
    if frequency == "monthly":
        start = date.replace(day=1)
        return start, _month_end(start)
    raise ValueError(f"Unknown frequency: {frequency}")


def _next_period_start(origin: pd.Timestamp, frequency: str) -> pd.Timestamp:
    origin = pd.Timestamp(origin).normalize()
    if frequency == "daily":
        return origin + pd.Timedelta(days=1)
    if frequency == "weekly":
        return origin + pd.Timedelta(days=7 - int(origin.weekday()))
    if frequency == "monthly":
        return (origin.replace(day=1) + pd.offsets.MonthBegin(1)).normalize()
    raise ValueError(f"Unknown frequency: {frequency}")


def target_periods(origin: pd.Timestamp, spec: HorizonSpec) -> list[dict]:
    """Return future target periods without consulting price observations."""
    start = _next_period_start(origin, spec.frequency)
    periods = []
    for step in range(1, spec.steps + 1):
        if spec.frequency == "daily":
            period_start = start + pd.Timedelta(days=step - 1)
        elif spec.frequency == "weekly":
            period_start = start + pd.Timedelta(days=7 * (step - 1))
        else:
            period_start = (start.to_period("M") + (step - 1)).to_timestamp().normalize()
        period_end = _period_bounds(period_start, spec.frequency)[1]
        periods.append({
            "lead": step,
            "period_start": period_start,
            "period_end": period_end,
            "days_ahead": int((period_start - pd.Timestamp(origin).normalize()).days),
            "period_days": int((period_end - period_start).days + 1),
        })
    return periods


def build_dataset_profile(raw: pd.DataFrame, clean: pd.DataFrame, snapshot: Path) -> dict:
    """Summarize raw and cleaned coverage without using future labels."""
    dates = pd.to_datetime(raw.get("report_date"), errors="coerce").dt.normalize()
    identity = SERIES_KEY + ["report_date"]
    duplicate_mask = raw.duplicated(identity, keep=False) if set(identity) <= set(raw) else pd.Series(False, index=raw.index)
    invalid_price = pd.to_numeric(raw.get("price_index"), errors="coerce")
    invalid_price_mask = ~np.isfinite(invalid_price.to_numpy(dtype=float)) | (invalid_price.to_numpy(dtype=float) <= 0)
    source_dates = raw.get("source_pdf", pd.Series("", index=raw.index)).map(_source_date)
    mismatch = source_dates.notna() & dates.notna() & source_dates.ne(dates)
    observed = clean.loc[clean.is_observed.fillna(False).astype(bool)].copy()
    observed["observed_price"] = pd.to_numeric(observed.observed_price, errors="coerce")
    coverage = (observed.groupby(SERIES_KEY, sort=True)
                .agg(first_observed=("report_date", "min"),
                     last_observed=("report_date", "max"),
                     observed_rows=("observed_price", "count"))
                .reset_index())
    coverage["first_observed"] = pd.to_datetime(coverage["first_observed"]).dt.strftime("%Y-%m-%d")
    coverage["last_observed"] = pd.to_datetime(coverage["last_observed"]).dt.strftime("%Y-%m-%d")
    coverage["calendar_span_days"] = (
        pd.to_datetime(coverage["last_observed"]) - pd.to_datetime(coverage["first_observed"])
    ).dt.days + 1
    coverage["calendar_days_without_observation"] = (
        coverage["calendar_span_days"] - coverage["observed_rows"]
    ).clip(lower=0)
    median_gaps = {}
    for key, group in observed.groupby(SERIES_KEY, sort=True):
        differences = pd.to_datetime(group.report_date).sort_values().drop_duplicates().diff().dt.days.dropna()
        median_gaps[tuple(key)] = float(differences.median()) if not differences.empty else None
    coverage["median_observation_gap_days"] = [
        median_gaps.get(tuple(key))
        for key in coverage[SERIES_KEY].itertuples(index=False, name=None)
    ]
    return {
        "snapshot": str(snapshot),
        "snapshot_sha256": sha256(snapshot),
        "raw_rows": int(len(raw)),
        "raw_date_min": dates.min().date().isoformat() if dates.notna().any() else None,
        "raw_date_max": dates.max().date().isoformat() if dates.notna().any() else None,
        "raw_series_count": int(raw[SERIES_KEY].drop_duplicates().shape[0]) if set(SERIES_KEY) <= set(raw) else None,
        "raw_categories": sorted(raw.product_category.dropna().astype(str).unique().tolist()) if "product_category" in raw else [],
        "raw_duplicate_rows": int(duplicate_mask.sum()),
        "raw_invalid_price_rows": int(np.asarray(invalid_price_mask, dtype=bool).sum()),
        "raw_source_date_mismatch_rows": int(mismatch.sum()),
        "raw_source_date_missing_rows": int(source_dates.isna().sum()),
        "raw_source_date_matched_rows": int((source_dates.notna() & dates.notna() & source_dates.eq(dates)).sum()),
        "clean_rows_after_causal_reindex": int(len(clean)),
        "observed_rows_after_quality_rules": int(len(observed)),
        "clean_series_count": int(clean.groupby(SERIES_KEY).ngroups),
        "series_coverage": coverage.to_dict(orient="records"),
        "quality_policy": {
            "target_rows": "is_observed and observed_price only",
            "input_fill": "causal forward fill limited by max_fill_days",
            "source_quality_exclusions": DataPreprocessor.preprocessing_contract(),
            "sealed_holdout_start": HOLDOUT_START.date().isoformat(),
        },
    }


def _source_date(value) -> pd.Timestamp:
    text = str(value)
    match = re.search(r"([A-Za-z]+)-(\d{1,2})-(\d{4})", text)
    if not match:
        return pd.NaT
    try:
        return pd.Timestamp(datetime.strptime(
            " ".join(match.groups()), "%B %d %Y")).normalize()
    except ValueError:
        return pd.NaT


def build_period_panel(clean: pd.DataFrame, spec: HorizonSpec) -> pd.DataFrame:
    """Create valid period targets from observed labels only."""
    observed = clean.loc[
        clean.is_observed.fillna(False).astype(bool)
        & np.isfinite(pd.to_numeric(clean.observed_price, errors="coerce"))
        & pd.to_numeric(clean.observed_price, errors="coerce").gt(0),
        SERIES_KEY + ["report_date", "observed_price"],
    ].copy()
    observed["report_date"] = pd.to_datetime(observed.report_date).dt.normalize()
    if spec.frequency == "daily":
        observed["period_start"] = observed.report_date
    elif spec.frequency == "weekly":
        observed["period_start"] = observed.report_date - pd.to_timedelta(observed.report_date.dt.weekday, unit="D")
    else:
        observed["period_start"] = observed.report_date.values.astype("datetime64[M]").astype("datetime64[ns]")
    grouped = (observed.groupby(SERIES_KEY + ["period_start"], sort=True)
               .agg(period_value=("observed_price", "mean"),
                    observed_days=("observed_price", "count"),
                    last_observed_date=("report_date", "max"))
               .reset_index())
    bounds = grouped.period_start.map(lambda value: _period_bounds(value, spec.frequency))
    grouped["period_end"] = [end for _, end in bounds]
    grouped["period_days"] = (grouped.period_end - grouped.period_start).dt.days + 1
    grouped["coverage_ratio"] = grouped.observed_days / grouped.period_days
    return grouped.loc[grouped.observed_days.ge(spec.minimum_coverage)].reset_index(drop=True)


def _history_features(history: pd.DataFrame, origin: pd.Timestamp, spec: HorizonSpec) -> dict | None:
    end = pd.Timestamp(origin).normalize()
    period_ends = pd.to_datetime(history.period_end).to_numpy(dtype="datetime64[ns]")
    stop = int(np.searchsorted(period_ends, end.to_datetime64(), side="right"))
    if stop == 0:
        return None
    values = history.period_value.to_numpy(dtype=float)[:stop]
    if not np.isfinite(values).any() or values[-1] <= 0:
        return None
    anchor = float(values[-1])
    row = {
        "anchor": anchor,
        "history_periods": int(len(values)),
        "last_observed_age_days": int((end - history.last_observed_date.iloc[stop - 1]).days),
    }
    for lag in spec.history_lags:
        value = float(values[-lag]) if len(values) >= lag else np.nan
        row[f"lag_{lag}"] = value
        row[f"lag_rel_{lag}"] = value / anchor - 1.0 if np.isfinite(value) else np.nan
    for window in spec.rolling_windows:
        values_window = values[-window:]
        row[f"roll_mean_{window}"] = float(np.mean(values_window))
        row[f"roll_std_{window}"] = float(np.std(values_window, ddof=0)) if len(values_window) > 1 else 0.0
        row[f"roll_rel_{window}"] = row[f"roll_mean_{window}"] / anchor - 1.0
    row["return_1"] = (
        anchor / float(values[-2]) - 1.0
        if len(values) >= 2 and values[-2] > 0 else np.nan
    )
    row["return_3"] = (
        anchor / float(values[-4]) - 1.0
        if len(values) >= 4 and values[-4] > 0 else np.nan
    )
    row["volatility_cv"] = row[f"roll_std_{spec.rolling_windows[-1]}"] / anchor
    return row


def _seasonal_value(target_lookup: dict, target_start: pd.Timestamp,
                    origin: pd.Timestamp, spec: HorizonSpec, anchor: float) -> tuple[float, bool]:
    if spec.frequency == "daily":
        source_start = target_start - pd.Timedelta(days=spec.seasonal_periods)
    elif spec.frequency == "weekly":
        source_start = target_start - pd.Timedelta(days=7 * spec.seasonal_periods)
    else:
        source_start = (target_start.to_period("M") - spec.seasonal_periods).to_timestamp().normalize()
    match = target_lookup.get(source_start)
    if match is not None and pd.Timestamp(match.period_end) <= pd.Timestamp(origin).normalize():
        return float(match.period_value), False
    return anchor, True


def origin_schedule(spec: HorizonSpec, start: pd.Timestamp, end: pd.Timestamp, stride: int) -> list[pd.Timestamp]:
    """Generate origins aligned to the target frequency."""
    start, end = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()
    if spec.frequency == "daily":
        return list(pd.date_range(start, end, freq=f"{stride}D"))
    if spec.frequency == "weekly":
        dates = pd.date_range(start, end, freq="D")
        return [date for date in dates if date.weekday() == 6 and ((date - dates[0]).days // 7) % stride == 0]
    dates = pd.date_range(start, end, freq="ME")
    return [date for index, date in enumerate(dates) if index % stride == 0]


def complete_origin_schedule(spec: HorizonSpec, start: pd.Timestamp,
                             end: pd.Timestamp, target_cutoff: pd.Timestamp,
                             stride: int) -> list[pd.Timestamp]:
    cutoff = pd.Timestamp(target_cutoff).normalize()
    return [origin for origin in origin_schedule(spec, start, end, stride)
            if target_periods(origin, spec)[-1]["period_end"] <= cutoff]


def prepare_history_index(clean: pd.DataFrame, spec: HorizonSpec) -> dict:
    panel = build_period_panel(clean, spec)
    result = {}
    for key, group in panel.groupby(SERIES_KEY, sort=True):
        history = group.reset_index(drop=True)
        lookup = {row.period_start: row for row in history.itertuples(index=False)}
        result[tuple(key)] = (history, lookup)
    return result


def build_examples(clean: pd.DataFrame, spec: HorizonSpec, origins: Iterable[pd.Timestamp],
                   cutoff: pd.Timestamp, history_index: dict | None = None) -> pd.DataFrame:
    histories = history_index if history_index is not None else prepare_history_index(clean, spec)
    rows = []
    cutoff = pd.Timestamp(cutoff).normalize()
    for origin in origins:
        origin = pd.Timestamp(origin).normalize()
        descriptors = target_periods(origin, spec)
        for key, (history, target_lookup) in histories.items():
            features = _history_features(history, origin, spec)
            if (features is None
                    or features["last_observed_age_days"] > MAX_INPUT_AGE_DAYS):
                continue
            for descriptor in descriptors:
                if descriptor["period_end"] > cutoff:
                    continue
                target = target_lookup.get(descriptor["period_start"])
                if target is None:
                    continue
                actual = float(target.period_value)
                anchor = float(features["anchor"])
                seasonal_value, seasonal_fallback = _seasonal_value(
                    target_lookup, descriptor["period_start"], origin, spec, anchor)
                row = {
                    **features,
                    **{column: str(value) for column, value in zip(SERIES_KEY, key)},
                    "series": "||".join(map(str, key)),
                    "forecast_origin": origin,
                    "target_start": descriptor["period_start"],
                    "target_end": descriptor["period_end"],
                    "lead": int(descriptor["lead"]),
                    "days_ahead": int(descriptor["days_ahead"]),
                    "period_days": int(descriptor["period_days"]),
                    "actual": actual,
                    "persistence": anchor,
                    "seasonal_naive": seasonal_value,
                    "seasonal_naive_used_persistence": seasonal_fallback,
                }
                row["target_relative"] = actual / anchor - 1.0
                row["priority_product"] = (
                    row["product_name"].strip().lower(),
                    row["product_variant"].strip().lower(),
                ) in {("chili", "labuyo"), ("lettuce", "romaine"),
                     ("lettuce", "green ice"), ("lettuce", "iceberg"),
                     ("bell pepper", "red")}
                rows.append(row)
    if not rows:
        raise ValueError(f"No examples built for {spec.name}")
    result = pd.DataFrame(rows)
    result["volatility_bucket"] = pd.cut(
        result.volatility_cv.fillna(0), [-np.inf, 0.05, 0.15, np.inf],
        labels=["low", "medium", "high"], right=False).astype(str)
    return result.sort_values(["forecast_origin", "series", "lead"]).reset_index(drop=True)


def build_forecast_inputs(clean: pd.DataFrame, spec: HorizonSpec, origin: pd.Timestamp,
                          history_index: dict | None = None) -> pd.DataFrame:
    """Build origin-bounded feature rows without consulting future target labels."""
    histories = history_index if history_index is not None else prepare_history_index(clean, spec)
    origin = pd.Timestamp(origin).normalize()
    descriptors = target_periods(origin, spec)
    rows = []
    for key, (history, _) in histories.items():
        features = _history_features(history, origin, spec)
        if (features is None
                or features["last_observed_age_days"] > MAX_INPUT_AGE_DAYS):
            continue
        identity = {column: str(value) for column, value in zip(SERIES_KEY, key)}
        series = "||".join(map(str, key))
        for descriptor in descriptors:
            rows.append({
                **features,
                **identity,
                "series": series,
                "forecast_origin": origin,
                "target_start": descriptor["period_start"],
                "target_end": descriptor["period_end"],
                "lead": int(descriptor["lead"]),
                "days_ahead": int(descriptor["days_ahead"]),
                "period_days": int(descriptor["period_days"]),
            })
    if not rows:
        raise ValueError(f"No eligible origin-time features for {spec.name} at {origin.date()}")
    return pd.DataFrame(rows).sort_values(
        ["series", "lead"]).reset_index(drop=True)


def build_publication_rows(forecasts: pd.DataFrame, horizon: str,
                           product_ids: dict[tuple[str, ...], str]) -> list[dict]:
    """Map direct horizon predictions to the stored forecast_values contract.

    This creates API-compatible candidate rows only; it performs no database
    writes, activation, or fallback to another horizon.
    """
    if horizon not in SPECS:
        raise ValueError(f"Unknown forecast horizon: {horizon}")
    if forecasts.empty:
        raise ValueError("Cannot serialize an empty horizon forecast")
    spec = SPECS[horizon]
    required = set(SERIES_KEY) | {
        "forecast_origin", "target_start", "target_end", "lead", "period_days", "predicted_price",
    }
    missing = required - set(forecasts.columns)
    if missing:
        raise ValueError(f"Horizon forecasts are missing publication fields: {sorted(missing)}")

    rows = []
    for _, group in forecasts.groupby(SERIES_KEY, sort=True):
        origins = pd.to_datetime(
            group.forecast_origin, errors="coerce").dt.normalize().dropna().unique()
        if len(origins) != 1:
            raise ValueError("Each publication batch must contain one origin per product")
        origin = pd.Timestamp(origins[0]).normalize()
        descriptors = target_periods(origin, spec)
        by_lead = {int(lead): values for lead, values in group.groupby("lead", sort=True)}
        if set(by_lead) != set(range(1, spec.steps + 1)):
            raise ValueError(f"{horizon} candidate must forecast every lead for every product")
        identity = tuple(str(group.iloc[0][column]) for column in SERIES_KEY)
        product_id = product_ids.get(identity)
        if not product_id:
            raise ValueError(f"No product ID maps to candidate series: {'||'.join(identity)}")

        for descriptor in descriptors:
            lead = int(descriptor["lead"])
            target_rows = by_lead[lead]
            if len(target_rows) != 1:
                raise ValueError(f"Duplicate {horizon} forecast lead {lead} for {'||'.join(identity)}")
            prediction = target_rows.iloc[0]
            start = pd.Timestamp(prediction.target_start).normalize()
            end = pd.Timestamp(prediction.target_end).normalize()
            if start != descriptor["period_start"] or end != descriptor["period_end"]:
                raise ValueError(f"{horizon} lead {lead} has incorrect calendar target bounds")
            value = float(prediction.predicted_price)
            if not np.isfinite(value) or value <= 0:
                raise ValueError(f"{horizon} lead {lead} has an invalid price prediction")
            period_days = int(descriptor["period_days"])
            rows.append({
                "product_id": product_id,
                "prediction_date": end.date().isoformat(),
                "predicted_price": round_price(value),
                "forecast_horizon": horizon,
                "forecast_origin_date": origin.date().isoformat(),
                "target_period_start": start.date().isoformat(),
                "target_period_end": end.date().isoformat(),
                "forecast_step": lead,
                "confidence_score": None,
                "confidence_level": "Insufficient data",
                "covered_days": period_days,
                "period_days": period_days,
            })
    return rows


def _metric(frame: pd.DataFrame, prediction: str) -> dict:
    actual = pd.to_numeric(frame.actual, errors="coerce").to_numpy(dtype=float)
    predicted = pd.to_numeric(frame[prediction], errors="coerce").to_numpy(dtype=float)
    negative_actuals = int(np.count_nonzero(np.isfinite(actual) & (actual < 0)))
    invalid_labels = int(np.count_nonzero(~np.isfinite(actual) | (actual < 0)))
    invalid_predictions = int(np.count_nonzero(~np.isfinite(predicted)))
    valid = np.isfinite(actual) & np.isfinite(predicted) & (actual >= 0)
    actual, predicted = actual[valid], predicted[valid]
    if len(actual) == 0:
        return {"n": 0, "mae_php": None, "rmse_php": None, "mape_pct": None,
                "wape_pct": None, "bias_php": None, "within_5_php_pct": None,
                "underprediction_pct": None, "large_error_over_php20_pct": None,
                "excluded_nonpositive_actuals": negative_actuals,
                "invalid_label_count": invalid_labels,
                "invalid_prediction_count": invalid_predictions,
                "percentage_sample_count": 0,
                "percentage_excluded_zero_or_near_zero": 0}
    error = predicted - actual
    absolute = np.abs(error)
    percentage_rows = actual >= 1e-8
    percentage_count = int(np.count_nonzero(percentage_rows))
    return {
        "n": int(len(actual)),
        "mae_php": float(np.mean(absolute)),
        "rmse_php": float(np.sqrt(np.mean(error ** 2))),
        "mape_pct": (float(np.mean(absolute[percentage_rows] / actual[percentage_rows]) * 100)
                     if percentage_count else None),
        "wape_pct": (float(np.sum(absolute) / np.sum(actual) * 100)
                     if np.sum(actual) >= 1e-8 else None),
        "bias_php": float(np.mean(error)),
        "within_5_php_pct": float(np.mean(absolute <= 5) * 100),
        "underprediction_pct": float(np.mean(error < 0) * 100),
        "large_error_over_php20_pct": float(np.mean(absolute > 20) * 100),
        "excluded_nonpositive_actuals": negative_actuals,
        "invalid_label_count": invalid_labels,
        "invalid_prediction_count": invalid_predictions,
        "percentage_sample_count": percentage_count,
        "percentage_excluded_zero_or_near_zero": int(len(actual) - percentage_count),
    }


def grouped_metrics(frame: pd.DataFrame, prediction: str, group: str) -> list[dict]:
    rows = []
    for key, group_frame in frame.groupby(group, dropna=False, sort=True):
        row = {group: str(key), **_metric(group_frame, prediction)}
        rows.append(row)
    return rows


def _macro_series_metrics(frame: pd.DataFrame, prediction: str) -> dict:
    per_series = [_metric(rows, prediction) for _, rows in frame.groupby("series", sort=True)]
    result = {"series_count": len(per_series)}
    for name in ("mae_php", "rmse_php", "mape_pct", "wape_pct", "bias_php",
                 "within_5_php_pct", "underprediction_pct", "large_error_over_php20_pct"):
        values = [row[name] for row in per_series if row.get(name) is not None]
        result[name] = float(np.mean(values)) if values else None
    return result


def _priority_series(series: str) -> bool:
    parts = series.lower().split("||")
    return len(parts) >= 3 and (parts[1], parts[2]) in PRIORITY_IDENTITY_PARTS


def _feature_frame(frame: pd.DataFrame, columns: list[str], categories: dict[str, list[str]] | None = None) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    numeric = [column for column in columns if column not in CATEGORICAL_COLUMNS]
    data = {
        column: pd.to_numeric(frame[column], errors="coerce").replace(
            [np.inf, -np.inf], np.nan)
        for column in numeric
    }
    category_map = ({key: list(values) for key, values in categories.items()}
                    if categories is not None else {})
    for column in CATEGORICAL_COLUMNS:
        values = frame[column].fillna("Unknown").astype(str)
        allowed = category_map.get(column)
        if allowed is None:
            allowed = sorted(values.unique().tolist())
        if "Unknown" not in allowed:
            allowed = [*allowed, "Unknown"]
        values = values.where(values.isin(allowed), "Unknown")
        category_map[column] = allowed
        data[column] = pd.Series(
            pd.Categorical(values, categories=allowed), index=frame.index)
    result = pd.DataFrame(data, index=frame.index)
    return result, category_map


def model_feature_columns(spec: HorizonSpec) -> list[str]:
    return [
        "anchor", "history_periods", "last_observed_age_days", "lead", "days_ahead", "period_days",
        "return_1", "return_3", "volatility_cv",
        *[f"lag_{lag}" for lag in spec.history_lags],
        *[f"lag_rel_{lag}" for lag in spec.history_lags],
        *[f"roll_mean_{window}" for window in spec.rolling_windows],
        *[f"roll_std_{window}" for window in spec.rolling_windows],
        *[f"roll_rel_{window}" for window in spec.rolling_windows],
        *CATEGORICAL_COLUMNS,
    ]


def _fit_lgbm(train: pd.DataFrame, validation: pd.DataFrame, strategy: str, spec: HorizonSpec):
    base_columns = [column for column in model_feature_columns(spec) if column in train.columns]
    if strategy == "per_lead":
        models = {}
        _, category_map = _feature_frame(train, base_columns)
        for lead in range(1, spec.steps + 1):
            train_lead = train.loc[train.lead.eq(lead)]
            validation_lead = validation.loc[validation.lead.eq(lead)]
            if train_lead.empty or validation_lead.empty:
                continue
            x_train, category_map = _feature_frame(train_lead, base_columns, category_map)
            x_validation, _ = _feature_frame(validation_lead, base_columns, category_map)
            model = lgb.LGBMRegressor(
                objective="regression_l1", n_estimators=800, learning_rate=0.03,
                num_leaves=31, min_child_samples=80, reg_lambda=5.0,
                feature_fraction=0.85, bagging_fraction=0.85, bagging_freq=1,
                random_state=42, n_jobs=4, verbosity=-1,
            )
            model.fit(x_train, train_lead.target_relative,
                      eval_set=[(x_validation, validation_lead.target_relative)],
                      categorical_feature=list(CATEGORICAL_COLUMNS),
                      callbacks=[lgb.early_stopping(60, verbose=False)])
            models[lead] = model
        return {"strategy": strategy, "models": models, "category_map": category_map, "columns": base_columns}
    x_train, category_map = _feature_frame(train, base_columns)
    x_validation, _ = _feature_frame(validation, base_columns, category_map)
    model = lgb.LGBMRegressor(
        objective="regression_l1", n_estimators=800, learning_rate=0.03,
        num_leaves=31, min_child_samples=80, reg_lambda=5.0,
        feature_fraction=0.85, bagging_fraction=0.85, bagging_freq=1,
        random_state=42, n_jobs=4, verbosity=-1,
    )
    model.fit(x_train, train.target_relative,
              eval_set=[(x_validation, validation.target_relative)],
              categorical_feature=list(CATEGORICAL_COLUMNS),
              callbacks=[lgb.early_stopping(60, verbose=False)])
    return {"strategy": strategy, "model": model, "category_map": category_map, "columns": base_columns}


def _fit_final(train: pd.DataFrame, strategy: str, spec: HorizonSpec, selected: dict):
    base_columns = selected["columns"]
    if strategy == "per_lead":
        models = {}
        _, category_map = _feature_frame(train, base_columns)
        for lead in range(1, spec.steps + 1):
            rows = train.loc[train.lead.eq(lead)]
            if rows.empty:
                continue
            x_train, category_map = _feature_frame(rows, base_columns, category_map)
            validation_model = selected["models"].get(lead)
            rounds = (max(1, int(validation_model.best_iteration_ or 300))
                      if validation_model else 300)
            model = lgb.LGBMRegressor(
                objective="regression_l1", n_estimators=rounds, learning_rate=0.03,
                num_leaves=31, min_child_samples=80, reg_lambda=5.0,
                feature_fraction=0.85, bagging_fraction=0.85, bagging_freq=1,
                random_state=42, n_jobs=4, verbosity=-1,
            )
            model.fit(x_train, rows.target_relative,
                      categorical_feature=list(CATEGORICAL_COLUMNS))
            models[lead] = model
        return {
            **selected,
            "models": models,
            "category_map": category_map,
            "rounds_by_lead": {
                str(lead): int(model.n_estimators_) for lead, model in models.items()
            },
        }
    x_train, category_map = _feature_frame(train, base_columns)
    rounds = max(1, int(selected["model"].best_iteration_ or 300))
    model = lgb.LGBMRegressor(
        objective="regression_l1", n_estimators=rounds, learning_rate=0.03,
        num_leaves=31, min_child_samples=80, reg_lambda=5.0,
        feature_fraction=0.85, bagging_fraction=0.85, bagging_freq=1,
        random_state=42, n_jobs=4, verbosity=-1,
    )
    model.fit(x_train, train.target_relative,
              categorical_feature=list(CATEGORICAL_COLUMNS))
    return {
        **selected,
        "model": model,
        "category_map": category_map,
        "rounds_by_lead": {"shared": int(model.n_estimators_)},
    }


def _predict(model_bundle: dict, frame: pd.DataFrame) -> np.ndarray:
    if model_bundle["strategy"] == "per_lead":
        result = np.full(len(frame), np.nan, dtype=float)
        for lead, rows in frame.groupby("lead", sort=False):
            model = model_bundle["models"].get(int(lead))
            if model is None:
                continue
            x, _ = _feature_frame(rows, model_bundle["columns"], model_bundle["category_map"])
            positions = frame.index.get_indexer(rows.index)
            result[positions] = model.predict(x)
    else:
        x, _ = _feature_frame(frame, model_bundle["columns"], model_bundle["category_map"])
        result = model_bundle["model"].predict(x)
    return np.maximum(0.01, frame.anchor.to_numpy(dtype=float) * (1.0 + result))


class HorizonModelBundle:
    """Load and run a saved direct horizon model without production activation."""

    def __init__(self, model_dir: Path):
        self.model_dir = Path(model_dir).resolve()
        inference_manifest_path = self.model_dir / "inference_manifest.json"
        manifest_path = (inference_manifest_path if inference_manifest_path.exists()
                         else self.model_dir / "manifest.json")
        self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.name == "inference_manifest.json":
            parent_name = self.manifest.get("parent_manifest_file")
            if parent_name != "manifest.json":
                raise ValueError("Inference manifest has an invalid parent manifest reference")
            parent_path = self.model_dir / parent_name
            expected_parent_hash = self.manifest.get("parent_manifest_sha256")
            if (not expected_parent_hash or not parent_path.is_file()
                    or sha256(parent_path) != expected_parent_hash):
                raise ValueError("Inference manifest parent checksum mismatch")
        self.horizon = self.manifest.get("horizon")
        if self.horizon not in SPECS:
            raise ValueError(f"Unknown candidate horizon in manifest: {self.horizon}")
        manifest_steps = self.manifest.get("steps", SPECS[self.horizon].steps)
        current_spec = SPECS[self.horizon]
        legacy_spec = LEGACY_SPECS[self.horizon]
        if manifest_steps == current_spec.steps:
            self.spec = current_spec
        elif (manifest_steps == legacy_spec.steps
              and self.horizon in {"weekly", "monthly"}):
            self.spec = legacy_spec
        else:
            raise ValueError("Candidate manifest step count does not match its horizon")
        self.strategy = self.manifest.get("strategy")
        if self.strategy not in {"shared", "per_lead"}:
            raise ValueError(f"Unknown candidate strategy: {self.strategy}")
        feature_schema = self.manifest.get("feature_schema", {})
        declared_columns = feature_schema.get("columns")
        declared_categories = feature_schema.get("categories")
        self.columns: list[str] | None = list(declared_columns) if declared_columns else None
        self.category_map: dict[str, list[str]] | None = (
            {key: list(values) for key, values in declared_categories.items()}
            if declared_categories is not None else None
        )
        self.models = {}
        for key, filename in self.manifest.get("model_files", {}).items():
            relative_path = Path(filename)
            if relative_path.is_absolute() or ".." in relative_path.parts:
                raise ValueError(f"Unsafe candidate model path: {filename}")
            path = (self.model_dir / relative_path).resolve()
            if self.model_dir not in path.parents:
                raise ValueError(f"Candidate model path escapes its bundle: {filename}")
            if not path.is_file():
                raise FileNotFoundError(path)
            expected_hash = self.manifest.get("model_sha256", {}).get(key)
            if expected_hash and sha256(path) != expected_hash:
                raise ValueError(f"Candidate model hash mismatch: {filename}")
            if self.manifest.get("schema_version", 1) >= 2 and not expected_hash:
                raise ValueError(f"Version 2 manifest is missing a hash for {filename}")
            model = lgb.Booster(model_file=str(path))
            model_columns = list(model.feature_name())
            embedded_categories = model.pandas_categorical
            if (not model_columns or not embedded_categories
                    or len(embedded_categories) != len(CATEGORICAL_COLUMNS)):
                raise ValueError(f"Candidate model lacks a complete feature/category schema: {filename}")
            model_categories = {
                name: [str(value) for value in values]
                for name, values in zip(CATEGORICAL_COLUMNS, embedded_categories)
            }
            if self.columns is None:
                self.columns = model_columns
                self.category_map = model_categories
            elif model_columns != self.columns or model_categories != self.category_map:
                raise ValueError("Per-lead candidate models disagree on feature/category schema")
            if model_columns != self.columns or model_categories != self.category_map:
                raise ValueError(f"Candidate feature contract disagrees with model file: {filename}")
            self.models[str(key)] = model
        if not self.models or self.columns is None or self.category_map is None:
            raise ValueError("Candidate manifest contains no usable model files")
        market_origins = [
            value for value in self.category_map.get("origin", [])
            if value != "Unknown"
        ]
        if (market_origins and all(
                re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
                for value in market_origins)):
            raise ValueError(
                "Candidate origin feature contains forecast dates instead of market origins; "
                "rebuild this superseded feature-collision artifact"
            )
        expected_keys = ({"shared"} if self.strategy == "shared" else
                         {str(lead) for lead in range(1, self.spec.steps + 1)})
        if set(self.models) != expected_keys:
            raise ValueError("Candidate manifest does not contain exactly one model per required lead")
        if self.manifest.get("schema_version", 1) >= 2:
            if self.manifest.get("artifact_role") != "candidate":
                raise ValueError("Version 2 horizon artifacts must be marked as candidates")
            expected_pipeline_hash = self.manifest.get("feature_pipeline_sha256")
            supported_steps = COMPATIBLE_PIPELINE_STEP_COUNTS.get(
                expected_pipeline_hash, {})
            current_pipeline_hash = sha256(Path(__file__).resolve())
            current_code_steps = {
                name: {scope[name].steps for scope in HORIZON_SPEC_SCOPES.values()}
                for name in HORIZON_SPEC_SCOPES["objective"]
            }
            if (not expected_pipeline_hash
                    or (expected_pipeline_hash == current_pipeline_hash
                        and self.spec.steps not in current_code_steps[self.horizon])
                    or (expected_pipeline_hash != current_pipeline_hash
                        and supported_steps.get(self.horizon) != self.spec.steps)):
                raise ValueError("Candidate feature-pipeline source hash is missing or mismatched")
            if feature_schema.get("categorical_columns") != list(CATEGORICAL_COLUMNS):
                raise ValueError("Candidate categorical feature contract is invalid")
            target = self.manifest.get("target_definition", {})
            if target.get("minimum_coverage") != self.spec.minimum_coverage:
                raise ValueError("Candidate target coverage does not match its horizon specification")
            input_contract = self.manifest.get("input_contract", {})
            if input_contract.get("maximum_last_observation_age_days") != MAX_INPUT_AGE_DAYS:
                raise ValueError("Candidate maximum input age differs from the current preprocessing contract")
            if input_contract.get("history_lags") != list(self.spec.history_lags):
                raise ValueError("Candidate history lags differ from the current horizon specification")
            if input_contract.get("rolling_windows") != list(self.spec.rolling_windows):
                raise ValueError("Candidate rolling windows differ from the current horizon specification")

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        if frame.empty:
            raise ValueError("Cannot predict an empty horizon feature frame")
        missing_columns = set(self.columns) - set(frame.columns)
        if missing_columns:
            raise ValueError(f"Candidate input is missing features: {sorted(missing_columns)}")
        leads = pd.to_numeric(frame.lead, errors="coerce")
        if leads.isna().any() or not leads.isin(range(1, self.spec.steps + 1)).all():
            raise ValueError("Candidate input contains an invalid forecast lead")
        if self.strategy == "shared":
            model = self.models.get("shared")
            if model is None:
                raise ValueError("Shared candidate manifest has no shared model")
            features, _ = _feature_frame(frame, self.columns, self.category_map)
            relative = model.predict(features)
        else:
            relative = np.full(len(frame), np.nan, dtype=float)
            for lead, rows in frame.groupby("lead", sort=False):
                model = self.models.get(str(int(lead)))
                if model is None:
                    continue
                features, _ = _feature_frame(rows, self.columns, self.category_map)
                positions = frame.index.get_indexer(rows.index)
                relative[positions] = model.predict(features)
        if not np.isfinite(relative).all():
            raise ValueError("Candidate did not produce a finite prediction for every input row")
        anchor = pd.to_numeric(frame.anchor, errors="coerce").to_numpy(dtype=float)
        if not np.isfinite(anchor).all() or (anchor <= 0).any():
            raise ValueError("Candidate inputs require finite, positive price anchors")
        predictions = np.maximum(
            0.01,
            anchor * (1.0 + relative),
        )
        if not np.isfinite(predictions).all():
            raise ValueError("Candidate produced a nonfinite price prediction")
        return predictions

    def forecast(self, clean: pd.DataFrame, origin: pd.Timestamp) -> pd.DataFrame:
        inputs = build_forecast_inputs(clean, self.spec, origin)
        inputs["predicted_price"] = self.predict(inputs)
        return inputs

    def forecast_rows(self, clean: pd.DataFrame, origin: pd.Timestamp,
                      product_ids: dict[tuple[str, ...], str]) -> list[dict]:
        """Create API-compatible rows for an offline/shadow candidate forecast."""
        return build_publication_rows(self.forecast(clean, origin), self.horizon, product_ids)


def _select_strategy(validation_scores: dict[str, dict]) -> str:
    return min(validation_scores, key=lambda name: (
        validation_scores[name]["mae_php"] if validation_scores[name]["mae_php"] is not None else math.inf,
        validation_scores[name]["rmse_php"] if validation_scores[name]["rmse_php"] is not None else math.inf,
        validation_scores[name]["mape_pct"] if validation_scores[name]["mape_pct"] is not None else math.inf,
    ))


def _lead_band_metrics(frame: pd.DataFrame, prediction: str, spec: HorizonSpec) -> dict:
    if spec.frequency == "daily":
        bands = {"days_1_7": frame.lead.between(1, 7),
                 "days_8_14": frame.lead.between(8, 14)}
    elif spec.frequency == "weekly":
        bands = {"weeks_1_3": frame.lead.between(1, min(3, spec.steps))}
        if spec.steps == 4:
            bands["week_4"] = frame.lead.eq(4)
        elif spec.steps >= 5:
            bands["weeks_4_5"] = frame.lead.between(4, min(5, spec.steps))
        if spec.steps >= 6:
            bands["weeks_6_7"] = frame.lead.between(6, min(7, spec.steps))
    else:
        bands = {f"month_{month}": frame.lead.eq(month)
                 for month in range(1, spec.steps + 1)}
    return {
        name: _metric(frame.loc[mask], prediction)
        for name, mask in bands.items()
    }


def run_horizon(clean: pd.DataFrame, spec: HorizonSpec, train_end: pd.Timestamp,
                validation_end: pd.Timestamp, test_end: pd.Timestamp,
                stride: int) -> dict:
    first = pd.Timestamp(clean.report_date.min()).normalize() + pd.Timedelta(days=30)
    validation_origins = complete_origin_schedule(
        spec, train_end + pd.Timedelta(days=1), validation_end,
        validation_end, stride)
    test_origins = complete_origin_schedule(
        spec, validation_end + pd.Timedelta(days=1), test_end,
        test_end, stride)
    if not validation_origins or not test_origins:
        raise ValueError(f"Not enough complete rolling origins for {spec.name}")

    sample_stride = 7 if spec.frequency == "daily" else 1
    history_index = prepare_history_index(clean, spec)
    training_origins = origin_schedule(
        spec, first, max(test_origins), sample_stride)
    all_examples = build_examples(clean, spec, training_origins, test_end, history_index)
    train = all_examples.loc[
        all_examples.forecast_origin.lt(pd.Timestamp(train_end).normalize())
        & all_examples.target_end.le(pd.Timestamp(train_end).normalize())
    ].reset_index(drop=True)
    if train.empty:
        raise ValueError(f"No historical fitting examples for {spec.name}")
    validation = build_examples(clean, spec, validation_origins, validation_end, history_index)
    test = build_examples(clean, spec, test_origins, test_end, history_index)
    validation_scores = {}
    validation_bundles = {}
    for strategy in ("shared", "per_lead"):
        bundle = _fit_lgbm(train, validation, strategy, spec)
        validation_bundles[strategy] = bundle
        validation[f"candidate_{strategy}"] = _predict(bundle, validation)
    common_validation = validation[["candidate_shared", "candidate_per_lead"]].notna().all(axis=1)
    if not common_validation.any():
        raise ValueError(f"No common validation predictions for {spec.name} strategies")
    for strategy in ("shared", "per_lead"):
        validation_scores[strategy] = _metric(
            validation.loc[common_validation], f"candidate_{strategy}")
    selected = _select_strategy(validation_scores)
    test[f"candidate_{selected}"] = np.nan
    final = None
    fit_log = []
    for origin in test_origins:
        fit_rows = all_examples.loc[
            all_examples.forecast_origin.lt(origin) & all_examples.target_end.le(origin)
        ].reset_index(drop=True)
        target_rows = test.loc[test.forecast_origin.eq(origin)]
        if fit_rows.empty or target_rows.empty:
            continue
        final = _fit_final(
            fit_rows, selected, spec, validation_bundles[selected])
        predictions = _predict(final, target_rows)
        test.loc[target_rows.index, f"candidate_{selected}"] = predictions
        fit_log.append({
            "forecast_origin": origin.date().isoformat(),
            "fit_rows": int(len(fit_rows)),
            "latest_training_target_end": pd.Timestamp(fit_rows.target_end.max()).date().isoformat(),
            "prediction_rows": int(len(target_rows)),
        })
    test = test.dropna(subset=[f"candidate_{selected}"]).reset_index(drop=True)
    if final is None or test.empty:
        raise ValueError(f"No rolling test predictions generated for {spec.name}")
    return {
        "spec": spec,
        "source_data_as_of": pd.to_datetime(clean.report_date).max().date().isoformat(),
        "selected_strategy": selected,
        "counts": {"train": len(train), "validation": len(validation), "test": len(test),
                   "validation_origins": len(validation_origins),
                   "test_origins": len(test_origins),
                   "training_origin_stride": sample_stride,
                   "evaluation_origin_stride": stride},
        "validation_scores": validation_scores,
        "validation": validation,
        "test": test,
        "model": final,
        "test_fit_log": fit_log,
        "origins": {
            "train": [str(value.date()) for value in training_origins],
            "validation": [str(value.date()) for value in validation_origins],
            "test": [str(value.date()) for value in test_origins],
        },
    }


def _report_result(result: dict) -> dict:
    spec = result["spec"]
    selected = result["selected_strategy"]
    validation = result["validation"]
    test = result["test"]
    prediction = f"candidate_{selected}"
    by_lead = grouped_metrics(test, prediction, "lead")
    by_series = grouped_metrics(test, prediction, "series")
    by_volatility = grouped_metrics(test, prediction, "volatility_bucket")
    by_origin = grouped_metrics(test, prediction, "forecast_origin")
    priority = [row for row in by_series if _priority_series(row["series"])]
    persistence_by_series = {
        row["series"]: row for row in grouped_metrics(test, "persistence", "series")
    }
    paired_series = []
    for row in by_series:
        baseline = persistence_by_series[row["series"]]
        paired_series.append({
            "series": row["series"],
            "candidate": row,
            "persistence": baseline,
            "mae_delta_php": row["mae_php"] - baseline["mae_php"],
            "rmse_delta_php": row["rmse_php"] - baseline["rmse_php"],
            "mape_delta_pct_points": row["mape_pct"] - baseline["mape_pct"],
            "within_5_delta_percentage_points": (
                row["within_5_php_pct"] - baseline["within_5_php_pct"]),
        })
    candidate_test = _metric(test, prediction)
    persistence_test = _metric(test, "persistence")
    return {
        "horizon": spec.name,
        "target_definition": {
            "frequency": spec.frequency,
            "steps": spec.steps,
            "minimum_period_coverage": spec.minimum_coverage,
            "target": "mean of valid observed_price labels in the target period" if spec.frequency != "daily" else "observed_price on each target calendar date",
            "weekly_boundary": "Monday through Sunday",
            "monthly_boundary": "calendar month",
        },
        "selected_strategy": selected,
        "counts": result["counts"],
        "origins": result["origins"],
        "strategy_selection_policy": (
            "Lowest validation MAE, then RMSE, then MAPE; both strategies are scored "
            "on the same validation rows where both produce predictions."
        ),
        "validation": {
            "persistence": _metric(validation, "persistence"),
            "seasonal_naive": _metric(validation, "seasonal_naive"),
            "candidate_strategies": result["validation_scores"],
        },
        "test": {
            "persistence": persistence_test,
            "seasonal_naive": _metric(test, "seasonal_naive"),
            "candidate": candidate_test,
            "candidate_macro_series": _macro_series_metrics(test, prediction),
            "persistence_macro_series": _macro_series_metrics(test, "persistence"),
            "delta_vs_persistence": {
                "mae_php": candidate_test["mae_php"] - persistence_test["mae_php"],
                "rmse_php": candidate_test["rmse_php"] - persistence_test["rmse_php"],
                "mape_percentage_points": candidate_test["mape_pct"] - persistence_test["mape_pct"],
                "within_5_php_percentage_points": (
                    candidate_test["within_5_php_pct"] - persistence_test["within_5_php_pct"]),
                "bias_php": candidate_test["bias_php"] - persistence_test["bias_php"],
            },
            "by_lead": by_lead,
            "by_required_lead_band": _lead_band_metrics(test, prediction, spec),
            "by_origin": by_origin,
            "by_series": by_series,
            "per_series_vs_persistence": paired_series,
            "priority_products": priority,
            "by_volatility": by_volatility,
        },
        "candidate_confidence": "not calibrated; no probability or interval emitted",
        "aggregate_metric_note": (
            "Pooled metrics weight every valid target row equally across product identities; "
            "series-macro metrics average each product series equally. Prices are PHP per "
            "series-specific unit, so cross-unit pooled PHP errors are descriptive only."
        ),
        "bias_sign": "prediction minus actual; negative means underprediction",
        "candidate_beats_persistence_on_mae_rmse_mape": all(
            candidate_test[name] < persistence_test[name]
            for name in ("mae_php", "rmse_php", "mape_pct")),
    }


def _save_models(result: dict, output_dir: Path, source_sha: str) -> dict:
    spec = result["spec"]
    path = output_dir / spec.name / result["selected_strategy"]
    path.mkdir(parents=True, exist_ok=True)
    bundle = result["model"]
    if bundle["strategy"] == "per_lead":
        expected_filenames = [f"lead_{lead}.txt" for lead in bundle["models"]]
    else:
        expected_filenames = ["shared.txt"]
    existing_models = [path / filename for filename in expected_filenames if (path / filename).exists()]
    if existing_models:
        raise FileExistsError(f"Refusing to overwrite candidate model: {existing_models[0]}")
    manifest_path = path / "manifest.json"
    if manifest_path.exists():
        raise FileExistsError(f"Refusing to overwrite candidate manifest: {manifest_path}")
    if bundle["strategy"] == "per_lead":
        model_paths = {}
        for lead, model in bundle["models"].items():
            model_path = path / f"lead_{lead}.txt"
            model.booster_.save_model(str(model_path))
            model_paths[str(lead)] = model_path.name
    else:
        model_path = path / "shared.txt"
        bundle["model"].booster_.save_model(str(model_path))
        model_paths = {"shared": model_path.name}
    fit_log = result.get("test_fit_log", [])
    last_fit = fit_log[-1] if fit_log else {}
    model_hashes = {key: sha256(path / filename) for key, filename in model_paths.items()}
    manifest = {
        "schema_version": 2,
        "artifact_role": "candidate",
        "horizon": spec.name,
        "strategy": result["selected_strategy"],
        "source_snapshot_sha256": source_sha,
        "feature_pipeline_sha256": sha256(Path(__file__).resolve()),
        "feature_pipeline_sha256": sha256(Path(__file__).resolve()),
        "source_data_as_of": result.get("source_data_as_of"),
        "steps": spec.steps,
        "target_definition": {
            "frequency": spec.frequency,
            "target": (
                "observed price on each target calendar date" if spec.frequency == "daily"
                else "mean of valid observed prices within the target period"
            ),
            "week_boundary": "Monday through Sunday" if spec.frequency == "weekly" else None,
            "month_boundary": "calendar month" if spec.frequency == "monthly" else None,
            "minimum_coverage": spec.minimum_coverage,
        },
        "selection": "lowest validation MAE, then RMSE, then MAPE",
        "final_refit_estimators": bundle.get("rounds_by_lead", {}),
        "final_refit": {
            "forecast_origin": last_fit.get("forecast_origin"),
            "latest_training_target_end": last_fit.get("latest_training_target_end"),
        },
        "feature_schema": {
            "columns": list(bundle["columns"]),
            "categorical_columns": list(CATEGORICAL_COLUMNS),
            "categories": {
                key: list(values) for key, values in bundle["category_map"].items()
            },
        },
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
        "model_files": model_paths,
        "model_sha256": model_hashes,
        "production_activated": False,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def write_result(result: dict, output_dir: Path, source_sha: str) -> dict:
    report = _report_result(result)
    report["test_fit_log"] = result["test_fit_log"]
    report["model_manifest"] = _save_models(result, output_dir, source_sha)
    report_path = output_dir / result["spec"].name / "report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    for split_name in ("validation", "test"):
        frame = result[split_name].copy()
        frame["forecast_origin"] = pd.to_datetime(
            frame.forecast_origin).dt.strftime("%Y-%m-%d")
        frame["target_start"] = pd.to_datetime(frame.target_start).dt.strftime("%Y-%m-%d")
        frame["target_end"] = pd.to_datetime(frame.target_end).dt.strftime("%Y-%m-%d")
        frame.to_csv(report_path.parent / f"{split_name}_predictions.csv", index=False)
    return report


def run_cli(args) -> dict:
    data_path = Path(args.data).resolve()
    output_dir = Path(args.output_dir).resolve()
    raw = load_snapshot(data_path)
    report_dates = pd.to_datetime(raw.report_date, errors="coerce").dt.normalize()
    if report_dates.max() >= pd.Timestamp(args.holdout_start):
        raise ValueError("Input snapshot reaches the sealed prospective holdout")
    clean = DataPreprocessor().validate(raw)
    profile = build_dataset_profile(raw, clean, data_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    if (output_dir / "summary.json").exists():
        raise FileExistsError(f"Refusing to overwrite a completed horizon run: {output_dir}")
    (output_dir / "dataset_profile.json").write_text(json.dumps(profile, indent=2, allow_nan=False), encoding="utf-8")
    train_end = pd.Timestamp(args.train_end)
    validation_end = pd.Timestamp(args.validation_end)
    test_end = pd.Timestamp(args.test_end)
    specs = HORIZON_SPEC_SCOPES[args.scope]
    if not train_end < validation_end < test_end < pd.Timestamp(args.holdout_start):
        raise ValueError("Chronological cutoffs must end before the holdout")
    reports = {}
    for name, stride in (("daily", args.daily_stride), ("weekly", args.weekly_stride), ("monthly", args.monthly_stride)):
        report_path = output_dir / name / "report.json"
        if name not in args.horizons:
            if report_path.exists():
                prior_report = json.loads(report_path.read_text(encoding="utf-8"))
                prior_sha = prior_report.get("model_manifest", {}).get("source_snapshot_sha256")
                if prior_sha != profile["snapshot_sha256"]:
                    raise ValueError(f"Existing {name} report uses a different data snapshot")
                prior_steps = prior_report.get("target_definition", {}).get("steps")
                if prior_steps != specs[name].steps:
                    raise ValueError(f"Existing {name} report uses a different horizon scope")
                reports[name] = prior_report
            continue
        if report_path.exists():
            raise FileExistsError(f"Refusing to overwrite completed {name} horizon: {report_path}")
        result = run_horizon(clean, specs[name], train_end, validation_end, test_end, stride)
        reports[name] = write_result(result, output_dir, profile["snapshot_sha256"])
    summary = {
        "source_snapshot": str(data_path),
        "source_snapshot_sha256": profile["snapshot_sha256"],
        "holdout_start": pd.Timestamp(args.holdout_start).date().isoformat(),
        "holdout_labels_used": False,
        "production_activated": False,
        "task_scope": args.scope,
        "splits": {"train_end": args.train_end, "validation_end": args.validation_end, "test_end": args.test_end},
        "origin_strides": {
            "daily": args.daily_stride,
            "weekly": args.weekly_stride,
            "monthly": args.monthly_stride,
        },
        "horizons": reports,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--train-end", default="2024-08-26")
    parser.add_argument("--validation-end", default="2025-09-12")
    parser.add_argument("--test-end", default="2026-09-30")
    parser.add_argument("--holdout-start", default=HOLDOUT_START.date().isoformat())
    parser.add_argument("--daily-stride", type=int, default=30)
    parser.add_argument("--weekly-stride", type=int, default=4)
    parser.add_argument("--monthly-stride", type=int, default=1)
    parser.add_argument("--horizons", nargs="+", choices=("daily", "weekly", "monthly"),
                        default=("daily", "weekly", "monthly"))
    parser.add_argument("--scope", choices=tuple(HORIZON_SPEC_SCOPES), default="objective",
                        help="Use the Objective 14/4/1 counts or detailed-phase 14/7/3 counts")
    args = parser.parse_args()
    if min(args.daily_stride, args.weekly_stride, args.monthly_stride) < 1:
        raise ValueError("Origin strides must be positive")
    summary = run_cli(args)
    for name, result in summary["horizons"].items():
        test = result["test"]
        print(
            f"{name}: candidate MAE={test['candidate']['mae_php']:.3f} PHP, "
            f"MAPE={test['candidate']['mape_pct']:.3f}%, "
            f"persistence MAE={test['persistence']['mae_php']:.3f} PHP, "
            f"origins={result['counts']['test_origins']}"
        )
    print(f"Detailed report: {Path(args.output_dir).resolve() / 'summary.json'}")


if __name__ == "__main__":
    main()
