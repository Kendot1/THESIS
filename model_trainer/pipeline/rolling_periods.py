"""Manila issue-date rolling ranges, separate from calendar-period evaluation."""
from datetime import date, datetime, timedelta, timezone
PH_TIME = timezone(timedelta(hours=8))
ROLLING_CONTRACT = 'rolling_daily7_weekly4_monthly30_v2'

def manila_today(now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('An aware timestamp is required')
    return now.astimezone(PH_TIME).date()

def rolling_period_bounds(origin, horizon, step):
    counts = {'daily': 7, 'weekly': 4, 'monthly': 1}
    if horizon not in counts or type(step) is not int or not 1 <= step <= counts[horizon]:
        raise ValueError('Unsupported rolling horizon or step')
    origin = date.fromisoformat(str(origin)[:10])
    first, last = ((step, step) if horizon == 'daily' else
                   (1 + (step-1)*7, step*7) if horizon == 'weekly' else (0,29))
    return origin + timedelta(days=first), origin + timedelta(days=last)
