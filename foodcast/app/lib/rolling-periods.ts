/** Calendar dates in the Manila issue-date contract; UTC arithmetic avoids DST. */
export type RollingPeriod = { target_start: string; target_end: string; lead: number; period_days: number };
export const ROLLING_CONTRACT = 'rolling_daily7_weekly4_monthly30_v2';
export function manilaToday(now: Date = new Date()): string {
  if (!Number.isFinite(now.getTime())) throw new Error('Invalid time');
  return new Date(now.getTime() + 8 * 3600000).toISOString().slice(0, 10);
}
export function rollingPeriods(origin: string): Record<'daily' | 'weekly' | 'monthly', RollingPeriod[]> {
  const timestamp = Date.parse(`${origin}T00:00:00Z`);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(origin) || !Number.isFinite(timestamp) || new Date(timestamp).toISOString().slice(0, 10) !== origin) throw new Error('Invalid origin');
  const date = (offset: number) => new Date(timestamp + offset * 86400000).toISOString().slice(0, 10);
  const period = (lead: number, from: number, to: number): RollingPeriod => ({ lead, target_start: date(from), target_end: date(to), period_days: to - from + 1 });
  return { daily: Array.from({ length: 7 }, (_, i) => period(i + 1, i + 1, i + 1)), weekly: Array.from({ length: 4 }, (_, i) => period(i + 1, i * 7 + 1, i * 7 + 7)), monthly: [period(1, 0, 29)] };
}
export function rollingPeriodLabel(start: string, end: string, horizon: string, language = 'en'): string {
  const short = (value: string) => new Date(`${value}T00:00:00Z`).toLocaleDateString(language === 'tl' ? 'fil-PH' : 'en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
  return `${horizon === 'weekly' ? `${language === 'tl' ? 'Linggo' : 'Week'} ` : ''}${short(start)}${start === end ? '' : `–${short(end)}`}`;
}
