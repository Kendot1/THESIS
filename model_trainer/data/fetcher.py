"""
Fetch food price data from Supabase.
Supports full fetch and incremental (since last date) fetch.
"""

import pandas as pd
from datetime import date
from typing import Optional

from supabase import create_client, Client

from config.settings import get_settings
from utils.logger import get_logger

log = get_logger(__name__)

# Cursor, series identity, observed price, and report date. Keep the
# projection aligned with DataPreprocessor and TrainingPipeline._fingerprint.
PRICE_COLUMNS = (
    "id,product_category,product_name,product_variant,origin,unit,"
    "report_date,price_index,source_pdf"
)


def iso_report_date(value: str) -> str:
    """Accept only an unambiguous calendar date for database bounds."""
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError("Date bounds must use YYYY-MM-DD")
    return value


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
    def fetch_all(self, through_date: Optional[str] = None) -> pd.DataFrame:
        """Fetch prices, optionally bounded by an inclusive report date."""
        log.info("Fetching food prices through %s ...", through_date or "latest")
        rows = self._paginated_fetch(through_date=through_date)
        df = pd.DataFrame(rows)
        log.info(f"Fetched {len(df):,} rows total.")
        return df

    def fetch_since(self, since_date: str, through_date: Optional[str] = None) -> pd.DataFrame:
        """
        Fetch rows where report_date >= *since_date* (ISO format).
        An optional through_date bounds the inclusive end of the query.
        """
        log.info(f"Fetching food prices since {since_date} ...")
        rows = self._paginated_fetch(since_date=since_date, through_date=through_date)
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
        query = self._client.table(self._table).select(PRICE_COLUMNS).eq(
            "product_name", product_name)
        if product_variant:
            query = query.eq("product_variant", product_variant)
        else:
            query = query.is_("product_variant", "null")
        if origin:
            query = query.eq("origin", origin)
        if product_category:
            query = query.eq("product_category", product_category)
        response = query.order("report_date", desc=True).limit(limit).execute()
        return pd.DataFrame(response.data)

    def fetch_category_products(self, category: str) -> pd.DataFrame:
        """Fetch all products within a category."""
        response = (self._client.table(self._table)
                    .select(PRICE_COLUMNS)
                    .eq("product_category", category)
                    .order("report_date", desc=True)
                    .execute())
        return pd.DataFrame(response.data)

    # ──────────────────────────────────────────────
    # Internals
    # ──────────────────────────────────────────────
    def _paginated_fetch(
        self, since_date: Optional[str] = None, page_size: int = 1000,
        through_date: Optional[str] = None,
    ) -> list:
        """
        Supabase caps responses at 1 000 rows by default.
        This paginates with a stable (report_date, id) cursor so concurrent
        inserts cannot shift later pages and silently duplicate or skip rows.
        """
        if since_date is not None:
            since_date = iso_report_date(since_date)
        if through_date is not None:
            through_date = iso_report_date(through_date)
        if since_date and through_date and since_date > through_date:
            raise ValueError("since_date must not follow through_date")
        if type(page_size) is not int or not 1 <= page_size <= 1000:
            raise ValueError("page_size must be an integer between 1 and 1000")
        all_rows: list = []
        last_date = None
        last_id = None

        while True:
            query = self._client.table(self._table).select(PRICE_COLUMNS)

            if since_date:
                query = query.gte("report_date", since_date)

            if through_date:
                query = query.lte("report_date", through_date)

            if last_date is not None:
                query = query.or_(
                    f"report_date.gt.{last_date},"
                    f"and(report_date.eq.{last_date},id.gt.{last_id})"
                )

            query = (
                query
                .order("report_date", desc=False)
                .order("id", desc=False)
                .limit(page_size)
            )

            resp = query.execute()
            batch = resp.data or []
            all_rows.extend(batch)

            if len(batch) < page_size:
                break
            last_date = batch[-1]["report_date"]
            last_id = batch[-1]["id"]

        return all_rows
