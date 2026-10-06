"""Experimental causal features for irregularly observed daily price panels.

Not part of the production feature contract. Compute a regression slope in
calendar days from actual observations; never count forward-filled input prices
as fresh evidence. All rolling windows end on the day before the feature row.
"""
import numpy as np
import pandas as pd

from data.preprocessor import SERIES_KEY
from features.builder import assert_daily

OBSERVATION_FEATURES = ["observed_count_7d", "observed_count_30d", "last_observed_age_days",
                        "observed_slope_7d", "observed_slope_14d"]


def _observed_slope(values):
    valid = np.isfinite(values)
    if valid.sum() < 2:
        return np.nan
    x = np.arange(len(values), dtype=float)[valid]
    y = values[valid]
    centered = x - x.mean()
    return float(np.dot(centered, y - y.mean()) / np.dot(centered, centered))


def observation_history_features(frame):
    frame = frame.sort_values(SERIES_KEY + ["report_date"]).reset_index(drop=True).copy()
    assert_daily(frame)
    blocks = []
    for _, block in frame.groupby(SERIES_KEY, sort=False):
        observed = block.observed_price.where(block.is_observed).astype(float)
        past = observed.shift(1)
        result = block[SERIES_KEY + ["report_date"]].copy()
        for window in [7, 30]:
            result[f"observed_count_{window}d"] = past.notna().rolling(window, min_periods=1).sum()
        seen = block.report_date.where(observed.notna()).shift(1).ffill()
        result["last_observed_age_days"] = (block.report_date - seen).dt.days.astype(float)
        for window in [7, 14]:
            result[f"observed_slope_{window}d"] = past.rolling(window, min_periods=2).apply(
                _observed_slope, raw=True)
        blocks.append(result)
    if not blocks:
        return pd.DataFrame(columns=SERIES_KEY + ["report_date"] + OBSERVATION_FEATURES)
    return pd.concat(blocks, ignore_index=True)
