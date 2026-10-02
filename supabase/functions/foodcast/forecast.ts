export interface PriceHistoryRow {
  report_date: string;
  price_index: number;
}

export interface PredictionRow {
  prediction_date: string;
  predicted_price: number;
  lower_bound?: number | null;
  upper_bound?: number | null;
}

export interface NormalizedPrediction {
  date: string;
  predicted_price: number;
  lower_bound: number | null;
  upper_bound: number | null;
}

export interface ForecastPoint {
  date: string;
  name: string;
  actual: number | null;
  predicted: number | null;
  lower: number | null;
  upper: number | null;
}

const MONTH_NAMES = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

export function dateOnly(value: string): string {
  return String(value || "").split("T")[0];
}

function isIsoDate(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) &&
    Number.isFinite(Date.parse(`${value}T00:00:00Z`));
}

function roundPrice(value: number): number {
  return Math.round(value * 100) / 100;
}

export function addUtcDays(date: string, days: number): string {
  const parsed = new Date(`${date}T00:00:00Z`);
  parsed.setUTCDate(parsed.getUTCDate() + days);
  return parsed.toISOString().split("T")[0];
}

/** Keep only predictions that are still in the future for this series. */
export function selectFuturePredictions(
  predictions: PredictionRow[],
  lastActualDate: string,
  horizon = 30,
): NormalizedPrediction[] {
  const byDate = new Map<string, NormalizedPrediction>();
  for (const row of predictions || []) {
    const date = dateOnly(row.prediction_date);
    const point = Number(row.predicted_price);
    if (!isIsoDate(date) || date <= lastActualDate || !Number.isFinite(point) || point <= 0) continue;

    const rawLower = Number(row.lower_bound);
    const rawUpper = Number(row.upper_bound);
    const hasInterval = Number.isFinite(rawLower) && Number.isFinite(rawUpper) && rawLower > 0 && rawUpper > 0;
    byDate.set(date, {
      date,
      predicted_price: roundPrice(point),
      lower_bound: hasInterval ? roundPrice(Math.min(rawLower, point)) : null,
      upper_bound: hasInterval ? roundPrice(Math.max(rawUpper, point)) : null,
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

export function makeTrendFallback(
  lastActualDate: string,
  currentPrice: number,
  recentPrices: number[],
  horizon = 30,
): NormalizedPrediction[] {
  void recentPrices;
  const point = roundPrice(Math.max(0.01, Number(currentPrice)));
  return Array.from({ length: horizon }, (_, index) => ({
    date: addUtcDays(lastActualDate, index + 1),
    predicted_price: point,
    lower_bound: null,
    upper_bound: null,
  }));
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
      lower: null,
      upper: null,
    });
  }
  for (const prediction of predictions) {
    const parsed = new Date(`${prediction.date}T00:00:00Z`);
    result.push({
      date: prediction.date,
      name: `${MONTH_NAMES[parsed.getUTCMonth()]} ${parsed.getUTCDate()}`,
      actual: null,
      predicted: prediction.predicted_price,
      lower: prediction.lower_bound,
      upper: prediction.upper_bound,
    });
  }
  return result.sort((a, b) => a.date.localeCompare(b.date));
}
