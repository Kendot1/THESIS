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

    @staticmethod
    def source_target_availability(clean, available_through):
        """Apply the report-date availability assumption to observed labels."""
        try:
            cutoff = pd.Timestamp(available_through)
        except (TypeError, ValueError) as exc:
            raise ValueError("Availability cutoff must be an ISO timestamp") from exc
        if cutoff.tzinfo is None:
            raise ValueError("Availability cutoff must include a timezone")
        cutoff = cutoff.tz_convert("UTC")
        cutoff_date = cutoff.tz_convert("Asia/Manila").date()

        observed = clean.get("is_observed", pd.Series(False, index=clean.index))
        observed = observed.fillna(False).astype(bool)
        total_observed = int(observed.sum())
        dates = pd.to_datetime(clean.get(
            "report_date", pd.Series(pd.NaT, index=clean.index)), errors="coerce")
        in_date_scope = dates.dt.date <= cutoff_date
        eligible = observed & in_date_scope
        mask = eligible.rename("report_date_label_available")
        audit = {
            "status": "report_date_based",
            "availability_assumption": "available_by_end_of_report_date_in_Asia/Manila",
            "fit_availability_cutoff_utc": cutoff.isoformat(timespec="microseconds"),
            "fit_report_date_cutoff_manila": cutoff_date.isoformat(),
            "observed_training_labels": total_observed,
            "labels_with_report_date": int((observed & dates.notna()).sum()),
            "labels_available_by_fit_cutoff": int(eligible.sum()),
            "labels_without_report_date": int((observed & dates.isna()).sum()),
            "labels_after_fit_cutoff": int((observed & dates.notna() & ~in_date_scope).sum()),
            "coverage": float(eligible.sum() / total_observed) if total_observed else None,
        }
        return mask, audit

    @staticmethod
    def source_input_view(clean, available_through):
        """Rebuild causal inputs using report dates through the origin-day cutoff.

        The returned frame keeps ``observed_price`` and ``is_observed`` as truth
        labels. Only ``price_index`` is masked and forward-filled for features.
        Prices are assumed to be available by the end of their report date.
        """
        required = {"report_date", "is_observed", "observed_price"}
        if not required.issubset(clean.columns):
            raise ValueError("As-of price inputs require report dates and observed labels")
        try:
            cutoff = pd.Timestamp(available_through)
        except (TypeError, ValueError) as exc:
            raise ValueError("Availability cutoff must be an ISO timestamp") from exc
        if cutoff.tzinfo is None:
            raise ValueError("Availability cutoff must include a timezone")
        cutoff = cutoff.tz_convert("UTC")

        view = clean.sort_values(SERIES_KEY + ["report_date"]).reset_index(drop=True).copy()
        cutoff_date = cutoff.tz_convert("Asia/Manila").date()
        report_dates = pd.to_datetime(view.report_date, errors="coerce")
        view = view.loc[report_dates.dt.date <= cutoff_date].copy().reset_index(drop=True)
        report_date_excluded = int(len(clean) - len(view))
        observed = view.is_observed.fillna(False).astype(bool)
        available = observed & pd.to_numeric(view.observed_price, errors="coerce").notna()

        view["price_index"] = pd.to_numeric(view.observed_price, errors="coerce").where(available)
        view["price_index"] = view.groupby(SERIES_KEY, sort=False)["price_index"].ffill(
            limit=get_settings().max_fill_days)
        audit = {
            "report_date_as_of_utc": cutoff.isoformat(timespec="microseconds"),
            "report_date_cutoff_manila": cutoff_date.isoformat(),
            "rows_after_report_date_cutoff": report_date_excluded,
            "observed_rows": int(observed.sum()),
            "observations_available_by_cutoff": int(available.sum()),
            "observed_rows_excluded": int(observed.sum() - available.sum()),
            "input_price_rows_after_causal_fill": int(view.price_index.notna().sum()),
        }
        return view, audit

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
