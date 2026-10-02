"""
Lag features & rolling window statistics.
Computed per product+variant group to avoid data leakage.
"""

import pandas as pd
import numpy as np
from typing import List

from config.settings import get_settings
from utils.logger import get_logger

log = get_logger(__name__)

# Must match the series key used in the preprocessor
from data.preprocessor import SERIES_KEY


def _group_col(df: pd.DataFrame) -> list:
    """Return the groupby columns that exist in the DataFrame."""
    return [c for c in SERIES_KEY if c in df.columns]


class LagFeatures:
    """
    Build lag and rolling-window features grouped by product_name + product_variant.
    All features use only past data (no future leakage).
    """

    def __init__(
        self,
        lag_days: List[int] | None = None,
        rolling_windows: List[int] | None = None,
    ):
        cfg = get_settings()
        self.lag_days = lag_days or cfg.lag_days
        self.rolling_windows = rolling_windows or cfg.rolling_windows

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add lag, rolling mean, rolling std, rolling min/max,
        and price momentum features.
        """
        df = df.copy()
        group_cols = _group_col(df)
        sort_cols = group_cols + ["report_date"]
        df = df.sort_values(sort_cols).reset_index(drop=True)
        grouped = df.groupby(group_cols)["price_index"]

        # ── Lag features ──
        for lag in self.lag_days:
            df[f"price_lag_{lag}d"] = grouped.shift(lag)

        # ── Rolling window features ──
        for win in self.rolling_windows:
            rolled = grouped.transform(
                lambda s: s.shift(1).rolling(window=win, min_periods=1).mean()
            )
            df[f"price_rolling_mean_{win}d"] = rolled

            rolled_std = grouped.transform(
                lambda s: s.shift(1).rolling(window=win, min_periods=1).std()
            )
            df[f"price_rolling_std_{win}d"] = rolled_std

            rolled_min = grouped.transform(
                lambda s: s.shift(1).rolling(window=win, min_periods=1).min()
            )
            df[f"price_rolling_min_{win}d"] = rolled_min

            rolled_max = grouped.transform(
                lambda s: s.shift(1).rolling(window=win, min_periods=1).max()
            )
            df[f"price_rolling_max_{win}d"] = rolled_max

        # ── Volatility (coefficient of variation over 14-day window) ──
        mean_14 = grouped.transform(
            lambda s: s.shift(1).rolling(window=14, min_periods=2).mean()
        )
        std_14 = grouped.transform(
            lambda s: s.shift(1).rolling(window=14, min_periods=2).std()
        )
        df["price_volatility_14d"] = np.where(
            mean_14 != 0, std_14 / mean_14, 0.0
        )

        # ── Momentum / rate of change (MUST use strictly past data!) ──
        # price_pct_change_1d: yesterday's return = (lag_1d - lag_2d) / lag_2d
        df["price_lag_2d"] = grouped.shift(2)
        df["price_pct_change_1d"] = np.where(
            (df["price_lag_2d"].notna()) & (df["price_lag_2d"] != 0),
            (df["price_lag_1d"] - df["price_lag_2d"]) / df["price_lag_2d"],
            0.0,
        )
        lag_3 = grouped.shift(3)
        previous_change = np.where(
            lag_3.notna() & (lag_3 != 0),
            (df["price_lag_2d"] - lag_3) / lag_3, 0.0)
        df["price_acceleration_1d"] = df["price_pct_change_1d"] - previous_change
        df["price_bollinger_position_14d"] = np.where(
            (std_14 > 0) & np.isfinite(std_14) & np.isfinite(mean_14)
            & np.isfinite(df["price_lag_1d"]),
            (df["price_lag_1d"] - mean_14) / (2 * std_14), 0.0)

        # price_pct_change_7d: past week's return = (lag_1d - lag_8d) / lag_8d
        df["price_lag_8d"] = grouped.shift(8)
        df["price_pct_change_7d"] = np.where(
            (df["price_lag_8d"].notna()) & (df["price_lag_8d"] != 0),
            (df["price_lag_1d"] - df["price_lag_8d"]) / df["price_lag_8d"],
            0.0,
        )

        # ── Expanding mean (long-term average up to current point) ──
        df["price_expanding_mean"] = grouped.transform(
            lambda s: s.shift(1).expanding(min_periods=1).mean()
        )

        # ── Price deviation from expanding mean ──
        df["price_deviation_from_mean"] = np.where(
            df["price_expanding_mean"] != 0,
            (df["price_lag_1d"] - df["price_expanding_mean"]) / df["price_expanding_mean"],
            0.0,
        )

        # ── Technical Indicators (RSI & MACD) ──
        # Relative Strength Index (RSI - 14 day)
        def _compute_rsi(s: pd.Series, window=14) -> pd.Series:
            delta = s.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=window, min_periods=1).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=window, min_periods=1).mean()
            rs = gain / (loss + 1e-6)
            return 100 - (100 / (1 + rs))
        
        df["price_rsi_14d"] = grouped.transform(lambda s: _compute_rsi(s.shift(1)))

        # MACD (Moving Average Convergence Divergence: 12-day EMA - 26-day EMA)
        def _compute_macd(s: pd.Series) -> pd.Series:
            ema12 = s.ewm(span=12, adjust=False, min_periods=1).mean()
            ema26 = s.ewm(span=26, adjust=False, min_periods=1).mean()
            macd = ema12 - ema26
            return macd

        df["price_macd"] = grouped.transform(lambda s: _compute_macd(s.shift(1)))
        
        # MACD Signal (9-day EMA of MACD)
        macd_grouped = df.groupby(group_cols)["price_macd"]
        df["price_macd_signal"] = macd_grouped.transform(
            lambda s: s.ewm(span=9, adjust=False, min_periods=1).mean()
        )

        n_features = (
            len(self.lag_days)
            + len(self.rolling_windows) * 4
            + 10  # indicators, including acceleration and Bollinger position
        )
        log.info(f"Added {n_features} lag / rolling features.")
        return df
