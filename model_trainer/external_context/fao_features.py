"""Causal research lookups for independently timestamped FAO index releases."""
from calendar import monthrange
from datetime import date, datetime, timedelta
import math
import re


class FAOArchive:
    def __init__(self, rows):
        self.rows = []
        seen = set()
        for row in rows:
            if row.get('historical_availability_verified') is not True or row.get('base_definition_verified') is not True:
                raise ValueError('Historical value and index definition must be verified')
            if row.get('metric') != 'FAO Food Price Index' or row.get('unit') != 'index_points' or row.get('base_period') != '2014-2016=100':
                raise ValueError('Unexpected index definition')
            if not re.fullmatch(r'\d{4}-\d{2}', row['reference_period']):
                raise ValueError('Invalid reference month')
            year, month = map(int, row['reference_period'].split('-'))
            end = date(year, month, monthrange(year, month)[1])
            available = datetime.fromisoformat(row['available_at_utc'])
            if available.tzinfo is None or available.utcoffset() is None or available.date() <= end:
                raise ValueError('Invalid available-by time')
            published = date.fromisoformat(row['declared_publication_date'])
            if published > available.date() or published <= end:
                raise ValueError('Publication date inconsistent with reference period or availability')
            value = float(row['value'])
            if isinstance(row['value'], bool) or not math.isfinite(value) or value <= 0:
                raise ValueError('Invalid index level')
            key = (row['reference_period'], available)
            if key in seen:
                raise ValueError('Duplicate or ambiguous release vintage')
            seen.add(key)
            self.rows.append((dict(row), end, available, value))
        self.rows = tuple(self.rows)

    def at(self, origin, *, lag_days, max_age_days):
        if origin.tzinfo is None or origin.utcoffset() is None:
            raise ValueError('Origin requires timezone')
        if type(lag_days) is not int or type(max_age_days) is not int or lag_days < 0 or max_age_days < 0:
            raise ValueError('Lag and age must be nonnegative integer days')
        cutoff = origin - timedelta(days=lag_days)
        eligible = [r for r in self.rows if r[2] <= cutoff]
        selected = max(eligible, key=lambda r: (r[1], r[2]), default=None)
        result = {'value': None, 'missing': 1, 'reference_age_days': None, 'availability_age_days': None,
                  'reference_period': None, 'source_id': None, 'reason': 'no_available_release',
                  'lag_days': lag_days, 'max_age_days': max_age_days}
        if selected:
            row, end, available, value = selected
            age = (origin.date() - end).days
            result.update(reference_age_days=age, availability_age_days=(origin-available).total_seconds()/86400,
                          reference_period=row['reference_period'], source_id=row['source_id'])
            if age > max_age_days:
                result['reason'] = 'stale_reference'
            else:
                result.update(value=value, missing=0, reason='available_verified_release')
        return result
