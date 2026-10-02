"""
Time-based feature engineering.
Extracts calendar, seasonality, and cyclical features from report_date.
"""

import pandas as pd
import numpy as np

from utils.logger import get_logger

log = get_logger(__name__)

# Fixed seasonal markers used by both batch and recursive feature generation.
_PH_HOLIDAY_DOYS = [pd.Timestamp(2001, m, d).dayofyear
                    for m, d in [(1, 1), (2, 25), (4, 9), (5, 1), (6, 12),
                                 (8, 21), (11, 1), (11, 30), (12, 25), (12, 30)]]


def holiday_proximity(day_of_year, month, day):
    proximity = False
    for holiday in _PH_HOLIDAY_DOYS:
        distance = abs(day_of_year - holiday)
        proximity = proximity | (np.minimum(distance, 365 - distance) <= 3)
    return proximity | ((month == 3) & (day >= 25)) | ((month == 4) & (day <= 5))


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
        day = df["day_of_month"]
        df["is_payday_window"] = (day.between(13, 17) | (day >= 28) | (day <= 2)).astype(int)
        df["is_holiday_proximity"] = holiday_proximity(
            df["day_of_year"], df["month"], day).astype(int)

        # Days since start of dataset (trend feature)
        min_date = pd.Timestamp('2000-01-01')
        df["days_since_start"] = (dt - min_date).dt.days

        log.info("Added 21 temporal features.")
        return df
