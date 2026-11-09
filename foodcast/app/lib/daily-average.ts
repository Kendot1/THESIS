import { rollingPeriods } from './rolling-periods';
type Day = { date: string; prediction: number };
/** Exact inclusive means over saved daily forecasts. No fallback or partial mean. */
export function aggregateDailyPath(origin: string, path: Day[]) {
  const periods = rollingPeriods(origin);
  const byDate = new Map<string, number>();
  for (const row of path) {
    const stamp = Date.parse(`${row.date}T00:00:00Z`);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(row.date) || !Number.isFinite(stamp) || new Date(stamp).toISOString().slice(0, 10) !== row.date || byDate.has(row.date) || typeof row.prediction !== 'number' || !Number.isFinite(row.prediction)) throw new Error('Invalid or duplicate daily path');
    byDate.set(row.date, row.prediction);
  }
  return (['daily', 'weekly', 'monthly'] as const).flatMap(horizon => periods[horizon].map(period => {
    const dates = Array.from({ length: period.period_days }, (_, i) => new Date(Date.parse(period.target_start) + i * 86400000).toISOString().slice(0, 10));
    const missing = dates.filter(date => !byDate.has(date));
    return { ...period, horizon, forecast_origin: origin,
      prediction: missing.length ? null : dates.reduce((sum, date) => sum + byDate.get(date)!, 0) / dates.length,
      covered_days: dates.length - missing.length,
      unavailable: missing.length > 0, unavailable_reason: missing.length ? `Unsupported daily forecast dates: ${missing.join(', ')}` : null,
      confidence_score: null, lower_bound: null, upper_bound: null,
      model: horizon === 'daily' ? 'Retained daily model' : 'Daily model average' };
  }));
}
