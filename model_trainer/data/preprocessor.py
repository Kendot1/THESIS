"""Causal daily panel construction. Imputed inputs are never scored as truth."""
import re
from datetime import datetime
import numpy as np
import pandas as pd
from config.settings import get_settings

SERIES_KEY = ['product_category', 'product_name', 'product_variant', 'origin', 'unit']


def normalize_unit(value):
    value = str(value).strip().lower() if pd.notna(value) else 'unknown'
    return {'per kg': 'kg', 'kilogram': 'kg', 'pc': 'piece', 'per piece': 'piece',
            'l': 'liter', '1 liter': 'liter', '1l': 'liter', '350 ml': '350ml',
            'milliliter': 'ml', 'btl': 'bottle'}.get(value, value)


def source_date(source):
    match = re.search(r'([A-Za-z]+)-(\d{1,2})-(\d{4})', str(source))
    try:
        return pd.Timestamp(datetime.strptime(' '.join(match.groups()), '%B %d %Y')) if match else pd.NaT
    except ValueError:
        return pd.NaT


class DataPreprocessor:
    REQUIRED_COLUMNS = SERIES_KEY + ['report_date', 'price_index']

    def validate(self, df):
        missing = set(self.REQUIRED_COLUMNS) - set(df.columns)
        if missing:
            raise ValueError(f'Missing required columns: {sorted(missing)}')
        df = df.copy()
        df['report_date'] = pd.to_datetime(df.report_date, errors='coerce').dt.normalize()
        df['price_index'] = pd.to_numeric(df.price_index, errors='coerce')
        for col in SERIES_KEY:
            df[col] = df[col].fillna('Unknown').astype(str).str.strip()
        df['product_variant'] = df.product_variant.replace({'': 'Standard', 'Unknown': 'Standard', 'null': 'Standard'})
        df['unit'] = df.unit.map(normalize_unit)
        oil_size = df.product_category.eq('Oils') & df.product_variant.str.lower().isin(['1l', '350ml'])
        df.loc[oil_size & df.product_variant.str.lower().eq('1l'), 'unit'] = 'liter'
        df.loc[oil_size & df.product_variant.str.lower().eq('350ml'), 'unit'] = '350ml'
        df.loc[df.product_name.eq('Chicken Egg'), 'unit'] = 'piece'
        identity = SERIES_KEY[:-1]
        known = df[df.unit.ne('unknown')].groupby(identity).unit.agg(lambda s: sorted(set(s)))
        inferred = {key: values[0] for key, values in known.items() if len(values) == 1}
        unknown = df.unit.eq('unknown')
        df.loc[unknown, 'unit'] = [inferred.get(tuple(row), 'unknown')
                                   for row in df.loc[unknown, identity].itertuples(index=False, name=None)]
        df = df[df.report_date.notna() & np.isfinite(df.price_index) & (df.price_index > 0)].copy()
        df = df[~df.product_name.isin(['', 'Unknown']) & ~df.product_category.isin(['', 'Unknown'])]
        if df.empty:
            raise ValueError('No valid price rows')
        if 'is_observed' in df:
            if not df.is_observed.dropna().isin([True, False]).all():
                raise ValueError('is_observed must be boolean')
            df['is_observed'] = df.is_observed.fillna(False).astype(bool)
        elif 'source_pdf' in df:
            dates = df.source_pdf.map(source_date)
            df['is_observed'] = dates.eq(df.report_date)
        else:
            raise ValueError('Provide is_observed provenance or dated source_pdf URLs')
        # Copied/unknown rows are not new observations. Reconstruct filling causally.
        df['price_index'] = df.price_index.where(df.is_observed)
        duplicates = df.duplicated(SERIES_KEY + ['report_date'], keep=False)
        if duplicates.any():
            conflicting = df.loc[duplicates].groupby(SERIES_KEY + ['report_date']).price_index.nunique()
            if (conflicting > 1).any():
                raise ValueError('Conflicting observed prices for the same series/date')
        df = df.sort_values('is_observed', ascending=False).drop_duplicates(SERIES_KEY + ['report_date'])
        groups = []
        for key, group in df.groupby(SERIES_KEY, sort=True):
            group = group.set_index('report_date').sort_index()
            group = group.reindex(pd.date_range(group.index.min(), group.index.max(), freq='D'))
            for col, value in zip(SERIES_KEY, key):
                group[col] = value
            group['is_observed'] = group.is_observed.fillna(False).astype(bool)
            group['observed_price'] = group.price_index.where(group.is_observed)
            group['price_index'] = group.observed_price.ffill(limit=get_settings().max_fill_days)
            group.index.name = 'report_date'
            groups.append(group.reset_index())
        return pd.concat(groups, ignore_index=True).sort_values(SERIES_KEY + ['report_date']).reset_index(drop=True)

    @staticmethod
    def time_split(df, test_size=0.15):
        dates = np.sort(df.report_date.unique())
        if not 0 < test_size < 1 or len(dates) < 2:
            raise ValueError('Need at least two dates and a split fraction between zero and one')
        cutoff = dates[max(1, min(len(dates)-1, int(len(dates)*(1-test_size))))]
        return df[df.report_date < cutoff].copy(), df[df.report_date >= cutoff].copy()

    @staticmethod
    def split_three(df, validation_size=0.15, test_size=0.15):
        if min(validation_size, test_size) <= 0 or validation_size + test_size >= 1:
            raise ValueError('Invalid chronological split fractions')
        dates = np.sort(df.report_date.unique())
        a, b = int(len(dates)*(1-validation_size-test_size)), int(len(dates)*(1-test_size))
        if not 0 < a < b < len(dates):
            raise ValueError('Not enough distinct dates for three partitions')
        return (df[df.report_date < dates[a]].copy(),
                df[(df.report_date >= dates[a]) & (df.report_date < dates[b])].copy(),
                df[df.report_date >= dates[b]].copy())
