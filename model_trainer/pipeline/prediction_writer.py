"""
Batch Prediction Writer.

Generates predictions for ALL products in food_prices and writes them
to the normalized `predictions` table in Supabase (FK to products.id).

Usage:
    python main.py predict --horizon monthly
    python main.py predict --horizon weekly
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone
from typing import List, Dict

from supabase import create_client

from data.fetcher import DataFetcher
from data.preprocessor import DataPreprocessor
from features.temporal import TemporalFeatures
from features.lag_features import LagFeatures
from features.categorical import CategoricalEncoder
from models.registry import ModelRegistry
from models.model_store import ModelStore
from config.settings import get_settings
from utils.logger import get_logger

log = get_logger(__name__)

# ── Stabilization constants ──
MAX_DAILY_CHANGE = 0.05
HARD_CLIP_BAND = 0.20

HORIZON_MAP = {"daily": 1, "weekly": 7, "monthly": 30}


def _compute_trend(prices: np.ndarray, window: int = 14) -> float:
    recent = prices[-window:]
    if len(recent) < 3:
        return 0.0
    x = np.arange(len(recent), dtype=np.float64)
    coeffs = np.polyfit(x, recent, 1)
    return float(coeffs[0])


def _stabilize_prediction(
    raw_price: float,
    prev_price: float,
    anchor_price: float,
    trend_per_day: float,
    step: int,
) -> float:
    model_delta = raw_price - prev_price
    if abs(model_delta) < prev_price * 0.001:
        effective_delta = trend_per_day * 0.5
    else:
        effective_delta = 0.85 * model_delta + 0.15 * trend_per_day

    price = prev_price + effective_delta
    max_up = prev_price * (1 + MAX_DAILY_CHANGE)
    max_dn = prev_price * (1 - MAX_DAILY_CHANGE)
    price = float(np.clip(price, max_dn, max_up))
    clip_lo = anchor_price * (1 - HARD_CLIP_BAND)
    clip_hi = anchor_price * (1 + HARD_CLIP_BAND)
    price = float(np.clip(price, clip_lo, clip_hi))
    return round(price, 2)


class PredictionWriter:
    """Batch-generate predictions and write to the normalized predictions table."""

    def __init__(self):
        self.cfg = get_settings()
        self.fetcher = DataFetcher()
        self.preprocessor = DataPreprocessor()
        self.temporal = TemporalFeatures()
        self.lags = LagFeatures()
        self.encoder = CategoricalEncoder()

        self._supabase = create_client(self.cfg.supabase_url, self.cfg.supabase_key)

    def _build_product_id_map(self) -> Dict[tuple, int]:
        """
        Load products table and build a lookup:
          (name, variant, origin) -> products.id
        """
        r = self._supabase.table("products").select("id, name, variant, origin").execute()
        lookup = {}
        for row in r.data:
            key = (row["name"], row.get("variant") or "", row.get("origin") or "")
            lookup[key] = row["id"]
        return lookup

    def _register_product(self, name: str, variant: str, origin: str, category: str) -> str:
        try:
            r = self._supabase.table("products").insert({
                "name": name,
                "variant": variant,
                "origin": origin,
                "category": category,
                "description": f"{name} is a tracked commodity in the NCR agri-fishery market."
            }).execute()
            if r.data and len(r.data) > 0:
                log.info(f"  Auto-registered new product: {name} | {variant} | {origin}")
                return r.data[0]["id"]
        except Exception as e:
            log.warning(f"  Failed to auto-register {name}: {e}")
        return None

    def run(self, horizon: str = "monthly") -> Dict:
        """Generate predictions for all products and write to predictions table."""
        horizon_days = HORIZON_MAP.get(horizon, 30)
        log.info(f"Starting batch prediction (horizon={horizon}, {horizon_days} days)")

        # Load models
        registry = ModelRegistry.get()
        registry.load_all()

        # Build product_id lookup from normalized products table
        product_id_map = self._build_product_id_map()
        if not product_id_map:
            log.error("products table is empty. Run seed_metadata.py first.")
            return {"success": 0, "failed": 0, "total": 0}
        log.info(f"Loaded {len(product_id_map)} product IDs from products table.")

        # Get all price data
        all_df = self.fetcher.fetch_all()
        if all_df.empty:
            log.error("No data in food_prices table.")
            return {"success": 0, "failed": 0, "total": 0}

        all_df = self.preprocessor.validate(all_df)

        # Group by product series (name, variant, origin)
        group_cols = ["product_name"]
        if "product_variant" in all_df.columns:
            group_cols.append("product_variant")
        if "origin" in all_df.columns:
            group_cols.append("origin")

        series_groups = all_df.groupby(group_cols)
        total = len(series_groups)
        log.info(f"Found {total} unique product series to predict.")

        success = 0
        failed = 0
        all_rows: List[Dict] = []

        for keys, group_df in series_groups:
            if isinstance(keys, str):
                keys = (keys,)

            product_name = keys[0]
            variant = keys[1] if len(keys) > 1 else ""
            if not variant or variant.lower() == "unknown":
                variant = "Standard"
                
            origin = keys[2] if len(keys) > 2 else ""

            # Look up product_id from normalized table
            lookup_key = (product_name, variant or "", origin or "")
            product_id = product_id_map.get(lookup_key)

            if product_id is None:
                # Auto-register this product series
                category = group_df["product_category"].iloc[0] if "product_category" in group_df.columns else "Unknown"
                product_id = self._register_product(product_name, variant or "", origin or "", category)
                if product_id:
                    product_id_map[lookup_key] = product_id
                else:
                    log.warning(f"  Could not register ({product_name}, {variant}, {origin}) - skipping")
                    failed += 1
                    continue

            try:
                predictions = self._predict_series(
                    group_df, product_name, horizon_days, registry
                )

                for p in predictions:
                    all_rows.append({
                        "product_id": product_id,
                        "prediction_date": p["date"],
                        "predicted_price": p["predicted_price"],
                        "lower_bound": p["lower_bound"],
                        "upper_bound": p["upper_bound"],
                    })

                success += 1
                if success % 20 == 0:
                    log.info(f"  Progress: {success}/{total} series predicted")

            except Exception as e:
                log.warning(f"  Failed to predict {product_name}: {e}")
                failed += 1

        # Write to Supabase
        if all_rows:
            self._write_to_supabase(all_rows)

        stats = {
            "success": success,
            "failed": failed,
            "total": total,
            "rows_written": len(all_rows),
        }
        log.info(f"Batch prediction complete: {stats}")
        return stats

    def _predict_series(
        self,
        series_df: pd.DataFrame,
        product_name: str,
        horizon_days: int,
        registry: ModelRegistry,
    ) -> List[Dict]:
        """Generate predictions for a single product series."""
        if len(series_df) < 5:
            raise ValueError(f"Insufficient data ({len(series_df)} rows)")

        current_price = float(series_df["price_index"].iloc[-1])
        real_prices = series_df["price_index"].values
        anchor_price = float(np.mean(real_prices[-7:]))
        trend_per_day = _compute_trend(real_prices, window=14)

        # Build features
        featured_df = self.temporal.transform(series_df.copy())
        featured_df = self.lags.transform(featured_df)
        featured_df = self.encoder.transform(featured_df)

        feature_cols = [
            c for c in featured_df.columns
            if c not in [
                "id", "report_date", "source_pdf", "created_at",
                "product_name", "product_category", "product_variant",
                "origin", "unit", "price_index",
            ]
            and featured_df[c].dtype in ["int64", "float64", "int32", "float32"]
        ]
        for col in feature_cols:
            if col in featured_df.columns:
                featured_df[col] = featured_df[col].fillna(0.0)

        last_date = series_df["report_date"].max()
        if isinstance(last_date, str):
            last_date = pd.to_datetime(last_date)

        predictions = []

        # Try LSTM + LightGBM ensemble
        try:
            if registry.lstm is None:
                raise FileNotFoundError("LSTM model not loaded")

            X_seq, _, _, _, _ = registry.lstm.build_sequences_inference(featured_df)
            if len(X_seq) == 0:
                raise ValueError("Not enough history for LSTM sequence")

            last_seq = X_seq[[-1]]
            points, lowers, uppers = registry.lstm.predict_with_uncertainty(
                last_seq, current_prices=[current_price], n_samples=30
            )
            points = points[0]
            lowers = lowers[0]
            uppers = uppers[0]

            # Stage 2: LightGBM residual
            try:
                if registry.lgbm is not None and registry.ensemble is not None:
                    last_features = featured_df.iloc[[-1]][feature_cols].copy()
                    last_features["lstm_prediction"] = current_price
                    lgbm_point, lgbm_lower, lgbm_upper = registry.lgbm.predict_residual_with_intervals(last_features)
                    lgbm_points = np.full(30, lgbm_point[0])
                    lgbm_lowers = np.full(30, lgbm_lower[0])
                    lgbm_uppers = np.full(30, lgbm_upper[0])
                    points, lowers, uppers = registry.ensemble.predict_with_intervals(
                        points, lowers, uppers,
                        lgbm_points, lgbm_lowers, lgbm_uppers
                    )
            except Exception as res_err:
                log.debug(f"No stacking ensemble for {product_name}: {res_err}")

            points = points[:horizon_days]
            lowers = lowers[:horizon_days]
            uppers = uppers[:horizon_days]

            prev_price = current_price
            for day_offset in range(1, horizon_days + 1):
                future_date = last_date + timedelta(days=day_offset)
                raw_point = float(points[day_offset - 1])
                final_point = _stabilize_prediction(
                    raw_point, prev_price, anchor_price,
                    trend_per_day, step=day_offset
                )
                predictions.append({
                    "date": future_date.strftime("%Y-%m-%d"),
                    "predicted_price": final_point,
                    "lower_bound": round(float(lowers[day_offset - 1]), 2),
                    "upper_bound": round(float(uppers[day_offset - 1]), 2),
                })
                prev_price = final_point

        except (FileNotFoundError, ValueError, Exception) as e:
            log.debug(f"ML model failed for {product_name}, using trend fallback: {e}")
            sma = float(series_df["price_index"].tail(7).mean())
            std = float(series_df["price_index"].tail(7).std())
            if pd.isna(std) or std == 0:
                std = sma * 0.05

            for day_offset in range(1, horizon_days + 1):
                future_date = last_date + timedelta(days=day_offset)
                fallback_price = round(sma + trend_per_day * day_offset * 0.3, 2)
                predictions.append({
                    "date": future_date.strftime("%Y-%m-%d"),
                    "predicted_price": fallback_price,
                    "lower_bound": round(fallback_price - 1.28 * std, 2),
                    "upper_bound": round(fallback_price + 1.28 * std, 2),
                })

        return predictions

    def _write_to_supabase(self, rows: List[Dict]):
        """Clear old predictions and write new batch."""
        log.info(f"Writing {len(rows)} prediction rows to predictions table...")

        # Delete old predictions
        try:
            self._supabase.table("predictions").delete().neq(
                "id", "00000000-0000-0000-0000-000000000000"
            ).execute()
            log.info("  Cleared old predictions.")
        except Exception as e:
            log.warning(f"  Could not clear old predictions: {e}")

        # Upsert in batches of 500
        batch_size = 500
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            try:
                self._supabase.table("predictions").upsert(batch, on_conflict="product_id,prediction_date").execute()
            except Exception as e:
                log.error(f"  Failed to upsert batch {i // batch_size}: {e}")

        log.info("  Successfully wrote predictions to Supabase.")
