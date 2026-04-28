"""
Fetch food price data from Supabase.
Supports full fetch and incremental (since last date) fetch.
"""

import pandas as pd
from datetime import datetime, timedelta, timezone
from typing import Optional

from supabase import create_client, Client

from config.settings import get_settings
from utils.logger import get_logger

log = get_logger(__name__)


class DataFetcher:
    """Pulls food_prices rows from Supabase into a pandas DataFrame."""

    def __init__(self):
        cfg = get_settings()
        if not cfg.supabase_url or not cfg.supabase_key:
            raise ValueError(
                "SUPABASE_URL and SUPABASE_KEY environment variables are required."
            )
        self._client: Client = create_client(cfg.supabase_url, cfg.supabase_key)
        self._table = cfg.food_prices_table

    # ──────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────
    def fetch_all(self) -> pd.DataFrame:
        """Fetch the entire food_prices table."""
        log.info("Fetching ALL food price records ...")
        rows = self._paginated_fetch()
        df = pd.DataFrame(rows)
        log.info(f"Fetched {len(df):,} rows total.")
        return df

    def fetch_since(self, since_date: str) -> pd.DataFrame:
        """
        Fetch rows where report_date >= *since_date* (ISO format).
        Used for incremental training.
        """
        log.info(f"Fetching food prices since {since_date} ...")
        rows = self._paginated_fetch(since_date=since_date)
        df = pd.DataFrame(rows)
        log.info(f"Fetched {len(df):,} new rows since {since_date}.")
        return df

    def fetch_latest_date(self) -> Optional[str]:
        """Return the most recent report_date in the table."""
        resp = (
            self._client.table(self._table)
            .select("report_date")
            .order("report_date", desc=True)
            .limit(1)
            .execute()
        )
        if resp.data:
            return resp.data[0]["report_date"]
        return None

    def fetch_product_history(
        self, product_name: str, product_variant: Optional[str] = None, origin: Optional[str] = None, product_category: Optional[str] = None, limit: int = 365
    ) -> pd.DataFrame:
        """Fetch historical data for a specific product and variant."""
        query = self._client.table(self._table).select("*").eq("product_name", product_name)
        
        if product_variant:
            query = query.eq("product_variant", product_variant)
        else:
            query = query.is_("product_variant", "null")
            
        if origin:
            query = query.eq("origin", origin)
            
        if product_category:
            query = query.eq("product_category", product_category)
            
        resp = (
            query
            .order("report_date", desc=True)
            .limit(limit)
            .execute()
        )
        return pd.DataFrame(resp.data)

    def fetch_category_products(self, category: str) -> pd.DataFrame:
        """Fetch all products within a category."""
        resp = (
            self._client.table(self._table)
            .select("*")
            .eq("product_category", category)
            .order("report_date", desc=True)
            .execute()
        )
        return pd.DataFrame(resp.data)

    # ──────────────────────────────────────────────
    # Internals
    # ──────────────────────────────────────────────
    def _paginated_fetch(
        self, since_date: Optional[str] = None, page_size: int = 1000
    ) -> list:
        """
        Supabase caps responses at 1 000 rows by default.
        This paginates through the full table using offset-based pagination.
        """
        all_rows: list = []
        offset = 0

        while True:
            query = self._client.table(self._table).select("*")

            if since_date:
                query = query.gte("report_date", since_date)

            query = (
                query
                .order("report_date", desc=False)
                .range(offset, offset + page_size - 1)
            )

            resp = query.execute()
            batch = resp.data or []
            all_rows.extend(batch)

            if len(batch) < page_size:
                break
            offset += page_size

        return all_rows
