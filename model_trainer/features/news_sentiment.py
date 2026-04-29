"""
News sentiment feature engineering.
Converts news articles into numerical features that are time-aligned
with the price DataFrame for model training.

Features produced per product per date:
- news_sentiment_score      : weighted sum of impact x confidence
- news_event_count          : number of relevant events in window
- news_avg_confidence       : average confidence of relevant events
- news_positive_count       : events predicting price increase
- news_negative_count       : events predicting price decrease
- avg_sentiment_3d          : average sentiment over 3-day window
- avg_sentiment_7d          : average sentiment over 7-day window
- news_volume_3d            : article count in 3-day window
- news_volume_7d            : article count in 7-day window
- supply_shock_flag         : 1 if supply shock detected in window
- inflation_mentions        : count of inflation-related articles
"""

import pandas as pd
import numpy as np
import json
from typing import Dict, List

from data.news_fetcher import NewsFetcher
from utils.logger import get_logger

log = get_logger(__name__)

# Impact -> numeric score mapping
IMPACT_SCORES: Dict[str, float] = {
    "increase": 1.0,
    "decrease": -1.0,
    "uncertain": 0.0,
}


class NewsSentimentFeatures:
    """
    Build per-product, per-date sentiment features from news articles.
    Uses multiple time windows (3d, 7d, 14d) for robust signal extraction.
    """

    def __init__(self, lookback_days: int = 14):
        self._fetcher = NewsFetcher()
        self._lookback_days = lookback_days

    def build_features(self, price_df: pd.DataFrame) -> pd.DataFrame:
        """
        Fetch news articles, compute sentiment features, and merge
        them into the price DataFrame.
        """
        price_df = price_df.copy()

        # Get unique product names
        product_names = price_df["product_name"].unique().tolist()

        # Fetch relevant articles
        try:
            articles_df = self._fetcher.fetch_articles_for_products(product_names, days=90)
        except Exception as e:
            log.warning(f"Failed to fetch news articles: {e}. Using zero-filled features.")
            return self._add_zero_features(price_df)

        if articles_df.empty:
            log.info("No news articles found -- zero-filling sentiment features.")
            return self._add_zero_features(price_df)

        # Parse event fields (handles both new and legacy format)
        articles_df = self._fetcher.parse_event_fields(articles_df)

        # Compute per-product, per-date aggregates
        sentiment_rows = self._aggregate_sentiment(price_df, articles_df)
        sentiment_df = pd.DataFrame(sentiment_rows)

        if sentiment_df.empty:
            return self._add_zero_features(price_df)

        # Merge
        price_df = price_df.merge(
            sentiment_df,
            on=["product_name", "report_date"],
            how="left",
        )

        # Fill NaN (dates with no matching events)
        for col in self._feature_cols():
            if col in price_df.columns:
                price_df[col] = price_df[col].fillna(0.0)

        log.info(f"Added {len(self._feature_cols())} news sentiment features.")
        return price_df

    # ------------------------------------------------------------------
    def _aggregate_sentiment(
        self, price_df: pd.DataFrame, articles_df: pd.DataFrame
    ) -> List[dict]:
        """
        For each (product_name, report_date) pair, aggregate articles
        from multiple time windows into sentiment features.
        """
        rows = []

        # Parse article timestamps
        if "created_at" in articles_df.columns:
            articles_df = articles_df.copy()
            articles_df["article_date"] = pd.to_datetime(
                articles_df["created_at"], errors="coerce"
            ).dt.normalize()
        else:
            return rows

        for product in price_df["product_name"].unique():
            product_lower = product.lower()

            # Filter articles affecting this product
            def _product_match(prods):
                if isinstance(prods, str):
                    try:
                        prods = json.loads(prods)
                    except (json.JSONDecodeError, TypeError):
                        return False
                if not isinstance(prods, list):
                    return False
                return any(p.lower() == product_lower for p in prods)

            product_articles = articles_df[
                articles_df["affected_products"].apply(_product_match)
            ]

            if product_articles.empty:
                continue

            for date in price_df.loc[
                price_df["product_name"] == product, "report_date"
            ].unique():
                row = {"product_name": product, "report_date": date}

                # 3-day window
                w3 = product_articles[
                    (product_articles["article_date"] >= date - pd.Timedelta(days=3))
                    & (product_articles["article_date"] <= date)
                ]
                # 7-day window
                w7 = product_articles[
                    (product_articles["article_date"] >= date - pd.Timedelta(days=7))
                    & (product_articles["article_date"] <= date)
                ]
                # Full lookback window
                w_full = product_articles[
                    (product_articles["article_date"] >= date - pd.Timedelta(days=self._lookback_days))
                    & (product_articles["article_date"] <= date)
                ]

                if w_full.empty:
                    continue

                # Core sentiment features
                sentiments = w_full.get("sentiment_score", pd.Series(dtype=float)).fillna(0.0)
                impacts = w_full.get("event_impact", pd.Series(dtype=str)).map(IMPACT_SCORES).fillna(0.0)
                confidences = w_full.get("event_confidence", pd.Series(dtype=float)).fillna(0.0)

                row["news_sentiment_score"] = float((impacts * confidences).sum())
                row["news_event_count"] = len(w_full)
                row["news_avg_confidence"] = float(confidences.mean()) if len(confidences) > 0 else 0.0
                row["news_positive_count"] = int((w_full.get("event_impact", pd.Series()) == "increase").sum())
                row["news_negative_count"] = int((w_full.get("event_impact", pd.Series()) == "decrease").sum())

                # Windowed averages
                s3 = w3.get("sentiment_score", pd.Series(dtype=float)).fillna(0.0)
                s7 = w7.get("sentiment_score", pd.Series(dtype=float)).fillna(0.0)
                row["avg_sentiment_3d"] = float(s3.mean()) if len(s3) > 0 else 0.0
                row["avg_sentiment_7d"] = float(s7.mean()) if len(s7) > 0 else 0.0

                # Volume
                row["news_volume_3d"] = len(w3)
                row["news_volume_7d"] = len(w7)

                # Supply shock flag
                event_types = w_full.get("event_type", pd.Series(dtype=str))
                keywords_col = w_full.get("keywords", pd.Series(dtype=object))
                shock_keywords = ["shortage", "typhoon", "flood", "drought", "crop damage", "supply_shock"]

                shock_flag = 0
                if not event_types.empty:
                    shock_flag = int((event_types == "supply_shock").any() or (event_types == "weather").any())
                if shock_flag == 0 and not keywords_col.empty:
                    for kws in keywords_col:
                        if isinstance(kws, list):
                            if any(sk in kw.lower() for kw in kws for sk in shock_keywords):
                                shock_flag = 1
                                break
                        elif isinstance(kws, str):
                            try:
                                kw_list = json.loads(kws)
                                if any(sk in kw.lower() for kw in kw_list for sk in shock_keywords):
                                    shock_flag = 1
                                    break
                            except (json.JSONDecodeError, TypeError):
                                pass

                row["supply_shock_flag"] = shock_flag

                # Inflation mentions
                inflation_count = 0
                for kws in keywords_col:
                    if isinstance(kws, list):
                        inflation_count += sum(1 for kw in kws if "inflation" in kw.lower())
                    elif isinstance(kws, str):
                        try:
                            kw_list = json.loads(kws)
                            inflation_count += sum(1 for kw in kw_list if "inflation" in kw.lower())
                        except (json.JSONDecodeError, TypeError):
                            pass
                row["inflation_mentions"] = inflation_count

                rows.append(row)

        return rows

    # ------------------------------------------------------------------
    @staticmethod
    def _feature_cols() -> List[str]:
        return [
            "news_sentiment_score",
            "news_event_count",
            "news_avg_confidence",
            "news_positive_count",
            "news_negative_count",
            "avg_sentiment_3d",
            "avg_sentiment_7d",
            "news_volume_3d",
            "news_volume_7d",
            "supply_shock_flag",
            "inflation_mentions",
        ]

    @staticmethod
    def _add_zero_features(df: pd.DataFrame) -> pd.DataFrame:
        for col in NewsSentimentFeatures._feature_cols():
            df[col] = 0.0
        return df
