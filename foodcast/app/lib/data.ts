export const DEFAULT_PRODUCT_IMAGE = "https://images.unsplash.com/photo-1610348725531-843dff563e2c?auto=format&fit=crop&q=80&w=800";

// ─── Types ─────────────────────────────────────────────────

export interface ForecastDataPoint {
  date: string;
  name: string;
  actual: number | null;
  predicted: number | null;
  horizon?: ForecastHorizon;
  target_period_start?: string;
  target_period_end?: string;
  forecast_step?: number;
  covered_days?: number;
  period_days?: number;
  confidence_score?: number | null;
  confidence_level?: string | null;
}

export interface Product {
  id: string;
  name: string;
  description: string;
  category: string;
  image: string;
  variant: string;
  origin: string;
  currentPrice: number;
  predictedPrice: number;
  previousPrice: number;
  volume: string;
  unit: string;
  sentiment: "Bullish" | "Bearish" | "Neutral";
  sparklineData: { value: number }[];
  forecastData: ForecastDataPoint[];
  dailyForecast: {
    date: string;
    predicted_price: number;
    reasoning: string;
  }[];
  forecastSource?: "model" | "trend_fallback";
  forecastOriginDate?: string;
  forecastModelRunId?: string;
  lastActualDate?: string;
}

export interface ForecastQualityMetrics {
  mae: number | null;
  rmse: number | null;
  mape: number | null;
  directional_accuracy: number | null;
  prediction_success: number | null;
  success_tolerance?: number | null;
  success_definition?: string;
  within_10_tolerance?: number | null;
  within_10_definition?: string;
  within_10_accuracy_pct?: number | null;
  within_10_count?: number | null;
  within_10_sample_count?: number | null;
  metric_aggregation?: string;
  training_through?: string | null;
  sample_count: number | null;
  processed_from?: string | null;
  processed_through?: string | null;
  processed_observed_rows?: number | null;
  processed_series_count?: number | null;
  product_metrics?: Record<string, {
    sample_count: number;
    sample_origin_count?: number;
    sample_basis?: string;
    mape?: number | null;
    prediction_success?: number | null;
    evaluation_source?: string;
    confidence_by_horizon?: Partial<Record<ForecastHorizon, ForecastConfidenceMetric>>;
    confidence_by_step?: Partial<Record<ForecastHorizon, Record<number, ForecastStepConfidenceMetric>>>;
    horizon_metrics?: Record<string, {
      mae: number | null;
      rmse: number | null;
      mape: number | null;
      prediction_success?: number | null;
      sample_count: number;
      horizon_min_days?: number;
      horizon_max_days?: number;
    }>;
  }>;
  evaluation_scope?: string | null;
  evaluation_source?: string | null;
}

export type ForecastHorizon = "daily" | "weekly" | "monthly";

export interface ForecastConfidenceMetric {
  forecast_horizon_days: 1 | 7 | 30;
  confidence_score: number | null;
  confidence_level: "Very High" | "High" | "Moderate" | "Low" | "Very Low" | "Insufficient data";
  mae: number | null;
  rmse: number | null;
  mape: number | null;
  sample_count: number;
  sample_origin_count?: number;
  sample_support?: number;
  evaluation_source: "chronological_validation";
  confidence_method: string;
  model_version: string;
  evidence_status: "validated" | "insufficient_data" | "unverified_provenance";
}

export interface ForecastStepConfidenceMetric extends Omit<ForecastConfidenceMetric, "forecast_horizon_days"> {
  forecast_horizon_days: number;
  forecast_step: number;
}

export interface HorizonAccuracySummary {
  within_tolerance_count: number;
  sample_count: number;
  mae: number;
  rmse: number;
  mape: number;
}

export interface HistoricalForecastAccuracy {
  model_run_id: string;
  tolerance: number;
  within_tolerance_count: number;
  sample_count: number;
  mae: number;
  rmse: number;
  mape: number;
  evaluation_source: string;
  window_start: string;
  window_end: string;
  aggregation: string;
  development_test_reused_for_selection: boolean;
  horizons: Record<ForecastHorizon, HorizonAccuracySummary>;
}

/** Accept only the publisher-aligned, model-bound Within-10% backtest summary. */
export function verifiedHistoricalAccuracy(
  benchmark: HistoricalForecastAccuracy | null | undefined,
  modelRunId: string | null | undefined,
): HistoricalForecastAccuracy | null {
  if (!benchmark || !modelRunId || benchmark.model_run_id !== modelRunId
    || benchmark.tolerance !== 0.1
    || benchmark.evaluation_source !== "chronological_development_test"
    || benchmark.aggregation !== "row_weighted_pooled_published_horizons"
    || typeof benchmark.development_test_reused_for_selection !== "boolean"
    || !/^\d{4}-\d{2}-\d{2}$/.test(benchmark.window_start)
    || !/^\d{4}-\d{2}-\d{2}$/.test(benchmark.window_end)
    || benchmark.window_end < benchmark.window_start) return null;

  const finiteNonnegative = (value: number) => Number.isFinite(value) && value >= 0;
  const horizonMetrics = [benchmark.horizons?.daily, benchmark.horizons?.weekly, benchmark.horizons?.monthly]
    .filter((metric): metric is HorizonAccuracySummary => Boolean(metric));
  if (horizonMetrics.length !== 3 || horizonMetrics.some(metric =>
    !Number.isInteger(metric.sample_count) || metric.sample_count <= 0
    || !Number.isInteger(metric.within_tolerance_count) || metric.within_tolerance_count < 0
    || metric.within_tolerance_count > metric.sample_count
    || [metric.mae, metric.rmse, metric.mape].some(value => !finiteNonnegative(value)))) return null;

  const samples = horizonMetrics.reduce((total, metric) => total + metric.sample_count, 0);
  const successes = horizonMetrics.reduce((total, metric) => total + metric.within_tolerance_count, 0);
  if (samples !== benchmark.sample_count || successes !== benchmark.within_tolerance_count
    || !Number.isInteger(benchmark.sample_count) || benchmark.sample_count <= 0
    || !finiteNonnegative(benchmark.mae) || !finiteNonnegative(benchmark.rmse)
    || !finiteNonnegative(benchmark.mape)) return null;
  return benchmark;
}

export const FORECAST_HORIZON_DAYS = { daily: 1, weekly: 7, monthly: 30 } as const;
const PUBLISHED_FORECAST_MONTHS = 3;

/** Calendar lead time is measured from the saved backend vintage, never row position. */
export function forecastTargetDate(origin: string | undefined, horizon: ForecastHorizon): string | null {
  if (!origin || !/^\d{4}-\d{2}-\d{2}$/.test(origin)) return null;
  const timestamp = Date.parse(`${origin}T00:00:00Z`);
  if (!Number.isFinite(timestamp) || new Date(timestamp).toISOString().slice(0, 10) !== origin) return null;
  return new Date(timestamp + FORECAST_HORIZON_DAYS[horizon] * 86400000).toISOString().slice(0, 10);
}

/** Use saved period prices, filling missing periods from the same daily model path. */
export function forecastHorizonPoints(data: ForecastDataPoint[], origin: string | undefined, horizon: ForecastHorizon) {
  if (!forecastTargetDate(origin, "daily")) return [];
  const points = data.filter(point => {
    const timestamp = Date.parse(`${point.date}T00:00:00Z`);
    const lead = (timestamp - Date.parse(`${origin}T00:00:00Z`)) / 86400000;
    const legacyDaily = !point.horizon && horizon === "daily";
    return (point.horizon === horizon || legacyDaily) && Number.isInteger(lead) && lead > 0
      && new Date(timestamp).toISOString().slice(0, 10) === point.date
      && point.predicted != null && Number.isFinite(point.predicted) && point.predicted > 0;
    })
    .sort((left, right) => left.date.localeCompare(right.date));
  if (horizon === "daily") return points;

  // Older published vintages can have the daily path without saved calendar
  // period rows. Fill only missing weeks/months from those same model prices.
  const periods = new Map<string, ForecastDataPoint>();
  for (const point of points) periods.set(point.target_period_start ?? point.date, point);
  const dailyForecasts = data.filter(point => {
    const timestamp = Date.parse(`${point.date}T00:00:00Z`);
    const lead = (timestamp - Date.parse(`${origin}T00:00:00Z`)) / 86400000;
    return (point.horizon === "daily" || !point.horizon)
      && Number.isInteger(lead) && lead > 0
      && new Date(timestamp).toISOString().slice(0, 10) === point.date
      && point.predicted != null && Number.isFinite(point.predicted) && point.predicted > 0;
  }).sort((left, right) => left.date.localeCompare(right.date));
  const grouped = new Map<string, { start: string; end: string; values: number[]; lastDate: string }>();
  for (const point of dailyForecasts) {
    const date = new Date(`${point.date}T00:00:00Z`);
    let start: Date;
    let end: Date;
    if (horizon === "weekly") {
      start = new Date(date);
      start.setUTCDate(start.getUTCDate() - ((start.getUTCDay() + 6) % 7));
      end = new Date(start);
      end.setUTCDate(end.getUTCDate() + 6);
    } else {
      start = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), 1));
      end = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 0));
    }
    const startDate = start.toISOString().slice(0, 10);
    const endDate = end.toISOString().slice(0, 10);
    const group = grouped.get(startDate) ?? { start: startDate, end: endDate, values: [], lastDate: point.date };
    group.values.push(point.predicted!);
    group.lastDate = point.date;
    grouped.set(startDate, group);
  }
  const labelDate = (value: string, options: Intl.DateTimeFormatOptions) =>
    new Date(`${value}T00:00:00Z`).toLocaleDateString("en-US", { ...options, timeZone: "UTC" });
  const derived = [...grouped.values()].sort((left, right) => left.start.localeCompare(right.start));
  derived.forEach((period, index) => {
    if (periods.has(period.start)) return;
    const name = horizon === "weekly"
      ? `Week ${labelDate(period.start, { month: "short", day: "numeric" })}–${labelDate(period.end, { month: "short", day: "numeric" })}`
      : labelDate(period.start, { month: "long", year: "numeric" });
    periods.set(period.start, {
      date: period.lastDate,
      name,
      actual: null,
      predicted: period.values.reduce((sum, value) => sum + value, 0) / period.values.length,
      horizon,
      target_period_start: period.start,
      target_period_end: period.end,
      forecast_step: index + 1,
      covered_days: period.values.length,
      period_days: Math.round((Date.parse(`${period.end}T00:00:00Z`) - Date.parse(`${period.start}T00:00:00Z`)) / 86400000) + 1,
      confidence_score: null,
      confidence_level: "Insufficient data",
    });
  });
  const combined = [...periods.values()].sort((left, right) => left.date.localeCompare(right.date));
  const originDate = new Date(`${origin}T00:00:00Z`);
  const horizonEnd = new Date(Date.UTC(
    originDate.getUTCFullYear(),
    originDate.getUTCMonth() + PUBLISHED_FORECAST_MONTHS + 1,
    0,
  )).toISOString().slice(0, 10);
  const withinPublishedHorizon = combined.filter(point => point.date <= horizonEnd);
  return horizon === "weekly" ? withinPublishedHorizon.slice(0, 12) : withinPublishedHorizon;
}

/** Display only backend evidence tied to this product, horizon, and forecast model. */
export function productHorizonConfidence(product: Product, status: ForecastStatus | null | undefined,
  horizon: ForecastHorizon): ForecastConfidenceMetric | null {
  const originIsValid = forecastTargetDate(product.forecastOriginDate, "daily") != null;
  const points = forecastHorizonPoints(product.forecastData, product.forecastOriginDate, horizon);
  if (product.forecastSource !== "model" || !product.forecastModelRunId
    || product.forecastModelRunId !== status?.modelRunId || !originIsValid
    || !product.lastActualDate || !points.some(point => point.date > product.lastActualDate!)) return null;
  const identity = [product.category, product.name, product.variant || "Standard",
    product.origin || "Unknown", product.unit || "unknown"].join("||");
  const metricsByProduct = status.modelMetrics?.product_metrics;
  const candidates = [
    metricsByProduct?.[product.id]?.confidence_by_horizon?.[horizon],
    metricsByProduct?.[identity]?.confidence_by_horizon?.[horizon],
  ];
  for (const metric of candidates) {
    if (!metric || metric.forecast_horizon_days !== FORECAST_HORIZON_DAYS[horizon]
      || metric.model_version !== product.forecastModelRunId
      || metric.evaluation_source !== "chronological_validation"
      || !metric.confidence_method || !Number.isInteger(metric.sample_count) || metric.sample_count < 0
      || [metric.mae, metric.rmse, metric.mape].some(value => value != null && (!Number.isFinite(value) || value < 0))) continue;
    const validScore = metric.evidence_status === "validated" && metric.sample_count >= 8
      && Number.isInteger(metric.sample_origin_count) && metric.sample_origin_count! >= 8
      && metric.confidence_score != null && Number.isFinite(metric.confidence_score)
      && metric.confidence_score >= 0 && metric.confidence_score <= 100
      && ["Very High", "High", "Moderate", "Low", "Very Low"].includes(metric.confidence_level)
      && [metric.mae, metric.rmse, metric.mape].every(value => value != null);
    const insufficient = metric.evidence_status === "insufficient_data"
      && ((Number.isInteger(metric.sample_origin_count) && metric.sample_origin_count! < 8)
        || metric.sample_count < 8)
      && metric.confidence_score == null && metric.confidence_level === "Insufficient data";
    if (validScore || insufficient) return metric;
  }
  return null;
}

export interface ProductValidationReliability {
  confidence_score: number;
  confidence_level: Exclude<ForecastConfidenceMetric["confidence_level"], "Insufficient data">;
  sample_count: number;
  sample_origin_count: number;
}

/** Use a model-bound, chronological per-product validation hit rate when a
 * horizon-specific confidence estimate has not been validated yet. */
export function productValidationReliability(product: Product, status: ForecastStatus | null | undefined): ProductValidationReliability | null {
  const metrics = status?.modelMetrics;
  const originIsValid = forecastTargetDate(product.forecastOriginDate, "daily") != null;
  const hasFutureForecast = forecastHorizonPoints(
    product.forecastData, product.forecastOriginDate, "daily",
  ).some(point => point.date > (product.lastActualDate ?? ""));
  if (product.forecastSource !== "model" || !product.forecastModelRunId
    || product.forecastModelRunId !== status?.modelRunId || !originIsValid
    || !product.lastActualDate || !hasFutureForecast
    || metrics?.evaluation_source !== "chronological_validation"
    || metrics.success_definition !== "absolute_percentage_error_at_most_tolerance"
    || metrics.success_tolerance !== 0.05) return null;

  const identity = [product.category, product.name, product.variant || "Standard",
    product.origin || "Unknown", product.unit || "unknown"].join("||");
  // Legacy run metrics can include an empty ID-keyed entry alongside the
  // measured identity-keyed snapshot. Use the first valid matching metric.
  const metric = [metrics.product_metrics?.[product.id], metrics.product_metrics?.[identity]]
    .find(candidate => candidate?.evaluation_source === "chronological_validation"
      && Number.isInteger(candidate.sample_count) && candidate.sample_count >= 20
      && Number.isInteger(candidate.sample_origin_count) && candidate.sample_origin_count! >= 1
      && candidate.prediction_success != null && Number.isFinite(candidate.prediction_success)
      && candidate.prediction_success >= 0 && candidate.prediction_success <= 1);
  if (!metric) return null;
  const rawRate = metric.prediction_success!;
  const sampleCount = metric.sample_count;
  const originCount = metric.sample_origin_count!;

  // Treat forecast origins as the effective evidence count because many
  // target rows share overlapping forecast windows. A Beta prior centered on
  // the model-wide validation hit rate pulls sparse 0%/100% samples inward.
  const priorOrigins = 10;
  const overallRate = metrics.prediction_success;
  const productRates = Object.values(metrics.product_metrics ?? {})
    .map(candidate => candidate.prediction_success)
    .filter((rate): rate is number => rate != null && Number.isFinite(rate) && rate >= 0 && rate <= 1);
  const priorRate = overallRate != null && Number.isFinite(overallRate)
    && overallRate >= 0 && overallRate <= 1
    ? overallRate
    : productRates.length
      ? productRates.reduce((sum, rate) => sum + rate, 0) / productRates.length
      : rawRate;
  const confidenceScore = ((rawRate * originCount) + (priorRate * priorOrigins))
    / (originCount + priorOrigins) * 100;

  const confidenceLevel = confidenceScore >= 90 ? "Very High"
    : confidenceScore >= 80 ? "High"
      : confidenceScore >= 70 ? "Moderate"
        : confidenceScore >= 60 ? "Low" : "Very Low";
  return {
    confidence_score: confidenceScore,
    confidence_level: confidenceLevel,
    sample_count: sampleCount!,
    sample_origin_count: originCount,
  };
}

export function verifiedPredictionSuccess(metrics: ForecastQualityMetrics | null | undefined) {
  const value = metrics?.prediction_success;
  return metrics?.evaluation_source === "chronological_validation"
    && metrics.success_definition === "absolute_percentage_error_at_most_tolerance"
    && metrics.success_tolerance === 0.05 && (metrics.sample_count ?? 0) >= 30
    && value != null && Number.isFinite(value) && value >= 0 && value <= 1
    ? value : null;
}

export function verifiedWithinTenAccuracy(metrics: ForecastQualityMetrics | null | undefined) {
  const value = metrics?.within_10_accuracy_pct;
  return metrics?.evaluation_source === "chronological_validation"
    && metrics.within_10_definition === "absolute_percentage_error_at_most_tolerance"
    && metrics.within_10_tolerance === 0.10
    && metrics.metric_aggregation === "row_weighted_across_observed_product_date_step_targets"
    && (metrics.within_10_sample_count ?? 0) >= 30
    && value != null && Number.isFinite(value) && value >= 0 && value <= 100
    ? value : null;
}

export interface ForecastStatus {
  modelRunId: string;
  generatedAt: string;
  horizon: number;
  rowCount: number;
  metrics: ForecastQualityMetrics | null;
  modelMetrics?: ForecastQualityMetrics | null;
  historicalAccuracy?: HistoricalForecastAccuracy | null;
}

export function formatRelativeAge(timestamp: string | null | undefined, locale = "en", now = Date.now()) {
  if (!timestamp) return null;
  const date = new Date(timestamp);
  if (!Number.isFinite(date.getTime())) return null;
  let value = Math.max(0, (now - date.getTime()) / 1000);
  let unit: Intl.RelativeTimeFormatUnit = "second";
  if (value >= 60) { value /= 60; unit = "minute"; }
  if (unit === "minute" && value >= 60) { value /= 60; unit = "hour"; }
  if (unit === "hour" && value >= 24) { value /= 24; unit = "day"; }
  if (unit === "day" && value >= 30) { value /= 30; unit = "month"; }
  if (unit === "month" && value >= 12) { value /= 12; unit = "year"; }
  const language = locale === "tl" ? "fil" : "en";
  return new Intl.RelativeTimeFormat(language, { numeric: "auto" })
    .format(-Math.floor(value), unit);
}

export function formatScheduledDaRefreshAge(locale = "en", now = Date.now()) {
  const localParts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Manila",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(now));
  const part = (type: string) => localParts.find((item) => item.type === type)?.value ?? "0";
  const year = Number(part("year"));
  const month = Number(part("month"));
  const day = Number(part("day"));
  const hour = Number(part("hour"));
  const minute = Number(part("minute"));
  let latestRefreshUtc = Date.UTC(year, month - 1, day, 1 - 8, 0);
  if (hour < 1 || (hour === 1 && minute === 0 && now < latestRefreshUtc)) {
    latestRefreshUtc -= 24 * 60 * 60 * 1000;
  }
  return formatRelativeAge(new Date(latestRefreshUtc).toISOString(), locale, now);
}

export interface NewsArticle {
  id: string;
  title: string;
  title_tl?: string;
  excerpt: string;
  content: string;
  content_tl?: string;
  category: string;
  date: string;
  image: string;
  url: string;
  source: string;
  sentimentScore?: number;
  keywords?: string[];
  affectedProducts?: string[];
  timeValidityDays?: number;
  probability?: number;
  effectMagnitude?: string;
}

const PRICE_IMPACT_NEWS_EVENT_TYPES = new Set([
  "supply_shock",
  "demand_spike",
  "policy_change",
  "import_export",
  "price_movement",
  "weather",
  "fuel_energy",
]);

function normalizeNewsEventType(value: string): string {
  return value.trim().toLowerCase().replace(/[\s-]+/g, "_");
}

/** Only surface news tied to an identified food product and market driver. */
export function isPriceImpactNews(article: Pick<NewsArticle, "category" | "affectedProducts">): boolean {
  const eventType = normalizeNewsEventType(article.category);
  return PRICE_IMPACT_NEWS_EVENT_TYPES.has(eventType)
    && Array.isArray(article.affectedProducts)
    && article.affectedProducts.some(product => typeof product === "string" && product.trim().length > 0);
}

export function decodeNewsKeyword(keyword: string): string {
  try {
    return decodeURIComponent(keyword);
  } catch {
    return keyword;
  }
}

function getNewsExcerpt(content: string | null | undefined): string {
  if (!content) return "";
  return content.length > 150 ? `${content.substring(0, 150).trimEnd()}...` : content;
}

export function formatNewsPublicationDate(
  publishedAt: string | null,
  publishedDate: string | null,
  precision: string | null,
  sourceUrl?: string | null,
): string {
  const sourceDate = precision === "date" ? publishedDate
    : precision === "timestamp" ? publishedAt : null;
  let dateValue: string | null = null;
  if (sourceDate) {
    const candidate = precision === "date" ? `${publishedDate}T12:00:00Z` : sourceDate;
    const parsed = new Date(candidate);
    if (Number.isFinite(parsed.getTime())) dateValue = candidate;
  }

  // The repository's source-date extractor treats YYYY/M/D URL path segments
  // as publication-date evidence. Use the same source when row metadata is absent.
  if (!dateValue && sourceUrl) {
    try {
      const parsedUrl = new URL(sourceUrl);
      if (parsedUrl.protocol === "http:" || parsedUrl.protocol === "https:") {
        const match = parsedUrl.pathname.match(/\/(\d{4})\/(\d{1,2})\/(\d{1,2})(?:\/|$)/);
        if (match) {
          const year = match[1];
          const month = match[2].padStart(2, "0");
          const day = match[3].padStart(2, "0");
          const dateOnly = `${year}-${month}-${day}`;
          const candidate = `${dateOnly}T12:00:00Z`;
          const parsed = new Date(candidate);
          if (Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === dateOnly) {
            dateValue = candidate;
          }
        }
      }
    } catch {
      // Ignore malformed source URLs and keep the unavailable state.
    }
  }

  if (!dateValue) return "Publication date unavailable";
  const parsed = new Date(dateValue);
  if (!Number.isFinite(parsed.getTime())) return "Publication date unavailable";
  return parsed.toLocaleDateString("en-US", {
    year: "numeric", month: "short", day: "numeric", timeZone: "UTC",
  });
}

// Dashboard cards and search need prices, not the full chart/history payload.
export type DashboardProduct = Pick<Product,
  "id" | "name" | "category" | "image" | "variant" | "origin" |
  "currentPrice" | "predictedPrice" | "unit" | "forecastSource" | "lastActualDate"
> & { forecastDate: string | null };

export function toDashboardProduct(product: Product): DashboardProduct {
  const { id, name, category, image, variant, origin, currentPrice, unit, lastActualDate } = product;
  const actualTime = Date.parse(`${lastActualDate}T00:00:00Z`);
  const expectedDate = Number.isFinite(actualTime)
    ? new Date(actualTime + 86_400_000).toISOString().split("T")[0] : null;
  const nextDay = product.dailyForecast?.find(row => row.date === expectedDate
    && Number.isFinite(row.predicted_price) && row.predicted_price > 0);
  return { id, name, category, image, variant, origin, currentPrice, unit, lastActualDate,
    predictedPrice: nextDay?.predicted_price ?? currentPrice,
    forecastDate: nextDay?.date ?? null,
    forecastSource: nextDay ? product.forecastSource : "trend_fallback" };
}

// ─── Supabase Edge Function Base URL ───────────────────────

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;
const EDGE_FN_BASE = `${SUPABASE_URL}/functions/v1/foodcast`;

const memoryCache: Record<string, { data: any; expiry: number }> = {};
const pendingRequests = new Map<string, Promise<unknown>>();

// Invalidate payloads cached before weekly/monthly rows were published.
const CACHE_VERSION = "v8_saved_period_forecasts";
const LOCAL_CACHE_PREFIX = `foodcast_cache_${CACHE_VERSION}_`;
const CACHE_TTL = 1000 * 60 * 60; // 1 hour persistent cache

// Server-side raw HTTP request that bypasses Next.js's patched fetch()
// This avoids the "items over 2MB can not be cached" warning entirely.
async function nativeServerFetch(url: string, headers: Record<string, string>): Promise<any> {
  const https = require('https');
  const http = require('http');

  return new Promise((resolve, reject) => {
    const mod = url.startsWith('https') ? https : http;
    const req = mod.request(url, { method: 'GET', headers }, (res: any) => {
      if (res.statusCode && res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        // Follow redirects
        nativeServerFetch(res.headers.location, headers).then(resolve).catch(reject);
        return;
      }

      const chunks: Buffer[] = [];
      res.on('data', (chunk: Buffer) => chunks.push(chunk));
      res.on('end', () => {
        const body = Buffer.concat(chunks).toString('utf8');
        if (res.statusCode && res.statusCode >= 400) {
          reject(new Error(`HTTP ${res.statusCode}: ${body.substring(0, 200)}`));
          return;
        }
        try {
          resolve(JSON.parse(body));
        } catch (e) {
          reject(new Error(`JSON parse error: ${body.substring(0, 200)}`));
        }
      });
    });
    req.on('error', reject);
    req.end();
  });
}

async function fetchFromNetwork<T>(path: string, retries = 3, bypassCache = false): Promise<T> {
  const isServer = typeof window === 'undefined';
  let fs: any, pathModule: any;
  let cacheFilePath = '';
  
  if (isServer && !bypassCache) {
    try {
      fs = require('fs');
      pathModule = require('path');
      const cacheDir = pathModule.join(process.cwd(), '.next', 'custom-cache');
      if (!fs.existsSync(cacheDir)) {
        fs.mkdirSync(cacheDir, { recursive: true });
      }
      cacheFilePath = pathModule.join(
        cacheDir, `${CACHE_VERSION}_${path.replace(/[^a-zA-Z0-9]/g, '_')}.json`);
      
      // Check if cache file exists and is less than 1 hour old
      if (fs.existsSync(cacheFilePath)) {
        const stats = fs.statSync(cacheFilePath);
        const age = Date.now() - Math.max(stats.mtimeMs, stats.ctimeMs);
        if (age < 60 * 60 * 1000) {
          const fileData = fs.readFileSync(cacheFilePath, 'utf8');
          const data = JSON.parse(fileData);
          memoryCache[path] = { data, expiry: Date.now() + 60 * 60 * 1000 };
          return data;
        }
      }
    } catch (e) {
      console.warn("File cache read error:", e);
    }
  }

  const now = Date.now();
  let lastError: any;
  const requestHeaders = {
    "Authorization": `Bearer ${SUPABASE_ANON_KEY}`,
    "Content-Type": "application/json",
  };
  const url = `${EDGE_FN_BASE}/${path}`;

  for (let attempt = 0; attempt < retries; attempt++) {
    try {
      let data: T;

      if (isServer) {
        // Use native Node.js HTTP — bypasses Next.js fetch cache entirely (no 2MB limit)
        data = await nativeServerFetch(url, requestHeaders);
      } else {
        // Client-side: use normal fetch
        const res = await fetch(url, { headers: requestHeaders, cache: 'no-store' });
        if (!res.ok) {
          const err = await res.json().catch(() => ({ error: res.statusText }));
          throw new Error(err.error || `Edge function error: ${res.status}`);
        }
        data = await res.json();
      }
      
      // Write to file cache (server only)
      if (!bypassCache && isServer && fs && cacheFilePath) {
        try {
          fs.writeFileSync(cacheFilePath, JSON.stringify(data));
        } catch (e) {
          console.warn("File cache write error:", e);
        }
      }
      
      // Update memory cache (1 hour)
      if (!bypassCache) {
        memoryCache[path] = { data, expiry: now + 60 * 60 * 1000 };
      }
      
      // Update localStorage (client only)
      if (!bypassCache && !isServer) {
        try {
          localStorage.setItem(LOCAL_CACHE_PREFIX + path, JSON.stringify({
            data,
            expiry: now + CACHE_TTL
          }));
        } catch (e) {
          console.warn("LocalStorage cache write failed (quota exceeded?):", e);
        }
      }
      
      return data;
    } catch (e) {
      lastError = e;
      if (e instanceof Error && e.message.includes("503") && attempt < retries - 1) {
        await new Promise(r => setTimeout(r, 1000 * Math.pow(2, attempt)));
        continue;
      }
      if (e instanceof Error && !e.message.includes("503")) {
        throw e;
      }
    }
  }
  
  throw lastError;
}

async function edgeFetch<T>(path: string): Promise<T> {
  const now = Date.now();
  
  // 1. Check in-memory cache (fastest)
  if (memoryCache[path] && memoryCache[path].expiry > now) {
    return memoryCache[path].data;
  }

  // 2. Check persistent browser cache
  if (typeof window !== "undefined") {
    try {
      const cached = localStorage.getItem(LOCAL_CACHE_PREFIX + path);
      if (cached) {
        const parsed = JSON.parse(cached);
        if (parsed.expiry > now) {
          // Rehydrate memory cache
          memoryCache[path] = { data: parsed.data, expiry: parsed.expiry };
          
          // Trigger a background revalidation if data is older than 5 minutes
          if (now > parsed.expiry - CACHE_TTL + (5 * 60 * 1000)) {
             fetchFromNetwork(path).catch(console.error);
          }
          
          return parsed.data;
        }
      }
    } catch (e) {
      console.warn("LocalStorage cache read failed:", e);
    }
  }

  // 3. Fallback to network fetch (causes loading state)
  // Share a cold request between components instead of repeating the same
  // expensive upstream query before the first response reaches the cache.
  let pending = pendingRequests.get(path);
  if (!pending) {
    pending = fetchFromNetwork<T>(path).finally(() => pendingRequests.delete(path));
    pendingRequests.set(path, pending);
  }
  return pending as Promise<T>;
}

// ─── Data Fetching (calls Supabase Edge Function) ──────────

export async function fetchProducts(): Promise<Product[]> {
  // A failed refresh must not replace existing rows with an empty list. SWR
  // retains its previous data on rejection; ISR retains the last good page.
  return edgeFetch<Product[]>("products");
}

export async function fetchProductPriceHistory(product: Pick<Product, "name" | "variant" | "origin" | "category" | "unit">): Promise<ForecastDataPoint[]> {
  const query = new URLSearchParams({
    name: product.name,
    variant: product.variant,
    origin: product.origin,
    category: product.category,
    unit: product.unit,
  });
  return edgeFetch<ForecastDataPoint[]>(`product-history?${query.toString()}`);
}

// Comparison prices should reflect the current database/forecast state, not
// the page's ISR payload or the one-hour browser cache.
export async function fetchLiveProducts(): Promise<Product[]> {
  return fetchFromNetwork<Product[]>("products", 3, true);
}

export async function fetchDashboardProducts(): Promise<DashboardProduct[]> {
  try {
    // Dashboard prices are live operational data; do not reuse build, disk, or
    // browser caches after a new forecast vintage is published.
    const data = await fetchFromNetwork<unknown>("dashboard-products", 3, true);
    // Older Edge deployments answer unknown paths with their status object.
    // Never pass that object into Home, which expects an iterable product list.
    if (Array.isArray(data) && data.every(product =>
      product && Object.hasOwn(product, "forecastDate"))) return data as DashboardProduct[];
    console.warn("Dashboard summary has no dated daily forecast; using live product details");
  } catch (e) {
    console.error("Error fetching dashboard products:", e);
  }
  try {
    // Never resurrect a cached weekly average as a live daily forecast when
    // the summary endpoint times out or an older Edge deployment is serving.
    return (await fetchLiveProducts()).map(toDashboardProduct);
  } catch (e) {
    console.error("Error fetching live dashboard fallback:", e);
    return [];
  }
}

export async function fetchForecastStatus(): Promise<ForecastStatus | null> {
  const response = await fetchFromNetwork<ForecastStatus | null>("forecast-status", 1, true);
  if (!response || typeof response.generatedAt !== "string") return null;
  return response;
}

// Fetch trending views from Supabase
export async function fetchTrendingInteractions(): Promise<Record<string, number>> {
  try {
    const { supabase } = await import("../../lib/supabase");
    const today = new Date().toISOString().split('T')[0];
    const thirtyDaysAgo = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
    
    const { data, error } = await supabase
      .from('product_daily_views')
      .select('product_id, view_count')
      .gte('date', thirtyDaysAgo); // Last 30 days trends
      
    if (error) throw error;
    
    // Aggregate counts by product_id
    const counts: Record<string, number> = {};
    if (data) {
      data.forEach(row => {
        counts[row.product_id] = (counts[row.product_id] || 0) + row.view_count;
      });
    }
    return counts;
  } catch (e) {
    console.error("Failed to fetch trending interactions:", e);
    return {};
  }
}

export async function fetchNews(limit = 10): Promise<NewsArticle[]> {
  try {
    // Fetch extra rows so older deployments that haven't filtered at the API
    // still leave enough relevant articles after this client-side safety gate.
    const articles = await edgeFetch<NewsArticle[]>(`news?limit=${Math.max(limit * 4, limit)}`);
    return articles.map(article => ({
      ...article,
      excerpt: getNewsExcerpt(article.content),
      date: !article.date || article.date === "Publication date unavailable"
        ? formatNewsPublicationDate(null, null, "unknown", article.url)
        : article.date,
      // The edge response uses this image only when the source supplied none.
      image: article.image === "/news/market.png" ? "" : article.image || "",
    })).filter(isPriceImpactNews).slice(0, limit);
  } catch (e) {
    console.error("Error fetching news:", e);
    return [];
  }
}

// ─── Direct Supabase Queries (lightweight, no Edge Fn needed) ──

export async function fetchCategories(): Promise<string[]> {
  try {
    return await edgeFetch<string[]>('categories?type=products');
  } catch (e) {
    console.error("Failed to fetch categories:", e);
    return ["All"];
  }
}

/** Convert a snake_case DB event_type to a pretty label: "policy_change" → "Policy Change" */
export function formatEventType(dbKey: string): string {
  return dbKey
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

/** Convert a pretty label back to a snake_case DB key: "Policy Change" → "policy_change" */
export function toEventTypeKey(label: string): string {
  if (label === "All") return "All";
  return label.toLowerCase().replace(/ /g, '_');
}

/** Fetch all unique news event_type values from the Edge function, returned as pretty labels. */
export async function fetchNewsCategories(): Promise<string[]> {
  try {
    const rawCategories = await edgeFetch<string[]>('categories?type=news');
    if (!rawCategories || rawCategories.length === 0) return ["All"];
    
    // The Edge Function returns the raw DB keys (e.g. 'policy_change')
    // We filter out "All", format the rest, and prepend "All" again
    const uniqueTypes = rawCategories.filter(c =>
      c !== "All" && PRICE_IMPACT_NEWS_EVENT_TYPES.has(normalizeNewsEventType(c))
    );
    const labels = uniqueTypes.map(formatEventType).sort();
    return ["All", ...labels];
  } catch (e) {
    console.error("Failed to fetch news categories:", e);
    return ["All"];
  }
}

export async function fetchProductById(id: string): Promise<Product | null> {
  const allProducts = await fetchProducts();
  return allProducts.find((p) => p.id === id) ?? null;
}

export async function fetchPaginatedNews(
  start: number, 
  limit: number, 
  search?: string, 
  category?: string,
  dateFilter?: string
): Promise<{ data: NewsArticle[], total: number, rawCount: number }> {
  try {
    const { supabase } = await import("../../lib/supabase");
    const fetchRows = async (withPublicationMetadata: boolean) => {
      let query = supabase.from("news_articles").select(
        withPublicationMetadata
          ? "id, title, title_tl, content, content_tl, event_type, published_at, published_date, publication_precision, image_url, url, source, sentiment_score, keywords, affected_products"
          : "id, title, title_tl, content, content_tl, event_type, published_at, image_url, url, source, sentiment_score, keywords, affected_products",
        { count: "exact" }
      );

      // The scraper records affected_products only when an article has a
      // supported, concrete food-market impact. Hide unrelated legacy rows too.
      query = query
        .in("event_type", Array.from(PRICE_IMPACT_NEWS_EVENT_TYPES))
        .not("affected_products", "is", null)
        .neq("affected_products", "{}");

      if (search) {
        query = query.or(`title.ilike.%${search}%,content.ilike.%${search}%,source.ilike.%${search}%`);
      }
      if (category && category !== "All") {
        query = query.eq("event_type", category);
      }
      if (dateFilter === "Today") {
        const yesterday = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
        query = query.gte("published_at", yesterday);
      } else if (dateFilter === "Recent") {
        const thirtyDaysAgo = new Date();
        thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);
        query = query.gte("published_at", thirtyDaysAgo.toISOString());
      }

      return query.order("published_at", { ascending: false }).range(start, start + limit - 1);
    };

    let result = await fetchRows(true);
    if (result.error?.code === "42703" && /published_date|publication_precision/.test(result.error.message)) {
      result = await fetchRows(false);
    }
    const { data, count, error } = result;

    if (error) {
      console.error("Error fetching paginated news:", error);
      return { data: [], total: 0, rawCount: 0 };
    }

    type NewsRow = {
      id: string;
      title: string;
      title_tl: string | null;
      content: string | null;
      content_tl: string | null;
      event_type: string | null;
      published_at: string | null;
      published_date?: string | null;
      publication_precision?: string | null;
      image_url: string | null;
      url: string;
      source: string;
      sentiment_score: number | null;
      keywords: string[] | null;
      affected_products: string[] | null;
    };
    const rawCount = data?.length ?? 0;
    const articles = ((data || []) as unknown as NewsRow[]).map(article => ({
      id: article.id,
      title: article.title,
      title_tl: article.title_tl || undefined,
      excerpt: getNewsExcerpt(article.content),
      content: article.content || "",
      content_tl: article.content_tl || "",
      category: (article.event_type || "News").replace(/_/g, ' '),
      date: formatNewsPublicationDate(article.published_at ?? null, article.published_date ?? null, article.publication_precision ?? null, article.url),
      image: article.image_url || "",
      url: article.url || "",
      source: article.source || "",
      sentimentScore: article.sentiment_score ?? undefined,
      keywords: article.keywords || [],
      affectedProducts: article.affected_products || [],
    })).filter(isPriceImpactNews);

    return { data: articles, total: count || 0, rawCount };
  } catch (e) {
    console.error("Failed to fetch paginated news:", e);
    return { data: [], total: 0, rawCount: 0 };
  }
}

// Hooks have been moved to hooks.ts to support Server Components
