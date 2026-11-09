import { forecastHorizonPoints } from "./data";
import type { ForecastDataPoint, ForecastHorizon, Product } from "./data";

/** Select saved prices for the current contract; never aggregate a daily path. */
export function marketAnalysisForecasts(
  product: Pick<Product, "forecastSource" | "forecastOriginDate" | "forecastData">,
  horizon: ForecastHorizon,
  contract: "rolling" | "calendar_research" = "rolling",
): ForecastDataPoint[] {
  const origin = product.forecastOriginDate;
  if (horizon !== "daily" && product.forecastSource !== "model") return [];
  if (contract === "rolling" || horizon === "daily") {
    return forecastHorizonPoints(product.forecastData, origin, horizon);
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
