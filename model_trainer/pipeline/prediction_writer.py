"""Generate one complete forecast vintage and publish it atomically."""
from datetime import date, datetime, timedelta, timezone
import calendar
from pathlib import Path
from uuid import uuid4
import json
import hashlib

import numpy as np
import pandas as pd
from supabase import create_client

from config.settings import get_settings
from data.fetcher import DataFetcher
from data.preprocessor import DataPreprocessor, SERIES_KEY
from features.builder import FeatureBuilder
from models.registry import ModelRegistry
from models.model_store import ModelStore
from utils.metrics import SUCCESS_TOLERANCE, compute_all_metrics
from utils.prices import mean_price as _mean_price, round_price as _round_price
from evaluation.product_confidence import METHOD as CONFIDENCE_METHOD
from evaluation.interval_calibration import (
    build_model_confidence_evaluations,
    interval_from_calibration,
    validation_intervals_by_series,
)


HORIZON_MAP = {"daily": 1, "weekly": 7, "monthly": 30}
PUBLISHED_FORECAST_STEPS = {"daily": 7, "weekly": 4, "monthly": 1}
PUBLISHED_DAILY_FORECAST_DAYS = PUBLISHED_FORECAST_STEPS["daily"]
PH_TIME = timezone(timedelta(hours=8))
MIGRATION = "supabase/migrations/202609240001_atomic_forecast_vintages.sql"
SAFE_DELETE_MIGRATION = "supabase/migrations/202609250001_fix_forecast_safe_delete.sql"
QUALITY_METRICS_MIGRATION = "supabase/migrations/202610010002_forecast_run_quality_metrics.sql"
PERIOD_FORECAST_MIGRATION = "supabase/migrations/202610090001_multi_period_point_forecasts.sql"
INTERVAL_MIGRATION = "supabase/migrations/202610170001_prediction_interval_calibration.sql"




class PredictionWriter:
    def __init__(self):
        self.cfg = get_settings()
        self.fetcher = DataFetcher()
        self.preprocessor = DataPreprocessor()
        self.db = create_client(self.cfg.supabase_url, self.cfg.supabase_key)

    def _product_ids(self):
        try:
            response = self.db.table("products").select(
                "id,name,variant,origin,category,unit").execute()
        except Exception as exc:
            if "42703" in str(exc) and "products.unit" in str(exc):
                raise RuntimeError(
                    f"Supabase publishing schema is outdated: products.unit is missing. "
                    f"Apply {MIGRATION}, then retry. To inspect forecasts without "
                    "publishing, use `python main.py preview`."
                ) from exc
            raise
        return {
            (row["category"], row["name"], row.get("variant") or "Standard",
             row.get("origin") or "Unknown", row.get("unit") or "unknown"): row["id"]
            for row in response.data
        }

    def check_schema(self, product_ids=None):
        if not (product_ids if product_ids is not None else self._product_ids()):
            raise RuntimeError('No unit-aware products are available for forecast publication')
        try:
            self.db.table('forecast_runs').select('id,metrics').limit(1).execute()
        except Exception as exc:
            raise RuntimeError(
                f'Forecast quality schema is unavailable. Apply {QUALITY_METRICS_MIGRATION} '
                'before running the daily pipeline.') from exc
        try:
            self.db.table('forecast_values').select(
                'forecast_horizon,forecast_origin_date,target_period_start,target_period_end,'
                'forecast_step,confidence_score,confidence_level,covered_days,period_days,'
                'lower_bound,upper_bound,interval_level,interval_width,interval_reliability'
            ).limit(1).execute()
        except Exception as exc:
            raise RuntimeError(
                f'Multi-period/interval forecast schema is unavailable. Apply '
                f'{PERIOD_FORECAST_MIGRATION} and {INTERVAL_MIGRATION} '
                'before running the daily pipeline.') from exc

    @staticmethod
    def _is_history_shortfall(exc):
        message = str(exc)
        return any(reason in message for reason in [
            "Insufficient causal feature history",
            "Incomplete causal features for live LSTM forecast",
        ])

    @staticmethod
    def _persistence_fallback(engine, series, horizon_days):
        ordered = series.sort_values("report_date")
        finite = ordered[np.isfinite(ordered.price_index.to_numpy(dtype=float))]
        if finite.empty:
            raise ValueError("Series has no usable causal price for fallback")
        anchor = float(finite.price_index.iloc[-1])
        origin = np.datetime64(finite.report_date.iloc[-1], "D")
        dates = origin + np.arange(1, horizon_days + 1).astype("timedelta64[D]")
        point = np.full(horizon_days, anchor, dtype=float)
        return dates, point

    @staticmethod
    def _extend_inputs_to_origin(clean, origin, max_fill_days):
        """Build each series through the real issue date using causal fills only."""
        groups = []
        clean = clean.copy()
        clean["report_date"] = pd.to_datetime(clean.report_date, errors="coerce").dt.normalize()
        origin = pd.Timestamp(origin).normalize()
        if clean.empty:
            raise ValueError("Cannot extend empty price inputs")
        if clean.report_date.isna().any():
            raise ValueError("Price inputs contain an invalid report date")
        if clean.report_date.max() > origin:
            raise ValueError("Price inputs contain a report date after forecast origin")
        for key, history in clean.groupby(SERIES_KEY, sort=True):
            history = history.set_index("report_date").sort_index()
            history = history.reindex(pd.date_range(history.index.min(), origin, freq="D"))
            for column, value in zip(SERIES_KEY, key):
                history[column] = value
            history["is_observed"] = history.is_observed.fillna(False).astype(bool)
            history["observed_price"] = history.observed_price.where(history.is_observed)
            history["price_index"] = history.observed_price.ffill(limit=max_fill_days)
            history.index.name = "report_date"
            groups.append(history.reset_index())
        return (pd.concat(groups, ignore_index=True)
                .sort_values(SERIES_KEY + ["report_date"]).reset_index(drop=True))

    @staticmethod
    def _rows(product_id, dates, point, origin, product_metrics,
              allow_confidence=True):
        origin = pd.Timestamp(origin).date()
        forecasts = {"daily": [], "weekly": [], "monthly": []}

        def confidence(horizon, step):
            if not allow_confidence:
                return None, "Insufficient data"
            step_metrics = (product_metrics.get("confidence_by_step", {}) or {}).get(horizon, {})
            metric = step_metrics.get(str(step), step_metrics.get(step, {}))
            score = metric.get("confidence_score")
            level = metric.get("confidence_level")
            if (metric.get("evidence_status") == "validated"
                    and product_metrics.get(
                        "confidence_evaluation_source", "chronological_validation"
                    ) == "chronological_validation"
                    and metric.get("evaluation_source") == "chronological_validation"
                    and isinstance(score, (int, float)) and np.isfinite(score)
                    and 0 <= score <= 100
                    and level in {"Very High", "High", "Moderate", "Low", "Very Low"}):
                return float(score), level
            return None, "Insufficient data"

        for step, (raw_date, value) in enumerate(zip(dates, point), start=1):
            target = pd.Timestamp(raw_date).date()
            score, level = confidence("daily", step)
            forecasts["daily"].append({
                "product_id": product_id,
                "prediction_date": target.isoformat(),
                "forecast_horizon": "daily",
                "forecast_origin_date": origin.isoformat(),
                "target_period_start": target.isoformat(),
                "target_period_end": target.isoformat(),
                "forecast_step": step,
                "predicted_price": _round_price(float(value)),
                "confidence_score": score,
                "confidence_level": level,
                "covered_days": 1,
                "period_days": 1,
            })

        for horizon in ("weekly", "monthly"):
            periods = {}
            for row in forecasts["daily"]:
                target = pd.Timestamp(row["prediction_date"]).date()
                if horizon == "weekly":
                    start = target - pd.Timedelta(days=target.weekday())
                    end = start + pd.Timedelta(days=6)
                else:
                    start = target.replace(day=1)
                    end = (start + pd.offsets.MonthBegin(1) - pd.Timedelta(days=1)).date()
                periods.setdefault((start, end), []).append(row)

            for step, ((start, end), rows) in enumerate(sorted(periods.items()), start=1):
                score, level = confidence(horizon, step)
                forecasts[horizon].append({
                    "product_id": product_id,
                    "prediction_date": rows[-1]["prediction_date"],
                    "forecast_horizon": horizon,
                    "forecast_origin_date": origin.isoformat(),
                    "target_period_start": start.isoformat(),
                    "target_period_end": end.isoformat(),
                    "forecast_step": step,
                    "predicted_price": _mean_price(
                        row["predicted_price"] for row in rows),
                    "confidence_score": score,
                    "confidence_level": level,
                    "covered_days": len(rows),
                    "period_days": (end - start).days + 1,
                })
        return forecasts["daily"] + forecasts["weekly"] + forecasts["monthly"]

    @staticmethod
    def _next_period_start(origin, horizon):
        origin = pd.Timestamp(origin).normalize()
        if horizon == "weekly":
            return origin + pd.Timedelta(days=7 - int(origin.weekday()))
        if horizon == "monthly":
            return (origin.replace(day=1) + pd.offsets.MonthBegin(1)).normalize()
        raise ValueError(f"Unsupported period horizon: {horizon}")

    @staticmethod
    def _period_baseline(series, origin, horizon):
        """Return the latest completed observed calendar-period mean.

        This is a separate persistence baseline for period targets. It never
        averages the daily forecast path into a weekly or monthly prediction.
        """
        origin = pd.Timestamp(origin).normalize()
        observed = series.loc[
            series.is_observed.fillna(False).astype(bool)
            & pd.to_numeric(series.observed_price, errors="coerce").gt(0)
            & pd.to_datetime(series.report_date).le(origin),
            ["report_date", "observed_price"],
        ].copy()
        observed["report_date"] = pd.to_datetime(observed.report_date).dt.normalize()
        observed["observed_price"] = pd.to_numeric(observed.observed_price, errors="coerce")
        observed = observed.dropna(subset=["report_date", "observed_price"])
        if observed.empty:
            raise ValueError(f"No observed price available for {horizon} persistence baseline")
        if horizon == "weekly":
            observed["period_start"] = (
                observed.report_date - pd.to_timedelta(observed.report_date.dt.weekday, unit="D")
            )
            observed["period_end"] = observed.period_start + pd.Timedelta(days=6)
            minimum_coverage = 4
        elif horizon == "monthly":
            observed["period_start"] = observed.report_date.values.astype("datetime64[M]").astype("datetime64[ns]")
            observed["period_end"] = observed.period_start + pd.offsets.MonthEnd(0)
            minimum_coverage = 15
        else:
            raise ValueError(f"Unsupported period horizon: {horizon}")
        grouped = (observed.groupby(["period_start", "period_end"], sort=True)
                   .agg(value=("observed_price", "mean"), observed_days=("observed_price", "count"))
                   .reset_index())
        completed = grouped.loc[
            (grouped.period_end <= origin) & grouped.observed_days.ge(minimum_coverage)
        ]
        if completed.empty:
            # Preserve a usable forecast for short histories while exposing
            # the limitation through the forecast source metadata.
            return float(observed.observed_price.iloc[-1]), "latest_observed_price_insufficient_period_history"
        latest = completed.iloc[-1]
        return float(latest.value), "completed_period_mean_persistence"

    @staticmethod
    def _rolling_period_bounds(origin, horizon, step):
        """Origin-relative publication contract; historical calendar helpers stay intact."""
        if horizon not in {"weekly", "monthly"} or type(step) is not int:
            raise ValueError("Unsupported rolling horizon or step")
        if not 1 <= step <= (4 if horizon == "weekly" else 1):
            raise ValueError("Unsupported rolling horizon or step")
        from pipeline.rolling_periods import rolling_period_bounds
        return rolling_period_bounds(origin, horizon, step)

    @staticmethod
    def _production_rows(product_id, daily_dates, daily_point, origin, series,
                          product_metrics, allow_confidence=True):
        """Build exactly 7 daily, 4 weekly, and 1 monthly rows.

        Daily rows and exact inclusive rolling means use one saved daily path.
        Historical calendar helpers and their evaluation contracts stay separate.
        Missing required dates produce unavailable periods, never partial means.
        """
        origin = pd.Timestamp(origin).normalize()
        dates = [pd.Timestamp(value).normalize() for value in daily_dates]
        points = [float(value) for value in daily_point]
        if len(points) != len(dates) or len(set(dates)) != len(dates):
            raise ValueError("Invalid or duplicate daily forecast dates")
        if any(pd.isna(d) for d in dates) or not np.isfinite(points).all():
            raise ValueError("Invalid daily forecast dates or values")
        by_date = dict(zip(dates, points))
        origin_rows = series.loc[pd.to_datetime(series.report_date).dt.normalize() == origin]
        if not origin_rows.empty:
            anchor = float(origin_rows.price_index.iloc[-1])
            if np.isfinite(anchor) and anchor > 0:
                by_date[origin] = anchor
        required_daily = [origin + pd.Timedelta(days=step) for step in range(1, 8)]
        if any(d not in by_date for d in required_daily):
            raise ValueError("Production daily targets must include seven dates after origin")

        def confidence(step):
            if not allow_confidence:
                return None, "Insufficient data"
            metric = ((product_metrics.get("confidence_by_step", {}) or {})
                       .get("daily", {}).get(str(step), {}))
            if (metric.get("evidence_status") == "validated"
                    and product_metrics.get(
                        "confidence_evaluation_source", "chronological_validation"
                    ) == "chronological_validation"
                    and metric.get("evaluation_source") == "chronological_validation"
                    and isinstance(metric.get("confidence_score"), (int, float))
                    and np.isfinite(metric.get("confidence_score"))
                    and 0 <= metric.get("confidence_score") <= 100
                    and metric.get("confidence_level") in {
                        "Very High", "High", "Moderate", "Low", "Very Low",
                    }):
                return float(metric["confidence_score"]), metric["confidence_level"]
            return None, "Insufficient data"

        def interval(step, value):
            calibration = ((product_metrics.get("prediction_intervals", {}) or {})
                           .get("daily", {}).get(str(step)))
            bounds = interval_from_calibration(value, calibration)
            if bounds is None:
                return {}
            lower, upper = bounds
            return {
                "lower_bound": _round_price(lower),
                "upper_bound": _round_price(upper),
                "interval_level": float(calibration["nominal_level"]),
                "interval_width": _round_price(upper - lower),
                "interval_reliability": calibration.get(
                    "reliability_status", "calibrated_on_validation_only"),
            }

        rows = []
        for step, date in enumerate(required_daily, start=1):
            value = by_date[date]
            score, level = confidence(step)
            rows.append({
                "product_id": product_id,
                "prediction_date": date.date().isoformat(),
                "forecast_horizon": "daily",
                "forecast_origin_date": origin.date().isoformat(),
                "target_period_start": date.date().isoformat(),
                "target_period_end": date.date().isoformat(),
                "forecast_step": step,
                "predicted_price": _round_price(value),
                "confidence_score": score,
                "confidence_level": level,
                "covered_days": 1,
                "period_days": 1,
                **interval(step, value),
            })

        for horizon in ("weekly", "monthly"):
            source = "complete_daily_path_mean"
            for step in range(1, PUBLISHED_FORECAST_STEPS[horizon] + 1):
                period_start, period_end = PredictionWriter._rolling_period_bounds(
                    origin, horizon, step)
                required = pd.date_range(period_start, period_end)
                missing = [d.date().isoformat() for d in required if d not in by_date]
                value = None if missing else float(np.mean([by_date[d] for d in required]))
                rows.append({
                    "product_id": product_id,
                    "prediction_date": period_end.isoformat(),
                    "forecast_horizon": horizon,
                    "forecast_origin_date": origin.date().isoformat(),
                    "target_period_start": period_start.isoformat(),
                    "target_period_end": period_end.isoformat(),
                    "forecast_step": step,
                    "predicted_price": None if value is None else _round_price(value),
                    "unavailable": bool(missing),
                    "unavailable_reason": "Unsupported daily forecast dates: " + ", ".join(missing) if missing else None,
                    "confidence_score": None,
                    "confidence_level": "Insufficient data",
                    "covered_days": len(required) - len(missing),
                    "period_days": int((period_end - period_start).days + 1),
                    "period_forecast_source": source,
                })
        return rows

    @staticmethod
    def _confidence_profile(bundle_path, metadata, profile_path=None):
        """Load only bundle-bound confidence evidence from untouched validation."""
        if profile_path is None:
            profile_path = (Path(__file__).resolve().parents[1] / "confidence_profiles"
                            / f"{bundle_path.name}.json")
        if not profile_path.exists():
            return {}, None
        try:
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            metadata_sha256 = hashlib.sha256(
                (bundle_path / "metadata.json").read_bytes()).hexdigest()
            ensemble_sha256 = hashlib.sha256(
                (bundle_path / "ensemble.json").read_bytes()).hexdigest()
            forecasts_sha256 = hashlib.sha256(
                (bundle_path / "test_forecasts.csv").read_bytes()).hexdigest()
            if (
                profile.get("profile_schema_version") != 1
                or profile.get("profile_status") != "chronological_validation"
                or profile.get("model_run_id") != bundle_path.name
                or profile.get("data_fingerprint") != metadata.get("data_fingerprint")
                or profile.get("model_metadata_sha256") != metadata_sha256
                or profile.get("ensemble_sha256") != ensemble_sha256
                or profile.get("source_forecasts_sha256") != forecasts_sha256
                or profile.get("confidence_method") != CONFIDENCE_METHOD
                or profile.get("evaluation_source") != "chronological_validation"
                or profile.get("development_test_reused_for_selection") is not False
            ):
                return {}, None
            confidence = profile.get("product_confidence_by_identity")
            if not isinstance(confidence, dict):
                return {}, None
            return confidence, profile["evaluation_source"]
        except (OSError, ValueError, TypeError, KeyError):
            return {}, None

    @staticmethod
    def _validation_metrics_from_file(bundle_path):
        """Recover per-product validation metrics for older saved bundles."""
        path = Path(bundle_path) / "validation_forecasts.csv"
        if not path.exists():
            return {}, {}
        frame = pd.read_csv(path, usecols=["series", "origin", "actual", "ensemble"])
        frame["actual"] = pd.to_numeric(frame.actual, errors="coerce")
        frame["ensemble"] = pd.to_numeric(frame.ensemble, errors="coerce")

        def summarize(rows):
            if rows.empty:
                return {}
            actual = rows.actual.to_numpy(dtype=float)
            predicted = rows.ensemble.to_numpy(dtype=float)
            metrics = compute_all_metrics(actual, predicted)
            valid_rows = rows.loc[
                np.isfinite(rows.actual) & np.isfinite(rows.ensemble) & rows.actual.ge(0)]
            return {
                **metrics,
                "sample_count": metrics["n"],
                "sample_origin_count": int(valid_rows.origin.nunique()),
                "sample_basis": "observed_validation_targets_across_forecast_steps",
            }

        per_identity = {
            str(identity): summarize(rows)
            for identity, rows in frame.groupby("series", sort=True)
        }
        return per_identity, summarize(frame)

    @staticmethod
    def _quality_metrics(model_run_id, product_ids):
        bundle_path = ModelStore().runs / model_run_id
        metadata = json.loads((bundle_path / "metadata.json").read_text(encoding="utf-8"))
        run_metrics = metadata.get("metrics", {})
        validation = dict(run_metrics.get("validation", {}).get("ensemble", {}))
        validation_by_identity = run_metrics.get("product_validation_metrics_by_identity", {})
        file_metrics, file_summary = PredictionWriter._validation_metrics_from_file(bundle_path)
        try:
            prediction_intervals_by_identity = validation_intervals_by_series(bundle_path)
        except (OSError, ValueError, KeyError, pd.errors.ParserError):
            prediction_intervals_by_identity = {}
        try:
            catalog_items = [
                {
                    "id": pid,
                    "category": ident[0],
                    "name": ident[1],
                    "variant": ident[2],
                    "origin": ident[3],
                    "unit": ident[4],
                }
                for ident, pid in product_ids.items()
            ]
            picp_report = build_model_confidence_evaluations(
                bundle_path, products_catalog=catalog_items
            )
            picp_by_product_horizon = {}
            for rec in picp_report.get("records", []):
                picp_by_product_horizon.setdefault(rec["commodity_id"], {})[
                    rec["forecast_horizon"]
                ] = rec
        except (OSError, ValueError, KeyError, pd.errors.ParserError):
            picp_report = None
            picp_by_product_horizon = {}
        validation = {key: value for key, value in {
            **file_summary, **validation,
        }.items() if value is not None}
        product_metrics = {}
        confidence_by_identity = run_metrics.get("product_confidence_by_identity", {})
        if not isinstance(confidence_by_identity, dict):
            confidence_by_identity = {}
        confidence_evaluation_source = "chronological_validation"
        confidence_profile_status = "bundle_validation"
        def saved_confidence_metrics():
            for profile in confidence_by_identity.values():
                if not isinstance(profile, dict):
                    continue
                for steps in (profile.get("confidence_by_step", {}) or {}).values():
                    if isinstance(steps, dict):
                        yield from (metric for metric in steps.values()
                                    if isinstance(metric, dict))

        has_validated_bundle_confidence = any(
            metric.get("evidence_status") == "validated"
            and metric.get("confidence_method") == CONFIDENCE_METHOD
            and isinstance(metric.get("confidence_score"), (int, float))
            and np.isfinite(metric.get("confidence_score"))
            for metric in saved_confidence_metrics())
        if not has_validated_bundle_confidence:
            profile_confidence, profile_source = PredictionWriter._confidence_profile(
                bundle_path, metadata)
            if profile_source is not None:
                confidence_by_identity = profile_confidence
                confidence_evaluation_source = profile_source
                confidence_profile_status = "development_validated_with_selection_reuse"
        for identity, product_id in product_ids.items():
            series = "||".join(identity)
            validation_product = {
                **file_metrics.get(series, {}),
                **{key: value for key, value in validation_by_identity.get(series, {}).items()
                   if value is not None},
            }
            confidence_product = confidence_by_identity.get(series, {})
            product_metrics[product_id] = {
                **confidence_product,
                "mae": validation_product.get("mae"),
                "rmse": validation_product.get("rmse"),
                "mape": validation_product.get("mape"),
                "sample_count": validation_product.get("sample_count", 0),
                "sample_origin_count": validation_product.get("sample_origin_count"),
                "sample_basis": validation_product.get(
                    "sample_basis", "observed_validation_targets_across_forecast_steps"),
                "prediction_success": validation_product.get("prediction_success"),
                "within_5_php_count": validation_product.get("within_5_php_count"),
                "within_5_php_tolerance": validation_product.get("within_5_php_tolerance"),
                "within_5_php_sample_count": validation_product.get("within_5_php_sample_count"),
                "within_5_php_accuracy_pct": validation_product.get("within_5_php_accuracy_pct"),
                "within_5_percent_count": validation_product.get("within_5_percent_count"),
                "within_5_percent_sample_count": validation_product.get("within_5_percent_sample_count"),
                "within_5_percent_accuracy_pct": validation_product.get("within_5_percent_accuracy_pct"),
                "prediction_intervals": prediction_intervals_by_identity.get(series, {}),
                "picp_by_horizon": picp_by_product_horizon.get(product_id, {}),
                "evaluation_source": "chronological_validation",
                "confidence_evaluation_source": confidence_evaluation_source,
            }
        source_data = run_metrics.get("source_data", {})
        processed_from = source_data.get("processed_from")
        if not processed_from:
            processed_from = metadata.get("split", {}).get("train", {}).get("start")
        processed_through = source_data.get("processed_through")
        if not processed_through:
            processed_through = metadata.get("split", {}).get("test", {}).get("end")
        training_through = metadata.get("split", {}).get("train", {}).get("end")
        if isinstance(processed_from, str):
            processed_from = processed_from[:10]
        if isinstance(processed_through, str):
            processed_through = processed_through[:10]
        return {
            "mae": validation.get("mae"),
            "rmse": validation.get("rmse"),
            "mape": validation.get("mape"),
            "directional_accuracy": validation.get("directional_accuracy"),
            "prediction_success": validation.get("prediction_success"),
            "success_tolerance": SUCCESS_TOLERANCE,
            "success_definition": "absolute_percentage_error_at_most_tolerance",
            "within_5_php_count": validation.get("within_5_php_count"),
            "within_5_php_tolerance": validation.get("within_5_php_tolerance"),
            "within_5_php_sample_count": validation.get("within_5_php_sample_count"),
            "within_5_php_accuracy_pct": validation.get("within_5_php_accuracy_pct"),
            "within_5_percent_count": validation.get("within_5_percent_count"),
            "within_5_percent_sample_count": validation.get("within_5_percent_sample_count"),
            "within_5_percent_accuracy_pct": validation.get("within_5_percent_accuracy_pct"),
            "within_5_percent_excluded_zero_or_near_zero": validation.get(
                "within_5_percent_excluded_zero_or_near_zero"),
            "within_10_tolerance": 0.10,
            "within_10_definition": "absolute_percentage_error_at_most_tolerance",
            "within_10_accuracy_pct": validation.get("within_10_accuracy_pct"),
            "within_10_count": validation.get("within_10_count"),
            "within_10_sample_count": validation.get("within_10_sample_count"),
            "evaluation_source": "chronological_validation",
            "sample_count": validation.get("n"),
            "product_metrics": product_metrics,
            "picp_confidence_evaluation": picp_report,
            "confidence_method": CONFIDENCE_METHOD,
            "confidence_evaluation_source": confidence_evaluation_source,
            "confidence_profile_status": confidence_profile_status,
            "processed_from": processed_from,
            "processed_through": processed_through,
            "training_through": training_through[:10] if isinstance(training_through, str) else training_through,
            "processed_observed_rows": source_data.get("observed_rows"),
            "processed_series_count": source_data.get("series_count"),
            "validation_start": metadata.get("split", {}).get("validation", {}).get("start"),
            "validation_end": metadata.get("split", {}).get("validation", {}).get("end"),
            "evaluation_scope": "observed_chronological_validation_targets_all_forecast_steps",
            "metric_aggregation": "row_weighted_across_observed_product_date_step_targets",
        }

    def sync_model_confidence_evaluations(self, model_run_id, product_ids):
        """Upsert out-of-sample PICP evaluations into public.model_confidence_evaluations."""
        bundle_path = ModelStore().runs / model_run_id
        catalog_items = [
            {
                "id": pid,
                "category": ident[0],
                "name": ident[1],
                "variant": ident[2],
                "origin": ident[3],
                "unit": ident[4],
            }
            for ident, pid in product_ids.items()
        ]
        report = build_model_confidence_evaluations(
            bundle_path, products_catalog=catalog_items
        )
        rows = report.get("records", [])
        if not rows:
            return 0
        try:
            response = self.db.rpc(
                "upsert_model_confidence_evaluations", {"p_rows": rows}
            ).execute()
            return int(response.data or len(rows))
        except Exception:
            return 0

    def run(self, horizon="monthly", origin_date=None):
        if horizon not in HORIZON_MAP:
            raise ValueError(f"Unsupported forecast mode: {horizon}")
        registry = ModelRegistry.get().load_all()
        product_ids = self._product_ids()
        self.check_schema(product_ids)
        quality_metrics = self._quality_metrics(registry.run_id, product_ids)
        today = pd.Timestamp(datetime.now(PH_TIME).date())
        latest_date_str = self.fetcher.fetch_latest_date()
        latest_date = pd.Timestamp(latest_date_str) if latest_date_str else today
        if origin_date:
            effective_origin = pd.Timestamp(origin_date)
        else:
            effective_origin = max(today, latest_date)
        raw = self.fetcher.fetch_all(through_date=effective_origin.date().isoformat())
        report_dates = pd.to_datetime(raw.get("report_date"), errors="coerce").dropna()
        if report_dates.empty:
            raise RuntimeError("No dated price rows are available for forecast publication")
        # Issue date is Manila today or the latest available database report date.
        # Some rows are copied forward from their source PDF; validate() keeps
        # those rows out of observed labels, while the causal fill limit decides
        # whether their source price is still recent enough to use as an input.
        issue_origin = effective_origin
        horizon_days = 30
        clean = self.preprocessor.validate(raw)
        clean = self._extend_inputs_to_origin(
            clean, issue_origin, self.cfg.max_fill_days)
        series_count = clean.groupby(SERIES_KEY).ngroups
        rows, failures, fallbacks, unavailable = [], [], [], []
        model_count = 0
        forecast_products = {}
        market_daily = FeatureBuilder.category_return_history(clean)
        market_daily['category_return'] = market_daily.category_return.fillna(0.0)
        market_groups = {str(category): group for category, group
                         in market_daily.groupby('product_category', sort=False)}
        product_daily = FeatureBuilder.product_return_history(clean)
        product_daily['product_return'] = product_daily.product_return.fillna(0.0)
        product_groups = {tuple(map(str, key)): group for key, group
                          in product_daily.groupby(SERIES_KEY[:3], sort=False)}
        prepared, prepared_meta = [], []
        for key, series in clean.groupby(SERIES_KEY, sort=True):
            product_id = product_ids.get(tuple(key))
            if product_id is None:
                category, name, variant, origin_val, unit = key
                try:
                    res = self.db.table("products").upsert({
                        "name": str(name),
                        "variant": str(variant),
                        "origin": str(origin_val),
                        "category": str(category),
                        "unit": str(unit),
                        "description": f"{variant} {name} is a tracked commodity in the NCR agri-fishery market.",
                    }, on_conflict="name,variant,origin,unit").execute()
                    if res.data:
                        product_id = res.data[0]["id"]
                        product_ids[tuple(key)] = product_id
                except Exception:
                    pass
            if product_id is None:
                failures.append({"series": tuple(key), "error": "missing products row"})
                continue
            if not np.isfinite(float(series.price_index.iloc[-1])):
                observed = series.loc[series.is_observed, "report_date"]
                last_observed = (pd.Timestamp(observed.max()).date().isoformat()
                                 if not observed.empty else None)
                detail = {
                    "series": tuple(key),
                    "reason": "no observed price within max_fill_days of forecast origin",
                    "last_observed_date": last_observed,
                }
                unavailable.append(detail)
                forecast_products[product_id] = {
                    "source": "unavailable",
                    "origin_date": issue_origin.date().isoformat(),
                    "reason": detail["reason"],
                    "last_observed_date": last_observed,
                }
                continue
            try:
                category = str(key[0])
                origin = issue_origin
                market = market_groups.get(category)
                history = ([] if market is None else market.loc[
                    pd.to_datetime(market.report_date) <= origin,
                    'category_return'].to_numpy(dtype=float).tolist())
                product_market = product_groups.get(tuple(map(str, key[:3])))
                product_history = ([] if product_market is None else product_market.loc[
                    pd.to_datetime(product_market.report_date) <= origin,
                    'product_return'].to_numpy(dtype=float).tolist())
                item = registry.engine._prepare(series, None, history, product_history)
                prepared.append(item)
                prepared_meta.append((tuple(key), series, product_id))
            except (ValueError, FileNotFoundError) as exc:
                if self._is_history_shortfall(exc):
                    try:
                        dates, point = self._persistence_fallback(
                            registry.engine, series, horizon_days)
                        rows.extend(self._production_rows(
                            product_id, dates, point, issue_origin, series,
                            quality_metrics.get("product_metrics", {}).get(product_id, {}),
                            allow_confidence=False))
                        forecast_products[product_id] = {
                            "source": "persistence_fallback",
                            "origin_date": issue_origin.date().isoformat(),
                            "period_forecast_source": "complete_daily_path_mean",
                        }
                        fallbacks.append({"series": tuple(key), "reason": str(exc)})
                    except ValueError as fallback_exc:
                        failures.append({"series": tuple(key), "error": str(fallback_exc)})
                else:
                    failures.append({"series": tuple(key), "error": str(exc)})
        if prepared:
            try:
                forecasts = registry.engine.forecast_many(prepared, horizon_days)
                for (_, series, product_id), forecast in zip(prepared_meta, forecasts):
                    rows.extend(self._production_rows(
                        product_id, forecast.dates, forecast.point, issue_origin, series,
                        quality_metrics.get("product_metrics", {}).get(product_id, {})))
                    forecast_products[product_id] = {
                        "source": "model",
                        "origin_date": issue_origin.date().isoformat(),
                        "period_forecast_source": "complete_daily_path_mean",
                    }
                    model_count += 1
            except (ValueError, FileNotFoundError) as exc:
                failures.extend({"series": key, "error": str(exc)}
                                for key, _, _ in prepared_meta)
        if failures:
            raise RuntimeError(
                f"Forecast vintage was not published: {len(failures)} unsupported series; "
                f"first={failures[0]}")
        if not rows:
            raise RuntimeError("Forecast vintage was not published: no series has usable recent inputs")
        expected_rows_by_horizon = dict(PUBLISHED_FORECAST_STEPS)
        published_ids = {
            product_id for product_id, detail in forecast_products.items()
            if detail.get("source") != "unavailable"
        }
        for product_id in published_ids:
            product_rows = [row for row in rows if row["product_id"] == product_id]
            counts = {
                name: sum(row["forecast_horizon"] == name for row in product_rows)
                for name in expected_rows_by_horizon
            }
            if counts != expected_rows_by_horizon:
                raise RuntimeError(
                    f"Forecast output contract violated for product {product_id}: "
                    f"expected {expected_rows_by_horizon}, got {counts}")
        quality_metrics["publication_contract"] = {
            "daily_steps": PUBLISHED_FORECAST_STEPS["daily"],
            "weekly_steps": PUBLISHED_FORECAST_STEPS["weekly"],
            "monthly_steps": PUBLISHED_FORECAST_STEPS["monthly"],
            "contract_id": "rolling_daily7_weekly4_monthly30_v2",
            "weekly_target": "four consecutive 7-day windows starting origin+1",
            "monthly_target": "origin price plus 29 future daily forecasts: origin through origin+29 inclusive",
            "period_model": (
                "equal-weight means of complete daily forecast paths; "
                "historical calendar evaluation does not validate this contract"
            ),
        }
        run_id = str(uuid4())
        payload = {
            "p_run_id": run_id,
            "p_model_run_id": registry.run_id,
            "p_generated_at": datetime.now(timezone.utc).isoformat(),
            "p_horizon": horizon_days,
            "p_rows": rows,
            "p_metrics": quality_metrics,
        }
        quality_metrics_published = True
        payload["p_metrics"]["forecast_products"] = forecast_products
        result = None
        for attempt in range(3):
            try:
                result = self.db.rpc("publish_forecast_run_with_metrics", payload).execute()
                break
            except Exception as exc:
                if "57014" in str(exc) and attempt < 2:
                    import time
                    time.sleep(2.0 * (attempt + 1))
                    continue
                if "21000" in str(exc) and "DELETE requires a WHERE clause" in str(exc):
                    raise RuntimeError(
                        f"Supabase safe-update enforcement blocked forecast publication. "
                        f"Apply {SAFE_DELETE_MIGRATION}, then retry. The failed RPC was "
                        "rolled back atomically."
                    ) from exc
                message = str(exc).lower()
                metrics_rpc_missing = (
                    "publish_forecast_run_with_metrics" in message
                    and ("schema cache" in message or "does not exist" in message
                         or "could not find the function" in message)
                )
                if metrics_rpc_missing:
                    # Preserve normal forecast publishing during migration rollout;
                    # quality metrics become available after the migration is applied.
                    legacy_payload = {key: value for key, value in payload.items()
                                      if key != "p_metrics"}
                    try:
                        result = self.db.rpc("publish_forecast_run", legacy_payload).execute()
                        break
                    except Exception as legacy_exc:
                        if "publish_forecast_run" in str(legacy_exc):
                            raise RuntimeError(
                                f"Supabase atomic forecast publishing is unavailable. Apply "
                                f"{MIGRATION}, then retry."
                            ) from legacy_exc
                        raise
                    quality_metrics_published = False
                    break
                else:
                    raise
        confidence_evaluations_upserted = self.sync_model_confidence_evaluations(
            registry.run_id, product_ids
        )
        return {"forecast_run_id": run_id, "model_run_id": registry.run_id,
                "forecast_origin_date": issue_origin.date().isoformat(),
                "series": series_count,
                "model_series": model_count,
                "fallback_series": len(fallbacks),
                "fallback_details": fallbacks,
                "unavailable_series": len(unavailable),
                "unavailable_details": unavailable,
                "rows_written": len(rows),
                "quality_metrics_published": quality_metrics_published,
                "confidence_evaluations_upserted": confidence_evaluations_upserted,
                "database_result": result.data}
