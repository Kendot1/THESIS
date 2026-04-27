"""
Fetch news articles from the news_articles table.
Supports the new scraping pipeline and falls back to stored_events.
"""

import pandas as pd
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, List

from supabase import create_client, Client

from config.settings import get_settings
from utils.logger import get_logger

log = get_logger(__name__)


class NewsFetcher:
    """Pull news articles from Supabase for sentiment feature construction."""

    def __init__(self):
        cfg = get_settings()
        self._client: Client = create_client(cfg.supabase_url, cfg.supabase_key)
        self._news_table = "news_articles"
        self._events_table = cfg.news_events_table  # stored_events (legacy)

    # ------------------------------------------------------------------
    # Primary API (news_articles table)
    # ------------------------------------------------------------------
    def fetch_recent_articles(self, days: int = 30) -> pd.DataFrame:
        """Fetch articles from the last N days."""
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        try:
            resp = (
                self._client.table(self._news_table)
                .select("*")
                .gte("created_at", since)
                .order("created_at", desc=True)
                .execute()
            )
            df = pd.DataFrame(resp.data or [])
            log.info(f"Fetched {len(df)} news articles from last {days} days.")
            return df
        except Exception as e:
            log.warning(f"Failed to fetch from news_articles: {e}")
            return pd.DataFrame()

    def fetch_articles_for_products(self, product_names: List[str], days: int = 30) -> pd.DataFrame:
        """Fetch articles whose affected_products match the given product names."""
        all_articles = self.fetch_recent_articles(days=days)
        if all_articles.empty:
            return all_articles

        product_set = {p.lower() for p in product_names}

        def _matches(row) -> bool:
            products = row.get("affected_products", [])
            if isinstance(products, str):
                try:
                    products = json.loads(products)
                except (json.JSONDecodeError, TypeError):
                    return False
            if not isinstance(products, list):
                return False
            return any(p.lower() in product_set for p in products)

        mask = all_articles.apply(_matches, axis=1)
        return all_articles[mask].copy()

    def fetch_articles_for_product(self, product_name: str, days: int = 14) -> pd.DataFrame:
        """Fetch articles for a single product (used by reasoning)."""
        return self.fetch_articles_for_products([product_name], days=days)

    # ------------------------------------------------------------------
    # Legacy API (stored_events table -- for backward compatibility)
    # ------------------------------------------------------------------
    def fetch_all_events(self) -> pd.DataFrame:
        """Fetch all stored news events (legacy stored_events table)."""
        log.info("Fetching news events ...")

        # Try new table first, fall back to legacy
        articles = self.fetch_recent_articles(days=90)
        if not articles.empty:
            return articles

        try:
            resp = (
                self._client.table(self._events_table)
                .select("*")
                .order("created_at", desc=True)
                .execute()
            )
            df = pd.DataFrame(resp.data or [])
            log.info(f"Fetched {len(df)} news events (legacy).")
            return df
        except Exception as e:
            log.warning(f"Failed to fetch news events: {e}")
            return pd.DataFrame()

    def fetch_events_for_products(self, product_names: list) -> pd.DataFrame:
        """Fetch events matching products (tries new table, falls back to legacy)."""
        # Try new pipeline first
        articles = self.fetch_articles_for_products(product_names)
        if not articles.empty:
            return articles

        # Fall back to legacy stored_events
        all_events = pd.DataFrame()
        try:
            resp = (
                self._client.table(self._events_table)
                .select("*")
                .order("created_at", desc=True)
                .execute()
            )
            all_events = pd.DataFrame(resp.data or [])
        except Exception as e:
            log.warning(f"Legacy events fetch failed: {e}")
            return pd.DataFrame()

        if all_events.empty:
            return all_events

        product_set = {p.lower() for p in product_names}

        def _matches(row) -> bool:
            event = row.get("extracted_event")
            if isinstance(event, str):
                try:
                    event = json.loads(event)
                except (json.JSONDecodeError, TypeError):
                    return False
            if not isinstance(event, dict):
                return False
            affected = event.get("affected_products", [])
            return any(p.lower() in product_set for p in affected)

        mask = all_events.apply(_matches, axis=1)
        filtered = all_events[mask].copy()
        log.info(f"Found {len(filtered)} events matching requested products.")
        return filtered

    def parse_event_fields(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Flatten event data into separate columns.
        Works with both new (news_articles) and legacy (stored_events) format.
        """
        if df.empty:
            return df

        df = df.copy()

        # New format: fields are already top-level columns
        if "sentiment_score" in df.columns and "event_type" in df.columns:
            df["event_impact"] = df["sentiment_score"].apply(
                lambda s: "increase" if s < -0.2 else ("decrease" if s > 0.2 else "uncertain")
            )
            df["event_confidence"] = df["sentiment_score"].abs()
            df["event_reason"] = df.get("title", pd.Series([""] * len(df)))
            df["event_main"] = df.get("title", pd.Series([""] * len(df)))
            if "affected_products" not in df.columns:
                df["affected_products"] = [[] for _ in range(len(df))]
            return df

        # Legacy format: extract from JSONB field
        if "extracted_event" not in df.columns:
            return df

        def _extract(val):
            if isinstance(val, str):
                try:
                    return json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    return {}
            return val if isinstance(val, dict) else {}

        events = df["extracted_event"].apply(_extract)
        df["event_impact"] = events.apply(lambda e: e.get("impact", "uncertain"))
        df["event_confidence"] = events.apply(lambda e: float(e.get("confidence", 0.0)))
        df["event_reason"] = events.apply(lambda e: e.get("reason", ""))
        df["event_main"] = events.apply(lambda e: e.get("main_event", ""))
        df["affected_products"] = events.apply(lambda e: e.get("affected_products", []))

        return df
