"""
Price comparison API routes.
Compare current vs historical, across origins, and across variants.
"""

import pandas as pd
from fastapi import APIRouter, HTTPException

from api.schemas import (
    ComparisonRequest, ComparisonResponse, PricePoint,
)
from data.fetcher import DataFetcher
from data.preprocessor import DataPreprocessor
from utils.logger import get_logger

log = get_logger(__name__)
router = APIRouter(prefix="/comparisons", tags=["Comparisons"])


@router.post("/", response_model=ComparisonResponse)
async def compare(request: ComparisonRequest):
    """Compare prices for a product across different dimensions."""
    try:
        fetcher = DataFetcher()
        preprocessor = DataPreprocessor()

        history_df = fetcher.fetch_product_history(
            request.product_name, product_variant=request.product_variant, limit=request.period_days
        )
        if history_df.empty:
            raise HTTPException(404, f"No data for '{request.product_name}'")

        history_df = preprocessor.validate(history_df)
        current_price = float(history_df["price_index"].iloc[-1])

        series = {}

        if request.compare_by == "history":
            series = _compare_history(history_df, request.period_days)

        elif request.compare_by == "origin":
            series = _compare_by_origin(fetcher, preprocessor, request)

        elif request.compare_by == "variant":
            series = _compare_by_variant(fetcher, preprocessor, request)

        else:
            raise HTTPException(400, f"Invalid compare_by: {request.compare_by}")

        return ComparisonResponse(
            product_name=request.product_name,
            compare_by=request.compare_by,
            current_price=current_price,
            series=series,
        )

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Comparison error: {e}", exc_info=True)
        raise HTTPException(500, f"Comparison failed: {str(e)}")


def _compare_history(df: pd.DataFrame, period_days: int) -> dict:
    """Compare current period with the previous period."""
    if df.empty:
        return {}

    midpoint = df["report_date"].max() - pd.Timedelta(days=period_days // 2)

    recent = df[df["report_date"] > midpoint]
    older = df[df["report_date"] <= midpoint]

    series = {}
    if not recent.empty:
        series["Current Period"] = [
            PricePoint(
                date=row["report_date"].strftime("%Y-%m-%d"),
                price=float(row["price_index"]),
            )
            for _, row in recent.iterrows()
        ]

    if not older.empty:
        series["Previous Period"] = [
            PricePoint(
                date=row["report_date"].strftime("%Y-%m-%d"),
                price=float(row["price_index"]),
            )
            for _, row in older.iterrows()
        ]

    return series


def _compare_by_origin(fetcher, preprocessor, request) -> dict:
    """Compare prices across different origins (Local vs Imported)."""
    # Get the product's category
    history = fetcher.fetch_product_history(request.product_name, product_variant=request.product_variant, limit=10)
    if history.empty:
        return {}

    category = history.iloc[0].get("product_category", "")
    all_df = fetcher.fetch_category_products(category)

    if all_df.empty:
        return {}

    all_df = preprocessor.validate(all_df)
    all_df = all_df[all_df["product_name"] == request.product_name]

    series = {}
    for origin, group in all_df.groupby("origin"):
        group = group.tail(request.period_days)
        series[str(origin)] = [
            PricePoint(
                date=row["report_date"].strftime("%Y-%m-%d"),
                price=float(row["price_index"]),
                label=str(origin),
            )
            for _, row in group.iterrows()
        ]

    return series


def _compare_by_variant(fetcher, preprocessor, request) -> dict:
    """Compare prices across product variants within the same base product."""
    # Get all products in the same category
    history = fetcher.fetch_product_history(request.product_name, product_variant=request.product_variant, limit=10)
    if history.empty:
        return {}

    category = history.iloc[0].get("product_category", "")
    all_df = fetcher.fetch_category_products(category)

    if all_df.empty:
        return {}

    all_df = preprocessor.validate(all_df)

    # Find products with similar names (variant matching)
    base_name = request.product_name.split()[0].lower()
    variants = all_df[
        all_df["product_name"].str.lower().str.contains(base_name, na=False)
    ]

    series = {}
    for product, group in variants.groupby("product_name"):
        group = group.tail(request.period_days)
        label = str(product)
        variant = group.iloc[0].get("product_variant", "")
        if variant and variant != "Unknown":
            label = f"{product} ({variant})"

        series[label] = [
            PricePoint(
                date=row["report_date"].strftime("%Y-%m-%d"),
                price=float(row["price_index"]),
                label=label,
            )
            for _, row in group.iterrows()
        ]

    return series
