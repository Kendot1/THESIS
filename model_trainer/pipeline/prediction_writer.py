"""Generate one complete forecast vintage and publish it atomically."""
from datetime import datetime, timezone
from uuid import uuid4
import csv
import json

import numpy as np
import pandas as pd
from supabase import create_client

from config.settings import get_settings
from data.fetcher import DataFetcher
from data.preprocessor import DataPreprocessor, SERIES_KEY
from features.builder import FeatureBuilder
from models.registry import ModelRegistry
from models.model_store import ModelStore
from utils.metrics import SUCCESS_TOLERANCE


HORIZON_MAP = {"daily": 1, "weekly": 7, "monthly": 30}
MIGRATION = "supabase/migrations/202609240001_atomic_forecast_vintages.sql"
SAFE_DELETE_MIGRATION = "supabase/migrations/202609250001_fix_forecast_safe_delete.sql"
QUALITY_METRICS_MIGRATION = "supabase/migrations/202610010002_forecast_run_quality_metrics.sql"


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

    def check_schema(self):
        if not self._product_ids():
            raise RuntimeError('No unit-aware products are available for forecast publication')
        try:
            self.db.table('forecast_runs').select('id,metrics').limit(1).execute()
        except Exception as exc:
            raise RuntimeError(
                f'Forecast quality schema is unavailable. Apply {QUALITY_METRICS_MIGRATION} '
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
        lower, upper = engine.ensemble.intervals(point, anchor, fallback=True)
        return dates, point, lower, upper

    @staticmethod
    def _rows(product_id, dates, point, lower, upper):
        return [{
            "product_id": product_id,
            "prediction_date": str(np.datetime_as_string(date, unit="D")),
            "predicted_price": round(float(point[index]), 2),
            "lower_bound": round(float(lower[index]), 2),
            "upper_bound": round(float(upper[index]), 2),
        } for index, date in enumerate(dates)]

    @staticmethod
    def _quality_metrics(model_run_id, product_ids):
        bundle_path = ModelStore().runs / model_run_id
        metadata_path = bundle_path / "metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metrics = metadata.get("metrics", {})
        test = metrics.get("test", {}).get("ensemble", {})
        interval = metrics.get("test_interval_metrics", {}).get("0.8", {})
        ensemble = json.loads((bundle_path / "ensemble.json").read_text(encoding="utf-8"))
        widths = ensemble.get("interval_widths", {}).get("0.8", ensemble.get("widths", []))
        category_widths = ensemble.get("category_interval_widths", {})
        latest_by_product_date = {}
        forecasts_path = bundle_path / "test_forecasts.csv"
        if widths and forecasts_path.is_file():
            with forecasts_path.open(newline="", encoding="utf-8") as forecasts_file:
                for row in csv.DictReader(forecasts_file):
                    identity = tuple(row.get("series", "").split("||"))
                    product_id = product_ids.get(identity)
                    horizon = int(row["horizon"])
                    target_date = row.get("date", "")[:10]
                    origin_date = row.get("origin", "")[:10]
                    if (product_id is None or horizon < 1 or horizon > len(widths)
                            or not target_date or not origin_date
                            or origin_date >= target_date):
                        continue
                    actual = float(row["actual"])
                    point = float(row["ensemble"])
                    anchor = float(row["anchor"])
                    if (not np.isfinite([actual, point, anchor]).all()
                            or min(actual, point, anchor) <= 0):
                        continue
                    row_widths = category_widths.get(identity[0], {}).get('0.8', widths)
                    half_width = float(row_widths[horizon - 1]) * anchor
                    lower = max(0.01, point - half_width)
                    upper = point + half_width
                    key = (product_id, target_date)
                    previous = latest_by_product_date.get(key)
                    if previous is None or origin_date > previous["origin_date"]:
                        latest_by_product_date[key] = {
                            "origin_date": origin_date,
                            "actual": actual,
                            "point": point,
                            "lower": lower,
                            "upper": upper,
                        }
        product_samples = {}
        for (product_id, _), row in latest_by_product_date.items():
            sample = product_samples.setdefault(product_id, {
                "covered": 0, "successes": 0, "count": 0, "absolute_percentage_errors": [],
                "absolute_errors": [], "squared_errors": []})
            sample["covered"] += int(row["lower"] <= row["actual"] <= row["upper"])
            sample["count"] += 1
            sample["absolute_percentage_errors"].append(
                abs(row["actual"] - row["point"]) / row["actual"] * 100)
            error = abs(row['actual']-row['point'])
            sample['absolute_errors'].append(error)
            sample['squared_errors'].append(error**2)
            sample['successes'] += int(error/row['actual'] <= SUCCESS_TOLERANCE)
        product_metrics = {
            product_id: {
                "interval_coverage": sample["covered"] / sample["count"],
                "covered_count": sample["covered"],
                "interval_level": 0.8,
                "sample_count": sample["count"],
                "sample_basis": "unique_actual_dates",
                "prediction_success": sample['successes']/sample['count'],
                "evaluation_source": "historical_holdout",
                "mape": sum(sample["absolute_percentage_errors"])
                / sample["count"],
            }
            for product_id, sample in product_samples.items() if sample["count"]
        }
        source_data = metrics.get("source_data", {})
        processed_from = source_data.get("processed_from")
        if not processed_from:
            processed_from = metadata.get("split", {}).get("train", {}).get("start")
        processed_through = source_data.get("processed_through")
        if not processed_through:
            processed_through = metadata.get("split", {}).get("test", {}).get("end")
        if isinstance(processed_through, str):
            processed_through = processed_through[:10]
        if isinstance(processed_from, str):
            processed_from = processed_from[:10]
        unique_covered = sum(sample["covered"] for sample in product_samples.values())
        unique_count = sum(sample["count"] for sample in product_samples.values())
        range_coverage = (unique_covered / unique_count if unique_count else
                          interval.get("observed_coverage", metrics.get("test_interval_coverage")))
        prediction_success = (sum(sample['successes'] for sample in product_samples.values())
                              / unique_count if unique_count else test.get('prediction_success'))
        def average_samples(key):
            return sum(sum(sample[key]) for sample in product_samples.values())/unique_count
        return {
            "mae": average_samples('absolute_errors') if unique_count else test.get('mae'),
            "rmse": np.sqrt(average_samples('squared_errors')) if unique_count else test.get('rmse'),
            "mape": average_samples('absolute_percentage_errors') if unique_count else test.get('mape'),
            "directional_accuracy": None,
            "interval_level": 0.8,
            "interval_coverage": range_coverage,
            "covered_count": unique_covered if unique_count else None,
            "prediction_success": prediction_success,
            "success_tolerance": SUCCESS_TOLERANCE,
            "success_definition": "absolute_percentage_error_at_most_tolerance",
            "evaluation_source": "historical_holdout",
            "coverage_sample_count": unique_count or None,
            "sample_count": unique_count or test.get("n"),
            "product_metrics": product_metrics,
            "processed_from": processed_from,
            "processed_through": processed_through,
            "processed_observed_rows": source_data.get("observed_rows"),
            "processed_series_count": source_data.get("series_count"),
            "test_start": metadata.get("split", {}).get("test", {}).get("start"),
            "test_end": metadata.get("split", {}).get("test", {}).get("end"),
            "evaluation_scope": metrics.get("evaluation_scope"),
        }

    def run(self, horizon="monthly"):
        horizon_days = HORIZON_MAP[horizon]
        registry = ModelRegistry.get().load_all()
        product_ids = self._product_ids()
        clean = self.preprocessor.validate(self.fetcher.fetch_all())
        series_count = clean.groupby(SERIES_KEY).ngroups
        rows, failures, fallbacks = [], [], []
        market_daily = FeatureBuilder.category_return_history(clean)
        market_daily['category_return'] = market_daily.category_return.fillna(0.0)
        market_groups = {str(category): group for category, group
                         in market_daily.groupby('product_category', sort=False)}
        prepared, prepared_meta = [], []
        for key, series in clean.groupby(SERIES_KEY, sort=True):
            product_id = product_ids.get(tuple(key))
            if product_id is None:
                failures.append({"series": tuple(key), "error": "missing products row"})
                continue
            try:
                category = str(key[0])
                origin = pd.Timestamp(series.report_date.max())
                market = market_groups.get(category)
                history = ([] if market is None else market.loc[
                    pd.to_datetime(market.report_date) <= origin,
                    'category_return'].to_numpy(dtype=float).tolist())
                item = registry.engine._prepare(series, None, history)
                prepared.append(item)
                prepared_meta.append((tuple(key), series, product_id))
            except (ValueError, FileNotFoundError) as exc:
                if self._is_history_shortfall(exc):
                    try:
                        dates, point, lower, upper = self._persistence_fallback(
                            registry.engine, series, horizon_days)
                        rows.extend(self._rows(
                            product_id, dates, point, lower, upper))
                        fallbacks.append({"series": tuple(key), "reason": str(exc)})
                    except ValueError as fallback_exc:
                        failures.append({"series": tuple(key), "error": str(fallback_exc)})
                else:
                    failures.append({"series": tuple(key), "error": str(exc)})
        if prepared:
            try:
                forecasts = registry.engine.forecast_many(prepared, horizon_days)
                for (_, _, product_id), forecast in zip(prepared_meta, forecasts):
                    rows.extend(self._rows(product_id, forecast.dates, forecast.point,
                                           forecast.lower, forecast.upper))
            except (ValueError, FileNotFoundError) as exc:
                failures.extend({"series": key, "error": str(exc)}
                                for key, _, _ in prepared_meta)
        if failures:
            raise RuntimeError(
                f"Forecast vintage was not published: {len(failures)} unsupported series; "
                f"first={failures[0]}")
        run_id = str(uuid4())
        payload = {
            "p_run_id": run_id,
            "p_model_run_id": registry.run_id,
            "p_generated_at": datetime.now(timezone.utc).isoformat(),
            "p_horizon": horizon_days,
            "p_rows": rows,
            "p_metrics": self._quality_metrics(registry.run_id, product_ids),
        }
        quality_metrics_published = True
        try:
            result = self.db.rpc("publish_forecast_run_with_metrics", payload).execute()
        except Exception as exc:
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
                except Exception as legacy_exc:
                    if "publish_forecast_run" in str(legacy_exc):
                        raise RuntimeError(
                            f"Supabase atomic forecast publishing is unavailable. Apply "
                            f"{MIGRATION}, then retry."
                        ) from legacy_exc
                    raise
                quality_metrics_published = False
            else:
                raise
        return {"forecast_run_id": run_id, "model_run_id": registry.run_id,
                "series": series_count,
                "model_series": series_count-len(fallbacks),
                "fallback_series": len(fallbacks),
                "fallback_details": fallbacks,
                "rows_written": len(rows),
                "quality_metrics_published": quality_metrics_published,
                "database_result": result.data}
