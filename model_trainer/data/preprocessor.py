"""
Data validation, cleaning, and preprocessing.
Handles missing values, outliers, type coercion, and sort ordering.
"""

import pandas as pd
import numpy as np
from typing import Tuple

from utils.logger import get_logger

log = get_logger(__name__)


class DataPreprocessor:
    """Clean and validate raw food_prices DataFrame."""

    REQUIRED_COLUMNS = [
        "product_name",
        "product_category",
        "price_index",
        "report_date",
    ]

    def validate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Run all validation / cleaning steps in sequence.
        Returns a clean DataFrame ready for feature engineering.
        """
        log.info(f"Preprocessing {len(df):,} rows ...")

        df = self._check_required_columns(df)
        df = self._coerce_types(df)
        df = self._drop_invalid_rows(df)
        df = self._handle_duplicates(df)
        df = self._sort_and_index(df)
        df = self._fill_missing(df)
        df = self._remove_outliers(df)

        log.info(f"Preprocessing complete -- {len(df):,} clean rows.")
        return df

    # ──────────────────────────────────────────────
    def _check_required_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        missing = [c for c in self.REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")
        return df

    def _coerce_types(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["report_date"] = pd.to_datetime(df["report_date"], errors="coerce")
        df["price_index"] = pd.to_numeric(df["price_index"], errors="coerce")

        # Fill nullable text columns
        for col in ["product_variant", "origin", "unit"]:
            if col in df.columns:
                df[col] = df[col].fillna("Unknown")

        return df

    def _drop_invalid_rows(self, df: pd.DataFrame) -> pd.DataFrame:
        before = len(df)
        df = df.dropna(subset=["report_date", "price_index", "product_name"])
        df = df[df["price_index"] > 0]
        dropped = before - len(df)
        if dropped:
            log.warning(f"Dropped {dropped} invalid rows (null/negative price).")
        return df

    def _handle_duplicates(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Ensure strict time series by aggregating to 1 row per product per date.
        If a product has multiple variants/origins on the same day, take the mean price.
        """
        before = len(df)
        
        # Define aggregation functions
        agg_funcs = {col: 'first' for col in df.columns if col not in ["product_name", "report_date", "price_index"]}
        agg_funcs["price_index"] = "mean"
        
        df = df.groupby(["product_name", "report_date"], as_index=False).agg(agg_funcs)
        
        dupes = before - len(df)
        if dupes > 0:
            log.info(f"Aggregated {dupes} rows with duplicate product+date combinations.")
        return df

    def _sort_and_index(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.sort_values(["product_name", "report_date"]).reset_index(drop=True)
        return df

    def _fill_missing(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Ensure consistent time intervals (no gaps).
        Reindex each product to a continuous daily frequency,
        interpolate missing values, and forward-fill.
        """
        df = df.set_index("report_date")
        
        resampled_groups = []
        for name, group in df.groupby("product_name"):
            idx = pd.date_range(start=group.index.min(), end=group.index.max(), freq='D')
            group = group.reindex(idx)
            group["product_name"] = name
            
            # Fill categorical/text columns with forward fill
            for col in group.columns:
                if col != "price_index" and group[col].dtype == 'object':
                    group[col] = group[col].ffill().bfill()
                    
            # Interpolate price, then ffill/bfill edges
            group["price_index"] = group["price_index"].interpolate(method='time').ffill().bfill()
            resampled_groups.append(group)

        df = pd.concat(resampled_groups)
        df = df.reset_index().rename(columns={"index": "report_date"})
        return df

    def _remove_outliers(self, df: pd.DataFrame, z_threshold: float = 4.0) -> pd.DataFrame:
        """
        Remove rows where the price_index is more than *z_threshold*
        standard deviations away from the product's mean.
        Uses a generous threshold (4 sigma) to keep genuine spikes.
        """
        before = len(df)

        # Compute per-product mean and std
        stats = df.groupby("product_name")["price_index"].agg(["mean", "std"])
        df = df.merge(stats, on="product_name", how="left", suffixes=("", "_stat"))

        # Compute z-scores
        df["_z"] = np.where(
            (df["std"] > 0) & df["std"].notna(),
            (df["price_index"] - df["mean"]).abs() / df["std"],
            0.0,
        )

        # Filter
        df = df[df["_z"] <= z_threshold].drop(columns=["mean", "std", "_z"])
        removed = before - len(df)
        if removed:
            log.info(f"Removed {removed} outlier rows (>{z_threshold}σ).")
        return df.reset_index(drop=True)

    # ──────────────────────────────────────────────
    # Utility: train/test split by date
    # ──────────────────────────────────────────────
    @staticmethod
    def time_split(
        df: pd.DataFrame, test_days: int = 30
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Split data chronologically: last *test_days* days → test,
        everything before → train.
        """
        cutoff = df["report_date"].max() - pd.Timedelta(days=test_days)
        train = df[df["report_date"] <= cutoff].copy()
        test = df[df["report_date"] > cutoff].copy()
        return train, test
