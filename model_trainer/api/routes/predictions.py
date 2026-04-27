"""
Prediction API routes.
Provides daily, weekly, and monthly price forecasts.

Stabilization strategy (prevents recursive explosion WITHOUT flattening):
  1. Trend extraction — linear slope from last 14 days of REAL data
  2. Flatness injection — if model produces negligible change, use trend
  3. Growth cap — max ±5% change per day (safety rail only)
  4. Hard clip — ±20% of anchor (prevents runaway, wide enough for trends)
  5. Post-processing — detect flat sequences and overlay trend correction
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException

from api.schemas import PredictionRequest, PredictionResponse, PredictionPoint
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
router = APIRouter(prefix="/predictions", tags=["Predictions"])

HORIZON_MAP = {"daily": 1, "weekly": 7, "monthly": 30}

# ── Stabilization constants ──
MAX_DAILY_CHANGE = 0.05        # 5% cap per step (safety rail)
HARD_CLIP_BAND = 0.20          # ±20% of anchor (wide — only prevents explosion)
CONFIDENCE_DECAY = 0.04        # interval widens 4% per extra step
FLATNESS_THRESHOLD = 0.002     # CV < 0.2% across sequence → considered flat


def _compute_trend(prices: np.ndarray, window: int = 14) -> float:
    """
    Extract daily price trend (slope) from recent REAL data using linear regression.
    Returns the slope in price-units per day.
    """
    recent = prices[-window:]
    if len(recent) < 3:
        return 0.0
    x = np.arange(len(recent), dtype=np.float64)
    coeffs = np.polyfit(x, recent, 1)
    return float(coeffs[0])  # slope per day


def _stabilize_prediction(
    raw_price: float,
    prev_price: float,
    anchor_price: float,
    trend_per_day: float,
    step: int,
) -> float:
    """
    Stabilize a single-step prediction while preserving dynamics.

    Strategy:
      1. Compute the change the model predicts (model_delta).
      2. If the model's delta is negligible (< 0.1% of price), it has gone flat.
         In that case, substitute the historical trend direction.
      3. Apply a growth cap (±5%) as a safety rail.
      4. Apply a hard clip (±20% of anchor) as a final explosion guard.

    This replaces the old mean-reversion design which collapsed all output to flat.
    """
    model_delta = raw_price - prev_price

    # Detect flatness: model produces near-zero change
    if abs(model_delta) < prev_price * 0.001:
        # Model is flat — inject 50% of the historical trend
        effective_delta = trend_per_day * 0.5
    else:
        # Model is dynamic — trust its direction, but dampen large recursive errors
        # Blend: 85% model signal + 15% trend signal (adds directional bias)
        effective_delta = 0.85 * model_delta + 0.15 * trend_per_day

    price = prev_price + effective_delta

    # Safety rail: cap per-step change at ±5%
    max_up = prev_price * (1 + MAX_DAILY_CHANGE)
    max_dn = prev_price * (1 - MAX_DAILY_CHANGE)
    price = float(np.clip(price, max_dn, max_up))

    # Explosion guard: hard clip at ±20% of anchor
    clip_lo = anchor_price * (1 - HARD_CLIP_BAND)
    clip_hi = anchor_price * (1 + HARD_CLIP_BAND)
    price = float(np.clip(price, clip_lo, clip_hi))

    return round(price, 2)


def _stabilize_bounds(
    raw_lower: float,
    raw_upper: float,
    point: float,
    anchor_price: float,
    step: int,
) -> tuple:
    """Widen confidence bounds proportionally to recursion depth."""
    base_spread = max(abs(raw_upper - point), abs(point - raw_lower), anchor_price * 0.02)
    decay_factor = 1 + CONFIDENCE_DECAY * step
    spread = base_spread * decay_factor

    lower = round(point - spread, 2)
    upper = round(point + spread, 2)
    return lower, upper


def _apply_flatness_correction(
    predictions: list,
    current_price: float,
    trend_per_day: float,
) -> list:
    """
    Post-processing safety net: if the entire prediction sequence has
    near-zero variation (CV < threshold), overlay the historical trend
    to restore directionality.
    """
    prices = [p.predicted_price for p in predictions]
    if len(prices) < 3:
        return predictions

    mean_price = np.mean(prices)
    cv = np.std(prices) / mean_price if mean_price > 0 else 0

    if cv < FLATNESS_THRESHOLD and abs(trend_per_day) > 0.01:
        log.info(
            f"Flatness detected (CV={cv:.4f}). "
            f"Applying trend correction (slope={trend_per_day:.3f}/day)."
        )
        corrected = []
        prev = current_price
        for i, p in enumerate(predictions):
            # Overlay the trend: shift each point by cumulative trend
            trend_shift = trend_per_day * (i + 1)
            new_price = round(p.predicted_price + trend_shift * 0.5, 2)

            # Still cap the correction to prevent explosion
            max_up = prev * (1 + MAX_DAILY_CHANGE)
            max_dn = prev * (1 - MAX_DAILY_CHANGE)
            new_price = round(float(np.clip(new_price, max_dn, max_up)), 2)

            corrected.append(PredictionPoint(
                date=p.date,
                predicted_price=new_price,
                lower_bound=p.lower_bound,
                upper_bound=p.upper_bound,
                confidence_level=p.confidence_level,
            ))
            prev = new_price
        return corrected

    return predictions


@router.post("/", response_model=PredictionResponse)
async def predict(request: PredictionRequest):
    """Generate dynamic, stabilized price predictions for a product."""
    try:
        cfg = get_settings()
        horizon_days = HORIZON_MAP.get(request.horizon)
        if horizon_days is None:
            raise HTTPException(400, f"Invalid horizon: {request.horizon}")

        # Use the singleton registry instead of loading models per-request
        registry = ModelRegistry.get()
        registry.load_all()  # no-op if already loaded

        fetcher = DataFetcher()
        preprocessor = DataPreprocessor()
        store = ModelStore()

        # Feature transformers
        temporal = TemporalFeatures()
        lags = LagFeatures()
        encoder = CategoricalEncoder()

        # Fetch product history
        history_df = fetcher.fetch_product_history(
            request.product_name, product_variant=request.product_variant, limit=365
        )
        if history_df.empty:
            raise HTTPException(404, f"No data found for '{request.product_name}'")

        history_df = preprocessor.validate(history_df)
        current_price = float(history_df["price_index"].iloc[-1])

        # ── Extract trend and anchor from REAL data (never from predictions) ──
        real_prices = history_df["price_index"].values
        anchor_price = float(np.mean(real_prices[-7:]))
        trend_per_day = _compute_trend(real_prices, window=14)

        log.debug(
            f"{request.product_name}: anchor={anchor_price:.2f}, "
            f"trend={trend_per_day:+.3f}/day"
        )

        # Build features for LGBM predictions
        featured_df = temporal.transform(history_df)
        featured_df = lags.transform(featured_df)
        featured_df = encoder.transform(featured_df)

        # Determine feature columns once
        feature_cols = [
            c for c in featured_df.columns
            if c not in [
                "id", "report_date", "source_pdf", "created_at",
                "product_name", "product_category", "product_variant",
                "origin", "unit", "price_index",
            ]
            and featured_df[c].dtype in ["int64", "float64", "int32", "float32"]
        ]

        # Fill any remaining NaN in numeric feature columns
        for col in feature_cols:
            if col in featured_df.columns:
                featured_df[col] = featured_df[col].fillna(0.0)

        last_date = history_df["report_date"].max()
        predictions = []

        # ── DIRECT MULTI-STEP FORECASTING ──
        # We replace the recursive loop with a single 30-day forecast call
        # from our updated LSTM model, guaranteeing temporal variance.
        
        try:
            if registry.lstm is None:
                raise FileNotFoundError("LSTM model not loaded")
                
            X_seq, _, _, seq_products, seq_anchors = registry.lstm.build_sequences_inference(featured_df)
            if len(X_seq) == 0:
                raise ValueError("Not enough history for LSTM sequence")
                
            last_seq = X_seq[[-1]]
            
            # Stage 1: LSTM base forecast (30 days directly)
            point_prices, lower_prices, upper_prices = registry.lstm.predict_with_uncertainty(
                last_seq, current_prices=[current_price], n_samples=30
            )
            
            # Extract the single batch item
            points = point_prices[0]
            lowers = lower_prices[0]
            uppers = upper_prices[0]
            
            # Stage 2: LightGBM residual correction
            # Apply correction per step using the last known feature row
            residual_correction = np.zeros(30)
            try:
                if registry.lgbm is not None:
                    last_features = featured_df.iloc[[-1]][feature_cols].copy()
                    last_features["lstm_prediction"] = current_price  # Use current as anchor
                    residual_point = registry.lgbm.predict_residual(last_features)
                    # Apply the same correction to all steps (single-row estimate)
                    residual_correction = np.full(30, residual_point[0])
                    log.debug(f"Residual correction: {residual_point[0]:+.3f}")
            except (FileNotFoundError, Exception) as res_err:
                log.debug(f"No residual correction available: {res_err}")
            
            # Hybrid: LSTM base + LightGBM residual correction
            points = points + residual_correction
            lowers = lowers + residual_correction
            uppers = uppers + residual_correction
            
            # Slice to requested horizon
            points = points[:horizon_days]
            lowers = lowers[:horizon_days]
            uppers = uppers[:horizon_days]
            
            prev_price = current_price
            
            for day_offset in range(1, horizon_days + 1):
                future_date = last_date + timedelta(days=day_offset)
                
                raw_point = float(points[day_offset - 1])
                raw_lower = float(lowers[day_offset - 1])
                raw_upper = float(uppers[day_offset - 1])
                
                # Still apply safety rails to prevent absurd values
                final_point = _stabilize_prediction(
                    raw_point, prev_price, anchor_price,
                    trend_per_day, step=day_offset
                )
                
                predictions.append(PredictionPoint(
                    date=future_date.strftime("%Y-%m-%d"),
                    predicted_price=final_point,
                    lower_bound=round(raw_lower, 2),
                    upper_bound=round(raw_upper, 2),
                    confidence_level=0.8,
                ))
                prev_price = final_point

        except (FileNotFoundError, ValueError, Exception) as e:
            log.error(f"Direct multi-step failed: {e}")
            # Fallback: trend-based SMA
            valid_prices = history_df["price_index"]
            sma = float(valid_prices.tail(7).mean())
            std = float(valid_prices.tail(7).std())
            if pd.isna(std) or std == 0:
                std = sma * 0.05

            for day_offset in range(1, horizon_days + 1):
                future_date = last_date + timedelta(days=day_offset)
                fallback_price = round(sma + trend_per_day * day_offset * 0.3, 2)
                
                predictions.append(PredictionPoint(
                    date=future_date.strftime("%Y-%m-%d"),
                    predicted_price=fallback_price,
                    lower_bound=round(fallback_price - 1.28 * std, 2),
                    upper_bound=round(fallback_price + 1.28 * std, 2),
                    confidence_level=0.8,
                ))

        # ── Post-processing: detect and correct flat sequences ──
        # Check standard deviation of predictions to reject flatlines early
        if len(predictions) > 5:
            prices_tail = [p.predicted_price for p in predictions[5:]]
            tail_std = np.std(prices_tail)
            if tail_std < (current_price * 0.001):
                log.warning(f"Flatline detected (tail std: {tail_std:.4f})")
                
        predictions = _apply_flatness_correction(predictions, current_price, trend_per_day)

        # ── Validation warning ──
        if len(predictions) > 1:
            last_pred = predictions[-1].predicted_price
            total_change_pct = abs(last_pred - current_price) / current_price * 100
            if total_change_pct > 20:
                log.warning(
                    f"STABILITY WARNING: {request.product_name} total change "
                    f"{total_change_pct:.1f}% over {horizon_days} days."
                )

        # Get model version
        versions = store.list_versions()
        latest_version = versions[-1]["version"] if versions else None
        return PredictionResponse(
            product_name=request.product_name,
            horizon=request.horizon,
            current_price=current_price,
            predictions=predictions,
            model_version=latest_version,
        )

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Prediction error: {e}", exc_info=True)
        raise HTTPException(500, f"Prediction failed: {str(e)}")


@router.get("/products")
async def list_products():
    """List all available products for prediction."""
    try:
        fetcher = DataFetcher()
        df = fetcher.fetch_all()
        if df.empty:
            return {"products": []}

        products = (
            df.groupby(["product_name", "product_category"])
            .agg(
                latest_price=("price_index", "last"),
                data_points=("price_index", "count"),
            )
            .reset_index()
            .to_dict("records")
        )
        return {"products": products}
    except Exception as e:
        raise HTTPException(500, str(e))

