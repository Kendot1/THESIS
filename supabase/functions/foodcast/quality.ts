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
  forecast_origin_date: string
  forecast_horizon: string
  forecast_step: number
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
const MIN_MAPE_ACTUAL = 1e-8

const HORIZON_BUCKETS = {
  days_1_7: [1, 7], days_8_14: [8, 14], days_15_30: [15, 30],
} as const
type HorizonBucket = keyof typeof HORIZON_BUCKETS
type ScoredForecast = {
  runId: string; timestamp: number; productId: string; actual: number;
  point: number; leadDays: number; targetDate: string
}

function horizonBucket(days: number): HorizonBucket | null {
  return (Object.keys(HORIZON_BUCKETS) as HorizonBucket[]).find((key) => {
    const [minimum, maximum] = HORIZON_BUCKETS[key]
    return days >= minimum && days <= maximum
  }) ?? null
}

function keepLatest(map: Map<string, ScoredForecast>, key: string, row: ScoredForecast) {
  const previous = map.get(key)
  if (!previous || row.timestamp > previous.timestamp ||
      (row.timestamp === previous.timestamp && row.runId > previous.runId)) map.set(key, row)
}

function seriesKey(row: QualityProduct | QualityPrice): string {
  const category = 'product_category' in row ? row.product_category : row.category
  return `${category ?? ''}|${productSeriesKey(row)}`
}

function dateOnly(value: string): string {
  return String(value ?? "").split("T")[0]
}

function validCalendarDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const parsed = Date.parse(`${value}T00:00:00Z`)
  return Number.isFinite(parsed) && new Date(parsed).toISOString().slice(0, 10) === value
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

function summarize(rows: ScoredForecast[]) {
  if (!rows.length) return null
  const errors = rows.map((row) => Math.abs(row.point - row.actual))
  const percentageErrors = rows.map((row, index) => errors[index] / row.actual * 100)
  const successes = rows.filter((row, index) => percentageErrors[index] / 100 <= SUCCESS_TOLERANCE).length
  return {
    mae: errors.reduce((sum, value) => sum + value, 0) / rows.length,
    rmse: Math.sqrt(errors.reduce((sum, value) => sum + value ** 2, 0) / rows.length),
    mape: percentageErrors.reduce((sum, value) => sum + value, 0) / rows.length,
    prediction_success: successes / rows.length,
    success_tolerance: SUCCESS_TOLERANCE,
    success_definition: "absolute_percentage_error_at_most_tolerance",
    sample_count: rows.length,
    sample_basis: "unique_observed_product_dates",
  }
}

export function realizedForecastQuality(
  runs: QualityRun[],
  forecasts: QualityForecast[],
  products: QualityProduct[],
  prices: QualityPrice[],
) {
  const runTimes = new Map<string, number>()
  const conflictingRuns = new Set<string>()
  for (const run of runs) {
    const timestamp = Date.parse(run.generated_at)
    if (!Number.isFinite(timestamp) ||
        (runTimes.has(run.id) && runTimes.get(run.id) !== timestamp)) conflictingRuns.add(run.id)
    runTimes.set(run.id, timestamp)
  }

  const productById = new Map(products.map((product) => [product.id, product]))
  const actualBySeriesDate = new Map<string, number>()
  const ambiguousActuals = new Set<string>()
  for (const row of prices) {
    const reportDate = dateOnly(row.report_date)
    const price = Number(row.price_index)
    if (observedSourceDate(row.source_pdf) !== reportDate || !Number.isFinite(price)
        || price < MIN_MAPE_ACTUAL) continue
    const key = `${seriesKey(row)}|${reportDate}`
    if (actualBySeriesDate.has(key) && actualBySeriesDate.get(key) !== price) ambiguousActuals.add(key)
    else actualBySeriesDate.set(key, price)
  }

  const uniqueForecasts = new Map<string, QualityForecast>()
  const conflictingForecasts = new Set<string>()
  for (const row of forecasts) {
    if (row.forecast_horizon !== "daily") continue
    const key = JSON.stringify([row.run_id, row.product_id, dateOnly(row.prediction_date)])
    const previous = uniqueForecasts.get(key)
    if (previous && Number(previous.predicted_price) !== Number(row.predicted_price)) conflictingForecasts.add(key)
    uniqueForecasts.set(key, row)
  }

  const latestByProductDate = new Map<string, ScoredForecast>()
  const latestByHorizon = new Map<string, ScoredForecast>()
  for (const [forecastKey, row] of uniqueForecasts) {
    if (conflictingForecasts.has(forecastKey) || conflictingRuns.has(row.run_id)) continue
    const timestamp = runTimes.get(row.run_id)
    const product = productById.get(row.product_id)
    const targetDate = dateOnly(row.prediction_date)
    const originDate = dateOnly(row.forecast_origin_date)
    const point = Number(row.predicted_price)
    if (timestamp == null || !Number.isFinite(timestamp) || !product ||
        !validCalendarDate(originDate) || !validCalendarDate(targetDate) || targetDate <= originDate ||
        !Number.isFinite(point) || point <= 0) continue
    const actualKey = `${seriesKey(product)}|${targetDate}`
    if (ambiguousActuals.has(actualKey)) continue
    const actual = actualBySeriesDate.get(actualKey)
    if (actual === undefined) continue
    const leadDays = (Date.parse(`${targetDate}T00:00:00Z`) -
      Date.parse(`${originDate}T00:00:00Z`)) / 86_400_000
    if (!Number.isInteger(leadDays) || leadDays < 1 || leadDays > 30) continue
    const scored = { runId: row.run_id, timestamp, productId: row.product_id,
      actual, point, leadDays, targetDate }
    const key = `${row.product_id}|${targetDate}`
    keepLatest(latestByProductDate, key, scored)
    const bucket = horizonBucket(leadDays)
    if (bucket) keepLatest(latestByHorizon, `${key}|${bucket}`, scored)
  }

  const overallRows = [...latestByProductDate.values()]
  const productHorizonRows = new Map<string, Map<HorizonBucket, ScoredForecast[]>>()
  for (const row of latestByHorizon.values()) {
    const bucket = horizonBucket(row.leadDays)!
    const buckets = productHorizonRows.get(row.productId) ?? new Map<HorizonBucket, ScoredForecast[]>()
    const rows = buckets.get(bucket) ?? []
    rows.push(row)
    buckets.set(bucket, rows)
    productHorizonRows.set(row.productId, buckets)
  }
  const byProduct = new Map<string, ScoredForecast[]>()
  for (const row of overallRows) {
    const rows = byProduct.get(row.productId) ?? []
    rows.push(row)
    byProduct.set(row.productId, rows)
  }
  const overall = summarize(overallRows)
  if (!overall) return null
  return {
    ...overall,
    directional_accuracy: null,
    product_metrics: Object.fromEntries(Array.from(byProduct, ([id, rows]) => [id, {
      ...summarize(rows),
      evaluation_source: "realized_vintages",
      horizon_metrics: Object.fromEntries(Array.from(productHorizonRows.get(id) ?? [],
        ([bucket, horizonRows]) => [bucket, {
          ...summarize(horizonRows),
          horizon_min_days: HORIZON_BUCKETS[bucket][0],
          horizon_max_days: HORIZON_BUCKETS[bucket][1],
        }])),
    }])),
    evaluation_scope: "Latest daily forecast before each observed Philippine product date; one sample per product/date. Zero or near-zero actuals below 1e-8 are excluded because MAPE is undefined. Horizon buckets are kept separate and overlap in outcomes.",
    evaluation_source: "realized_vintages",
  }
}
