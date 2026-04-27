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
        """Extract data-driven factors from price history."""
        factors = []
        prices = df["price_index"].values
        current = prices[-1]

        # Short-term movement (5-day)
        if len(prices) >= 5:
            recent_change = (prices[-1] - prices[-5]) / prices[-5] * 100
            if abs(recent_change) > 1:
                direction = "increased" if recent_change > 0 else "decreased"
                factors.append(
                    f"Price has {direction} by {abs(recent_change):.1f}% over the past 5 days"
                )

        # Medium-term movement (30-day)
        if len(prices) >= 30:
            monthly_change = (prices[-1] - prices[-30]) / prices[-30] * 100
            if abs(monthly_change) > 3:
                direction = "risen" if monthly_change > 0 else "fallen"
                factors.append(
                    f"Monthly trend shows price has {direction} {abs(monthly_change):.1f}% over 30 days"
                )

        # Volatility
        if len(prices) >= 7:
            std_7d = np.std(prices[-7:])
            mean_7d = np.mean(prices[-7:])
            cv = std_7d / mean_7d if mean_7d > 0 else 0
            if cv > 0.05:
                factors.append(f"High price volatility detected ({cv:.1%} coefficient of variation)")
            elif cv < 0.01:
                factors.append("Low volatility in recent data suggests stable pricing")

        # Deviation from predicted
        if current > 0:
            pred_change = (predicted_price - current) / current * 100
            if abs(pred_change) > 1:
                direction = "increase" if pred_change > 0 else "decrease"
                factors.append(
                    f"Model predicts a {abs(pred_change):.1f}% {direction} from current price"
                )

        # Historical comparison
        if len(prices) >= 30:
            avg_30 = np.mean(prices[-30:])
            if current > avg_30 * 1.1:
                factors.append("Current price is above the 30-day average, suggesting elevated levels")
            elif current < avg_30 * 0.9:
                factors.append("Current price is below the 30-day average, suggesting a dip")

        # Seasonal context
        if "report_date" in df.columns:
            latest_date = df["report_date"].max()
            month = latest_date.month if hasattr(latest_date, "month") else None
            if month:
                if month in [6, 7, 8, 9, 10, 11]:
                    factors.append("Currently in wet season -- supply disruptions are more likely")
                if month in [11, 12]:
                    factors.append("Christmas season typically drives higher demand and prices")

        if not factors:
            factors.append("Price has been relatively stable in recent observations")

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

        # Trend description
        trend_map = {
            "increasing": "upward",
            "decreasing": "downward",
            "stable": "stable",
        }
        parts.append(f"Historical data shows a {trend_map.get(trend, 'mixed')} trend")

        # News alignment
        if news_factors:
            negative_news = sum(1 for f in news_factors if "price increase" in f.lower() or "negative" in f.lower())
            positive_news = sum(1 for f in news_factors if "price decrease" in f.lower() or "positive" in f.lower())

            if negative_news > positive_news:
                if trend == "increasing":
                    parts.append("reinforced by negative supply/price news")
                else:
                    parts.append("with some contradicting negative news signals")
            elif positive_news > negative_news:
                if trend == "decreasing":
                    parts.append("supported by positive supply news")
                else:
                    parts.append("with some positive news suggesting potential relief")
            else:
                parts.append("with mixed news signals")
        else:
            parts.append("with no significant recent news events")

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
