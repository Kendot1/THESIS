export const DEFAULT_PRODUCT_IMAGE = "https://images.unsplash.com/photo-1610348725531-843dff563e2c?auto=format&fit=crop&q=80&w=800";

// ─── Types ─────────────────────────────────────────────────

export interface ForecastDataPoint {
  date: string;
  name: string;
  actual: number | null;
  predicted: number | null;
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

export interface RangeHitMetrics {
  interval_coverage?: number | null;
  covered_count?: number | null;
  interval_level?: number | null;
  sample_count?: number | null;
  coverage_sample_count?: number | null;
  effective_sample_count?: number | null;
  coverage_uncertainty_method?: string;
  coverage_uncertainty_approximate?: boolean;
  coverage_uncertainty_validated?: boolean;
  sample_basis?: string;
  evaluation_source?: string | null;
  horizon_min_days?: number;
  horizon_max_days?: number;
  horizon_basis?: string;
  observed_min_lead_days?: number;
  observed_max_lead_days?: number;
}

export interface CoverageConfidenceInterval {
  lower: number;
  upper: number;
  confidenceLevel: 0.95;
  effectiveSampleCount: number;
  method: "wilson_effective_sample";
  approximate: true;
}

export interface ForecastQualityMetrics {
  mae: number | null;
  rmse: number | null;
  mape: number | null;
  directional_accuracy: number | null;
  interval_level: number | null;
  interval_coverage: number | null;
  prediction_success: number | null;
  success_tolerance?: number | null;
  success_definition?: string;
  sample_count: number | null;
  coverage_sample_count?: number | null;
  processed_from?: string | null;
  processed_through?: string | null;
  processed_observed_rows?: number | null;
  processed_series_count?: number | null;
  product_metrics?: Record<string, {
    interval_coverage: number;
    interval_level?: number | null;
    sample_count: number;
    sample_basis?: string;
    mape?: number | null;
    prediction_success?: number;
    evaluation_source?: string;
    confidence_by_horizon?: Partial<Record<ForecastHorizon, ForecastConfidenceMetric>>;
    horizon_metrics?: Record<string, RangeHitMetrics>;
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
  sample_support?: number;
  evaluation_source: "chronological_validation" | "historical_holdout";
  confidence_method: string;
  model_version: string;
  evidence_status: "validated" | "insufficient_data" | "unverified_provenance";
}

export const FORECAST_HORIZON_DAYS = { daily: 1, weekly: 7, monthly: 30 } as const;

/** Calendar lead time is measured from the saved backend vintage, never row position. */
export function forecastTargetDate(origin: string | undefined, horizon: ForecastHorizon): string | null {
  if (!origin || !/^\d{4}-\d{2}-\d{2}$/.test(origin)) return null;
  const timestamp = Date.parse(`${origin}T00:00:00Z`);
  if (!Number.isFinite(timestamp) || new Date(timestamp).toISOString().slice(0, 10) !== origin) return null;
  return new Date(timestamp + FORECAST_HORIZON_DAYS[horizon] * 86400000).toISOString().slice(0, 10);
}

/** Sample saved model prices at the selected cadence, without averaging or
 * extending the model's forecast window. Monthly uses the trained 30-day lead. */
export function forecastHorizonPoints(data: ForecastDataPoint[], origin: string | undefined, horizon: ForecastHorizon) {
  if (!forecastTargetDate(origin, horizon)) return [];
  const originTime = Date.parse(`${origin}T00:00:00Z`);
  const cadence = FORECAST_HORIZON_DAYS[horizon];
  return data.filter(point => {
    const timestamp = Date.parse(`${point.date}T00:00:00Z`);
    const lead = (timestamp - originTime) / 86400000;
    return Number.isInteger(lead) && lead > 0 && lead % cadence === 0
      && new Date(timestamp).toISOString().slice(0, 10) === point.date
      && point.predicted != null && Number.isFinite(point.predicted) && point.predicted > 0;
  })
    .sort((left, right) => left.date.localeCompare(right.date));
}

/** Display only backend evidence tied to this product, horizon, and forecast model. */
export function productHorizonConfidence(product: Product, status: ForecastStatus | null | undefined,
  horizon: ForecastHorizon): ForecastConfidenceMetric | null {
  const target = forecastTargetDate(product.forecastOriginDate, horizon);
  if (product.forecastSource !== "model" || !product.forecastModelRunId
    || product.forecastModelRunId !== status?.modelRunId || !target
    || !product.lastActualDate || target <= product.lastActualDate
    || !forecastHorizonPoints(product.forecastData, product.forecastOriginDate, horizon)
      .some(point => point.date === target)) return null;
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
      && metric.confidence_score != null && Number.isFinite(metric.confidence_score)
      && metric.confidence_score >= 0 && metric.confidence_score <= 100
      && ["Very High", "High", "Moderate", "Low", "Very Low"].includes(metric.confidence_level)
      && [metric.mae, metric.rmse, metric.mape].every(value => value != null);
    const insufficient = metric.evidence_status === "insufficient_data" && metric.sample_count < 8
      && metric.confidence_score == null && metric.confidence_level === "Insufficient data";
    if (validScore || insufficient) return metric;
  }
  return null;
}

/** Return only measured coverage for the nominal 80% prediction interval. */
export function verifiedRangeHitRate(metrics: RangeHitMetrics | null | undefined, minimumSamples = 30): number | null {
  const coverage = metrics?.interval_coverage;
  const sampleCount = metrics?.coverage_sample_count ?? metrics?.sample_count ?? 0;
  if (metrics?.coverage_sample_count != null && metrics.sample_count != null
      && metrics.coverage_sample_count !== metrics.sample_count) return null;
  if (metrics?.covered_count != null && (!Number.isInteger(metrics.covered_count)
      || metrics.covered_count < 0 || metrics.covered_count > sampleCount
      || coverage == null || Math.abs(metrics.covered_count / sampleCount - coverage) > 1e-12)) return null;
  return (metrics?.evaluation_source === "historical_holdout"
    || metrics?.evaluation_source === "realized_vintages")
    && metrics.interval_level === 0.8
    && Number.isInteger(sampleCount) && sampleCount >= minimumSamples
    && coverage != null && Number.isFinite(coverage) && coverage >= 0 && coverage <= 1
    ? coverage : null;
}

/** Do not let next-day evidence stand in for the long end of a 30-day outlook. */
export function verifiedLongRangeHitRate(metrics: RangeHitMetrics | null | undefined,
  minimumSamples = 20): number | null {
  return metrics?.evaluation_source === "realized_vintages"
    && metrics.sample_basis === "unique_actual_dates"
    && metrics.horizon_basis === "philippine_publication_date"
    && metrics.horizon_min_days === 15 && metrics.horizon_max_days === 30
    && Number.isInteger(metrics.observed_min_lead_days) && metrics.observed_min_lead_days! >= 15
    && Number.isInteger(metrics.observed_max_lead_days) && metrics.observed_max_lead_days! <= 30
    && metrics.observed_min_lead_days! <= metrics.observed_max_lead_days!
    ? verifiedRangeHitRate(metrics, minimumSamples) : null;
}

/** Approximate 95% interval; the serial adjustment has no exact coverage guarantee. */
export function verifiedCoverageConfidenceInterval(
  metrics: RangeHitMetrics | null | undefined,
  minimumSamples = 20,
): CoverageConfidenceInterval | null {
  if (verifiedRangeHitRate(metrics, minimumSamples) == null) return null;
  if (metrics?.evaluation_source !== "realized_vintages"
      || metrics.sample_basis !== "unique_actual_dates"
      || metrics.coverage_uncertainty_method !== "positive_serial_wilson_7d"
      || metrics.coverage_uncertainty_approximate !== true
      || metrics.coverage_uncertainty_validated !== true) return null;
  const hits = metrics?.covered_count;
  const total = metrics?.coverage_sample_count ?? metrics?.sample_count;
  const effectiveTotal = metrics?.effective_sample_count;
  if (!Number.isInteger(hits) || !Number.isInteger(total) || hits == null || total == null
      || hits < 0 || total < 1 || hits > total
      || effectiveTotal == null || !Number.isFinite(effectiveTotal)
      || effectiveTotal < 1 || effectiveTotal > total) return null;
  const observed = hits / total;
  // Ensure the displayed rate and exact counts describe the same evidence.
  if (Math.abs(observed - metrics!.interval_coverage!) > 1e-12) return null;
  const z = 1.959963984540054;
  const z2 = z * z;
  const denominator = 1 + z2 / effectiveTotal;
  const center = (observed + z2 / (2 * effectiveTotal)) / denominator;
  const margin = z * Math.sqrt(observed * (1 - observed) / effectiveTotal
    + z2 / (4 * effectiveTotal * effectiveTotal))
    / denominator;
  return { lower: Math.max(0, center - margin), upper: Math.min(1, center + margin),
    confidenceLevel: 0.95, effectiveSampleCount: effectiveTotal,
    method: "wilson_effective_sample", approximate: true };
}

export function verifiedPredictionSuccess(metrics: ForecastQualityMetrics | null | undefined) {
  const value = metrics?.prediction_success;
  return metrics?.success_definition === "absolute_percentage_error_at_most_tolerance"
    && metrics.success_tolerance === 0.05 && (metrics.sample_count ?? 0) >= 30
    && value != null && Number.isFinite(value) && value >= 0 && value <= 1
    ? value : null;
}

export interface ForecastStatus {
  modelRunId: string;
  generatedAt: string;
  horizon: number;
  rowCount: number;
  metrics: ForecastQualityMetrics | null;
  modelMetrics?: ForecastQualityMetrics | null;
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

export function formatNewsPublicationDate(
  publishedAt: string | null,
  publishedDate: string | null,
  precision: string | null,
): string {
  const sourceDate = precision === "date" ? publishedDate
    : precision === "timestamp" ? publishedAt : null;
  if (!sourceDate) return "Publication date unavailable";
  const dateValue = precision === "date" ? `${publishedDate}T12:00:00Z` : sourceDate;
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

const CACHE_VERSION = "v7_forecast_cadence";
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
    return await edgeFetch<NewsArticle[]>(`news?limit=${limit}`);
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
    const uniqueTypes = rawCategories.filter(c => c !== "All");
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
): Promise<{ data: NewsArticle[], total: number }> {
  try {
    const { supabase } = await import("../../lib/supabase");
    let query = supabase.from("news_articles").select("id, title, title_tl, content, content_tl, event_type, published_at, image_url, url, source, sentiment_score, keywords, affected_products", { count: "exact" });

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

    const { data, count, error } = await query
      .order("published_at", { ascending: false })
      .range(start, start + limit - 1);

    if (error) {
      console.error("Error fetching paginated news:", error);
      return { data: [], total: 0 };
    }

    const articles = (data || []).map(article => ({
      id: article.id,
      title: article.title,
      title_tl: article.title_tl,
      excerpt: article.content ? (article.content.substring(0, 150) + "...") : "",
      content: article.content || "",
      content_tl: article.content_tl || "",
      category: (article.event_type || "News").replace(/_/g, ' '),
      date: formatNewsPublicationDate(article.published_at, null, null),
      image: article.image_url || "/news/market.png",
      url: article.url,
      source: article.source,
      sentimentScore: article.sentiment_score,
      keywords: article.keywords || [],
      affectedProducts: article.affected_products || [],
    }));

    return { data: articles, total: count || 0 };
  } catch (e) {
    console.error("Failed to fetch paginated news:", e);
    return { data: [], total: 0 };
  }
}

// Hooks have been moved to hooks.ts to support Server Components
