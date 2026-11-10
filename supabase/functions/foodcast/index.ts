import { serve } from "https://deno.land/std@0.168.0/http/server.ts"
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.42.0"
import {
  mapDashboardSummary,
  normalizeSeriesUnit,
  productSeriesKey,
} from "./dashboard.ts"
import {
  buildForecastSequenceData,
  addUtcDays,
  meanFirstWeek,
  resolveForecastOrigin,
  selectFuturePredictions,
  selectSavedPeriodPredictions,
} from "./forecast.ts"
import type { SavedPeriodPrediction } from "./forecast.ts"
import { createSupabaseClient, publicError, statusForError, checkRateLimit, MemoryCache } from "./upstream.ts"

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
}
// The product's daily forecast view exposes 30 future days. The publisher
// keeps the full three-calendar-month path for weekly and monthly views.
const PUBLISHED_DAILY_FORECAST_DAYS = 30
const PRICE_IMPACT_NEWS_EVENT_TYPES = [
  "supply_shock",
  "demand_spike",
  "policy_change",
  "import_export",
  "price_movement",
  "weather",
  "fuel_energy",
]

function getSupabase() {
  return createSupabaseClient()
}

// ── /comparisons ─────────────────────────────────────────
async function handleComparisons(body: any) {
  const supabase = getSupabase()
  const {
    product_name,
    product_variant,
    origin,
    product_category,
    compare_by = "history",
    period_days = 30,
  } = body

  if (!product_name) throw new Error("product_name is required")

  // 1. Fetch the product's own history
  let query = supabase
    .from("food_prices")
    .select("*")
    .eq("product_name", product_name)

  if (product_variant) query = query.eq("product_variant", product_variant)
  if (origin) query = query.eq("origin", origin)
  if (product_category) query = query.eq("product_category", product_category)

  const { data: history, error } = await query
    .order("report_date", { ascending: true })
    .limit(period_days * 2)

  if (error) throw error
  if (!history || history.length === 0)
    throw new Error(`No data found for '${product_name}'`)

  const current_price = history[history.length - 1].price_index
  let series: Record<string, any[]> = {}

  if (compare_by === "history") {
    const mid = Math.floor(history.length / 2)
    series["Previous Period"] = history.slice(0, mid).map((r: any) => ({
      date: r.report_date,
      price: r.price_index,
    }))
    series["Current Period"] = history.slice(mid).map((r: any) => ({
      date: r.report_date,
      price: r.price_index,
    }))
  } else if (compare_by === "origin") {
    // Fetch ALL origins for this product
    const { data: allOrigins, error: oErr } = await supabase
      .from("food_prices")
      .select("*")
      .eq("product_name", product_name)
      .order("report_date", { ascending: true })
      .limit(period_days * 5)

    if (oErr) throw oErr
    const grouped: Record<string, any[]> = {}
    for (const row of allOrigins ?? []) {
      const key = row.origin || "Unknown"
      if (key === "Unknown") continue
      if (!grouped[key]) grouped[key] = []
      grouped[key].push({ date: row.report_date, price: row.price_index, label: key })
    }
    // Keep only last period_days per group
    for (const key of Object.keys(grouped)) {
      series[key] = grouped[key].slice(-period_days)
    }
  } else if (compare_by === "variant") {
    const category =
      product_category || history[0]?.product_category || "Unknown"
    const { data: allVariants, error: vErr } = await supabase
      .from("food_prices")
      .select("*")
      .eq("product_category", category)
      .order("report_date", { ascending: true })
      .limit(period_days * 10)

    if (vErr) throw vErr
    // Filter to products with the same base name
    const target = product_name.toLowerCase()
    const filtered = (allVariants ?? []).filter(
      (r: any) => r.product_name.toLowerCase() === target
    )
    const grouped: Record<string, any[]> = {}
    for (const row of filtered) {
      const variant = row.product_variant || "Standard"
      const label =
        variant !== "Standard" && variant !== "Unknown"
          ? `${row.product_name} (${variant})`
          : row.product_name
      if (!grouped[label]) grouped[label] = []
      grouped[label].push({ date: row.report_date, price: row.price_index, label })
    }
    for (const key of Object.keys(grouped)) {
      series[key] = grouped[key].slice(-period_days)
    }
  }

  return {
    product_name,
    product_variant: product_variant ?? null,
    origin: origin ?? null,
    product_category: product_category ?? null,
    compare_by,
    current_price,
    series,
  }
}

// ── /recommendations ─────────────────────────────────────
async function handleRecommendations(body: any) {
  const supabase = getSupabase()
  const { product_name, product_variant, origin, product_category } = body

  if (!product_name) throw new Error("product_name is required")

  // 1. Get the product's recent history
  let query = supabase
    .from("food_prices")
    .select("*")
    .eq("product_name", product_name)

  if (product_variant) query = query.eq("product_variant", product_variant)
  if (origin) query = query.eq("origin", origin)

  const { data: history, error: hErr } = await query
    .order("report_date", { ascending: true })
    .limit(30)

  if (hErr) throw hErr
  if (!history || history.length === 0)
    throw new Error(`No data for '${product_name}'`)

  const current_price = history[history.length - 1].price_index
  const category =
    product_category || history[0]?.product_category || "Unknown"
  const current_unit = history[history.length - 1].unit || "Unknown"

  // Determine trend
  let direction = "stable"
  if (history.length >= 7) {
    const weekAgo = history[history.length - 7].price_index
    if (current_price > weekAgo * 1.02) direction = "increase"
    else if (current_price < weekAgo * 0.98) direction = "decrease"
  }

  // 2. Get latest prices for all products in the same category
  const { data: categoryData, error: cErr } = await supabase
    .from("food_prices")
    .select("product_name, product_variant, origin, product_category, price_index, unit")
    .eq("product_category", category)
    .order("report_date", { ascending: false })
    .limit(500)

  if (cErr) throw cErr

  // Deduplicate: keep only the latest price per product series
  const seen = new Map<string, any>()
  for (const row of categoryData ?? []) {
    const key = `${row.product_name}|${row.product_variant || ""}|${row.origin || ""}`
    if (!seen.has(key)) seen.set(key, row)
  }

  // Filter: different product, same unit, cheaper
  const alternatives = Array.from(seen.values())
    .filter((row: any) => {
      if (row.product_name === product_name) return false
      if (current_unit !== "Unknown" && row.unit !== current_unit) return false
      return row.price_index < current_price
    })
    .sort((a: any, b: any) => a.price_index - b.price_index)
    .slice(0, 5)
    .map((row: any) => {
      const diff = row.price_index - current_price
      const diffPct = (diff / current_price) * 100
      return {
        product_name: row.product_name,
        product_variant: row.product_variant || null,
        origin: row.origin || null,
        product_category: row.product_category,
        current_price: Math.round(row.price_index * 100) / 100,
        price_difference: Math.round(diff * 100) / 100,
        price_difference_pct: Math.round(diffPct * 100) / 100,
        reason: `₱${Math.abs(diff).toFixed(2)}/unit cheaper (${Math.abs(diffPct).toFixed(1)}% savings)`,
      }
    })

  // Build recommendation reason
  let reason = ""
  if (direction === "increase") {
    reason = `The price of ${product_name} is currently trending upward (₱${current_price.toFixed(2)}).`
  } else if (direction === "decrease") {
    reason = `The price of ${product_name} is currently trending downward (₱${current_price.toFixed(2)}).`
  } else {
    reason = `The price of ${product_name} has been stable (₱${current_price.toFixed(2)}).`
  }

  if (alternatives.length > 0) {
    const cheapest = alternatives[0]
    reason += ` Consider switching to ${cheapest.product_name} which is ₱${Math.abs(cheapest.price_difference).toFixed(2)} cheaper per unit.`
  } else if (direction === "increase") {
    reason += " No cheaper alternatives were found in the same category."
  } else {
    reason += " This product is competitively priced within its category."
  }

  return {
    original_product: product_name,
    original_variant: product_variant ?? null,
    original_origin: origin ?? null,
    original_category: product_category ?? null,
    original_price: current_price,
    predicted_direction: direction,
    alternatives,
    recommendation_reason: reason,
  }
}

// ── Helper Functions ─────────────────────────────────────
function slugify(text: string) {
  return text.toString().toLowerCase().trim().replace(/\s+/g, "-").replace(/[^\w\-]+/g, "").replace(/\-\-+/g, "-");
}

const DEFAULT_PRODUCT_IMAGE = "https://images.unsplash.com/photo-1610348725531-843dff563e2c?auto=format&fit=crop&q=80&w=800";

async function fetchAllPaginated(queryFactory: (start: number, end: number, includeCount: boolean) => any, pageSize = 1000): Promise<any[]> {
  const first = await queryFactory(0, pageSize - 1, true);
  if (first.error) throw first.error;
  const allData: any[] = [...(first.data ?? [])];
  if (allData.length < pageSize) return allData;
  if (Number.isSafeInteger(first.count) && first.count >= allData.length) {
    // Offset pages are independent once the filtered count is known. Keep
    // database pressure bounded and concatenate in original offset order.
    for (let start = pageSize; start < first.count; start += pageSize * 4) {
      const offsets = Array.from({ length: Math.min(4, Math.ceil((first.count - start) / pageSize)) },
        (_, i) => start + i * pageSize);
      const pages = await Promise.all(offsets.map(offset => queryFactory(offset, offset + pageSize - 1)));
      for (const page of pages) {
        if (page.error) throw page.error;
        allData.push(...(page.data ?? []));
      }
    }
    return allData;
  }
  // Compatibility for callers without a count.
  for (let start = pageSize; ; start += pageSize) {
    const { data, error } = await queryFactory(start, start + pageSize - 1);
    if (error) throw error;
    allData.push(...(data ?? []));
    if (!data || data.length < pageSize) return allData;
  }
}

// ── /products ────────────────────────────────────────────
const productsCache = new MemoryCache<any[]>(300_000, 600_000); // 5 min fresh, 10 min SWR

async function handleProducts(url?: URL) {
  const allProducts = await productsCache.getOrFetch(() => loadProducts());

  if (!url) return allProducts;

  const pageParam = url.searchParams.get("page");
  const limitParam = url.searchParams.get("limit");
  const categoryParam = url.searchParams.get("category")?.trim();
  const searchParam = url.searchParams.get("search")?.trim();
  const liteParam = url.searchParams.get("lite") === "true";

  let filtered = allProducts;
  if (categoryParam && categoryParam !== "All") {
    filtered = filtered.filter((p: any) => p.category?.toLowerCase() === categoryParam.toLowerCase());
  }
  if (searchParam) {
    const q = searchParam.toLowerCase();
    filtered = filtered.filter((p: any) => p.name?.toLowerCase().includes(q));
  }

  // Lazy loading: strip heavy 365-day forecastData if caller asked for lite listing
  const formatItem = (p: any) => {
    if (liteParam) {
      const { forecastData: _unused, ...lite } = p;
      return lite;
    }
    return p;
  };

  const hasPagination = pageParam !== null || limitParam !== null;
  if (hasPagination) {
    const page = Math.max(1, parseInt(pageParam || "1", 10) || 1);
    const limit = Math.min(Math.max(1, parseInt(limitParam || "20", 10) || 20), 100);
    const total = filtered.length;
    const startIndex = (page - 1) * limit;
    const items = filtered.slice(startIndex, startIndex + limit).map(formatItem);

    return {
      items,
      pagination: {
        page,
        limit,
        total,
        totalPages: Math.ceil(total / limit),
      },
    };
  }

  if (liteParam || categoryParam || searchParam) {
    return filtered.map(formatItem);
  }

  return allProducts;
}

// Product charts load the selected series on demand. The list endpoint keeps
// its one-year window so catalog pages do not ship the entire price database.
async function handleProductHistory(url: URL) {
  const name = url.searchParams.get("name")?.trim();
  if (!name) throw new Error("name is required");
  const series = {
    product_name: name,
    product_variant: url.searchParams.get("variant") ?? "",
    origin: url.searchParams.get("origin") ?? "",
    product_category: url.searchParams.get("category") ?? "",
    unit: url.searchParams.get("unit") ?? "unknown",
  };
  const supabase = getSupabase();
  const rows = await fetchAllPaginated((start, end) => supabase.from("food_prices")
    .select("product_name, product_category, product_variant, origin, price_index, report_date, unit")
    .eq("product_name", name)
    .order("report_date", { ascending: true })
    .order("id", { ascending: true })
    .range(start, end));
  const seriesKey = productSeriesKey(series);
  const historyRows = rows
    .filter((row: any) => productSeriesKey(row) === seriesKey)
    .map((row: any) => ({
      report_date: String(row.report_date).split("T")[0],
      price_index: Number(row.price_index),
    }));
  const lastActualDate = historyRows[historyRows.length - 1]?.report_date;
  if (!lastActualDate) return [];

  return buildForecastSequenceData(historyRows, [], lastActualDate);
}

async function loadProducts() {
  const supabase = getSupabase()

  const oneYearAgo = new Date();
  oneYearAgo.setDate(oneYearAgo.getDate() - 365);
  const sinceDate = oneYearAgo.toISOString().split("T")[0];

  const [productRows, priceRows, { forecastRun, predRows }] = await Promise.all([
    fetchAllPaginated((s, e) => supabase.from("products").select("id, name, variant, origin, category, unit, image_url, description", { count: "exact" }).order("id").range(s, e)),
    fetchAllPaginated((s, e) => supabase.from("food_prices").select("product_name, product_category, product_variant, origin, price_index, report_date, unit", { count: "exact" }).gte("report_date", sinceDate).order("report_date", { ascending: true }).order("id", { ascending: true }).range(s, e)),
    (async () => {
      const runResponse = await supabase.from("forecast_runs").select("id, model_run_id, generated_at, metrics")
        .order("generated_at", { ascending: false }).order("id", { ascending: false }).limit(1).maybeSingle();
      if (runResponse.error) throw runResponse.error;
      const forecastRun = runResponse.data;
      // Only the run lookup is a dependency: overlap forecast pagination with
      // price history, retaining one immutable vintage during publication.
      const predRows = forecastRun ? await fetchAllPaginated((s, e) => supabase
        .from("forecast_values").select("product_id, prediction_date, predicted_price, forecast_horizon, forecast_origin_date, target_period_start, target_period_end, forecast_step, covered_days, period_days, confidence_score, confidence_level")
        .eq("run_id", forecastRun.id).order("product_id").order("forecast_horizon").order("forecast_step").range(s, e)) : [];
      return { forecastRun, predRows };
    })(),
  ]);

  if (priceRows.length === 0) return [];

  const productMetaByKey = new Map<string, any>();
  for (const p of productRows) {
    productMetaByKey.set(productSeriesKey(p), p);
  }

  const predsByProductId = new Map<string, any[]>();
  const confidenceEvidenceValidated = forecastRun?.metrics?.evaluation_source === "chronological_validation"
    && forecastRun?.metrics?.confidence_evaluation_source === "chronological_validation";
  for (const pred of predRows) {
    const safePrediction = confidenceEvidenceValidated ? pred : {
      ...pred,
      confidence_score: null,
      confidence_level: "Insufficient data",
    };
    if (!predsByProductId.has(safePrediction.product_id)) predsByProductId.set(safePrediction.product_id, []);
    predsByProductId.get(safePrediction.product_id)!.push(safePrediction);
  }

  const pricesByKey = new Map<string, any[]>();
  for (const row of priceRows) {
    const key = productSeriesKey(row);
    if (!pricesByKey.has(key)) pricesByKey.set(key, []);
    pricesByKey.get(key)!.push(row);
  }

  const products: any[] = [];

  for (const rows of pricesByKey.values()) {
    if (rows.length < 2) continue;

    const baseName = rows[0].product_name;
    const baseVariant = rows[0].product_variant || "";
    const baseOrigin = rows[0].origin || "";

    const normalizedUnit = normalizeSeriesUnit(rows[rows.length - 1]);
    const metaRow = productMetaByKey.get(
      [baseName, baseVariant, baseOrigin, normalizedUnit].join("|"));

    const category = metaRow?.category || rows[0].product_category || "Other";
    const description = metaRow?.description || `${baseName} is a tracked commodity in the NCR agri-fishery market.`;
    const image = metaRow?.image_url || DEFAULT_PRODUCT_IMAGE;

    const currentPrice = rows[rows.length - 1].price_index;
    const unit = normalizedUnit;
    const prevIdx = Math.max(0, rows.length - 8);
    const previousPrice = rows[prevIdx].price_index;

    let allForecastRows: any[] = [];
    if (metaRow) {
      allForecastRows = predsByProductId.get(metaRow.id) || [];
    }

    const lastActualDate = String(rows[rows.length - 1].report_date).split("T")[0];
    const savedProduct = forecastRun?.metrics?.forecast_products?.[metaRow?.id];
    const dailyRows = allForecastRows.filter(row => !row.forecast_horizon || row.forecast_horizon === "daily");
    const firstSavedDate = dailyRows[0]?.prediction_date?.split("T")[0];
    const forecastOriginDate = resolveForecastOrigin(
      lastActualDate,
      savedProduct?.origin_date ?? (firstSavedDate ? addUtcDays(firstSavedDate, -1) : null),
    );
    const forecastDays = forecastOriginDate === lastActualDate
      ? selectFuturePredictions(dailyRows, lastActualDate, PUBLISHED_DAILY_FORECAST_DAYS)
      : selectFuturePredictions(dailyRows, forecastOriginDate, PUBLISHED_DAILY_FORECAST_DAYS);
    const forecastSource = savedProduct?.source === "model" && forecastDays.length > 0
      ? "model" : "trend_fallback";
    const predictedPrice = meanFirstWeek(forecastDays, currentPrice);

    const changePct = currentPrice === 0 ? 0 : ((predictedPrice - currentPrice) / currentPrice) * 100;
    const sentiment = forecastSource !== "model"
      ? "Neutral"
      : changePct > 1 ? "Bullish" : changePct < -1 ? "Bearish" : "Neutral";
    const sparklineData = rows.slice(-7).map((r: any) => ({ value: r.price_index }));

    const periodPredictions: SavedPeriodPrediction[] = selectSavedPeriodPredictions(
      allForecastRows, forecastOriginDate, forecastDays.length > 0,
    )
      .map(row => ({
        date: String(row.prediction_date).split("T")[0],
        predicted_price: Number(row.predicted_price),
        forecast_horizon: row.forecast_horizon,
        target_period_start: String(row.target_period_start).split("T")[0],
        target_period_end: String(row.target_period_end).split("T")[0],
        forecast_step: Number(row.forecast_step),
        covered_days: Number(row.covered_days),
        period_days: Number(row.period_days),
        confidence_score: row.confidence_score == null ? null : Number(row.confidence_score),
        confidence_level: row.confidence_level,
      }));
    const forecastData = buildForecastSequenceData(rows, forecastDays,
      forecastOriginDate, periodPredictions);
    const volume = `${(rows.length * 150).toLocaleString()} ${unit}`;

    const dailyForecast: any[] = [];
    for (let i = 0; i < forecastDays.length; i++) {
      const p = forecastDays[i];
      const reasoning = "Price forecast from historical price patterns.";

      dailyForecast.push({
        date: p.date,
        predicted_price: p.predicted_price,
        reasoning,
      });
    }

    products.push({
      id: metaRow ? metaRow.id : slugify(`${baseName} ${baseVariant} ${baseOrigin} ${unit}`),
      name: baseName,
      description,
      category,
      image,
      variant: baseVariant,
      origin: baseOrigin,
      currentPrice,
      predictedPrice,
      previousPrice,
      volume,
      unit,
      sentiment,
      sparklineData,
      forecastData,
      dailyForecast,
      forecastSource,
      forecastOriginDate,
      forecastModelRunId: forecastRun?.model_run_id ?? null,
      lastActualDate,
    });
  }

  return products.sort((a: any, b: any) => a.name.localeCompare(b.name));
}

const dashboardProductsCache = new MemoryCache<any[]>(300_000, 600_000);

async function handleDashboardProducts() {
  return dashboardProductsCache.getOrFetch(async () => {
    const lookback = new Date();
    lookback.setDate(lookback.getDate() - 60);
    const { data, error } = await getSupabase().rpc("dashboard_product_summary", {
      p_since_date: lookback.toISOString().split("T")[0],
    });

    // Keep the endpoint usable while the additive migration is being rolled out
    // (or if the RPC is temporarily unavailable). The legacy response is more
    // expensive, but preserves the dashboard contract instead of returning 500.
    if (error || !data || !Array.isArray(data.rows) || data.requires_legacy) {
      // Existing queries do not define ordering for ties. Preserve that path
      // instead of silently picking a different metadata row/price/order.
      const legacyProducts = (await handleProducts()) as any[];
      return legacyProducts.map(({ id, name, category, image, variant, origin, currentPrice, unit, dailyForecast, forecastSource, lastActualDate }: any) =>
        ({ id, name, category, image, variant, origin, currentPrice, unit,
           predictedPrice: dailyForecast[0]?.predicted_price ?? currentPrice,
           forecastDate: dailyForecast[0]?.date ?? null,
           forecastSource, lastActualDate }));
    }
    return mapDashboardSummary(data.rows, {
      slugify,
      defaultImage: DEFAULT_PRODUCT_IMAGE,
    });
  });
}

const forecastStatusCache = new MemoryCache<any>(300_000, 600_000);

async function handleForecastStatus() {
  return forecastStatusCache.getOrFetch(async () => {
    const supabase = getSupabase()
    const latest = (columns: string) => supabase.from("forecast_runs")
      .select(columns)
      .order("generated_at", { ascending: false })
      .order("id", { ascending: false })
      .limit(1).maybeSingle()

    let response = await latest("model_run_id, generated_at, horizon, row_count, metrics")
    if (response.error?.code === "42703" && /\bmetrics\b/.test(response.error.message)) {
      response = await latest("model_run_id, generated_at, horizon, row_count")
    }
    if (response.error) throw response.error
    if (!response.data) return null

    const run = response.data
    const metrics = run.metrics && typeof run.metrics === "object" && !Array.isArray(run.metrics)
      ? run.metrics : null
    return {
      modelRunId: run.model_run_id,
      generatedAt: run.generated_at,
      horizon: run.horizon,
      rowCount: run.row_count,
      metrics,
      modelMetrics: metrics,
    }
  });
}

// ── /news ────────────────────────────────────────────────
async function handleNews(url: URL) {
  const supabase = getSupabase()
  const requestedLimit = parseInt(url.searchParams.get("limit") || "10", 10);
  const limit = Number.isFinite(requestedLimit) ? Math.min(Math.max(requestedLimit, 1), 100) : 10;

  let { data, error } = await supabase
    .from("news_articles")
    .select("id, title, title_tl, content, content_tl, event_type, published_at, published_date, publication_precision, image_url, url, source, sentiment_score, keywords, affected_products, time_validity_days, probability, effect_magnitude")
    .in("event_type", PRICE_IMPACT_NEWS_EVENT_TYPES)
    .not("affected_products", "is", null)
    .neq("affected_products", "{}")
    .order("published_at", { ascending: false })
    .limit(limit);

  // Keep news readable while the additive publication-provenance migration
  // rolls out. Without provenance, the source publication date stays unknown.
  if (error?.code === "42703" && /published_date|publication_precision/.test(error.message)) {
    const legacy = await supabase.from("news_articles")
      .select("id, title, title_tl, content, content_tl, event_type, published_at, image_url, url, source, sentiment_score, keywords, affected_products, time_validity_days, probability, effect_magnitude")
      .in("event_type", PRICE_IMPACT_NEWS_EVENT_TYPES)
      .not("affected_products", "is", null)
      .neq("affected_products", "{}")
      .order("published_at", { ascending: false }).limit(limit);
    data = legacy.data?.map(article => ({ ...article, published_date: null, publication_precision: "unknown" })) ?? null;
    error = legacy.error;
  }
  if (error) throw error;

  return (data || []).filter((article: any) =>
    Array.isArray(article.affected_products) && article.affected_products.some((product: unknown) =>
      typeof product === "string" && product.trim().length > 0
    )
  ).map((article: any) => ({
    id: article.id,
    title: article.title,
    title_tl: article.title_tl,
    excerpt: article.content ? (article.content.substring(0, 150) + "...") : "",
    content: article.content || "",
    content_tl: article.content_tl || "",
    category: (article.event_type || "News").replace(/_/g, ' '),
    date: (() => {
      const sourceDate = article.publication_precision === "date" ? article.published_date
        : article.publication_precision === "timestamp" ? article.published_at : null;
      if (!sourceDate) return "Publication date unavailable";
      const dateValue = article.publication_precision === "date"
        ? `${article.published_date}T12:00:00Z` : article.published_at;
      const parsed = new Date(dateValue);
      return Number.isFinite(parsed.getTime())
        ? parsed.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric", timeZone: "UTC" })
        : "Publication date unavailable";
    })(),
    image: article.image_url || "/news/market.png",
    url: article.url,
    source: article.source,
    sentimentScore: article.sentiment_score,
    keywords: article.keywords || [],
    affectedProducts: article.affected_products || [],
    timeValidityDays: article.time_validity_days,
    probability: article.probability,
    effectMagnitude: article.effect_magnitude,
  }));
}

// ── /categories ──────────────────────────────────────────
const categoriesCache = new MemoryCache<Record<string, string[]>>(900_000, 1_800_000); // 15 min

async function handleCategories(url: URL) {
  const supabase = getSupabase()
  const type = url.searchParams.get("type") || "products" // 'products' or 'news'

  const allCategories = await categoriesCache.getOrFetch(async () => {
    const [{ data: newsData }, { data: prodData }] = await Promise.all([
      supabase.from('news_articles').select('event_type'),
      supabase.from('products').select('category'),
    ]);
    const newsTypes = Array.from(new Set((newsData ?? []).map((r: any) => r.event_type).filter(Boolean))) as string[];
    const prodCats = Array.from(new Set((prodData ?? []).map((r: any) => r.category).filter(Boolean))) as string[];
    return {
      news: ["All", ...newsTypes.sort()],
      products: ["All", ...prodCats.sort()],
    };
  });

  return allCategories[type] || allCategories.products;
}

// ── Router ───────────────────────────────────────────────
serve(async (req) => {
  // Handle CORS preflight
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders })
  }

  // Rate Limiting Protection (120 req/min per IP)
  const clientIp = req.headers.get("x-forwarded-for")?.split(",")[0]?.trim()
    || req.headers.get("cf-connecting-ip")
    || req.headers.get("x-real-ip")
    || "unknown";
  const rateLimit = checkRateLimit(clientIp);
  const rateLimitHeaders = {
    "X-RateLimit-Limit": String(rateLimit.limit),
    "X-RateLimit-Remaining": String(rateLimit.remaining),
    "X-RateLimit-Reset": String(rateLimit.resetSeconds),
  };

  if (!rateLimit.allowed) {
    return new Response(JSON.stringify({ error: "Too many requests. Please slow down." }), {
      status: 429,
      headers: {
        ...corsHeaders,
        "Content-Type": "application/json",
        "Retry-After": String(rateLimit.resetSeconds),
        ...rateLimitHeaders,
      },
    });
  }

  try {
    const url = new URL(req.url)
    const path = url.pathname.split("/").pop() // last segment

    let result: any

    switch (path) {
      case "dashboard-products":
        result = await handleDashboardProducts()
        break
      case "forecast-status":
        result = await handleForecastStatus()
        break
      case "products":
        result = await handleProducts(url)
        break
      case "product-history":
        result = await handleProductHistory(url)
        break
      case "news":
        result = await handleNews(url)
        break
      case "comparisons": {
        const body = await req.json()
        result = await handleComparisons(body)
        break
      }
      case "recommendations": {
        const body = await req.json()
        result = await handleRecommendations(body)
        break
      }
      case "categories":
        result = await handleCategories(url)
        break
      default:
        return new Response(
          JSON.stringify({
            endpoints: [
              "/foodcast/products?page=1&limit=20&category=...&search=...&lite=true",
              "/foodcast/product-history?name=...&variant=...&origin=...&category=...&unit=...",
              "/foodcast/dashboard-products",
              "/foodcast/forecast-status",
              "/foodcast/news",
              "/foodcast/comparisons",
              "/foodcast/recommendations",
              "/foodcast/categories",
            ],
            status: "FOODCAST Supabase Backend — running (optimized: caching, rate-limiting, lazy-loading)",
          }),
          {
            headers: { ...corsHeaders, "Content-Type": "application/json", ...rateLimitHeaders },
            status: 200,
          }
        )
    }

    const cacheControlHeaders = req.method === "GET"
      ? { "Cache-Control": "public, max-age=60, s-maxage=300, stale-while-revalidate=600" }
      : { "Cache-Control": "no-store" };

    return new Response(JSON.stringify(result), {
      headers: {
        ...corsHeaders,
        "Content-Type": "application/json",
        ...cacheControlHeaders,
        ...rateLimitHeaders,
      },
      status: 200,
    })
  } catch (error: any) {
    const status = statusForError(error)
    console.error("FOODCAST request failed", error)
    return new Response(JSON.stringify({ error: publicError(error) }), {
      headers: { ...corsHeaders, "Content-Type": "application/json", ...rateLimitHeaders },
      status,
    })
  }
})
