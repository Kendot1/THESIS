"""
Explainability API routes.
Provides reasoning for price predictions using feature importance and news evidence.
"""

import numpy as np
from fastapi import APIRouter, HTTPException

from api.schemas import (
    ExplanationRequest, ExplanationResponse,
    FeatureContribution, NewsEvidence,
)
from data.fetcher import DataFetcher
from pipeline.reasoning import ReasoningGenerator
from utils.logger import get_logger

log = get_logger(__name__)
router = APIRouter(prefix="/explanations", tags=["Explanations"])

# Human-readable feature descriptions
FEATURE_DESCRIPTIONS = {
    "price_lag_1d": "Yesterday's price",
    "price_lag_3d": "Price 3 days ago",
    "price_lag_7d": "Price 1 week ago",
    "price_lag_14d": "Price 2 weeks ago",
    "price_lag_30d": "Price 1 month ago",
    "price_rolling_mean_7d": "7-day average price",
    "price_rolling_mean_14d": "14-day average price",
    "price_rolling_mean_30d": "30-day average price",
    "price_rolling_std_7d": "7-day price volatility",
    "price_rolling_std_14d": "14-day price volatility",
    "price_volatility_14d": "Price volatility coefficient",
    "price_pct_change_1d": "Daily price change rate",
    "price_pct_change_7d": "Weekly price change rate",
    "price_expanding_mean": "Long-term average price",
    "price_deviation_from_mean": "Deviation from long-term average",
    "price_rsi_14d": "Market momentum (RSI)",
    "price_macd": "Trend direction (MACD)",
    "price_macd_signal": "Trend momentum shift",
    "month": "Month of year",
    "month_sin": "Seasonal cycle (sine)",
    "month_cos": "Seasonal cycle (cosine)",
    "day_of_week": "Day of the week",
    "is_wet_season": "Wet season indicator (Jun-Nov)",
    "is_christmas_season": "Christmas season indicator (Nov-Dec)",
    "days_since_start": "Long-term trend indicator",
    "news_sentiment_score": "News sentiment impact score",
    "news_event_count": "Number of recent news events",
    "news_avg_confidence": "Average news confidence level",
    "news_positive_count": "Positive news events count",
    "news_negative_count": "Negative news events count",
    "avg_sentiment_3d": "3-day news sentiment average",
    "avg_sentiment_7d": "7-day news sentiment average",
    "news_volume_3d": "3-day news article volume",
    "news_volume_7d": "7-day news article volume",
    "supply_shock_flag": "Supply shock detected in news",
    "inflation_mentions": "Inflation mentions in news",
    "product_category_encoded": "Product category",
    "product_name_encoded": "Specific product",
    "origin_encoded": "Product origin (local/imported)",
}


@router.post("/", response_model=ExplanationResponse)
async def explain(request: ExplanationRequest):
    """Explain why a price is predicted to change."""
    try:
        fetcher = DataFetcher()
        reasoner = ReasoningGenerator()

        # Get product data
        history_df = fetcher.fetch_product_history(
            request.product_name, product_variant=request.product_variant, limit=60
        )
        if history_df.empty:
            raise HTTPException(404, f"No data for '{request.product_name}'")

        # In the separate reasoning pipeline, we need the predicted price to compare against.
        # Ideally, the user passes this, but for now we fetch a fresh prediction.
        from api.routes.predictions import predict
        from api.schemas import PredictionRequest
        
        predicted_price = 0.0
        try:
            pred_resp = await predict(PredictionRequest(
                product_name=request.product_name,
                product_variant=request.product_variant,
                horizon="daily"
            ))
            if pred_resp.predictions:
                predicted_price = pred_resp.predictions[0].predicted_price
        except Exception as e:
            log.warning(f"Could not fetch prediction for reasoning: {e}")
            if "price_index" in history_df.columns:
                predicted_price = float(history_df.iloc[-1]["price_index"])

        reasoning_data = reasoner.generate(
            product_name=request.product_name,
            history_df=history_df,
            predicted_price=predicted_price,
            product_variant=request.product_variant,
        )

        return ExplanationResponse(reasoning=reasoning_data)

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Explanation error: {e}", exc_info=True)
        raise HTTPException(500, f"Explanation failed: {str(e)}")
