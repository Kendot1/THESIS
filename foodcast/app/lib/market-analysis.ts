import { forecastHorizonPoints } from "./data";
import type { ForecastDataPoint, ForecastHorizon, Product } from "./data";

function addUtcDays(value: string, days: number): string {
  const date = new Date(`${value}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function averageDailyForecasts(
  data: ForecastDataPoint[],
  origin: string,
  horizon: "weekly" | "monthly",
): ForecastDataPoint[] {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(origin) || !Number.isFinite(Date.parse(`${origin}T00:00:00Z`))) return [];
  const daily = data
    .filter(point => (point.horizon === "daily" || point.horizon == null)
      && point.date >= origin
      && point.predicted != null
      && Number.isFinite(point.predicted)
      && point.predicted > 0)
    .sort((left, right) => left.date.localeCompare(right.date));
  const byDate = new Map(daily.map(point => [point.date, point]));
  const periods = horizon === "weekly"
    ? Array.from({ length: 4 }, (_, index) => ({
      step: index + 1,
      start: addUtcDays(origin, index * 7 + 1),
      end: addUtcDays(origin, index * 7 + 7),
    }))
    : [{ step: 1, start: origin, end: addUtcDays(origin, 29) }];

  return periods.flatMap(period => {
    const values: number[] = [];
    for (let offset = 0; offset <= (Date.parse(period.end) - Date.parse(period.start)) / 86400000; offset++) {
      const point = byDate.get(addUtcDays(period.start, offset));
      if (!point?.predicted || !Number.isFinite(point.predicted)) return [];
      values.push(point.predicted);
    }
    return [{
      date: period.end,
      name: period.start,
      actual: null,
      predicted: Number((values.reduce((sum, value) => sum + value, 0) / values.length).toFixed(2)),
      horizon,
      target_period_start: period.start,
      target_period_end: period.end,
      forecast_step: period.step,
      covered_days: values.length,
      period_days: values.length,
    }];
  });
}

/** Select saved prices for the current contract; never aggregate a daily path. */
export function marketAnalysisForecasts(
  product: Pick<Product, "forecastSource" | "forecastOriginDate" | "forecastData">,
  horizon: ForecastHorizon,
  contract: "rolling" | "calendar_research" = "rolling",
): ForecastDataPoint[] {
  const origin = product.forecastOriginDate;
  if (horizon !== "daily" && product.forecastSource !== "model") return [];
  if (horizon === "daily") {
    return forecastHorizonPoints(product.forecastData, origin, horizon);
  }
  if (contract === "rolling") {
    // The publisher persists means computed from its complete daily path, even
    // when the public payload contains only the first seven daily predictions.
    // Require exact origin-relative ranges, counts and steps before using them.
    const saved = product.forecastData
      .filter(point => point.horizon === horizon
        && point.date > (origin ?? "")
        && point.target_period_start != null
        && point.target_period_end === point.date
        && (horizon === "monthly"
          ? ((point.target_period_start === origin && point.date === addUtcDays(origin!, 29))
            || (point.target_period_start === addUtcDays(origin!, 1) && point.date === addUtcDays(origin!, 30)))
          : (point.forecast_step != null
            && point.target_period_start === addUtcDays(origin!, (point.forecast_step - 1) * 7 + 1)
            && point.date === addUtcDays(origin!, point.forecast_step * 7)))
        && point.predicted != null
        && Number.isFinite(point.predicted)
        && point.predicted > 0
        && (point.forecast_step == null || point.forecast_step > 0)
        && (point.covered_days == null || point.period_days == null || point.covered_days === point.period_days))
      .sort((left, right) => (left.forecast_step ?? 0) - (right.forecast_step ?? 0)
        || left.date.localeCompare(right.date));
    const expectedCount = horizon === "weekly" ? 4 : 1;
    if (saved.length >= expectedCount) return saved.slice(0, expectedCount);
    return averageDailyForecasts(product.forecastData, origin ?? "", horizon);
  }
  // Explicit historical research bypass only: retain the original calendar
  // targets without moving dates or passing these rows off as rolling prices.
  if (!origin || !/^\d{4}-\d{2}-\d{2}$/.test(origin)) return [];
  const timestamp = Date.parse(`${origin}T00:00:00Z`);
  if (!Number.isFinite(timestamp) || new Date(timestamp).toISOString().slice(0, 10) !== origin) return [];
  const date = (value: number) => new Date(value).toISOString().slice(0, 10);
  const periods: { start: string; end: string }[] = [];
  const value = new Date(timestamp);
  if (horizon === "weekly") {
    const mondayOffset = (value.getUTCDay() + 6) % 7;
    for (let step = 0; step < 4; step++) {
      const start = timestamp + (7 - mondayOffset + step * 7) * 86400000;
      periods.push({ start: date(start), end: date(start + 6 * 86400000) });
    }
  } else {
    periods.push({
      start: date(Date.UTC(value.getUTCFullYear(), value.getUTCMonth() + 1, 1)),
      end: date(Date.UTC(value.getUTCFullYear(), value.getUTCMonth() + 2, 0)),
    });
  }
  const selected: ForecastDataPoint[] = [];
  for (const [index, period] of periods.entries()) {
    const days = (Date.parse(period.end) - Date.parse(period.start)) / 86400000 + 1;
    const matches = product.forecastData.filter(point => point.horizon === horizon
      && point.date === period.end && point.target_period_start === period.start
      && point.target_period_end === period.end
      && point.predicted != null && Number.isFinite(point.predicted) && point.predicted > 0
      && (point.forecast_step == null || point.forecast_step === index + 1)
      && (point.covered_days == null || point.covered_days === days)
      && (point.period_days == null || point.period_days === days));
    if (matches.length !== 1) return [];
    selected.push(matches[0]);
  }
  return selected;
}
