"""Leakage-safe empirical prediction-interval calibration.

Intervals are calibrated from saved validation residuals and evaluated on a
separate chronological test file.  They are predictive intervals for future
prices, not confidence intervals for a mean and not probabilities that a
single forecast is correct.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


DEFAULT_NOMINAL_LEVEL = 0.80
DEFAULT_TARGET_COVERAGE = 0.95
DEFAULT_MIN_SAMPLES = 8
DEFAULT_MIN_ORIGINS = 4
DEFAULT_MIN_TEST_SAMPLES = 10
FORECAST_HORIZON_LEAD_BOUNDS = {
    "daily": (1, 7),
    "weekly": (1, 28),
    "monthly": (1, 30),
}


def minimum_conformal_sample_count(nominal_level: float, *, min_samples: int = DEFAULT_MIN_SAMPLES) -> int:
    """Minimum scores for a finite split-conformal absolute-residual interval."""
    if not 0 < nominal_level < 1:
        raise ValueError("nominal_level must be between zero and one")
    finite_rank_minimum = math.ceil(
        float(nominal_level) / (1.0 - float(nominal_level)) - 1e-12
    )
    return max(int(min_samples), finite_rank_minimum)


def calibrate_residual_interval(
    actual,
    predicted,
    *,
    origins=None,
    nominal_level: float = DEFAULT_NOMINAL_LEVEL,
    min_samples: int = DEFAULT_MIN_SAMPLES,
    min_origins: int = DEFAULT_MIN_ORIGINS,
) -> dict | None:
    """Return a finite-sample absolute-residual interval or ``None`` if unsupported.

    The order statistic is split-conformal under exchangeable residuals. For
    time-dependent price residuals this is an empirical calibration procedure;
    the exchangeability assumption is not guaranteed.
    """
    if not 0 < nominal_level < 1:
        raise ValueError("nominal_level must be between zero and one")
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    if actual.shape != predicted.shape:
        raise ValueError("actual and predicted must have the same shape")
    valid = np.isfinite(actual) & np.isfinite(predicted) & (actual > 0)
    if origins is not None:
        origin_values = np.asarray(origins, dtype=object)
        if origin_values.shape != actual.shape:
            raise ValueError("origins must have the same shape as actual")
        origin_values = origin_values[valid]
    else:
        origin_values = None
    residuals = actual[valid] - predicted[valid]
    sample_count = int(residuals.size)
    origin_count = int(pd.Series(origin_values).nunique()) if origin_values is not None else sample_count
    required_samples = minimum_conformal_sample_count(
        nominal_level, min_samples=min_samples
    )
    required_origins = max(int(min_origins), required_samples)
    if sample_count < required_samples or origin_count < required_origins:
        return None
    rank = int(math.ceil((sample_count + 1) * float(nominal_level) - 1e-12))
    if rank > sample_count:
        return None
    absolute_residuals = np.sort(np.abs(residuals))
    radius = float(absolute_residuals[rank - 1])
    if not np.isfinite(radius):
        return None
    return {
        "nominal_level": float(nominal_level),
        "lower_error_php": -radius,
        "upper_error_php": radius,
        "sample_count": sample_count,
        "origin_count": origin_count,
        "required_sample_count": required_samples,
        "required_origin_count": required_origins,
        "absolute_residual_order_statistic_rank": rank,
        "calibration_method": "split_conformal_absolute_residual_order_statistic",
        "calibration_source": "chronological_validation",
        "reliability_status": "limited",
    }


def interval_from_calibration(point: float, calibration: dict | None) -> tuple[float, float] | None:
    """Apply a signed-residual interval and enforce a positive price domain."""
    if calibration is None:
        return None
    point = float(point)
    lower = point + float(calibration["lower_error_php"])
    upper = point + float(calibration["upper_error_php"])
    if not np.isfinite(lower) or not np.isfinite(upper):
        return None
    lower = max(0.01, lower)
    upper = max(lower, upper)
    return float(lower), float(upper)


def interval_metrics(actual, lower, upper, *, nominal_level: float) -> dict:
    """Score empirical coverage and width for finite positive actuals."""
    actual = np.asarray(actual, dtype=float)
    lower = np.asarray(lower, dtype=float)
    upper = np.asarray(upper, dtype=float)
    valid = np.isfinite(actual) & np.isfinite(lower) & np.isfinite(upper) & (actual > 0)
    count = int(valid.sum())
    if count == 0:
        return {
            "nominal_level": float(nominal_level),
            "sample_count": 0,
            "coverage": None,
            "mean_width_php": None,
            "median_width_php": None,
            "reliability_status": "unavailable_no_finite_evaluation_rows",
        }
    covered = (actual[valid] >= lower[valid]) & (actual[valid] <= upper[valid])
    widths = upper[valid] - lower[valid]
    coverage = float(np.mean(covered))
    tolerance = 0.05
    status = "reliable" if count >= 20 and abs(coverage - nominal_level) <= tolerance else "limited"
    return {
        "nominal_level": float(nominal_level),
        "sample_count": count,
        "coverage": coverage,
        "mean_width_php": float(np.mean(widths)),
        "median_width_php": float(np.median(widths)),
        "reliability_status": status,
    }


def build_bundle_report(bundle_path: str | Path, *, nominal_levels=(0.80, 0.95)) -> dict:
    """Calibrate on validation forecasts and evaluate on the saved test split."""
    bundle_path = Path(bundle_path)
    validation = pd.read_csv(bundle_path / "validation_forecasts.csv")
    test = pd.read_csv(bundle_path / "test_forecasts.csv")
    required = {"series", "horizon", "origin", "actual", "ensemble"}
    if not required.issubset(validation.columns) or not required.issubset(test.columns):
        raise ValueError(f"Saved forecasts must contain {sorted(required)}")

    by_level = {}
    for level in nominal_levels:
        level_key = f"{float(level):.2f}"
        rows = []
        pooled_actual = []
        pooled_lower = []
        pooled_upper = []
        for (series, lead), calibration_rows in validation.groupby(["series", "horizon"], sort=True):
            calibration = calibrate_residual_interval(
                calibration_rows.actual, calibration_rows.ensemble,
                origins=calibration_rows.origin, nominal_level=float(level),
            )
            if calibration is None:
                continue
            eval_rows = test.loc[(test.series == series) & (test.horizon == lead)].copy()
            if eval_rows.empty:
                continue
            bounds = [interval_from_calibration(point, calibration)
                      for point in eval_rows.ensemble.to_numpy(dtype=float)]
            lower = np.array([pair[0] if pair else np.nan for pair in bounds])
            upper = np.array([pair[1] if pair else np.nan for pair in bounds])
            metrics = interval_metrics(
                eval_rows.actual.to_numpy(dtype=float), lower, upper,
                nominal_level=float(level),
            )
            rows.append({"series": str(series), "lead": int(lead), **calibration, **metrics})
            pooled_actual.append(eval_rows.actual.to_numpy(dtype=float))
            pooled_lower.append(lower)
            pooled_upper.append(upper)
        if rows:
            pooled = interval_metrics(
                np.concatenate(pooled_actual),
                np.concatenate(pooled_lower),
                np.concatenate(pooled_upper),
                nominal_level=float(level),
            )
            by_level[level_key] = {
                "pooled": pooled,
                "by_series_and_lead": rows,
                "selection_reuse": False,
                "evaluation_source": "chronological_test_after_validation_calibration",
            }
        else:
            by_level[level_key] = {
                "pooled": interval_metrics([], [], [], nominal_level=float(level)),
                "by_series_and_lead": [],
                "selection_reuse": False,
                "evaluation_source": "chronological_test_after_validation_calibration",
            }
    metadata = {}
    metadata_path = bundle_path / "metadata.json"
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    return {
        "schema_version": 1,
        "model_run_id": bundle_path.name,
        "data_fingerprint": metadata.get("data_fingerprint"),
        "calibration_policy": {
            "method": "split_conformal_absolute_residual_order_statistic",
            "positive_price_floor_php": 0.01,
            "minimum_calibration_samples": DEFAULT_MIN_SAMPLES,
            "minimum_calibration_origins": DEFAULT_MIN_ORIGINS,
            "finite_sample_minimum_by_nominal_level": {
                f"{float(level):.2f}": minimum_conformal_sample_count(float(level))
                for level in nominal_levels
            },
            "minimum_distinct_origins_by_nominal_level": {
                f"{float(level):.2f}": max(
                    DEFAULT_MIN_ORIGINS, minimum_conformal_sample_count(float(level))
                )
                for level in nominal_levels
            },
            "quantile_rule": "radius at sorted absolute-residual rank ceil((n+1)*nominal_level)",
            "exchangeability_assumption_guaranteed_for_timeseries": False,
            "validation_only_interval_status": "limited",
            "intervals_are_not_individual_correctness_probabilities": True,
        },
        "levels": by_level,
    }


def validation_intervals_by_series(bundle_path: str | Path, *, nominal_level=DEFAULT_NOMINAL_LEVEL) -> dict:
    """Return supported daily lead calibrations for production inference."""
    frame = pd.read_csv(Path(bundle_path) / "validation_forecasts.csv")
    result = {}
    for (series, lead), rows in frame.groupby(["series", "horizon"], sort=True):
        if int(lead) > 14:
            continue
        calibration = calibrate_residual_interval(
            rows.actual, rows.ensemble, origins=rows.origin,
            nominal_level=float(nominal_level),
        )
        if calibration is not None:
            result.setdefault(str(series), {}).setdefault("daily", {})[str(int(lead))] = calibration
    return result


def calculate_picp(actual, lower_bound, upper_bound) -> dict:
    """Calculate Prediction Interval Coverage Probability (PICP).

    PICP = (Number of actual observations inside prediction intervals
            / Total evaluated observations) * 100

    Fails closed (`empirical_coverage = None`) if inputs are empty, mismatched,
    contain non-finite or non-positive values, or have `lower_bound > upper_bound`.
    """
    actual_arr = np.asarray(actual, dtype=float)
    lower_arr = np.asarray(lower_bound, dtype=float)
    upper_arr = np.asarray(upper_bound, dtype=float)
    if (
        actual_arr.ndim != 1
        or actual_arr.shape != lower_arr.shape
        or actual_arr.shape != upper_arr.shape
    ):
        raise ValueError("actual, lower_bound, and upper_bound must be 1D arrays of equal length")
    total = int(actual_arr.size)
    if total == 0:
        return {
            "status": "insufficient_data",
            "empirical_coverage": None,
            "covered_count": 0,
            "sample_count": 0,
        }
    valid_bounds = (
        np.isfinite(actual_arr)
        & np.isfinite(lower_arr)
        & np.isfinite(upper_arr)
        & (actual_arr > 0)
        & (lower_arr > 0)
        & (upper_arr >= lower_arr)
    )
    if not bool(valid_bounds.all()):
        return {
            "status": "invalid_intervals",
            "empirical_coverage": None,
            "covered_count": 0,
            "sample_count": total,
        }
    inside = (actual_arr >= lower_arr) & (actual_arr <= upper_arr)
    covered_count = int(np.sum(inside))
    picp = float((covered_count / total) * 100.0)
    return {
        "status": "valid",
        "empirical_coverage": picp,
        "covered_count": covered_count,
        "sample_count": total,
    }


def calibrate_horizon_residual_interval(
    actual,
    predicted,
    *,
    origins=None,
    nominal_level: float = DEFAULT_TARGET_COVERAGE,
    min_samples: int = DEFAULT_MIN_SAMPLES,
    min_origins: int = DEFAULT_MIN_ORIGINS,
) -> dict | None:
    """Calibrate a residual-based prediction interval for a commodity and forecast horizon.

    Uses out-of-sample chronological validation residuals (`actual - predicted`)
    with finite-sample split-conformal order-statistic rank `ceil((n + 1) * nominal_level)`.
    """
    if not 0 < nominal_level < 1:
        raise ValueError("nominal_level must be between zero and one")
    actual_arr = np.asarray(actual, dtype=float)
    predicted_arr = np.asarray(predicted, dtype=float)
    if actual_arr.shape != predicted_arr.shape:
        raise ValueError("actual and predicted must have the same shape")
    valid = (
        np.isfinite(actual_arr)
        & np.isfinite(predicted_arr)
        & (actual_arr > 0)
        & (predicted_arr > 0)
    )
    if origins is not None:
        origin_values = np.asarray(origins, dtype=object)
        if origin_values.shape != actual_arr.shape:
            raise ValueError("origins must have the same shape as actual")
        origin_values = origin_values[valid]
    else:
        origin_values = None
    residuals = actual_arr[valid] - predicted_arr[valid]
    sample_count = int(residuals.size)
    origin_count = (
        int(pd.Series(origin_values).nunique())
        if origin_values is not None
        else sample_count
    )
    required_samples = minimum_conformal_sample_count(
        nominal_level, min_samples=min_samples
    )
    required_origins = int(min_origins)
    if sample_count < required_samples or origin_count < required_origins:
        return None
    rank = int(math.ceil((sample_count + 1) * float(nominal_level) - 1e-12))
    if rank > sample_count:
        return None
    absolute_residuals = np.sort(np.abs(residuals))
    radius = float(absolute_residuals[rank - 1])
    if not np.isfinite(radius) or radius < 0:
        return None
    return {
        "nominal_level": float(nominal_level),
        "target_coverage": float(nominal_level * 100.0),
        "lower_error_php": -radius,
        "upper_error_php": radius,
        "interval_half_width_php": radius,
        "sample_count": sample_count,
        "origin_count": origin_count,
        "required_sample_count": required_samples,
        "required_origin_count": required_origins,
        "absolute_residual_order_statistic_rank": rank,
        "calibration_method": "split_conformal_absolute_residual_order_statistic",
        "calibration_source": "chronological_validation",
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_model_confidence_evaluations(
    bundle_path: str | Path,
    *,
    products_catalog: list[dict] | str | Path | None = None,
    manifest_path: str | Path | None = None,
    nominal_level: float = DEFAULT_TARGET_COVERAGE,
    min_test_samples: int = DEFAULT_MIN_TEST_SAMPLES,
    require_active: bool = True,
) -> dict:
    """Calibrate prediction intervals on validation and evaluate out-of-sample PICP on test.

    Produces deduplicated records keyed by `(model_run_id, commodity_id, forecast_horizon,
    target_coverage, evaluation_period)` for database storage and API consumption.
    """
    if not 0 < nominal_level < 1:
        raise ValueError("nominal_level must be between zero and one")
    bundle_dir = Path(bundle_path)
    if not bundle_dir.is_dir():
        raise FileNotFoundError(f"Model bundle directory does not exist: {bundle_dir}")
    metadata_path = bundle_dir / "metadata.json"
    val_path = bundle_dir / "validation_forecasts.csv"
    test_path = bundle_dir / "test_forecasts.csv"
    for required_file in (metadata_path, val_path, test_path):
        if not required_file.is_file():
            raise FileNotFoundError(f"Missing required evaluation artifact: {required_file}")

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    model_run_id = str(metadata.get("run_id") or bundle_dir.name)
    if model_run_id != bundle_dir.name:
        raise ValueError("Model bundle directory name does not match metadata.json run_id")

    if manifest_path is None:
        candidate_manifest = bundle_dir.parent.parent / "manifest.json"
        if candidate_manifest.is_file():
            manifest_path = candidate_manifest
    active_run_id = None
    if manifest_path is not None and Path(manifest_path).is_file():
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        active_run_id = manifest.get("active_run")
    if require_active and active_run_id is not None and active_run_id != model_run_id:
        raise ValueError(
            f"Model run {model_run_id} is not the active model run ({active_run_id})"
        )

    expected_hashes = metadata.get("sha256", {})
    for file_name in ("validation_forecasts.csv", "test_forecasts.csv", "ensemble.json"):
        if file_name in expected_hashes:
            actual_hash = _sha256_file(bundle_dir / file_name)
            if actual_hash != expected_hashes[file_name]:
                raise ValueError(f"Artifact hash mismatch for {file_name} in {model_run_id}")

    validation = pd.read_csv(val_path)
    test = pd.read_csv(test_path)
    required_cols = {"series", "horizon", "origin", "date", "actual", "ensemble"}
    if not required_cols.issubset(validation.columns) or not required_cols.issubset(test.columns):
        raise ValueError(f"Forecast CSVs must contain columns: {sorted(required_cols)}")

    val_dates = pd.to_datetime(validation["date"], errors="raise")
    test_origins = pd.to_datetime(test["origin"], errors="raise")
    test_dates = pd.to_datetime(test["date"], errors="raise")
    if val_dates.max() >= test_origins.min() or val_dates.max() >= test_dates.min():
        raise ValueError(
            "Chronological leakage detected: validation target dates overlap test origins/dates"
        )

    calibration_period = (
        f"{val_dates.min().date().isoformat()}..{val_dates.max().date().isoformat()}"
    )
    evaluation_period = (
        f"{test_dates.min().date().isoformat()}..{test_dates.max().date().isoformat()}"
    )
    evaluation_timestamp = str(
        metadata.get("created_at")
        or metadata.get("metrics", {}).get("trained_at")
        or "2026-10-01T03:10:14.273362+00:00"
    )
    target_coverage_pct = round(float(nominal_level * 100.0), 4)

    if products_catalog is None:
        default_catalog = (
            bundle_dir.resolve().parents[3]
            / "audits"
            / "rolling_tomorrow_20261109"
            / "products.json"
        )
        if default_catalog.is_file():
            products_catalog = json.loads(default_catalog.read_text(encoding="utf-8"))
        else:
            products_catalog = []
    elif isinstance(products_catalog, (str, Path)):
        products_catalog = json.loads(Path(products_catalog).read_text(encoding="utf-8"))

    catalog_entries = []
    seen_series = set()
    for item in products_catalog:
        series_key = "||".join([
            str(item["category"]),
            str(item["name"]),
            str(item.get("variant") or "Standard"),
            str(item.get("origin") or "Unknown"),
            str(item.get("unit") or "unknown"),
        ])
        if series_key in seen_series:
            continue
        seen_series.add(series_key)
        catalog_entries.append({
            "commodity_id": str(item["id"]),
            "series_key": series_key,
            "category": str(item["category"]),
            "name": str(item["name"]),
            "variant": str(item.get("variant") or "Standard"),
            "origin": str(item.get("origin") or "Unknown"),
            "unit": str(item.get("unit") or "unknown"),
        })

    if not catalog_entries:
        for series_key in sorted(set(validation["series"].astype(str)) | set(test["series"].astype(str))):
            parts = series_key.split("||")
            if len(parts) != 5:
                continue
            catalog_entries.append({
                "commodity_id": series_key,
                "series_key": series_key,
                "category": parts[0],
                "name": parts[1],
                "variant": parts[2],
                "origin": parts[3],
                "unit": parts[4],
            })

    records = []
    unique_keys = set()
    horizon_summaries = {}

    for horizon_name, (lead_min, lead_max) in FORECAST_HORIZON_LEAD_BOUNDS.items():
        val_h = validation.loc[validation["horizon"].between(lead_min, lead_max)]
        test_h = test.loc[test["horizon"].between(lead_min, lead_max)]
        pooled_covered = 0
        pooled_samples = 0
        valid_commodities = 0
        unavailable_commodities = 0

        for entry in catalog_entries:
            series_key = entry["series_key"]
            commodity_id = entry["commodity_id"]
            dedup_key = (
                model_run_id,
                commodity_id,
                horizon_name,
                target_coverage_pct,
                evaluation_period,
            )
            if dedup_key in unique_keys:
                raise ValueError(f"Duplicate evaluation record key: {dedup_key}")
            unique_keys.add(dedup_key)

            val_rows = val_h.loc[val_h["series"] == series_key]
            test_rows = test_h.loc[test_h["series"] == series_key]
            calibration = calibrate_horizon_residual_interval(
                val_rows["actual"].to_numpy(dtype=float),
                val_rows["ensemble"].to_numpy(dtype=float),
                origins=val_rows["origin"].to_numpy(dtype=object),
                nominal_level=float(nominal_level),
            )
            cal_samples = int(len(val_rows))
            cal_origins = int(val_rows["origin"].nunique()) if not val_rows.empty else 0

            if calibration is None or len(test_rows) < int(min_test_samples):
                unavailable_commodities += 1
                records.append({
                    "model_run_id": model_run_id,
                    "commodity_id": commodity_id,
                    "series_key": series_key,
                    "category": entry["category"],
                    "name": entry["name"],
                    "variant": entry["variant"],
                    "origin": entry["origin"],
                    "unit": entry["unit"],
                    "forecast_horizon": horizon_name,
                    "lead_min": int(lead_min),
                    "lead_max": int(lead_max),
                    "target_coverage": target_coverage_pct,
                    "empirical_coverage": None,
                    "covered_count": 0,
                    "sample_count": int(len(test_rows)),
                    "calibration_sample_count": cal_samples,
                    "calibration_origin_count": cal_origins,
                    "interval_half_width_php": None,
                    "calibration_period": calibration_period,
                    "evaluation_period": evaluation_period,
                    "evaluation_dataset": "chronological_test_after_validation_calibration",
                    "evaluation_timestamp": evaluation_timestamp,
                    "status": "insufficient_data",
                })
                continue

            bounds = [
                interval_from_calibration(float(point), calibration)
                for point in test_rows["ensemble"].to_numpy(dtype=float)
            ]
            lower_arr = np.array([b[0] if b is not None else np.nan for b in bounds], dtype=float)
            upper_arr = np.array([b[1] if b is not None else np.nan for b in bounds], dtype=float)
            picp_result = calculate_picp(
                test_rows["actual"].to_numpy(dtype=float),
                lower_arr,
                upper_arr,
            )

            if picp_result["status"] != "valid" or picp_result["empirical_coverage"] is None:
                unavailable_commodities += 1
                records.append({
                    "model_run_id": model_run_id,
                    "commodity_id": commodity_id,
                    "series_key": series_key,
                    "category": entry["category"],
                    "name": entry["name"],
                    "variant": entry["variant"],
                    "origin": entry["origin"],
                    "unit": entry["unit"],
                    "forecast_horizon": horizon_name,
                    "lead_min": int(lead_min),
                    "lead_max": int(lead_max),
                    "target_coverage": target_coverage_pct,
                    "empirical_coverage": None,
                    "covered_count": 0,
                    "sample_count": int(picp_result["sample_count"]),
                    "calibration_sample_count": int(calibration["sample_count"]),
                    "calibration_origin_count": int(calibration["origin_count"]),
                    "interval_half_width_php": None,
                    "calibration_period": calibration_period,
                    "evaluation_period": evaluation_period,
                    "evaluation_dataset": "chronological_test_after_validation_calibration",
                    "evaluation_timestamp": evaluation_timestamp,
                    "status": picp_result["status"],
                })
                continue

            valid_commodities += 1
            pooled_covered += int(picp_result["covered_count"])
            pooled_samples += int(picp_result["sample_count"])
            records.append({
                "model_run_id": model_run_id,
                "commodity_id": commodity_id,
                "series_key": series_key,
                "category": entry["category"],
                "name": entry["name"],
                "variant": entry["variant"],
                "origin": entry["origin"],
                "unit": entry["unit"],
                "forecast_horizon": horizon_name,
                "lead_min": int(lead_min),
                "lead_max": int(lead_max),
                "target_coverage": target_coverage_pct,
                "empirical_coverage": round(float(picp_result["empirical_coverage"]), 4),
                "covered_count": int(picp_result["covered_count"]),
                "sample_count": int(picp_result["sample_count"]),
                "calibration_sample_count": int(calibration["sample_count"]),
                "calibration_origin_count": int(calibration["origin_count"]),
                "interval_half_width_php": round(float(calibration["interval_half_width_php"]), 4),
                "calibration_period": calibration_period,
                "evaluation_period": evaluation_period,
                "evaluation_dataset": "chronological_test_after_validation_calibration",
                "evaluation_timestamp": evaluation_timestamp,
                "status": "valid",
            })

        horizon_summaries[horizon_name] = {
            "forecast_horizon": horizon_name,
            "lead_min": int(lead_min),
            "lead_max": int(lead_max),
            "target_coverage": target_coverage_pct,
            "pooled_empirical_coverage": (
                round((pooled_covered / pooled_samples) * 100.0, 4)
                if pooled_samples > 0
                else None
            ),
            "covered_count": pooled_covered,
            "sample_count": pooled_samples,
            "valid_commodities": valid_commodities,
            "unavailable_commodities": unavailable_commodities,
        }

    return {
        "schema_version": 1,
        "metric": "PICP",
        "metric_formula": "(covered_observations / total_evaluated_observations) * 100",
        "model_run_id": model_run_id,
        "active_model_verified": bool(active_run_id == model_run_id) if active_run_id else None,
        "data_fingerprint": metadata.get("data_fingerprint"),
        "metadata_sha256": _sha256_file(metadata_path),
        "validation_forecasts_sha256": _sha256_file(val_path),
        "test_forecasts_sha256": _sha256_file(test_path),
        "target_coverage": target_coverage_pct,
        "calibration_method": "split_conformal_absolute_residual_order_statistic",
        "calibration_dataset": "validation_forecasts.csv",
        "calibration_period": calibration_period,
        "evaluation_dataset": "test_forecasts.csv",
        "evaluation_period": evaluation_period,
        "evaluation_timestamp": evaluation_timestamp,
        "minimum_calibration_samples": minimum_conformal_sample_count(nominal_level),
        "minimum_calibration_origins": DEFAULT_MIN_ORIGINS,
        "minimum_test_samples": int(min_test_samples),
        "bundle_test_interval_metrics": metadata.get("metrics", {}).get("test_interval_metrics", {}),
        "horizon_summaries": horizon_summaries,
        "records": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_bundle_report(args.bundle)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "model_run_id": report["model_run_id"],
        "levels": {level: value["pooled"] for level, value in report["levels"].items()},
    }, indent=2))


if __name__ == "__main__":
    main()

