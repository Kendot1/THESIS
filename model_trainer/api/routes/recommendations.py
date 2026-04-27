"""
Recommendation API routes.
Suggests cheaper alternatives when a product's price is increasing.
"""

import pandas as pd
from fastapi import APIRouter, HTTPException

from api.schemas import (
    RecommendationRequest, RecommendationResponse, Alternative,
)
from data.fetcher import DataFetcher
from data.preprocessor import DataPreprocessor
from utils.logger import get_logger

log = get_logger(__name__)
router = APIRouter(prefix="/recommendations", tags=["Recommendations"])


@router.post("/", response_model=RecommendationResponse)
async def recommend(request: RecommendationRequest):
    """Suggest alternative products when prices are rising."""
    try:
        fetcher = DataFetcher()
        preprocessor = DataPreprocessor()

        # Get current product info
        history = fetcher.fetch_product_history(
            request.product_name, product_variant=request.product_variant, limit=30
        )
        if history.empty:
            raise HTTPException(404, f"No data for '{request.product_name}'")

        history = preprocessor.validate(history)
        current_price = float(history["price_index"].iloc[-1])
        category = history.iloc[-1].get("product_category", "Unknown")

        # Determine price trend
        if len(history) >= 7:
            week_ago_price = float(history["price_index"].iloc[-7])
        else:
            week_ago_price = current_price

        if current_price > week_ago_price * 1.02:
            direction = "increase"
        elif current_price < week_ago_price * 0.98:
            direction = "decrease"
        else:
            direction = "stable"

        # Find alternatives in the same category
        category_df = fetcher.fetch_category_products(category)

        if category_df.empty:
            return RecommendationResponse(
                original_product=request.product_name,
                original_price=current_price,
                predicted_direction=direction,
                alternatives=[],
            )

        category_df = preprocessor.validate(category_df)
        alternatives = _find_alternatives(
            category_df, request.product_name, current_price, direction,
        )

        return RecommendationResponse(
            original_product=request.product_name,
            original_price=current_price,
            predicted_direction=direction,
            alternatives=alternatives,
        )

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Recommendation error: {e}", exc_info=True)
        raise HTTPException(500, f"Recommendation failed: {str(e)}")


def _find_alternatives(
    category_df: pd.DataFrame,
    product_name: str,
    current_price: float,
    direction: str,
    max_alternatives: int = 5,
) -> list:
    """
    Find cheaper or more stable alternatives within the same category.
    """
    alternatives = []

    # Get latest price for each product in the category
    latest_prices = (
        category_df
        .sort_values("report_date")
        .groupby("product_name")
        .agg(
            latest_price=("price_index", "last"),
            avg_price=("price_index", "mean"),
            price_std=("price_index", "std"),
            data_points=("price_index", "count"),
            product_category=("product_category", "first"),
        )
        .reset_index()
    )

    # Exclude the original product
    latest_prices = latest_prices[
        latest_prices["product_name"] != product_name
    ]

    # Score alternatives: cheaper price + lower volatility = better
    latest_prices["price_diff"] = latest_prices["latest_price"] - current_price
    latest_prices["price_diff_pct"] = (
        latest_prices["price_diff"] / current_price * 100
    )

    # Filter: only suggest products that are cheaper or have falling prices
    if direction == "increase":
        # When price is increasing, suggest cheaper alternatives
        candidates = latest_prices[
            latest_prices["latest_price"] < current_price
        ].copy()
    else:
        # When price is stable/decreasing, suggest similar-priced alternatives
        candidates = latest_prices[
            latest_prices["latest_price"] <= current_price * 1.1
        ].copy()

    if candidates.empty:
        # Fallback: suggest the cheapest products in the category
        candidates = latest_prices.nsmallest(max_alternatives, "latest_price")

    # Sort by price (cheapest first)
    candidates = candidates.nsmallest(max_alternatives, "latest_price")

    for _, row in candidates.iterrows():
        diff = float(row["latest_price"] - current_price)
        diff_pct = float(row["price_diff_pct"])

        if diff < 0:
            reason = f"₱{abs(diff):.2f}/unit cheaper ({abs(diff_pct):.1f}% savings)"
        elif row.get("price_std", 0) < category_df["price_index"].std():
            reason = "More stable price history"
        else:
            reason = "Alternative in the same category"

        alternatives.append(Alternative(
            product_name=str(row["product_name"]),
            product_category=str(row["product_category"]),
            current_price=round(float(row["latest_price"]), 2),
            predicted_price=round(float(row["avg_price"]), 2),
            price_difference=round(diff, 2),
            price_difference_pct=round(diff_pct, 2),
            reason=reason,
        ))

    return alternatives
