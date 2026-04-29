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
from utils.logger import get_logger

log = get_logger(__name__)
router = APIRouter(prefix="/comparisons", tags=["Comparisons"])


@router.post("/", response_model=ComparisonResponse)
async def compare(request: ComparisonRequest):
    """Compare prices for a product across different dimensions."""
    try:
        fetcher = DataFetcher()

        # For history comparisons, use the product's own history directly
        # (no preprocessor that would collapse variants/origins)
        history_df = fetcher.fetch_product_history(
            request.product_name, 
            product_variant=request.product_variant,
            origin=request.origin,
            product_category=request.product_category,
            limit=request.period_days
        )
        if history_df.empty:
            raise HTTPException(404, f"No data for '{request.product_name}'")

        # Light cleanup without collapsing variants
        history_df = _light_clean(history_df)
        
        # Isolate specific series
        if request.origin is None and "origin" in history_df.columns and history_df["origin"].nunique() > 1:
            last_origin = history_df.sort_values("report_date").iloc[-1]["origin"]
            history_df = history_df[history_df["origin"] == last_origin].copy()
            
        current_price = float(history_df["price_index"].iloc[-1])

        series = {}

        if request.compare_by == "history":
            series = _compare_history(history_df, request.period_days)

        elif request.compare_by == "origin":
            series = _compare_by_origin(fetcher, request)

        elif request.compare_by == "variant":
            series = _compare_by_variant(fetcher, request)

        else:
            raise HTTPException(400, f"Invalid compare_by: {request.compare_by}")

        return ComparisonResponse(
            product_name=request.product_name,
            product_variant=request.product_variant,
            origin=request.origin,
            product_category=request.product_category,
            compare_by=request.compare_by,
            current_price=current_price,
            series=series,
        )

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Comparison error: {e}", exc_info=True)
        raise HTTPException(500, f"Comparison failed: {str(e)}")


def _light_clean(df: pd.DataFrame) -> pd.DataFrame:
    """
    Minimal cleanup for comparison data — preserves variant/origin distinctions.
    Does NOT aggregate duplicates across variants like the full preprocessor does.
    """
    df = df.copy()
    df["report_date"] = pd.to_datetime(df["report_date"], errors="coerce")
    df["price_index"] = pd.to_numeric(df["price_index"], errors="coerce")
    df = df.dropna(subset=["report_date", "price_index", "product_name"])
    df = df[df["price_index"] > 0]

    for col in ["product_variant", "origin", "unit"]:
        if col in df.columns:
            df[col] = df[col].fillna("Unknown")

    df = df.sort_values("report_date").reset_index(drop=True)
    return df


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


def _compare_by_origin(fetcher, request) -> dict:
    """Compare prices across different origins (Local vs Imported)."""
    history = fetcher.fetch_product_history(
        request.product_name, 
        product_variant=request.product_variant, 
        origin=request.origin,
        product_category=request.product_category,
        limit=10
    )
    if history.empty:
        return {}

    category = history.iloc[0].get("product_category", "")
    all_df = fetcher.fetch_category_products(category)

    if all_df.empty:
        return {}

    # Light clean — preserve origin distinctions
    all_df = _light_clean(all_df)
    all_df = all_df[all_df["product_name"] == request.product_name]

    if "origin" not in all_df.columns:
        return {}

    series = {}
    for origin, group in all_df.groupby("origin"):
        if str(origin) == "Unknown":
            continue
        group = group.sort_values("report_date").tail(request.period_days)
        series[str(origin)] = [
            PricePoint(
                date=row["report_date"].strftime("%Y-%m-%d"),
                price=float(row["price_index"]),
                label=str(origin),
            )
            for _, row in group.iterrows()
        ]

    return series


def _compare_by_variant(fetcher, request) -> dict:
    """Compare prices across product variants within the same base product."""
    history = fetcher.fetch_product_history(
        request.product_name, 
        product_variant=request.product_variant, 
        origin=request.origin,
        product_category=request.product_category,
        limit=10
    )
    if history.empty:
        return {}

    category = history.iloc[0].get("product_category", "")
    all_df = fetcher.fetch_category_products(category)

    if all_df.empty:
        return {}

    # Light clean — preserve variant distinctions
    all_df = _light_clean(all_df)

    # Match products that share the FULL product name, not just the first word.
    # This prevents "Well Milled Rice" from matching "Well Water" etc.
    target_name = request.product_name.lower().strip()

    # Strategy: find products whose name contains the target, OR the target
    # contains them (handles both "Rice" matching "Well Milled Rice" and
    # "Well Milled Rice" matching "Rice, Well Milled").
    # But primarily we want same-name products with different variants.
    variants = all_df[
        all_df["product_name"].str.lower().str.strip() == target_name
    ]

    # If the product has no variant differentiation, broaden to similar names
    if len(variants["product_variant"].unique() if "product_variant" in variants.columns else []) <= 1:
        # Use the longest word (≥ 4 chars) from the product name for matching
        words = [w for w in target_name.split() if len(w) >= 4]
        if words:
            # Use the most specific (longest) word to reduce false matches
            match_word = max(words, key=len)
            variants = all_df[
                all_df["product_name"].str.lower().str.contains(match_word, na=False)
            ]

    series = {}
    if "product_variant" in variants.columns:
        # Group by product_name + variant for accurate comparison
        for (product, variant), group in variants.groupby(
            ["product_name", "product_variant"]
        ):
            group = group.sort_values("report_date").tail(request.period_days)
            label = str(product)
            if variant and str(variant) != "Unknown":
                label = f"{product} ({variant})"

            series[label] = [
                PricePoint(
                    date=row["report_date"].strftime("%Y-%m-%d"),
                    price=float(row["price_index"]),
                    label=label,
                )
                for _, row in group.iterrows()
            ]
    else:
        # No variant column — group by product name only
        for product, group in variants.groupby("product_name"):
            group = group.sort_values("report_date").tail(request.period_days)
            label = str(product)
            series[label] = [
                PricePoint(
                    date=row["report_date"].strftime("%Y-%m-%d"),
                    price=float(row["price_index"]),
                    label=label,
                )
                for _, row in group.iterrows()
            ]

    return series
