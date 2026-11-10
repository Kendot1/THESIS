"""Pure retrospective evaluator for origin-relative aggregates of daily forecasts.

This is a distinct rolling contract, NOT complete calendar weeks/months.
No fitting, I/O, publication or independent-confidence admission occurs here.
"""
import math
from collections import defaultdict
from datetime import date, timedelta

CONTRACT = 'daily_path_rolling_7days_4weeks_30day_mean_v1'
WINDOWS = ([('daily', i, i, i) for i in range(1, 8)]
           + [('weekly', i, 7*i-6, 7*i) for i in range(1, 5)]
           + [('monthly', 1, 1, 30)])
MIN_ORIGINS = 20


def _valid(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value >= 0)


def evaluate_daily_paths(paths, *, model_id, as_of):
    """Score complete saved daily paths; dates must close strictly before as_of.

    Each input path carries exact series identity, model_id, origin, fit_end,
    evidence_class and rows(date, prediction, actual). Caller must separately
    authenticate hashes, causal preprocessing and model-selection provenance.
    Missing days or values reduce scored coverage, never the required grid.
    Output confidence_pct deliberately remains null: historical hit frequency
    is not an independently validated future probability.
    """
    cutoff = date.fromisoformat(as_of)
    seen = set()
    groups = defaultdict(list)
    for path in paths:
        origin = date.fromisoformat(path['origin'])
        if path['model_id'] != model_id or not path.get('series'):
            raise ValueError('Exact model and series identity required')
        if date.fromisoformat(path['fit_end']) >= origin:
            raise ValueError('Fit must end strictly before forecast origin')
        if path.get('evidence_class') not in {'DEVELOPMENT_REUSED', 'UNTOUCHED'}:
            raise ValueError('Explicit evidence classification required')
        key = (path['series'], origin)
        if key in seen:
            raise ValueError('Duplicate series/origin path')
        seen.add(key)
        rows = {}
        for row in path['rows']:
            target = date.fromisoformat(row['date'])
            if target in rows or not 1 <= (target-origin).days <= 30:
                raise ValueError('Duplicate or out-of-contract target date')
            rows[target] = row
        for horizon, step, start, end in WINDOWS:
            dates = [origin + timedelta(days=i) for i in range(start, end+1)]
            values = [rows.get(d, {}) for d in dates]
            complete = (dates[-1] < cutoff
                        and all(_valid(r.get('prediction')) and _valid(r.get('actual'))
                                for r in values))
            error = None
            if complete:
                error = (math.fsum(r['prediction'] for r in values)
                         - math.fsum(r['actual'] for r in values)) / len(values)
            groups[(path['series'], horizon, step, start, end)].append(
                (origin, dates[-1], error, path['evidence_class']))
    cells = []
    for (series, horizon, step, start, end), records in groups.items():
        scored = [r for r in records if r[2] is not None]
        n = len(scored)
        hits = sum(abs(r[2]) <= 5 for r in scored)
        origins = len({r[0] for r in scored})
        periods = len({r[1] for r in scored})
        supported = origins >= MIN_ORIGINS and periods >= MIN_ORIGINS
        cells.append(dict(series=series, model_id=model_id, contract=CONTRACT,
                          horizon=horizon, step=step, start_offset=start, end_offset=end,
                          required=len(records), scored=n, hits=hits, origins=origins,
                          target_periods=periods,
                          coverage_pct=100*n/len(records),
                          mae_php=math.fsum(abs(r[2]) for r in scored)/n if n else None,
                          rmse_php=math.sqrt(math.fsum(r[2]**2 for r in scored)/n) if n else None,
                          historical_rate_pct=100*hits/n if supported else None,
                          confidence_pct=None,
                          status='HISTORICAL_ONLY' if supported else 'INSUFFICIENT_SUPPORT',
                          evidence_classes=sorted({r[3] for r in records})))
    return {'contract': CONTRACT, 'as_of': as_of, 'model_id': model_id,
            'tolerance_php': 5, 'minimum_distinct_origins_and_periods': MIN_ORIGINS,
            'cells': cells, 'independent_confidence_admitted': False}
