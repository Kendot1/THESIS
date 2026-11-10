"""One versioned, explicit feature contract for fitting and forecasting."""
import bisect
import numpy as np
import pandas as pd
from data.preprocessor import SERIES_KEY
from features.temporal import TemporalFeatures, holiday_proximity, moving_easter_features
from features.lag_features import LagFeatures
from features.categorical import CategoricalEncoder

FEATURE_VERSION = 4
CALENDAR = ['day_of_week','day_of_month','day_of_year','week_of_year','month','quarter',
    'year','is_weekend','is_month_start','is_month_end','month_sin','month_cos',
    'dow_sin','dow_cos','doy_sin','doy_cos','is_wet_season','is_christmas_season',
    'is_payday_window','is_holiday_proximity','days_since_start']
PRICE = [f'price_lag_{k}d' for k in [1,2,3,7,8,14,30]] + [
    f'price_rolling_{stat}_{k}d' for k in [3,7,14,30] for stat in ['mean','std','min','max']
] + ['price_volatility_14d','price_pct_change_1d','price_pct_change_7d',
     'price_expanding_mean','price_deviation_from_mean','price_rsi_14d','price_macd','price_macd_signal',
     'price_acceleration_1d','price_bollinger_position_14d']
SERIES_FEATURES = [f'{c}_encoded' for c in SERIES_KEY]
PRODUCT_GROUP_KEY = SERIES_KEY[:3]
FEATURE_COLUMNS_V3 = CALENDAR + PRICE + SERIES_FEATURES
MARKET_FEATURES = ['category_return_lag_1d', 'category_return_mean_7d',
    'category_return_std_7d']
FEATURE_COLUMNS_V4 = CALENDAR + PRICE + MARKET_FEATURES + SERIES_FEATURES
ANNUAL_FEATURES = ['annual_price_relative', 'annual_observation_age_days']
FEATURE_COLUMNS_V5 = FEATURE_COLUMNS_V4 + ANNUAL_FEATURES
LONG_MEMORY_FEATURES = ['price_pct_change_30d', 'price_pct_change_60d',
    'price_pct_change_90d', 'price_volatility_60d',
    'price_deviation_from_rolling_mean_60d']
FEATURE_COLUMNS_V6 = FEATURE_COLUMNS_V4 + LONG_MEMORY_FEATURES
FEATURE_COLUMNS_V7 = FEATURE_COLUMNS_V4 + ANNUAL_FEATURES + LONG_MEMORY_FEATURES
OBSERVATION_AGE_FEATURES = ['days_since_observation']
FEATURE_COLUMNS_V8 = FEATURE_COLUMNS_V6 + OBSERVATION_AGE_FEATURES
PRODUCT_RETURN_FEATURES = ['product_return_lag_1d', 'product_return_mean_7d',
    'product_return_std_7d']
FEATURE_COLUMNS_V9 = FEATURE_COLUMNS_V6 + PRODUCT_RETURN_FEATURES
PEER_PRODUCT_KEY = [SERIES_KEY[0], SERIES_KEY[1], SERIES_KEY[2], SERIES_KEY[4]]
CATEGORY_PEER_RETURN_FEATURES = [
    'category_peer_return_lag_1d', 'category_peer_return_mean_7d',
    'category_peer_return_std_7d', 'category_peer_return_mean_30d',
    'category_peer_return_std_30d', 'category_peer_return_count_log',
]
FEATURE_COLUMNS_V10 = FEATURE_COLUMNS_V6 + CATEGORY_PEER_RETURN_FEATURES
MOVING_EASTER_FEATURES = ['easter_offset_days', 'is_holy_week']
FEATURE_COLUMNS_V11 = FEATURE_COLUMNS_V6 + MOVING_EASTER_FEATURES
PRODUCT_VARIANT_KEY = [SERIES_KEY[0], SERIES_KEY[1], SERIES_KEY[4], SERIES_KEY[2]]
CROSS_VARIANT_RETURN_FEATURES = [
    'cross_variant_return_lag_1d', 'cross_variant_return_mean_7d',
    'cross_variant_return_std_7d', 'cross_variant_return_count_log',
]
FEATURE_COLUMNS_V12 = FEATURE_COLUMNS_V6 + CROSS_VARIANT_RETURN_FEATURES
FEATURE_COLUMNS_V13 = (FEATURE_COLUMNS_V6 + CATEGORY_PEER_RETURN_FEATURES
                       + CROSS_VARIANT_RETURN_FEATURES)
FEATURE_COLUMNS = FEATURE_COLUMNS_V4
LEGACY_FEATURE_COLUMNS = [c for c in FEATURE_COLUMNS_V3 if c not in {
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
    def __init__(self, artifact_dir=None, feature_version=None):
        self.artifact_dir = artifact_dir
        self.feature_version = int(feature_version or FEATURE_VERSION)
        self.encoder = CategoricalEncoder()
        if artifact_dir is not None:
            self.encoder._save_path = artifact_dir / 'categorical_mappings.json'
        self.temporal = TemporalFeatures()
        lag_days = [1,2,3,7,14,30]
        rolling_windows = [3,7,14,30]
        if self.feature_version in {6, 7, 8, 9, 10, 11, 12, 13}:
            lag_days.extend([31,61,91])
            rolling_windows.append(60)
        self.lags = LagFeatures(lag_days=lag_days, rolling_windows=rolling_windows)

    def fit(self, train):
        self.encoder.fit_transform(train[SERIES_KEY])
        return self

    def transform(self, df):
        df = df.sort_values(SERIES_KEY + ['report_date']).reset_index(drop=True)
        assert_daily(df)
        featured = self.encoder.transform(self.lags.transform(self.temporal.transform(df)))
        featured = self.add_category_return_features(featured)
        if self.feature_version in {5, 7}:
            featured = self.add_annual_analogue_features(featured)
        if self.feature_version == 8:
            featured = self.add_observation_age_feature(featured)
        if self.feature_version == 9:
            featured = self.add_product_return_features(featured)
        if self.feature_version == 10:
            featured = self.add_category_peer_return_features(featured)
        if self.feature_version == 12:
            featured = self.add_cross_variant_return_features(featured)
        if self.feature_version == 13:
            featured = self.add_category_peer_return_features(featured)
            featured = self.add_cross_variant_return_features(featured)
        return featured

    @property
    def feature_columns(self):
        return {
            2: LEGACY_FEATURE_COLUMNS, 3: FEATURE_COLUMNS_V3,
            4: FEATURE_COLUMNS_V4, 5: FEATURE_COLUMNS_V5,
            6: FEATURE_COLUMNS_V6, 7: FEATURE_COLUMNS_V7,
            8: FEATURE_COLUMNS_V8, 9: FEATURE_COLUMNS_V9,
            10: FEATURE_COLUMNS_V10, 11: FEATURE_COLUMNS_V11,
            12: FEATURE_COLUMNS_V12, 13: FEATURE_COLUMNS_V13,
        }[self.feature_version]

    @staticmethod
    def add_observation_age_feature(featured):
        """Measure days since the last prior observed source price, without target leakage."""
        result = featured.copy()
        observed = (result.get('is_observed', pd.Series(False, index=result.index))
                    .fillna(False).astype(bool)
                    & np.isfinite(pd.to_numeric(
                        result.get('observed_price', pd.Series(np.nan, index=result.index)),
                        errors='coerce')))
        last_observed = pd.to_datetime(result.report_date).where(observed)
        last_observed = last_observed.groupby(
            [result[column] for column in SERIES_KEY], sort=False).ffill()
        prior_observed = last_observed.groupby(
            [result[column] for column in SERIES_KEY], sort=False).shift(1)
        age = (pd.to_datetime(result.report_date) - prior_observed).dt.days
        # 91 means the last observed source row is more than 90 days old or
        # no prior observation exists. The cap avoids unbounded calendar drift.
        result['days_since_observation'] = age.fillna(91).clip(lower=1, upper=91).astype(float)
        return result

    @staticmethod
    def add_annual_analogue_features(featured):
        """Add an observed-only, one-year analogue available before each target."""
        result = featured.copy()
        result['annual_price_relative'] = 0.0
        result['annual_observation_age_days'] = 15.0
        for _, group in result.groupby(SERIES_KEY, sort=False):
            observed = (group.is_observed.fillna(False).astype(bool)
                        & np.isfinite(pd.to_numeric(group.observed_price, errors='coerce')))
            dates = pd.to_datetime(group.loc[observed, 'report_date']).to_numpy(
                dtype='datetime64[ns]')
            prices = pd.to_numeric(group.loc[observed, 'observed_price'],
                                    errors='coerce').to_numpy(dtype=float)
            if not len(dates):
                continue
            targets = pd.to_datetime(group.report_date)
            references = (targets - pd.DateOffset(years=1)).to_numpy(
                dtype='datetime64[ns]')
            positions = np.searchsorted(dates, references, side='right') - 1
            valid = positions >= 0
            safe_positions = np.maximum(positions, 0)
            ages = ((references - dates[safe_positions])
                    .astype('timedelta64[D]').astype(np.int64))
            valid &= (ages >= 0) & (ages <= 14)
            anchors = pd.to_numeric(group.price_lag_1d, errors='coerce').to_numpy(float)
            valid &= np.isfinite(anchors) & (anchors > 0)
            row_positions = result.index.get_indexer(group.index)
            row_positions = row_positions[valid]
            result.loc[row_positions, 'annual_price_relative'] = (
                prices[positions[valid]] / anchors[valid] - 1.0)
            result.loc[row_positions, 'annual_observation_age_days'] = ages[valid].astype(float)
        return result

    @staticmethod
    def category_return_history(df):
        """Median same-category price return by date, available after that date closes."""
        work = df.sort_values(SERIES_KEY + ['report_date']).copy()
        work['_series_return'] = work.groupby(SERIES_KEY, sort=False).price_index.pct_change(
            fill_method=None)
        market = (work.groupby(['product_category', 'report_date'], sort=True)['_series_return']
                  .median().rename('category_return').reset_index())
        return market

    @classmethod
    def add_category_return_features(cls, featured):
        market = cls.category_return_history(featured)
        market = market.sort_values(['product_category', 'report_date']).copy()
        grouped = market.groupby('product_category', sort=False)['category_return']
        market['category_return_lag_1d'] = grouped.shift(1)
        shifted = grouped.shift(1)
        market['category_return_mean_7d'] = shifted.groupby(
            market.product_category, sort=False).transform(
                lambda values: values.rolling(7, min_periods=1).mean())
        market['category_return_std_7d'] = shifted.groupby(
            market.product_category, sort=False).transform(
                lambda values: values.rolling(7, min_periods=2).std(ddof=0))
        columns = ['category_return_lag_1d', 'category_return_mean_7d',
                   'category_return_std_7d']
        market[columns] = market[columns].replace([np.inf, -np.inf], np.nan).fillna(0.0)
        return featured.merge(market[['product_category', 'report_date'] + columns],
                              on=['product_category', 'report_date'], how='left',
                              validate='many_to_one')

    @staticmethod
    def product_return_history(df):
        """Median return among same-product peers, indexed by report date."""
        work = df.sort_values(SERIES_KEY + ['report_date']).copy()
        work['_series_return'] = work.groupby(
            SERIES_KEY, sort=False).price_index.pct_change(fill_method=None)
        return (work.groupby(PRODUCT_GROUP_KEY + ['report_date'], sort=True)['_series_return']
                .median().rename('product_return').reset_index())

    @classmethod
    def add_product_return_features(cls, featured):
        market = cls.product_return_history(featured)
        market = market.sort_values(PRODUCT_GROUP_KEY + ['report_date']).copy()
        group_keys = [market[column] for column in PRODUCT_GROUP_KEY]
        shifted = market.groupby(PRODUCT_GROUP_KEY, sort=False)['product_return'].shift(1)
        market['product_return_lag_1d'] = shifted
        shifted_groups = shifted.groupby(group_keys, sort=False)
        market['product_return_mean_7d'] = shifted_groups.transform(
            lambda values: values.rolling(7, min_periods=1).mean())
        market['product_return_std_7d'] = shifted_groups.transform(
            lambda values: values.rolling(7, min_periods=2).std(ddof=0))
        columns = PRODUCT_RETURN_FEATURES
        market[columns] = market[columns].replace([np.inf, -np.inf], np.nan).fillna(0.0)
        return featured.merge(
            market[PRODUCT_GROUP_KEY + ['report_date'] + columns],
            on=PRODUCT_GROUP_KEY + ['report_date'], how='left', validate='many_to_one')

    @classmethod
    def category_peer_return_history(cls, featured):
        """Return raw daily category-peer statistics for point-in-time replay."""
        work = featured[SERIES_KEY + ['report_date', 'price_index']].copy()
        work = work.sort_values(SERIES_KEY + ['report_date']).reset_index(drop=True)
        work['_series_return'] = work.groupby(SERIES_KEY, sort=False).price_index.pct_change(
            fill_method=None)
        work['_series_return'] = work['_series_return'].replace([np.inf, -np.inf], np.nan)
        core_return = (work.groupby(PEER_PRODUCT_KEY + ['report_date'], sort=True)
                       ['_series_return'].median().rename('_core_return').reset_index())
        category_key = PEER_PRODUCT_KEY[0]
        core_return['_valid'] = core_return['_core_return'].notna().astype(float)
        core_return['_sum'] = core_return['_core_return'].fillna(0.0)
        totals = (core_return.groupby([category_key, 'report_date'], sort=True)
                  [['_valid', '_sum']].sum().reset_index()
                  .rename(columns={'_valid': '_total_count', '_sum': '_total_sum'}))
        market = core_return.merge(
            totals, on=[category_key, 'report_date'], how='left', validate='many_to_one')
        own_valid = market['_core_return'].notna().astype(float)
        count = (market['_total_count'] - own_valid).to_numpy(dtype=float)
        total = (market['_total_sum'] - market['_core_return'].fillna(0.0)).to_numpy(
            dtype=float)
        peer_mean = np.divide(
            total, count, out=np.zeros(len(market), dtype=float), where=count > 0)
        market['_peer_mean'] = np.where(count > 0, peer_mean, 0.0)
        market['_peer_count'] = np.maximum(count, 0.0)
        return market[PEER_PRODUCT_KEY + ['report_date', '_peer_mean', '_peer_count']]

    @classmethod
    def add_category_peer_return_features(cls, featured):
        """Add one-day-lagged same-category returns excluding the target product.

        The return panel collapses market-origin rows to one value per product
        identity before calculating peer aggregates. Aggregates are shifted so
        every training row uses only prices dated before its target date.
        """
        work = featured[SERIES_KEY + ['report_date', 'price_index']].copy()
        work = work.sort_values(SERIES_KEY + ['report_date']).reset_index(drop=True)
        work['_series_return'] = work.groupby(SERIES_KEY, sort=False).price_index.pct_change(
            fill_method=None)
        work['_series_return'] = work['_series_return'].replace([np.inf, -np.inf], np.nan)
        core_return = (work.groupby(PEER_PRODUCT_KEY + ['report_date'], sort=True)
                       ['_series_return'].median().rename('_core_return').reset_index())
        core_return = core_return.sort_values(PEER_PRODUCT_KEY + ['report_date']).reset_index(drop=True)
        category_key = PEER_PRODUCT_KEY[0]
        core_return['_valid'] = core_return['_core_return'].notna().astype(float)
        core_return['_sum'] = core_return['_core_return'].fillna(0.0)
        core_return['_sum_sq'] = core_return['_core_return'].fillna(0.0).pow(2)
        core_return['_positive'] = (core_return['_core_return'].gt(0)
                                    & core_return['_core_return'].notna()).astype(float)
        totals = (core_return.groupby([category_key, 'report_date'], sort=True)
                  [['_valid', '_sum', '_sum_sq', '_positive']].sum().reset_index()
                  .rename(columns={'_valid': '_total_count', '_sum': '_total_sum',
                                   '_sum_sq': '_total_sum_sq',
                                   '_positive': '_total_positive'}))
        market = core_return.merge(
            totals, on=[category_key, 'report_date'], how='left', validate='many_to_one')
        own_valid = market['_core_return'].notna().astype(float)
        market['_peer_count'] = market['_total_count'] - own_valid
        market['_peer_sum'] = (market['_total_sum']
                               - market['_core_return'].fillna(0.0))
        market['_peer_sum_sq'] = (market['_total_sum_sq']
                                  - market['_core_return'].fillna(0.0).pow(2))
        market['_peer_positive'] = (market['_total_positive']
                                    - (market['_core_return'].gt(0)
                                       & market['_core_return'].notna()).astype(float))
        count = market['_peer_count'].to_numpy(dtype=float)
        total = market['_peer_sum'].to_numpy(dtype=float)
        mean_return = np.divide(total, count, out=np.zeros(len(market)), where=count > 0)
        second_moment = np.divide(
            market['_peer_sum_sq'].to_numpy(dtype=float), count,
            out=np.zeros(len(market)), where=count > 0)
        std_return = np.sqrt(np.maximum(second_moment - mean_return ** 2, 0.0))
        market['_peer_mean'] = np.where(count > 0, mean_return, 0.0)
        market['_peer_std'] = np.where(count > 0, std_return, 0.0)
        market['_peer_count_log'] = np.log1p(np.maximum(count, 0.0))
        grouped = market.groupby(PEER_PRODUCT_KEY, sort=False)
        market['category_peer_return_lag_1d'] = grouped['_peer_mean'].shift(1)
        market['category_peer_return_mean_7d'] = grouped['_peer_mean'].transform(
            lambda values: values.shift(1).rolling(7, min_periods=1).mean())
        market['category_peer_return_std_7d'] = grouped['_peer_mean'].transform(
            lambda values: values.shift(1).rolling(7, min_periods=2).std(ddof=0))
        market['category_peer_return_mean_30d'] = grouped['_peer_mean'].transform(
            lambda values: values.shift(1).rolling(30, min_periods=1).mean())
        market['category_peer_return_std_30d'] = grouped['_peer_mean'].transform(
            lambda values: values.shift(1).rolling(30, min_periods=2).std(ddof=0))
        market['category_peer_return_count_log'] = grouped['_peer_count_log'].shift(1)
        columns = CATEGORY_PEER_RETURN_FEATURES
        market[columns] = (market[columns].replace([np.inf, -np.inf], np.nan)
                          .fillna(0.0))
        return featured.merge(
            market[PEER_PRODUCT_KEY + ['report_date'] + columns],
            on=PEER_PRODUCT_KEY + ['report_date'], how='left', validate='many_to_one')

    @staticmethod
    def cross_variant_peer_history(df):
        """Return same-family peer movement by variant and date.

        Market origins are first collapsed within a variant. For each variant,
        the peer statistic excludes that variant and only uses sibling variants
        with finite returns on the same date.
        """
        work = df[SERIES_KEY + ['report_date', 'price_index']].copy()
        work = work.sort_values(SERIES_KEY + ['report_date']).reset_index(drop=True)
        work['_series_return'] = work.groupby(SERIES_KEY, sort=False).price_index.pct_change(
            fill_method=None)
        work['_series_return'] = work['_series_return'].replace([np.inf, -np.inf], np.nan)
        variant_return = (work.groupby(PRODUCT_VARIANT_KEY + ['report_date'], sort=True)
                          ['_series_return'].median().rename('_variant_return').reset_index())
        group_keys = PRODUCT_VARIANT_KEY[:3]
        totals = (variant_return.groupby(group_keys + ['report_date'], sort=True)
                  ['_variant_return'].agg(['count', 'sum']).reset_index()
                  .rename(columns={'count': '_total_count', 'sum': '_total_sum'}))
        market = variant_return.merge(
            totals, on=group_keys + ['report_date'], how='left', validate='many_to_one')
        own_valid = market['_variant_return'].notna().astype(float)
        count = market['_total_count'].to_numpy(dtype=float) - own_valid.to_numpy(dtype=float)
        total = (market['_total_sum']
                 - market['_variant_return'].fillna(0.0)).to_numpy(dtype=float)
        market['_peer_return'] = np.divide(
            total, count, out=np.zeros(len(market), dtype=float), where=count > 0)
        market['_peer_count'] = count
        return market[PRODUCT_VARIANT_KEY + ['report_date', '_peer_return', '_peer_count']]

    @classmethod
    def add_cross_variant_return_features(cls, featured):
        """Add causal returns from sibling product variants, excluding self."""
        market = cls.cross_variant_peer_history(featured)
        grouped = market.groupby(PRODUCT_VARIANT_KEY, sort=False)
        shifted = grouped['_peer_return'].shift(1)
        market['cross_variant_return_lag_1d'] = shifted
        market['cross_variant_return_mean_7d'] = shifted.groupby(
            [market[column] for column in PRODUCT_VARIANT_KEY], sort=False).transform(
                lambda values: values.rolling(7, min_periods=1).mean())
        market['cross_variant_return_std_7d'] = shifted.groupby(
            [market[column] for column in PRODUCT_VARIANT_KEY], sort=False).transform(
                lambda values: values.rolling(7, min_periods=2).std(ddof=0))
        prior_count = grouped['_peer_count'].shift(1)
        market['cross_variant_return_count_log'] = np.log1p(
            prior_count.clip(lower=0.0))
        columns = CROSS_VARIANT_RETURN_FEATURES
        market[columns] = market[columns].replace([np.inf, -np.inf], np.nan).fillna(0.0)
        return featured.merge(
            market[PRODUCT_VARIANT_KEY + ['report_date'] + columns],
            on=PRODUCT_VARIANT_KEY + ['report_date'], how='left', validate='many_to_one')

    def load(self):
        self.encoder._load_mappings()
        if self.artifact_dir is not None:
            metadata_path = self.artifact_dir / 'lightgbm_meta.json'
            if metadata_path.exists():
                import json
                metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
                version = metadata.get('feature_version')
                if version not in {2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13}:
                    raise ValueError('Incompatible LightGBM feature version')
                self.feature_version = int(version)
                lag_days = [1,2,3,7,14,30]
                rolling_windows = [3,7,14,30]
                if self.feature_version in {6, 7, 8, 9, 10, 11, 12, 13}:
                    lag_days.extend([31,61,91])
                    rolling_windows.append(60)
                self.lags = LagFeatures(lag_days=lag_days, rolling_windows=rolling_windows)
        return self


def usable_targets(df, feature_columns=FEATURE_COLUMNS):
    return (df.is_observed & np.isfinite(df.observed_price)
            & np.isfinite(df[feature_columns]).all(axis=1))


class CausalFeatureState:
    """Incrementally reproduces the next-row feature contract for one series."""
    def __init__(self, history, encoder):
        history = history.sort_values('report_date')
        self.prices = list(history.price_index.astype(float))
        self.key = history.iloc[-1][SERIES_KEY].to_dict()
        observed = (history.get('is_observed', pd.Series(False, index=history.index))
                    .fillna(False).astype(bool)
                    & np.isfinite(pd.to_numeric(
                        history.get('observed_price', pd.Series(np.nan, index=history.index)),
                        errors='coerce')))
        self.observed_dates = list(pd.to_datetime(
            history.loc[observed, 'report_date']).tolist())
        self.observed_prices = list(pd.to_numeric(
            history.loc[observed, 'observed_price'], errors='coerce').astype(float))
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

    def row(self, date, market_history=None, product_market_history=None,
            category_peer_market_history=None, cross_variant_market_history=None):
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
        result.update(moving_easter_features(date))
        last_observation = self.observed_dates[-1] if self.observed_dates else None
        result['days_since_observation'] = float(min(
            91, max(1, (date - pd.Timestamp(last_observation)).days)
        )) if last_observation is not None else 91.0
        for lag in [1,2,3,7,8,14,30]:
            result[f'price_lag_{lag}d'] = p[-lag] if len(p) >= lag else np.nan
        for lag in [31,61,91]:
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
        for days, lag in ((30,31),(60,61),(90,91)):
            prior = p[-lag] if len(p) >= lag else np.nan
            result[f'price_pct_change_{days}d'] = (
                (p[-1] - prior) / prior
                if np.isfinite(prior) and prior != 0 and np.isfinite(p[-1]) else 0.0)
        mean60 = self._finite_stat(p[-60:], 'mean')
        std60 = self._finite_stat(p[-60:], 'std')
        result['price_volatility_60d'] = (
            std60 / mean60 if np.isfinite(std60) and np.isfinite(mean60) and mean60 != 0
            else np.nan)
        result['price_deviation_from_rolling_mean_60d'] = (
            (p[-1] - mean60) / mean60
            if len(p) and np.isfinite(p[-1]) and np.isfinite(mean60) and mean60 != 0
            else np.nan)
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
        if market_history is None:
            market = p[1:] / p[:-1] - 1.0 if len(p) > 1 else np.asarray([], dtype=float)
        else:
            market = np.asarray(market_history, dtype=float)
        market = market[np.isfinite(market)]
        result['category_return_lag_1d'] = float(market[-1]) if len(market) else 0.0
        result['category_return_mean_7d'] = float(np.mean(market[-7:])) if len(market) else 0.0
        result['category_return_std_7d'] = (float(np.std(market[-7:]))
                                             if len(market) >= 2 else 0.0)
        if product_market_history is None:
            product_market = p[1:] / p[:-1] - 1.0 if len(p) > 1 else np.asarray([], dtype=float)
        else:
            product_market = np.asarray(product_market_history, dtype=float)
        product_market = product_market[np.isfinite(product_market)]
        result['product_return_lag_1d'] = (
            float(product_market[-1]) if len(product_market) else 0.0)
        result['product_return_mean_7d'] = (
            float(np.mean(product_market[-7:])) if len(product_market) else 0.0)
        result['product_return_std_7d'] = (
            float(np.std(product_market[-7:], ddof=0)) if len(product_market) >= 2 else 0.0)
        if category_peer_market_history is None:
            category_peer = np.empty((0, 2), dtype=float)
        else:
            category_peer = np.asarray(category_peer_market_history, dtype=float).reshape(-1, 2)
            category_peer = category_peer[np.isfinite(category_peer).all(axis=1)]
        peer_returns = category_peer[-30:, 0]
        peer_counts = category_peer[-30:, 1]
        result['category_peer_return_lag_1d'] = (
            float(peer_returns[-1]) if len(peer_returns) else 0.0)
        result['category_peer_return_mean_7d'] = (
            float(np.mean(peer_returns[-7:])) if len(peer_returns) else 0.0)
        result['category_peer_return_std_7d'] = (
            float(np.std(peer_returns[-7:], ddof=0)) if len(peer_returns) >= 2 else 0.0)
        result['category_peer_return_mean_30d'] = (
            float(np.mean(peer_returns)) if len(peer_returns) else 0.0)
        result['category_peer_return_std_30d'] = (
            float(np.std(peer_returns, ddof=0)) if len(peer_returns) >= 2 else 0.0)
        result['category_peer_return_count_log'] = (
            float(np.log1p(max(0.0, peer_counts[-1]))) if len(peer_counts) else 0.0)
        if cross_variant_market_history is None:
            cross_variant = np.empty((0, 2), dtype=float)
        else:
            cross_variant = np.asarray(
                cross_variant_market_history, dtype=float).reshape(-1, 2)
            cross_variant = cross_variant[np.isfinite(cross_variant).all(axis=1)]
        cross_returns = cross_variant[-7:, 0]
        cross_counts = cross_variant[-7:, 1]
        result['cross_variant_return_lag_1d'] = (
            float(cross_returns[-1]) if len(cross_returns) else 0.0)
        result['cross_variant_return_mean_7d'] = (
            float(np.mean(cross_returns)) if len(cross_returns) else 0.0)
        result['cross_variant_return_std_7d'] = (
            float(np.std(cross_returns, ddof=0)) if len(cross_returns) >= 2 else 0.0)
        result['cross_variant_return_count_log'] = (
            float(np.log1p(max(0.0, cross_counts[-1]))) if len(cross_counts) else 0.0)
        reference_date = date - pd.DateOffset(years=1)
        analogue_index = bisect.bisect_right(self.observed_dates, reference_date) - 1
        if analogue_index >= 0:
            age = int((reference_date - self.observed_dates[analogue_index]).days)
            anchor = result['price_lag_1d']
            if 0 <= age <= 14 and np.isfinite(anchor) and anchor > 0:
                result['annual_price_relative'] = self.observed_prices[analogue_index] / anchor - 1.0
                result['annual_observation_age_days'] = float(age)
            else:
                result['annual_price_relative'] = 0.0
                result['annual_observation_age_days'] = 15.0
        else:
            result['annual_price_relative'] = 0.0
            result['annual_observation_age_days'] = 15.0
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
