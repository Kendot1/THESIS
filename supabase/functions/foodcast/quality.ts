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

const HORIZON_BUCKETS = {
  days_1_7: [1, 7], days_8_14: [8, 14], days_15_30: [15, 30],
} as const
type HorizonBucket = keyof typeof HORIZON_BUCKETS
type ScoredForecast = {
  runId: string; timestamp: number; productId: string; lower: number;
  upper: number; actual: number; point: number; leadDays: number; targetDate: string
}

// Estimate how many independent Bernoulli outcomes the date sequence contains.
// Positive autocorrelation widens the interval; negative correlation never
// makes it narrower than the independent-outcome Wilson interval.
function effectiveCoverageSampleSize(rows: ScoredForecast[]): number | null {
  if (rows.length < 2) return null
  const ordered = [...rows].sort((a, b) => a.targetDate.localeCompare(b.targetDate))
  const observations = new Map<string, number>()
  let hits = 0
  for (const row of ordered) {
    const date = row.targetDate
    const hit = Number(row.lower <= row.actual && row.actual <= row.upper)
    observations.set(date, hit)
    hits += hit
  }
  const count = observations.size
  if (count < 2) return null
  const rate = hits / count
  const variance = rate * (1 - rate)
  // A constant hit sequence cannot identify its own serial correlation.
  if (variance === 0) return null
  const byDate = observations
  let inflation = 1
  const maxLag = Math.min(7, count - 1)
  for (let lag = 1; lag <= maxLag; lag++) {
    let covariance = 0
    let pairs = 0
    for (const [date, value] of byDate) {
      const day = new Date(`${date}T00:00:00Z`)
      const next = new Date(day.getTime() + lag * 86_400_000).toISOString().slice(0, 10)
      const nextValue = byDate.get(next)
      if (nextValue === undefined) continue
      covariance += (value - rate) * (nextValue - rate)
      pairs++
    }
    if (pairs < 3) continue
    const correlation = covariance / pairs / variance
    inflation += 2 * Math.max(0, correlation) * (1 - lag / (maxLag + 1))
  }
  return Math.max(1, Math.min(count, count / inflation))
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

function horizonQuality(rows: ScoredForecast[], bucket: HorizonBucket) {
  const count = rows.length
  const covered = rows.filter((row) => row.lower <= row.actual && row.actual <= row.upper).length
  const errors = rows.map((row) => Math.abs(row.point - row.actual))
  return {
    interval_coverage: covered / count, interval_level: 0.8,
    covered_count: covered, sample_count: count, coverage_sample_count: count,
    effective_sample_count: effectiveCoverageSampleSize(rows),
    coverage_uncertainty_method: "positive_serial_wilson_7d",
    coverage_uncertainty_approximate: true,
    // Sensitivity simulations show substantial undercoverage for persistent
    // hit/miss sequences. Keep the estimate diagnostic until calibrated.
    coverage_uncertainty_validated: false,
    sample_basis: "unique_actual_dates",
    evaluation_source: "realized_vintages",
    horizon_min_days: HORIZON_BUCKETS[bucket][0],
    horizon_max_days: HORIZON_BUCKETS[bucket][1],
    horizon_basis: "philippine_publication_date",
    observed_min_lead_days: Math.min(...rows.map((row) => row.leadDays)),
    observed_max_lead_days: Math.max(...rows.map((row) => row.leadDays)),
    mae: errors.reduce((sum, value) => sum + value, 0) / count,
    rmse: Math.sqrt(errors.reduce((sum, value) => sum + value ** 2, 0) / count),
    mape: errors.reduce((sum, value, index) => sum + value / rows[index].actual, 0) / count * 100,
  }
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

export function realizedForecastQuality(
  runs: QualityRun[],
  forecasts: QualityForecast[],
  products: QualityProduct[],
  prices: QualityPrice[],
) {
  // A run identifier must have one unambiguous publication instant.
  const conflictingRuns = new Set<string>()
  const runTimes = new Map<string, number>()
  for (const run of runs) {
    const timestamp = Date.parse(run.generated_at)
    if (!Number.isFinite(timestamp) ||
        (runTimes.has(run.id) && runTimes.get(run.id) !== timestamp)) conflictingRuns.add(run.id)
    runTimes.set(run.id, timestamp)
  }
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
  const latestByProductDate = new Map<string, ScoredForecast>()
  // Separate maps retain long-lead evidence even when a later short-lead
  // forecast exists for the same actual date. Never pool these maps: their
  // outcomes overlap across lead-time buckets.
  const latestByHorizon = new Map<string, ScoredForecast>()
  const uniqueForecasts = new Map<string, QualityForecast>()
  const conflictingForecasts = new Set<string>()
  for (const row of forecasts) {
    const key = JSON.stringify([row.run_id, row.product_id, dateOnly(row.prediction_date)])
    const previous = uniqueForecasts.get(key)
    if (previous && (Number(previous.predicted_price) !== Number(row.predicted_price) ||
        Number(previous.lower_bound) !== Number(row.lower_bound) ||
        Number(previous.upper_bound) !== Number(row.upper_bound))) conflictingForecasts.add(key)
    uniqueForecasts.set(key, row)
  }
  for (const [forecastKey, row] of uniqueForecasts) {
    if (conflictingForecasts.has(forecastKey) || conflictingRuns.has(row.run_id)) continue
    const run = generatedByRun.get(row.run_id)
    const product = productById.get(row.product_id)
    const predictionDate = dateOnly(row.prediction_date)
    const lower = Number(row.lower_bound)
    const upper = Number(row.upper_bound)
    const point = Number(row.predicted_price)
    if (!run || !Number.isFinite(run.timestamp) || !product || !validCalendarDate(predictionDate) ||
        predictionDate <= run.date || !Number.isFinite(lower) ||
        !Number.isFinite(upper) || lower <= 0 || upper < lower ||
        !Number.isFinite(point) || point <= 0 || point < lower || point > upper) continue
    const actualKey = `${seriesKey(product)}|${predictionDate}`
    if (ambiguousActuals.has(actualKey)) continue
    const actual = actualBySeriesDate.get(actualKey)
    if (actual === undefined) continue
    const leadDays = (Date.parse(`${predictionDate}T00:00:00Z`) -
      Date.parse(`${run.date}T00:00:00Z`)) / 86_400_000
    if (!Number.isInteger(leadDays) || leadDays < 1) continue
    const key = `${row.product_id}|${predictionDate}`
    const scored = { runId: row.run_id, timestamp: run.timestamp,
      productId: row.product_id, lower, upper, actual, point, leadDays, targetDate: predictionDate }
    keepLatest(latestByProductDate, key, scored)
    const bucket = horizonBucket(leadDays)
    if (bucket) keepLatest(latestByHorizon, `${key}|${bucket}`, scored)
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
  const byProductHorizon = new Map<string, Map<HorizonBucket, ScoredForecast[]>>()
  for (const row of latestByHorizon.values()) {
    const bucket = horizonBucket(row.leadDays)!
    const buckets = byProductHorizon.get(row.productId) ?? new Map<HorizonBucket, ScoredForecast[]>()
    const rows = buckets.get(bucket) ?? []
    rows.push(row)
    buckets.set(bucket, rows)
    byProductHorizon.set(row.productId, buckets)
  }
  return {
    mae: absoluteError / total,
    rmse: Math.sqrt(squaredError / total),
    mape: percentageError / total * 100,
    directional_accuracy: null,
    interval_level: 0.8,
    prediction_success: successes / total,
    success_tolerance: SUCCESS_TOLERANCE,
    success_definition: "absolute_percentage_error_at_most_tolerance",
    interval_coverage: covered / total,
    covered_count: covered,
    sample_count: total,
    coverage_sample_count: total,
    product_metrics: Object.fromEntries(Array.from(counts, ([id, count]) => [id, {
      interval_coverage: count.covered / count.total,
      covered_count: count.covered,
      interval_level: 0.8,
      sample_count: count.total,
      sample_basis: "unique_actual_dates",
      prediction_success: count.successes / count.total,
      mape: count.percentageError / count.total * 100,
      evaluation_source: "realized_vintages",
      horizon_metrics: Object.fromEntries(Array.from(byProductHorizon.get(id) ?? [],
        ([bucket, rows]) => [bucket, horizonQuality(rows, bucket)])),
    }])),
    evaluation_scope: "Overall: latest forecast before each Philippine observation date, one sample per product/date. Product horizon metrics: latest forecast within each lead-time bucket, one sample per product/date/bucket; buckets share outcomes and must not be pooled. Point success within 5% of actual price.",
    evaluation_source: "realized_vintages",
  }
}
