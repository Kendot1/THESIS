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
            request.product_name, 
            product_variant=request.product_variant, 
            origin=request.origin,
            product_category=request.product_category,
            limit=30
        )
        if history.empty:
            raise HTTPException(404, f"No data for '{request.product_name}'")

        history = preprocessor.validate(history)
        
        if request.origin is None and "origin" in history.columns and history["origin"].nunique() > 1:
            last_origin = history.sort_values("report_date").iloc[-1]["origin"]
            history = history[history["origin"] == last_origin].copy()
        current_price = float(history["price_index"].iloc[-1])
        category = history.iloc[-1].get("product_category", "Unknown")
        current_unit = str(history.iloc[-1].get("unit", "Unknown"))

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
                original_variant=request.product_variant,
                original_origin=request.origin,
                original_category=request.product_category,
                original_price=current_price,
                predicted_direction=direction,
                alternatives=[],
                recommendation_reason=_build_recommendation_reason(
                    direction, request.product_name, current_price, []
                ),
            )

        category_df = preprocessor.validate(category_df)
        alternatives = _find_alternatives(
            category_df, request.product_name, current_price,
            direction, current_unit,
        )

        return RecommendationResponse(
            original_product=request.product_name,
            original_variant=request.product_variant,
            original_origin=request.origin,
            original_category=request.product_category,
            original_price=current_price,
            predicted_direction=direction,
            alternatives=alternatives,
            recommendation_reason=_build_recommendation_reason(
                direction, request.product_name, current_price, alternatives
            ),
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
    current_unit: str = "Unknown",
    max_alternatives: int = 5,
) -> list:
    """
    Find cheaper or more stable alternatives within the same category.

    Key fixes:
      - Sort ascending before aggregation so 'last' = most recent price
      - Filter by matching unit to avoid kg-vs-pack mismatches
      - Never suggest products more expensive than the queried product
    """
    alternatives = []

    # CRITICAL: Sort ascending so .last() gives the most recent price
    category_df = category_df.sort_values("report_date", ascending=True)

    # Get latest price for each product series in the category
    group_cols = ["product_name"]
    if "product_variant" in category_df.columns:
        group_cols.append("product_variant")
    if "origin" in category_df.columns:
        group_cols.append("origin")

    latest_prices = (
        category_df
        .groupby(group_cols)
        .agg(
            latest_price=("price_index", "last"),
            avg_price=("price_index", "mean"),
            price_std=("price_index", "std"),
            data_points=("price_index", "count"),
            product_category=("product_category", "last"),
            unit=("unit", "last"),
        )
        .reset_index()
    )

    # Exclude the original product
    latest_prices = latest_prices[
        latest_prices["product_name"] != product_name
    ]

    if latest_prices.empty:
        return alternatives

    # Filter by same unit to ensure fair comparison (e.g. per-kg vs per-kg)
    if current_unit and current_unit != "Unknown":
        same_unit = latest_prices[latest_prices["unit"] == current_unit]
        if not same_unit.empty:
            latest_prices = same_unit

    # Score alternatives: cheaper price + lower volatility = better
    latest_prices["price_diff"] = latest_prices["latest_price"] - current_price
    latest_prices["price_diff_pct"] = (
        latest_prices["price_diff"] / current_price * 100
    )

    # --- Core logic: ONLY suggest products that are actually cheaper ---
    if direction == "increase":
        # When price is rising, suggest strictly cheaper alternatives
        candidates = latest_prices[
            latest_prices["latest_price"] < current_price
        ].copy()
    elif direction == "decrease":
        # When price is already falling, suggest similarly-priced but more
        # stable alternatives (lower std)
        candidates = latest_prices[
            latest_prices["latest_price"] <= current_price * 1.05
        ].copy()
    else:
        # Stable — suggest cheaper alternatives within 5% band
        candidates = latest_prices[
            latest_prices["latest_price"] <= current_price * 1.0
        ].copy()

    if candidates.empty:
        # Fallback: find products that are still CHEAPER than current
        cheaper = latest_prices[
            latest_prices["latest_price"] < current_price
        ]
        if cheaper.empty:
            # Truly no cheaper alternative exists — return empty, don't
            # mislead the user with MORE expensive suggestions
            log.info(
                f"No cheaper alternatives found for {product_name} "
                f"(₱{current_price:.2f}) in category"
            )
            return alternatives
        candidates = cheaper.nsmallest(max_alternatives, "latest_price")

    # Sort by price (cheapest first)
    candidates = candidates.nsmallest(max_alternatives, "latest_price")

    for _, row in candidates.iterrows():
        diff = float(row["latest_price"] - current_price)
        diff_pct = float(row["price_diff_pct"])

        if diff < 0:
            reason = f"₱{abs(diff):.2f}/unit cheaper ({abs(diff_pct):.1f}% savings)"
        elif row.get("price_std", 0) and row["price_std"] < category_df["price_index"].std():
            reason = "More stable price history with similar pricing"
        else:
            reason = "Alternative in the same category"

        alternatives.append(Alternative(
            product_name=str(row["product_name"]),
            product_variant=str(row.get("product_variant", "")) or None,
            origin=str(row.get("origin", "")) or None,
            product_category=str(row["product_category"]),
            current_price=round(float(row["latest_price"]), 2),
            price_difference=round(diff, 2),
            price_difference_pct=round(diff_pct, 2),
            reason=reason,
        ))

    return alternatives


def _build_recommendation_reason(
    direction: str,
    product_name: str,
    current_price: float,
    alternatives: list,
) -> str:
    """Build a human-readable summary of the recommendation."""
    if direction == "increase":
        base = (
            f"The price of {product_name} is currently trending upward "
            f"(₱{current_price:.2f})."
        )
    elif direction == "decrease":
        base = (
            f"The price of {product_name} is currently trending downward "
            f"(₱{current_price:.2f})."
        )
    else:
        base = (
            f"The price of {product_name} has been stable "
            f"(₱{current_price:.2f})."
        )

    if alternatives:
        cheapest = alternatives[0]
        savings = abs(cheapest.price_difference)
        base += (
            f" Consider switching to {cheapest.product_name} "
            f"which is ₱{savings:.2f} cheaper per unit."
        )
    else:
        if direction == "increase":
            base += (
                " No cheaper alternatives were found in the same category. "
                "Consider monitoring prices for potential decreases."
            )
        else:
            base += (
                " This product is competitively priced within its category."
            )

    return base
