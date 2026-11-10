import { rollingPeriods } from './rolling-periods';
import { localNewsEnabled, isAbsCbnArticle } from './news-source';

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
  lower_bound?: number | null;
  upper_bound?: number | null;
  interval_level?: number | null;
  interval_width?: number | null;
  interval_reliability?: string | null;
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
  confidence_pct?: number | null;
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
  within_5_php_tolerance?: number | null;
  within_5_php_count?: number | null;
  within_5_php_sample_count?: number | null;
  within_5_php_accuracy_pct?: number | null;
  within_5_percent_count?: number | null;
  within_5_percent_sample_count?: number | null;
  within_5_percent_accuracy_pct?: number | null;
  within_5_percent_excluded_zero_or_near_zero?: number | null;
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
    within_5_php_count?: number | null;
    within_5_php_sample_count?: number | null;
    within_5_php_accuracy_pct?: number | null;
    within_5_percent_count?: number | null;
    within_5_percent_sample_count?: number | null;
    within_5_percent_accuracy_pct?: number | null;
    evaluation_source?: string;
    confidence_by_horizon?: Partial<Record<ForecastHorizon, ForecastConfidenceMetric>>;
    confidence_by_step?: Partial<Record<ForecastHorizon, Record<number, ForecastStepConfidenceMetric>>>;
    horizon_metrics?: Record<string, {
      mae: number | null;
      rmse: number | null;
      mape: number | null;
      prediction_success?: number | null;
      within_5_php_count?: number | null;
      within_5_php_sample_count?: number | null;
      within_5_php_accuracy_pct?: number | null;
      within_5_percent_count?: number | null;
      within_5_percent_sample_count?: number | null;
      within_5_percent_accuracy_pct?: number | null;
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
export const FORECAST_HORIZON_STEPS = { daily: 14, weekly: 4, monthly: 1 } as const;

/** First end date from the shared, issue-origin-relative rolling contract. */
export function forecastTargetDate(origin: string | undefined, horizon: ForecastHorizon): string | null {
  if (!origin) return null;
  try { return rollingPeriods(origin)[horizon][0].target_end; } catch { return null; }
}

/** Select only exact saved ranges; never relabel calendar forecasts as rolling. */
export function forecastHorizonPoints(data: ForecastDataPoint[], origin: string | undefined, horizon: ForecastHorizon) {
  if (!origin || !forecastTargetDate(origin, horizon)) return [];
  const selected: ForecastDataPoint[] = [];
  for (const period of rollingPeriods(origin)[horizon]) {
    const { target_start: start, target_end: end, lead: step, period_days: days } = period;
    const matches = data.filter(point =>
      (point.horizon === horizon || (!point.horizon && horizon === "daily"))
      && point.date === end
      && point.predicted != null && Number.isFinite(point.predicted) && point.predicted > 0
      && (point.forecast_step == null || point.forecast_step === step)
      && (point.target_period_start === start || (horizon === "daily" && point.target_period_start == null))
      && (point.target_period_end === end || (horizon === "daily" && point.target_period_end == null))
      && (point.covered_days == null || point.covered_days === days)
      && (point.period_days == null || point.period_days === days));
    if (matches.length !== 1) return [];
    selected.push(matches[0]);
  }
  return selected;
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

export const INITIAL_UNIQUE_NEWS_COUNT = 7;

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
export function isPriceImpactNews(article: Pick<NewsArticle, "category" | "affectedProducts"> & { url?: string }): boolean {
  const eventType = normalizeNewsEventType(article.category);
  return isAbsCbnArticle(article) && PRICE_IMPACT_NEWS_EVENT_TYPES.has(eventType)
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
    year: "numeric", month: "short", day: "numeric", timeZone: "Asia/Manila",
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

// ─── Display rule: show only products with a saved model prediction ─────
// Display filter only. Trend-fallback, persistence-only and empty-forecast
// series are hidden from every page; metrics, DB rows and models are untouched.
const isFinitePositive = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value) && value > 0;

/** True when the product carries a saved model forecast with at least one
 * finite positive daily predicted price dated after its forecast origin. */
export function hasModelPrediction(product: Partial<Product> | null | undefined): boolean {
  if (!product || product.forecastSource !== "model") return false;
  const origin = product.forecastOriginDate || product.lastActualDate;
  if (!origin || !/^\d{4}-\d{2}-\d{2}$/.test(origin)) return false;
  const daily = Array.isArray(product.dailyForecast) && product.dailyForecast.some(row =>
    typeof row?.date === "string" && row.date > origin && isFinitePositive(row.predicted_price));
  if (daily) return true;
  return Array.isArray(product.forecastData) && product.forecastData.some(point =>
    (point?.horizon == null || point.horizon === "daily")
    && typeof point.date === "string" && point.date > origin && isFinitePositive(point.predicted));
}

/** Dashboard summaries have no forecast arrays; use their dated next-day model price. */
export function hasDashboardModelPrediction(product: Partial<DashboardProduct> | null | undefined): boolean {
  return Boolean(product) && product!.forecastSource === "model"
    && typeof product!.name === "string" && product!.name.trim().length > 0
    && typeof product!.lastActualDate === "string" && /^\d{4}-\d{2}-\d{2}$/.test(product!.lastActualDate)
    && isFinitePositive(product!.currentPrice)
    && isFinitePositive(product!.predictedPrice);
}

/** Shared filter for full product payloads (apply before stripping forecast arrays). */
export function filterDisplayableProducts<T extends Partial<Product>>(products: T[] | null | undefined): T[] {
  return Array.isArray(products) ? products.filter(hasModelPrediction) : [];
}

/** Shared filter for dashboard summary payloads. */
export function filterDisplayableDashboardProducts<T extends Partial<DashboardProduct>>(products: T[] | null | undefined): T[] {
  return Array.isArray(products) ? products.filter(hasDashboardModelPrediction) : [];
}

// ─── Supabase Edge Function Base URL ───────────────────────

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;
const EDGE_FN_BASE = `${SUPABASE_URL}/functions/v1/foodcast`;

const memoryCache: Record<string, { data: any; expiry: number }> = {};
const pendingRequests = new Map<string, Promise<unknown>>();

// Invalidate payloads cached before weekly/monthly rows were published.
const CACHE_VERSION = "v9_preserved_forecast_vintage";
const LOCAL_CACHE_PREFIX = `foodcast_cache_${CACHE_VERSION}_`;
const CACHE_TTL = 1000 * 60 * 60; // 1 hour persistent cache

// Server-side dynamic loader for Node.js built-ins so client bundlers (Turbopack/Webpack)
// never attempt to resolve 'fs', 'path', 'http', or 'https' in browser bundles.
function getServerBuiltin<T = any>(moduleName: string): T {
  const proc = typeof process !== "undefined" ? (process as any) : null;
  if (proc && typeof proc.getBuiltinModule === "function") {
    return proc.getBuiltinModule(moduleName) as T;
  }
  const dynamicRequire = (0, eval)("require") as NodeRequire;
  return dynamicRequire(moduleName) as T;
}

// Server-side raw HTTP request that bypasses Next.js's patched fetch()
// This avoids the "items over 2MB can not be cached" warning entirely.
async function nativeServerFetch(url: string, headers: Record<string, string>, timeoutMs = 15_000, redirects = 0, deadlineAt = Date.now() + timeoutMs): Promise<any> {
  const https = getServerBuiltin('https');
  const http = getServerBuiltin('http');

  return new Promise((resolve, reject) => {
    const mod = url.startsWith('https') ? https : http;
    const req = mod.request(url, { method: 'GET', headers }, (res: any) => {
      if (res.statusCode && res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        res.resume();
        try {
          const next = new URL(res.headers.location, url);
          if (redirects >= 5 || next.origin !== new URL(url).origin) {
            reject(new Error('Upstream redirect rejected'));
          } else {
            nativeServerFetch(next.href, headers, timeoutMs, redirects + 1, deadlineAt).then(resolve).catch(reject);
          }
        } catch {
          reject(new Error('Invalid upstream redirect'));
        }
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
    const deadline = setTimeout(() => req.destroy(new Error('Upstream request timed out: deadline exceeded')), Math.max(0, deadlineAt - Date.now()));
    req.on('close', () => clearTimeout(deadline));
    req.on('error', reject);
    req.end();
  });
}

async function fetchFromNetwork<T>(path: string, retries = 3, bypassCache = false, timeoutMs = 15_000): Promise<T> {
  const isServer = typeof window === 'undefined';
  let fs: any, pathModule: any;
  let cacheFilePath = '';
  
  if (isServer && !bypassCache) {
    try {
      fs = getServerBuiltin('fs');
      pathModule = getServerBuiltin('path');
      const candidates = [
        pathModule.join(process.cwd(), '.next', 'custom-cache'),
        pathModule.join(process.cwd(), '.next-development', 'custom-cache'),
      ];
      const cacheDir = candidates.find((d: string) => fs.existsSync(d)) || candidates[0];
      if (!fs.existsSync(cacheDir)) {
        fs.mkdirSync(cacheDir, { recursive: true });
      }
      const fileName = `${CACHE_VERSION}_${path.replace(/[^a-zA-Z0-9]/g, '_')}.json`;
      cacheFilePath = pathModule.join(cacheDir, fileName);

      // Check all candidate cache dirs for existing file
      for (const dir of candidates) {
        const potentialFile = pathModule.join(dir, fileName);
        if (fs.existsSync(potentialFile)) {
          const stats = fs.statSync(potentialFile);
          const age = Date.now() - Math.max(stats.mtimeMs, stats.ctimeMs);
          if (age < 60 * 60 * 1000) {
            const fileData = fs.readFileSync(potentialFile, 'utf8');
            const data = JSON.parse(fileData);
            memoryCache[path] = { data, expiry: Date.now() + 60 * 60 * 1000 };
            return data;
          }
        }
      }
    } catch (e) {
      console.warn("File cache read error:", e);
    }
  }

  const now = Date.now();
  let lastError: any;
  const requestHeaders = {
    "apikey": SUPABASE_ANON_KEY,
    "Authorization": `Bearer ${SUPABASE_ANON_KEY}`,
    "Content-Type": "application/json",
  };
  const url = `${EDGE_FN_BASE}/${path}`;

  for (let attempt = 0; attempt < retries; attempt++) {
    try {
      let data: T;

      if (isServer) {
        // Use native Node.js HTTP — bypasses Next.js fetch cache entirely (no 2MB limit)
        data = await nativeServerFetch(url, requestHeaders, timeoutMs);
      } else {
        // Client-side: use normal fetch with timeout
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), timeoutMs);
        try {
          const res = await fetch(url, { headers: requestHeaders, cache: 'no-store', signal: controller.signal });
          if (!res.ok) {
            const err = await res.json().catch(() => ({ error: res.statusText }));
            throw new Error(err.error || `Edge function error: ${res.status}`);
          }
          data = await res.json();
        } finally {
          clearTimeout(timer);
        }
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
      
      // Update localStorage (client only, skip payloads > 2MB to avoid QuotaExceededError)
      if (!bypassCache && !isServer) {
        try {
          const serialized = JSON.stringify({
            data,
            expiry: now + CACHE_TTL
          });
          if (serialized.length <= 2_000_000) {
            localStorage.setItem(LOCAL_CACHE_PREFIX + path, serialized);
          }
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
  return filterDisplayableProducts(await edgeFetch<Product[]>("products"))
    .map(product => ({ ...product, confidence_pct: null }));
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
  return filterDisplayableProducts(await fetchFromNetwork<Product[]>("products", 3, true))
    .map(product => ({ ...product, confidence_pct: null }));
}

export async function fetchDashboardProducts(): Promise<DashboardProduct[]> {
  const cached = memoryCache["dashboard-products"];
  if (cached && cached.expiry > Date.now()) return cached.data;
  // A failed summary must not trigger a second, much heavier history request
  // against the same unavailable database or masquerade as a successful [].
  let pending = pendingRequests.get("dashboard-products");
  if (!pending) {
    pending = (async () => {
      const data = await fetchFromNetwork<unknown>("dashboard-products", 1, false, 20_000);
      if (!Array.isArray(data) || !data.every(product =>
        product && Object.hasOwn(product, "forecastDate"))) {
        throw new Error("Invalid dashboard summary response");
      }
      const products = filterDisplayableDashboardProducts(data as DashboardProduct[]);
      memoryCache["dashboard-products"] = { data: products, expiry: Date.now() + 60_000 };
      return products;
    })().finally(() => pendingRequests.delete("dashboard-products"));
    pendingRequests.set("dashboard-products", pending);
  }
  return pending as Promise<DashboardProduct[]>;
}

export async function fetchForecastStatus(): Promise<ForecastStatus | null> {
  const cached = memoryCache["forecast-status"];
  if (cached && cached.expiry > Date.now()) return cached.data;
  let pending = pendingRequests.get("forecast-status");
  if (!pending) {
    pending = (async () => {
      const response = await fetchFromNetwork<ForecastStatus | null>("forecast-status", 1, false, 15_000);
      if (response === null) {
        memoryCache["forecast-status"] = { data: null, expiry: Date.now() + 60_000 };
        return null;
      }
      if (!response || typeof response.generatedAt !== "string") throw new Error("Invalid forecast status response");
      memoryCache["forecast-status"] = { data: response, expiry: Date.now() + 60_000 };
      return response;
    })().finally(() => pendingRequests.delete("forecast-status"));
    pendingRequests.set("forecast-status", pending);
  }
  return pending as Promise<ForecastStatus | null>;
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

// News alone may read the explicitly authorized local test source. A disabled
// bridge falls back to the configured source; enabled bridge failures never mix DBs.
async function localNewsRows(start: number, limit: number, search = '', category = 'All', dateFilter = 'All') {
  if (process.env.NODE_ENV !== 'development') return null;
  const query = new URLSearchParams({ start: String(start), limit: String(limit), search, category, dateFilter });
  if (typeof window === 'undefined') {
    if (!localNewsEnabled(process.env)) return null;
    return nativeServerFetch(`http://127.0.0.1:${process.env.PORT || '3000'}/api/local-news?${query}`, {});
  }
  const response = await fetch(`/api/local-news?${query}`, { cache: 'no-store' });
  if (response.status === 204 || response.status === 404) return null;
  if (!response.ok) throw new Error('Local news unavailable');
  return response.json();
}

export async function fetchNews(limit = 10): Promise<NewsArticle[]> {
  // Reject failed refreshes so SWR retains its last successful news population.
  return (await fetchPaginatedUniqueNews(0, limit)).data;
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

/** Supported food-market news filters, returned as display labels. */
export async function fetchNewsCategories(): Promise<string[]> {
  // These are the complete supported filter values, not an article query.
  return ["All", ...Array.from(PRICE_IMPACT_NEWS_EVENT_TYPES).map(formatEventType).sort()];
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
        .or("url.ilike.https://www.abs-cbn.com/%,url.ilike.https://abs-cbn.com/%,url.ilike.http://www.abs-cbn.com/%,url.ilike.http://abs-cbn.com/%")
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

      return query.order("published_at", { ascending: false }).range(start, start + limit - 1)
        .abortSignal(AbortSignal.timeout(15_000));
    };

    let result = await localNewsRows(start, limit, search, category, dateFilter) ?? await fetchRows(true);
    if (result.error?.code === "42703" && /published_date|publication_precision/.test(result.error.message)) {
      result = await fetchRows(false);
    }
    const { data, count, error } = result;

    if (error) throw error;

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
    throw e;
  }
}

export function newsIdentityKeys(article: NewsArticle) {
  const normalize = (value: string) => value.normalize("NFKC").trim().toLowerCase().replace(/\s+/g, " ");
  const keys: string[] = [];
  const canonicalUrl = article.url.trim().toLowerCase()
    .replace(/^https?:\/\/(?:www\.)?/, "")
    .split(/[?#]/, 1)[0]
    .replace(/\/+$/, "");
  if (canonicalUrl) keys.push(`url:${canonicalUrl}`);

  const title = normalize(article.title);
  if (title) keys.push(`story:${title}|${normalize(article.source)}|${normalize(article.date)}`);
  return keys.length ? keys : [`id:${article.id}`];
}

export function mergeUniqueNews(existing: NewsArticle[], incoming: NewsArticle[]) {
  const seen = new Set(existing.flatMap(newsIdentityKeys));
  const merged = [...existing];
  for (const article of incoming) {
    const keys = newsIdentityKeys(article);
    if (keys.some(key => seen.has(key))) continue;
    keys.forEach(key => seen.add(key));
    merged.push(article);
  }
  return merged;
}

/** Keep paging through duplicate stories until the requested unique count is reached. */
export async function fetchPaginatedUniqueNews(
  start: number,
  uniqueLimit: number,
  search?: string,
  category?: string,
  dateFilter?: string,
): Promise<{ data: NewsArticle[], total: number, rawCount: number }> {
  const articles: NewsArticle[] = [];
  const seen = new Set<string>();
  let total = 0;
  let rawCount = 0;

  while (articles.length < uniqueLimit) {
    const pageSize = uniqueLimit - articles.length;
    const page = await fetchPaginatedNews(start + rawCount, pageSize, search, category, dateFilter);
    total = page.total;
    if (page.rawCount === 0) break;

    rawCount += page.rawCount;
    for (const article of page.data) {
      const keys = newsIdentityKeys(article);
      if (keys.some(key => seen.has(key))) continue;
      keys.forEach(key => seen.add(key));
      articles.push(article);
    }

    if (start + rawCount >= total) break;
  }

  return { data: articles, total, rawCount };
}

// Hooks have been moved to hooks.ts to support Server Components
