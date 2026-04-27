"""
Time-based feature engineering.
Extracts calendar, seasonality, and cyclical features from report_date.
"""

import pandas as pd
import numpy as np

from utils.logger import get_logger

log = get_logger(__name__)


class TemporalFeatures:
    """Extract temporal features from the report_date column."""

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add temporal columns to the DataFrame.
        Expects a 'report_date' column of datetime type.
        """
        df = df.copy()
        dt = df["report_date"]

        # ── Calendar features ──
        df["day_of_week"] = dt.dt.dayofweek          # 0=Mon ... 6=Sun
        df["day_of_month"] = dt.dt.day
        df["day_of_year"] = dt.dt.dayofyear
        df["week_of_year"] = dt.dt.isocalendar().week.astype(int)
        df["month"] = dt.dt.month
        df["quarter"] = dt.dt.quarter
        df["year"] = dt.dt.year
        df["is_weekend"] = (dt.dt.dayofweek >= 5).astype(int)

        # ── Month boundaries (price reports often cluster here) ──
        df["is_month_start"] = dt.dt.is_month_start.astype(int)
        df["is_month_end"] = dt.dt.is_month_end.astype(int)

        # ── Cyclical encoding (sine / cosine) ──
        # This helps models understand that Dec 31 ≈ Jan 1
        df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
        df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)
        df["dow_sin"] = np.sin(2 * np.pi * df["day_of_week"] / 7)
        df["dow_cos"] = np.cos(2 * np.pi * df["day_of_week"] / 7)
        df["doy_sin"] = np.sin(2 * np.pi * df["day_of_year"] / 365)
        df["doy_cos"] = np.cos(2 * np.pi * df["day_of_year"] / 365)

        # ── Philippine seasonal context ──
        # Wet season: Jun–Nov, Dry season: Dec–May
        df["is_wet_season"] = df["month"].isin([6, 7, 8, 9, 10, 11]).astype(int)

        # Holiday proximity (Christmas season affects food prices in PH)
        df["is_christmas_season"] = df["month"].isin([11, 12]).astype(int)

        # Days since start of dataset (trend feature)
        min_date = dt.min()
        df["days_since_start"] = (dt - min_date).dt.days

        log.info(f"Added {15} temporal features.")
        return df
