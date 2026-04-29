"""
Reasoning generator for price predictions.
Produces human-readable explanations combining data-driven and news-supported factors.
"""

import numpy as np
import pandas as pd
import json
from typing import Dict, List, Optional, Any
from datetime import timedelta

from data.news_fetcher import NewsFetcher
from utils.logger import get_logger

log = get_logger(__name__)


class ReasoningGenerator:
    """
    Generate structured, human-readable reasoning for price predictions.

    Combines:
    - Data-driven reasoning (from historical price patterns)
    - News-supported reasoning (from scraped articles)
    """

    def __init__(self):
        self._fetcher = NewsFetcher()

    def generate(
        self,
        product_name: str,
        history_df: pd.DataFrame,
        predicted_price: float,
        product_variant: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate full reasoning for a product prediction.

        Returns:
            {
                "trend": "increasing" | "decreasing" | "stable",
                "data_factors": [...],
                "news_factors": [...],
                "confidence_explanation": "...",
                "risk_factors": [...],
            }
        """
        if history_df.empty:
            return self._empty_reasoning()

        # Data-driven analysis
        trend = self._analyze_trend(history_df)
        data_factors = self._extract_data_factors(history_df, predicted_price)

        # News-driven analysis
        news_factors, risk_factors = self._extract_news_factors(product_name)

        # Confidence explanation
        confidence_explanation = self._build_confidence_explanation(
            trend, data_factors, news_factors
        )

        return {
            "trend": trend,
            "data_factors": data_factors,
            "news_factors": news_factors,
            "confidence_explanation": confidence_explanation,
            "risk_factors": risk_factors,
        }

    # ------------------------------------------------------------------
    # Data-driven reasoning
    # ------------------------------------------------------------------
    def _analyze_trend(self, df: pd.DataFrame) -> str:
        """Determine the overall price trend from recent data."""
        if len(df) < 3:
            return "stable"

        prices = df["price_index"].values
        recent_5 = prices[-5:] if len(prices) >= 5 else prices
        recent_mean = np.mean(recent_5)
        older_mean = np.mean(prices[:-5]) if len(prices) > 5 else recent_mean

        pct_change = (recent_mean - older_mean) / older_mean if older_mean > 0 else 0

        if pct_change > 0.02:
            return "increasing"
        elif pct_change < -0.02:
            return "decreasing"
        return "stable"

    def _extract_data_factors(
        self, df: pd.DataFrame, predicted_price: float
    ) -> List[str]:
        """Extract data-driven factors from price history with specific values."""
        factors = []
        prices = df["price_index"].values
        current = float(prices[-1])

        # Short-term movement (5-day) — include actual prices
        if len(prices) >= 5:
            price_5d_ago = float(prices[-5])
            recent_change = (current - price_5d_ago) / price_5d_ago * 100
            if abs(recent_change) > 1:
                direction = "increased" if recent_change > 0 else "decreased"
                factors.append(
                    f"Price has {direction} by {abs(recent_change):.1f}% over the past 5 days "
                    f"(₱{price_5d_ago:.2f} → ₱{current:.2f})"
                )

        # Medium-term movement (30-day)
        if len(prices) >= 30:
            price_30d_ago = float(prices[-30])
            monthly_change = (current - price_30d_ago) / price_30d_ago * 100
            if abs(monthly_change) > 3:
                direction = "risen" if monthly_change > 0 else "fallen"
                factors.append(
                    f"Monthly trend shows price has {direction} {abs(monthly_change):.1f}% over 30 days "
                    f"(₱{price_30d_ago:.2f} → ₱{current:.2f})"
                )

        # Volatility
        if len(prices) >= 7:
            std_7d = float(np.std(prices[-7:]))
            mean_7d = float(np.mean(prices[-7:]))
            cv = std_7d / mean_7d if mean_7d > 0 else 0
            if cv > 0.05:
                factors.append(
                    f"High price volatility detected — 7-day range: "
                    f"₱{float(np.min(prices[-7:])):.2f} to ₱{float(np.max(prices[-7:])):.2f} "
                    f"({cv:.1%} coefficient of variation)"
                )
            elif cv < 0.01:
                factors.append(
                    f"Low volatility — price has stayed near ₱{mean_7d:.2f} over the past week"
                )

        # Deviation from predicted — include actual values
        if current > 0 and predicted_price > 0:
            pred_change = (predicted_price - current) / current * 100
            if abs(pred_change) > 1:
                direction = "increase" if pred_change > 0 else "decrease"
                factors.append(
                    f"Model predicts a {abs(pred_change):.1f}% {direction} from current ₱{current:.2f} "
                    f"to approximately ₱{predicted_price:.2f}"
                )
            elif abs(pred_change) <= 1:
                factors.append(
                    f"Model predicts price will remain near current level (₱{current:.2f})"
                )

        # Historical comparison with values
        if len(prices) >= 30:
            avg_30 = float(np.mean(prices[-30:]))
            deviation_pct = (current - avg_30) / avg_30 * 100
            if current > avg_30 * 1.1:
                factors.append(
                    f"Current price (₱{current:.2f}) is {abs(deviation_pct):.1f}% above the "
                    f"30-day average of ₱{avg_30:.2f}, suggesting elevated levels"
                )
            elif current < avg_30 * 0.9:
                factors.append(
                    f"Current price (₱{current:.2f}) is {abs(deviation_pct):.1f}% below the "
                    f"30-day average of ₱{avg_30:.2f}, suggesting a dip"
                )

        # Seasonal context
        if "report_date" in df.columns:
            latest_date = df["report_date"].max()
            month = latest_date.month if hasattr(latest_date, "month") else None
            if month:
                if month in [6, 7, 8, 9, 10, 11]:
                    factors.append("Currently in wet season — supply disruptions are more likely")
                if month in [11, 12]:
                    factors.append("Christmas season typically drives higher demand and prices")

        if not factors:
            factors.append(f"Price has been relatively stable near ₱{current:.2f} in recent observations")

        return factors

    # ------------------------------------------------------------------
    # News-driven reasoning
    # ------------------------------------------------------------------
    def _extract_news_factors(self, product_name: str) -> tuple:
        """Extract news-driven factors and risk factors."""
        news_factors = []
        risk_factors = []

        try:
            articles = self._fetcher.fetch_articles_for_product(product_name, days=14)
            if articles.empty:
                return news_factors, risk_factors

            articles = self._fetcher.parse_event_fields(articles)

            for _, row in articles.head(5).iterrows():
                title = str(row.get("title", ""))
                sentiment = float(row.get("sentiment_score", 0))
                event_type = str(row.get("event_type", "general"))

                if not title or title == "nan":
                    continue

                # Build readable factor
                if sentiment < -0.3:
                    factor = f"Negative news: \"{title[:80]}\" (suggests possible price increase)"
                elif sentiment > 0.3:
                    factor = f"Positive news: \"{title[:80]}\" (suggests possible price decrease)"
                else:
                    factor = f"Recent report: \"{title[:80]}\""

                news_factors.append(factor)

                # Risk factors
                if event_type in ("supply_shock", "weather"):
                    risk_factors.append(f"Supply risk: {title[:60]}")
                elif event_type == "policy_change":
                    risk_factors.append(f"Policy change: {title[:60]}")

        except Exception as e:
            log.debug(f"News reasoning extraction failed: {e}")

        return news_factors, risk_factors

    # ------------------------------------------------------------------
    # Confidence explanation
    # ------------------------------------------------------------------
    def _build_confidence_explanation(
        self, trend: str, data_factors: List[str], news_factors: List[str]
    ) -> str:
        """Build a summary confidence explanation."""
        parts = []

        # Trend description with strength indicator
        trend_map = {
            "increasing": "upward",
            "decreasing": "downward",
            "stable": "stable",
        }
        trend_word = trend_map.get(trend, 'mixed')

        # Determine confidence level from factor count
        data_count = len(data_factors)
        if data_count >= 4:
            confidence = "strong"
        elif data_count >= 2:
            confidence = "moderate"
        else:
            confidence = "limited"

        parts.append(
            f"Prediction confidence is {confidence} — "
            f"historical data shows a {trend_word} trend"
        )

        # News alignment with specifics
        if news_factors:
            negative_news = sum(
                1 for f in news_factors
                if "price increase" in f.lower() or "negative" in f.lower()
            )
            positive_news = sum(
                1 for f in news_factors
                if "price decrease" in f.lower() or "positive" in f.lower()
            )
            total_news = len(news_factors)

            if negative_news > positive_news:
                if trend == "increasing":
                    parts.append(
                        f"reinforced by {negative_news} of {total_news} "
                        f"recent news articles signaling supply concerns"
                    )
                else:
                    parts.append(
                        f"with {negative_news} contradicting negative news signal(s) "
                        f"that may push prices up"
                    )
            elif positive_news > negative_news:
                if trend == "decreasing":
                    parts.append(
                        f"supported by {positive_news} of {total_news} "
                        f"positive supply/demand news articles"
                    )
                else:
                    parts.append(
                        f"with {positive_news} positive news signal(s) "
                        f"suggesting potential price relief"
                    )
            else:
                parts.append(f"with mixed signals from {total_news} recent news articles")
        else:
            parts.append("with no significant recent news events to validate or contradict")

        return ", ".join(parts) + "."

    # ------------------------------------------------------------------
    def _empty_reasoning(self) -> Dict[str, Any]:
        return {
            "trend": "unknown",
            "data_factors": ["Insufficient historical data for analysis"],
            "news_factors": [],
            "confidence_explanation": "Limited data available for confident prediction.",
            "risk_factors": [],
        }
