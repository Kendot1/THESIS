"""One versioned, explicit feature contract for fitting and forecasting."""
import numpy as np
import pandas as pd
from data.preprocessor import SERIES_KEY
from features.temporal import TemporalFeatures, holiday_proximity
from features.lag_features import LagFeatures
from features.categorical import CategoricalEncoder

FEATURE_VERSION = 3
CALENDAR = ['day_of_week','day_of_month','day_of_year','week_of_year','month','quarter',
    'year','is_weekend','is_month_start','is_month_end','month_sin','month_cos',
    'dow_sin','dow_cos','doy_sin','doy_cos','is_wet_season','is_christmas_season',
    'is_payday_window','is_holiday_proximity','days_since_start']
PRICE = [f'price_lag_{k}d' for k in [1,2,3,7,8,14,30]] + [
    f'price_rolling_{stat}_{k}d' for k in [3,7,14,30] for stat in ['mean','std','min','max']
] + ['price_volatility_14d','price_pct_change_1d','price_pct_change_7d',
     'price_expanding_mean','price_deviation_from_mean','price_rsi_14d','price_macd','price_macd_signal',
     'price_acceleration_1d','price_bollinger_position_14d']
FEATURE_COLUMNS = CALENDAR + PRICE + [f'{c}_encoded' for c in SERIES_KEY]
LEGACY_FEATURE_COLUMNS = [c for c in FEATURE_COLUMNS if c not in {
    'is_payday_window', 'is_holiday_proximity',
    'price_acceleration_1d', 'price_bollinger_position_14d',
}]


def assert_daily(df):
    if df.duplicated(SERIES_KEY + ['report_date']).any():
        raise ValueError('Duplicate series/date')
    delta = df.groupby(SERIES_KEY, sort=False).report_date.diff().dropna()
    if not delta.eq(pd.Timedelta(days=1)).all():
        raise ValueError('Features and sequences require ordered consecutive calendar dates')


class FeatureBuilder:
    def __init__(self, artifact_dir=None):
        self.encoder = CategoricalEncoder()
        if artifact_dir is not None:
            self.encoder._save_path = artifact_dir / 'categorical_mappings.json'
        self.temporal = TemporalFeatures()
        self.lags = LagFeatures(lag_days=[1,2,3,7,14,30], rolling_windows=[3,7,14,30])

    def fit(self, train):
        self.encoder.fit_transform(train[SERIES_KEY])
        return self

    def transform(self, df):
        df = df.sort_values(SERIES_KEY + ['report_date']).reset_index(drop=True)
        assert_daily(df)
        return self.encoder.transform(self.lags.transform(self.temporal.transform(df)))

    def load(self):
        self.encoder._load_mappings()
        return self


def usable_targets(df):
    return df.is_observed & np.isfinite(df.observed_price) & np.isfinite(df[FEATURE_COLUMNS]).all(axis=1)


class CausalFeatureState:
    """Incrementally reproduces the next-row feature contract for one series."""
    def __init__(self, history, encoder):
        history = history.sort_values('report_date')
        self.prices = list(history.price_index.astype(float))
        self.key = history.iloc[-1][SERIES_KEY].to_dict()
        self.encoder = encoder
        values = pd.Series(self.prices, dtype=float)
        self.ema12 = float(values.ewm(span=12, adjust=False, min_periods=1).mean().iloc[-1])
        self.ema26 = float(values.ewm(span=26, adjust=False, min_periods=1).mean().iloc[-1])
        macd = (values.ewm(span=12, adjust=False, min_periods=1).mean()
                - values.ewm(span=26, adjust=False, min_periods=1).mean())
        self.signal = float(macd.ewm(span=9, adjust=False, min_periods=1).mean().iloc[-1])

    @staticmethod
    def _finite_stat(values, operation):
        finite = np.asarray(values, dtype=float)
        finite = finite[np.isfinite(finite)]
        if not len(finite):
            return np.nan
        if operation == 'std':
            return float(np.std(finite, ddof=1)) if len(finite) > 1 else np.nan
        return float(getattr(np, operation)(finite))

    def row(self, date):
        date = pd.Timestamp(date)
        p = np.asarray(self.prices, dtype=float)
        result = dict(self.key)
        result['report_date'] = date
        result.update({
            'day_of_week': date.dayofweek, 'day_of_month': date.day,
            'day_of_year': date.dayofyear, 'week_of_year': date.isocalendar().week,
            'month': date.month, 'quarter': date.quarter, 'year': date.year,
            'is_weekend': int(date.dayofweek >= 5), 'is_month_start': int(date.is_month_start),
            'is_month_end': int(date.is_month_end),
            'month_sin': np.sin(2*np.pi*date.month/12),
            'month_cos': np.cos(2*np.pi*date.month/12),
            'dow_sin': np.sin(2*np.pi*date.dayofweek/7),
            'dow_cos': np.cos(2*np.pi*date.dayofweek/7),
            'doy_sin': np.sin(2*np.pi*date.dayofyear/365),
            'doy_cos': np.cos(2*np.pi*date.dayofyear/365),
            'is_wet_season': int(date.month in [6,7,8,9,10,11]),
            'is_christmas_season': int(date.month in [11,12]),
            'is_payday_window': int(date.day in range(13, 18) or date.day >= 28 or date.day <= 2),
            'is_holiday_proximity': int(holiday_proximity(date.dayofyear, date.month, date.day)),
            'days_since_start': (date-pd.Timestamp('2000-01-01')).days,
        })
        for lag in [1,2,3,7,8,14,30]:
            result[f'price_lag_{lag}d'] = p[-lag] if len(p) >= lag else np.nan
        for window in [3,7,14,30]:
            values = p[-window:]
            for stat in ['mean','std','min','max']:
                result[f'price_rolling_{stat}_{window}d'] = self._finite_stat(values, stat)
        mean14 = self._finite_stat(p[-14:], 'mean')
        std14 = self._finite_stat(p[-14:], 'std')
        result['price_volatility_14d'] = std14/mean14 if mean14 != 0 else 0
        result['price_pct_change_1d'] = ((p[-1]-p[-2])/p[-2]
            if len(p) >= 2 and np.isfinite(p[-2]) and p[-2] != 0 else 0)
        result['price_pct_change_7d'] = ((p[-1]-p[-8])/p[-8]
            if len(p) >= 8 and np.isfinite(p[-8]) and p[-8] != 0 else 0)
        result['price_expanding_mean'] = self._finite_stat(p, 'mean')
        result['price_deviation_from_mean'] = (
            (p[-1]-result['price_expanding_mean'])/result['price_expanding_mean']
            if result['price_expanding_mean'] != 0 else 0)
        changes = pd.Series(p).diff().tail(14)
        gain = changes.where(changes > 0, 0).mean()
        loss = (-changes.where(changes < 0, 0)).mean()
        result['price_rsi_14d'] = 100-(100/(1+gain/(loss+1e-6)))
        result['price_macd'] = self.ema12-self.ema26
        result['price_macd_signal'] = self.signal
        prev_pct = ((p[-2]-p[-3])/p[-3]
            if len(p) >= 3 and np.isfinite(p[-3]) and p[-3] != 0 else 0)
        result['price_acceleration_1d'] = result['price_pct_change_1d'] - prev_pct
        std14 = self._finite_stat(p[-14:], 'std')
        mean14 = self._finite_stat(p[-14:], 'mean')
        result['price_bollinger_position_14d'] = (
            float((p[-1] - mean14) / (2 * std14))
            if std14 and np.isfinite(std14) and std14 > 0
            and np.isfinite(mean14) and len(p) > 0 and np.isfinite(p[-1])
            else 0.0)
        for column, mapping in self.encoder._mappings.items():
            result[f'{column}_encoded'] = mapping.get(
                str(result[column]), max(mapping.values())+1 if mapping else 0)
        return pd.DataFrame([result])

    def append(self, price):
        price = float(price)
        self.prices.append(price)
        self.ema12 = (2/13)*price + (11/13)*self.ema12
        self.ema26 = (2/27)*price + (25/27)*self.ema26
        macd = self.ema12-self.ema26
        self.signal = (2/10)*macd + (8/10)*self.signal
