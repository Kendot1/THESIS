import { productSeriesKey } from "./dashboard.ts"

export interface QualityRun {
  id: string
  generated_at: string
}

export interface QualityForecast {
  run_id: string
  product_id: string
  prediction_date: string
  predicted_price: number
  lower_bound: number
  upper_bound: number
}

export interface QualityPrice {
  product_name: string
  product_category: string | null
  product_variant: string | null
  origin: string | null
  unit: string | null
  report_date: string
  price_index: number
  source_pdf: string | null
}

export interface QualityProduct {
  id: string
  name: string
  variant: string | null
  origin: string | null
  category: string | null
  unit: string | null
}

const MONTHS: Record<string, number> = {
  january: 1, february: 2, march: 3, april: 4, may: 5, june: 6,
  july: 7, august: 8, september: 9, october: 10, november: 11, december: 12,
}

export const SUCCESS_TOLERANCE = 0.05

function seriesKey(row: QualityProduct | QualityPrice): string {
  const category = 'product_category' in row ? row.product_category : row.category
  return `${category ?? ''}|${productSeriesKey(row)}`
}

function dateOnly(value: string): string {
  return String(value ?? "").split("T")[0]
}

// Copied prices used to fill missing days are not new DA observations.
function observedSourceDate(sourcePdf: string | null): string | null {
  const match = String(sourcePdf ?? "").match(/([A-Za-z]+)-(\d{1,2})-(\d{4})/)
  if (!match) return null
  const month = MONTHS[match[1].toLowerCase()]
  const day = Number(match[2])
  const year = Number(match[3])
  if (!month || day < 1 || day > 31) return null
  const date = new Date(Date.UTC(year, month - 1, day))
  if (date.getUTCFullYear() !== year || date.getUTCMonth() + 1 !== month ||
      date.getUTCDate() !== day) return null
  return date.toISOString().slice(0, 10)
}

export function realizedForecastQuality(
  runs: QualityRun[],
  forecasts: QualityForecast[],
  products: QualityProduct[],
  prices: QualityPrice[],
) {
  const generatedByRun = new Map(runs.map((run) => [run.id, {
    timestamp: Date.parse(run.generated_at),
    // DA observations have Philippine calendar dates (UTC+8).
    date: Number.isFinite(Date.parse(run.generated_at))
      ? new Date(Date.parse(run.generated_at) + 8 * 60 * 60_000).toISOString().slice(0, 10)
      : '',
  }]))
  const productById = new Map(products.map((product) => [product.id, product]))
  const actualBySeriesDate = new Map<string, number>()
  const ambiguousActuals = new Set<string>()
  for (const row of prices) {
    const reportDate = dateOnly(row.report_date)
    const price = Number(row.price_index)
    if (observedSourceDate(row.source_pdf) !== reportDate ||
        !Number.isFinite(price) || price <= 0) continue
    const key = `${seriesKey(row)}|${reportDate}`
    if (actualBySeriesDate.has(key) && actualBySeriesDate.get(key) !== price) {
      ambiguousActuals.add(key)
    } else {
      actualBySeriesDate.set(key, price)
    }
  }

  // A target price is one observation even if the pipeline published several
  // forecasts for that product and date. Use the latest forecast made before
  // the observed date, so reruns do not multiply the evidence.
  const latestByProductDate = new Map<string, {
    runId: string; timestamp: number; productId: string; lower: number;
    upper: number; actual: number; point: number
  }>()
  for (const row of forecasts) {
    const run = generatedByRun.get(row.run_id)
    const product = productById.get(row.product_id)
    const predictionDate = dateOnly(row.prediction_date)
    const lower = Number(row.lower_bound)
    const upper = Number(row.upper_bound)
    const point = Number(row.predicted_price)
    if (!run || !Number.isFinite(run.timestamp) || !product ||
        predictionDate <= run.date || !Number.isFinite(lower) ||
        !Number.isFinite(upper) || lower <= 0 || upper < lower ||
        !Number.isFinite(point) || point <= 0 || point < lower || point > upper) continue
    const actualKey = `${seriesKey(product)}|${predictionDate}`
    if (ambiguousActuals.has(actualKey)) continue
    const actual = actualBySeriesDate.get(actualKey)
    if (actual === undefined) continue
    const key = `${row.product_id}|${predictionDate}`
    const previous = latestByProductDate.get(key)
    if (!previous || run.timestamp > previous.timestamp ||
        (run.timestamp === previous.timestamp && row.run_id > previous.runId)) {
      latestByProductDate.set(key, {
        runId: row.run_id, timestamp: run.timestamp, productId: row.product_id,
        lower, upper, actual, point,
      })
    }
  }

  const counts = new Map<string, { covered: number; successes: number; total: number;
    absoluteError: number; squaredError: number; percentageError: number }>()
  let covered = 0
  let total = 0
  let successes = 0
  let absoluteError = 0
  let squaredError = 0
  let percentageError = 0
  for (const row of latestByProductDate.values()) {
    const hit = Number(row.lower <= row.actual && row.actual <= row.upper)
    const error = Math.abs(row.point - row.actual)
    const relativeError = error / row.actual
    const success = Number(relativeError <= SUCCESS_TOLERANCE)
    const count = counts.get(row.productId) ?? { covered: 0, successes: 0, total: 0,
      absoluteError: 0, squaredError: 0, percentageError: 0 }
    count.covered += hit
    count.total += 1
    count.successes += success
    count.absoluteError += error
    count.squaredError += error ** 2
    count.percentageError += relativeError
    counts.set(row.productId, count)
    covered += hit
    total += 1
    successes += success
    absoluteError += error
    squaredError += error ** 2
    percentageError += relativeError
  }

  if (!total) return null
  return {
    mae: absoluteError / total,
    rmse: Math.sqrt(squaredError / total),
    mape: percentageError / total * 100,
    directional_accuracy: null,
    interval_level: null,
    prediction_success: successes / total,
    success_tolerance: SUCCESS_TOLERANCE,
    success_definition: "absolute_percentage_error_at_most_tolerance",
    interval_coverage: covered / total,
    sample_count: total,
    coverage_sample_count: total,
    product_metrics: Object.fromEntries(Array.from(counts, ([id, count]) => [id, {
      interval_coverage: count.covered / count.total,
      sample_count: count.total,
      sample_basis: "unique_actual_dates",
      prediction_success: count.successes / count.total,
      mape: count.percentageError / count.total * 100,
      evaluation_source: "realized_vintages",
    }])),
    evaluation_scope: "Latest forecast before each Philippine observation date, one sample per product/date; point success within 5% of actual price",
    evaluation_source: "realized_vintages",
  }
}
