export interface PriceHistoryRow {
  report_date: string;
  price_index: number;
}

export interface PredictionRow {
  prediction_date: string;
  predicted_price: number;
  forecast_origin_date?: string | null;
  confidence_score?: number | null;
  confidence_level?: string | null;
}

export interface NormalizedPrediction {
  date: string;
  predicted_price: number;
  confidence_score?: number | null;
  confidence_level?: string | null;
}

export interface SavedPeriodPrediction extends NormalizedPrediction {
  forecast_horizon: "weekly" | "monthly";
  target_period_start: string;
  target_period_end: string;
  forecast_step: number;
  covered_days: number;
  period_days: number;
}

export interface StoredPeriodPrediction {
  prediction_date: string;
  forecast_origin_date: string;
  forecast_horizon: "weekly" | "monthly";
  target_period_start: string;
  target_period_end: string;
  predicted_price: number;
  forecast_step: number;
  covered_days: number;
  period_days: number;
  confidence_score?: number | null;
  confidence_level?: string | null;
}

export interface ForecastPoint {
  date: string;
  name: string;
  actual: number | null;
  predicted: number | null;
  horizon?: "daily" | "weekly" | "monthly";
  target_period_start?: string;
  target_period_end?: string;
  forecast_step?: number;
  covered_days?: number;
  period_days?: number;
  confidence_score?: number | null;
  confidence_level?: string | null;
}

export type ForecastHorizon = "daily" | "weekly" | "monthly";

const MONTH_NAMES = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

export function dateOnly(value: string): string {
  return String(value || "").split("T")[0];
}

function isIsoDate(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) &&
    Number.isFinite(Date.parse(`${value}T00:00:00Z`)) &&
    new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) === value;
}

function roundPrice(value: number): number {
  return Math.round(value * 100) / 100;
}

export function addUtcDays(date: string, days: number): string {
  const parsed = new Date(`${date}T00:00:00Z`);
  parsed.setUTCDate(parsed.getUTCDate() + days);
  return parsed.toISOString().split("T")[0];
}

/** Use the saved forecast origin when it is current relative to this product's data. */
export function resolveForecastOrigin(lastActualDate: string, savedOrigin?: string | null): string {
  const actual = dateOnly(lastActualDate);
  const saved = dateOnly(String(savedOrigin || ""));
  return isIsoDate(actual) && isIsoDate(saved) && saved >= actual ? saved : actual;
}

/** Keep only stored period points tied to the selected, still-current daily forecast. */
export function selectSavedPeriodPredictions(
  rows: StoredPeriodPrediction[],
  origin: string,
  hasDailyPath: boolean,
): StoredPeriodPrediction[] {
  if (!hasDailyPath || !isIsoDate(origin)) return [];
  return (rows || []).filter((row) => {
    const target = dateOnly(row.prediction_date);
    const rowOrigin = dateOnly(row.forecast_origin_date);
    const start = dateOnly(row.target_period_start);
    const end = dateOnly(row.target_period_end);
    return rowOrigin === origin && isIsoDate(target) && target > origin
      && isIsoDate(start) && isIsoDate(end) && start <= end
      && (row.forecast_horizon === "weekly" || row.forecast_horizon === "monthly")
      && Number.isInteger(row.forecast_step) && row.forecast_step > 0
      && Number.isInteger(row.covered_days) && row.covered_days > 0
      && Number.isInteger(row.period_days) && row.period_days >= row.covered_days
      && Number.isFinite(Number(row.predicted_price)) && Number(row.predicted_price) > 0;
  });
}

/** Keep only predictions that are still in the future for this series. */
export function selectFuturePredictions(
  predictions: PredictionRow[],
  lastActualDate: string,
  horizon = 30,
): NormalizedPrediction[] {
  const byDate = new Map<string, NormalizedPrediction>();
  for (const row of predictions || []) {
    if (row.forecast_origin_date != null
      && dateOnly(row.forecast_origin_date) !== lastActualDate) continue;
    const date = dateOnly(row.prediction_date);
    const point = Number(row.predicted_price);
    if (!isIsoDate(date) || date <= lastActualDate || !Number.isFinite(point) || point <= 0) continue;
    const score = row.confidence_score == null ? null : Number(row.confidence_score);
    const allowedLevels = ["Very High", "High", "Moderate", "Low", "Very Low", "Insufficient data"];
    const confidenceScore = score != null && Number.isFinite(score) && score >= 0 && score <= 100
      ? score : null;
    const confidenceLevel = allowedLevels.includes(String(row.confidence_level))
      ? String(row.confidence_level) : "Insufficient data";

    byDate.set(date, {
      date,
      predicted_price: roundPrice(point),
      confidence_score: confidenceScore,
      confidence_level: confidenceLevel,
    });
  }
  const ordered = Array.from(byDate.values())
    .sort((a, b) => a.date.localeCompare(b.date));
  if (ordered[0]?.date !== addUtcDays(lastActualDate, 1)) return [];

  const contiguous: NormalizedPrediction[] = [];
  for (const row of ordered) {
    if (row.date !== addUtcDays(lastActualDate, contiguous.length + 1)) break;
    contiguous.push(row);
    if (contiguous.length === horizon) break;
  }
  return contiguous;
}

export function meanFirstWeek(predictions: NormalizedPrediction[], fallback: number): number {
  const firstWeek = predictions.slice(0, 7);
  if (firstWeek.length === 0) return roundPrice(fallback);
  return roundPrice(firstWeek.reduce((sum, row) => sum + row.predicted_price, 0) / firstWeek.length);
}

export function buildForecastData(
  historyRows: PriceHistoryRow[],
  predictions: NormalizedPrediction[],
): ForecastPoint[] {
  const dailyActuals = new Map<string, number[]>();
  for (const row of historyRows) {
    const date = dateOnly(row.report_date);
    const price = Number(row.price_index);
    if (!isIsoDate(date) || !Number.isFinite(price)) continue;
    if (!dailyActuals.has(date)) dailyActuals.set(date, []);
    dailyActuals.get(date)!.push(price);
  }

  const result: ForecastPoint[] = [];
  for (const [date, prices] of Array.from(dailyActuals.entries()).sort(([a], [b]) => a.localeCompare(b))) {
    const parsed = new Date(`${date}T00:00:00Z`);
    result.push({
      date,
      name: `${MONTH_NAMES[parsed.getUTCMonth()]} ${parsed.getUTCDate()}`,
      actual: roundPrice(prices.reduce((sum, price) => sum + price, 0) / prices.length),
      predicted: null,
    });
  }
  for (const prediction of predictions) {
    const parsed = new Date(`${prediction.date}T00:00:00Z`);
    result.push({
      date: prediction.date,
      name: `${MONTH_NAMES[parsed.getUTCMonth()]} ${parsed.getUTCDate()}`,
      actual: null,
      predicted: prediction.predicted_price,
    });
  }
  return result.sort((a, b) => a.date.localeCompare(b.date));
}

function addDays(date: string, days: number): string {
  const value = new Date(`${date}T00:00:00Z`);
  value.setUTCDate(value.getUTCDate() + days);
  return value.toISOString().slice(0, 10);
}

function periodBounds(date: string, horizon: Exclude<ForecastHorizon, "daily">) {
  if (horizon === "weekly") {
    const value = new Date(`${date}T00:00:00Z`);
    const mondayOffset = (value.getUTCDay() + 6) % 7;
    const start = addDays(date, -mondayOffset);
    return { start, end: addDays(start, 6) };
  }
  const start = `${date.slice(0, 7)}-01`;
  const nextMonth = new Date(`${start}T00:00:00Z`);
  nextMonth.setUTCMonth(nextMonth.getUTCMonth() + 1);
  return { start, end: addDays(nextMonth.toISOString().slice(0, 10), -1) };
}

function inclusiveDays(start: string, end: string): number {
  return Math.round((Date.parse(`${end}T00:00:00Z`) - Date.parse(`${start}T00:00:00Z`)) / 86_400_000) + 1;
}

function dateLabel(date: string): string {
  return new Date(`${date}T00:00:00Z`).toLocaleDateString("en-US", {
    month: "short", day: "numeric", timeZone: "UTC",
  });
}

function periodLabel(horizon: Exclude<ForecastHorizon, "daily">, start: string,
  end: string): string {
  const range = horizon === "weekly"
    ? `Week ${dateLabel(start)}–${dateLabel(end)}`
    : new Date(`${start}T00:00:00Z`).toLocaleDateString("en-US", {
      month: "long", year: "numeric", timeZone: "UTC",
    });
  return range;
}

/**
 * Return the daily path plus persisted weekly/monthly point forecasts and
 * closed-period historical averages. Weekly periods are Monday–Sunday;
 * monthly periods are calendar months. Partial forecast periods retain their
 * backend coverage counts and are never reconstructed from the daily series.
 */
export function buildForecastSequenceData(
  historyRows: PriceHistoryRow[],
  predictions: NormalizedPrediction[],
  origin: string,
  savedPeriods: SavedPeriodPrediction[] = [],
): ForecastPoint[] {
  const predictionByDate = new Map(predictions.map(row => [row.date, row]));
  const daily = buildForecastData(historyRows, predictions).map((point) => ({
    ...point,
    horizon: "daily" as const,
    target_period_start: point.date,
    target_period_end: point.date,
    ...(point.predicted == null ? {} : { forecast_step: predictions.findIndex(row => row.date === point.date) + 1,
      covered_days: 1, period_days: 1,
      confidence_score: predictionByDate.get(point.date)?.confidence_score ?? null,
      confidence_level: predictionByDate.get(point.date)?.confidence_level ?? "Insufficient data" }),
  }));
  const result: ForecastPoint[] = [...daily];

  for (const horizon of ["weekly", "monthly"] as const) {
    const actualByPeriod = new Map<string, { start: string; end: string; values: number[] }>();
    const dailyActuals = new Map<string, number[]>();
    for (const row of historyRows) {
      const date = dateOnly(row.report_date);
      const price = Number(row.price_index);
      if (!isIsoDate(date) || date > origin || !Number.isFinite(price)) continue;
      dailyActuals.set(date, [...(dailyActuals.get(date) ?? []), price]);
    }
    for (const [date, values] of dailyActuals) {
      const { start, end } = periodBounds(date, horizon);
      // Do not place a historical partial period on the same chart date as its
      // forecast continuation. Historical periods are closed before origin.
      if (end > origin) continue;
      const entry = actualByPeriod.get(start) ?? { start, end, values: [] };
      entry.values.push(values.reduce((sum, value) => sum + value, 0) / values.length);
      actualByPeriod.set(start, entry);
    }
    for (const period of actualByPeriod.values()) {
      const periodDays = inclusiveDays(period.start, period.end);
      result.push({
        date: period.end,
        name: periodLabel(horizon, period.start, period.end),
        actual: roundPrice(period.values.reduce((sum, value) => sum + value, 0) / period.values.length),
        predicted: null,
        horizon,
        target_period_start: period.start,
        target_period_end: period.end,
        covered_days: period.values.length,
        period_days: periodDays,
      });
    }

    const ordered = savedPeriods.filter((row) => row.forecast_horizon === horizon)
      .filter((row) => isIsoDate(row.date) && row.date > origin
        && isIsoDate(row.target_period_start) && isIsoDate(row.target_period_end)
        && row.target_period_start <= row.target_period_end
        && Number.isInteger(row.forecast_step) && row.forecast_step > 0
        && Number.isInteger(row.covered_days) && row.covered_days > 0
        && Number.isInteger(row.period_days) && row.period_days >= row.covered_days
        && Number.isFinite(row.predicted_price) && row.predicted_price > 0)
      .sort((left, right) => left.forecast_step - right.forecast_step);
    ordered.forEach((period) => {
      result.push({
        date: period.date,
        name: periodLabel(horizon, period.target_period_start, period.target_period_end),
        actual: null,
        predicted: roundPrice(period.predicted_price),
        horizon,
        target_period_start: period.target_period_start,
        target_period_end: period.target_period_end,
        forecast_step: period.forecast_step,
        covered_days: period.covered_days,
        period_days: period.period_days,
        confidence_score: period.confidence_score ?? null,
        confidence_level: period.confidence_level ?? "Insufficient data",
      });
    });
  }

  return result.sort((left, right) => left.date.localeCompare(right.date)
    || (left.horizon ?? "daily").localeCompare(right.horizon ?? "daily"));
}
