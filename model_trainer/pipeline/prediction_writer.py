"""Generate one complete forecast vintage and publish it atomically."""
from datetime import datetime, timedelta, timezone
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
from utils.metrics import SUCCESS_TOLERANCE
from utils.prices import mean_price as _mean_price, round_price as _round_price
from evaluation.product_confidence import METHOD as CONFIDENCE_METHOD


HORIZON_MAP = {"daily": 1, "weekly": 7, "monthly": 30}
PUBLISHED_FORECAST_MONTHS = 3
PH_TIME = timezone(timedelta(hours=8))
MIGRATION = "supabase/migrations/202609240001_atomic_forecast_vintages.sql"
SAFE_DELETE_MIGRATION = "supabase/migrations/202609250001_fix_forecast_safe_delete.sql"
QUALITY_METRICS_MIGRATION = "supabase/migrations/202610010002_forecast_run_quality_metrics.sql"
PERIOD_FORECAST_MIGRATION = "supabase/migrations/202610090001_multi_period_point_forecasts.sql"




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
                'forecast_step,confidence_score,confidence_level,covered_days,period_days'
            ).limit(1).execute()
        except Exception as exc:
            raise RuntimeError(
                f'Multi-period forecast schema is unavailable. Apply {PERIOD_FORECAST_MIGRATION} '
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
    def _confidence_profile(bundle_path, metadata):
        """Load a sidecar only when it is bound to this exact legacy bundle."""
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
            if (
                profile.get("profile_schema_version") != 1
                or profile.get("profile_status") != "development_validated_with_selection_reuse"
                or profile.get("model_run_id") != bundle_path.name
                or profile.get("data_fingerprint") != metadata.get("data_fingerprint")
                or profile.get("model_metadata_sha256") != metadata_sha256
                or profile.get("ensemble_sha256") != ensemble_sha256
                or profile.get("confidence_method") != CONFIDENCE_METHOD
                or profile.get("evaluation_source") != "chronological_development_test"
                or profile.get("development_test_reused_for_selection") is not True
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
        frame = frame[np.isfinite(frame.actual) & np.isfinite(frame.ensemble)].copy()

        def summarize(rows):
            if rows.empty:
                return {}
            actual = rows.actual.to_numpy(dtype=float)
            predicted = rows.ensemble.to_numpy(dtype=float)
            errors = np.abs(predicted - actual)
            usable = np.abs(actual) >= 1e-8
            percentage_errors = errors[usable] / np.abs(actual[usable])
            return {
                "mae": float(errors.mean()),
                "rmse": float(np.sqrt(np.mean(errors ** 2))),
                "mape": float(percentage_errors.mean() * 100) if len(percentage_errors) else None,
                "sample_count": int(len(rows)),
                "sample_origin_count": int(rows.origin.nunique()),
                "prediction_success": float(np.mean(percentage_errors <= SUCCESS_TOLERANCE))
                    if len(percentage_errors) else None,
                "within_10_accuracy_pct": float(np.mean(percentage_errors <= 0.10) * 100)
                    if len(percentage_errors) else None,
                "within_10_count": int(np.count_nonzero(percentage_errors <= 0.10)),
                "within_10_sample_count": int(len(percentage_errors)),
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
        validation = {key: value for key, value in {
            **file_summary, **validation,
        }.items() if value is not None}
        product_metrics = {}
        confidence_by_identity = run_metrics.get("product_confidence_by_identity", {})
        confidence_evaluation_source = "chronological_validation"
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
                "evaluation_source": "chronological_validation",
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
            "within_10_tolerance": 0.10,
            "within_10_definition": "absolute_percentage_error_at_most_tolerance",
            "within_10_accuracy_pct": validation.get("within_10_accuracy_pct"),
            "within_10_count": validation.get("within_10_count"),
            "within_10_sample_count": validation.get("within_10_sample_count"),
            "evaluation_source": "chronological_validation",
            "sample_count": validation.get("n"),
            "product_metrics": product_metrics,
            "confidence_method": CONFIDENCE_METHOD,
            "confidence_evaluation_source": confidence_evaluation_source,
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

    def run(self, horizon="monthly"):
        if horizon not in HORIZON_MAP:
            raise ValueError(f"Unsupported forecast mode: {horizon}")
        registry = ModelRegistry.get().load_all()
        product_ids = self._product_ids()
        self.check_schema(product_ids)
        quality_metrics = self._quality_metrics(registry.run_id, product_ids)
        today = pd.Timestamp(datetime.now(PH_TIME).date())
        raw = self.fetcher.fetch_all(through_date=today.date().isoformat())
        report_dates = pd.to_datetime(raw.get("report_date"), errors="coerce").dropna()
        if report_dates.empty:
            raise RuntimeError("No dated price rows are available for forecast publication")
        # Base the forecast on the latest date represented by the DA price table.
        # Some rows are copied forward from their source PDF; validate() keeps
        # those rows out of observed labels, while the causal fill limit decides
        # whether their source price is still recent enough to use as an input.
        issue_origin = min(today, report_dates.max().normalize())
        forecast_end = (
            issue_origin + pd.DateOffset(months=PUBLISHED_FORECAST_MONTHS)
        ) + pd.offsets.MonthEnd(0)
        horizon_days = int((forecast_end.normalize() - issue_origin.normalize()).days)
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
                item = registry.engine._prepare(series, None, history)
                prepared.append(item)
                prepared_meta.append((tuple(key), series, product_id))
            except (ValueError, FileNotFoundError) as exc:
                if self._is_history_shortfall(exc):
                    try:
                        dates, point = self._persistence_fallback(
                            registry.engine, series, horizon_days)
                        rows.extend(self._rows(product_id, dates, point,
                            dates[0] - np.timedelta64(1, "D"),
                            quality_metrics.get("product_metrics", {}).get(product_id, {}),
                            allow_confidence=False))
                        forecast_products[product_id] = {
                            "source": "persistence_fallback",
                            "origin_date": str(np.datetime_as_string(dates[0]-np.timedelta64(1, "D"), unit="D")),
                        }
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
                        forecast.dates[0] - np.timedelta64(1, "D"),
                        quality_metrics.get("product_metrics", {}).get(product_id, {})))
                    forecast_products[product_id] = {
                        "source": "model",
                        "origin_date": str(np.datetime_as_string(forecast.dates[0]-np.timedelta64(1, "D"), unit="D")),
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
                "database_result": result.data}
