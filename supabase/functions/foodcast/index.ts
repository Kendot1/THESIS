import { serve } from "https://deno.land/std@0.168.0/http/server.ts"
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.42.0"
import {
  mapDashboardSummary,
  normalizeSeriesUnit,
  productSeriesKey,
} from "./dashboard.ts"
import {
  buildForecastData,
  makeTrendFallback,
  meanFirstWeek,
  selectFuturePredictions,
} from "./forecast.ts"
import { realizedForecastQuality } from "./quality.ts"

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
}

function getSupabase() {
  return createClient(
    Deno.env.get("SUPABASE_URL") ?? "",
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? ""
  )
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

async function fetchAllPaginated(queryFactory: (start: number, end: number) => any, pageSize = 1000): Promise<any[]> {
  let allData: any[] = [];
  let start = 0;
  while (true) {
    const { data, error } = await queryFactory(start, start + pageSize - 1);
    if (error) throw error;
    if (!data || data.length === 0) break;
    allData.push(...data);
    if (data.length < pageSize) break;
    start += pageSize;
  }
  return allData;
}

// ── /products ────────────────────────────────────────────
async function handleProducts() {
  const supabase = getSupabase()

  const oneYearAgo = new Date();
  oneYearAgo.setDate(oneYearAgo.getDate() - 365);
  const sinceDate = oneYearAgo.toISOString().split("T")[0];

  const [productRows, priceRows, predRows] = await Promise.all([
    fetchAllPaginated((s, e) => supabase.from("products").select("id, name, variant, origin, category, unit, image_url, description").range(s, e)),
    fetchAllPaginated((s, e) => supabase.from("food_prices").select("product_name, product_category, product_variant, origin, price_index, report_date, unit").gte("report_date", sinceDate).order("report_date", { ascending: true }).range(s, e)),
    fetchAllPaginated((s, e) => supabase.from("predictions").select("product_id, prediction_date, predicted_price, lower_bound, upper_bound").order("prediction_date", { ascending: true }).range(s, e)),
  ]);

  if (priceRows.length === 0) return [];

  const productMetaByKey = new Map<string, any>();
  for (const p of productRows) {
    productMetaByKey.set(productSeriesKey(p), p);
  }

  const predsByProductId = new Map<string, any[]>();
  for (const pred of predRows) {
    if (!predsByProductId.has(pred.product_id)) predsByProductId.set(pred.product_id, []);
    predsByProductId.get(pred.product_id)!.push(pred);
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

    let allPredictions: any[] = [];
    if (metaRow) {
      allPredictions = predsByProductId.get(metaRow.id) || [];
    }

    const lastActualDate = String(rows[rows.length - 1].report_date).split("T")[0];
    const freshModelPredictions = selectFuturePredictions(allPredictions, lastActualDate);
    const forecastSource = freshModelPredictions.length > 0 ? "model" : "trend_fallback";
    const forecastDays = freshModelPredictions.length > 0
      ? freshModelPredictions
      : makeTrendFallback(
          lastActualDate,
          currentPrice,
          rows.slice(-7).map((row: any) => row.price_index),
        );
    const predictedPrice = meanFirstWeek(forecastDays, currentPrice);

    const changePct = currentPrice === 0 ? 0 : ((predictedPrice - currentPrice) / currentPrice) * 100;
    const sentiment = forecastSource !== "model"
      ? "Neutral"
      : changePct > 1 ? "Bullish" : changePct < -1 ? "Bearish" : "Neutral";
    const sparklineData = rows.slice(-7).map((r: any) => ({ value: r.price_index }));

    const forecastData = buildForecastData(rows, forecastDays);
    const volume = `${(rows.length * 150).toLocaleString()} ${unit}`;

    const dailyForecast: any[] = [];
    for (let i = 0; i < forecastDays.length; i++) {
      const p = forecastDays[i];
      const prevPrice = i === 0 ? currentPrice : forecastDays[i - 1].predicted_price;
      const diff = p.predicted_price - prevPrice;
      const pct = prevPrice === 0 ? 0 : (diff / prevPrice) * 100;

      let reasoning = "Model forecast is unavailable; this is a bounded statistical fallback and not a market recommendation.";
      if (forecastSource === "model") {
        reasoning = "Market forces expected to stabilize with consistent inventory levels.";
        if (pct > 0.5) reasoning = "Expected supply tightness combined with elevated local demand indicates upward pressure.";
        else if (pct < -0.5) reasoning = "Inflow of new harvests and eased supply chain bottlenecks are projected to ease prices.";
        else if (pct > 0.1) reasoning = "Slight uptick due to minor seasonal fluctuations and transport costs.";
        else if (pct < -0.1) reasoning = "Minor downward correction following market saturation in key trading posts.";
      }

      dailyForecast.push({
        date: p.date,
        predicted_price: p.predicted_price,
        lower_bound: p.lower_bound,
        upper_bound: p.upper_bound,
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
      lastActualDate,
    });
  }

  return products.sort((a: any, b: any) => a.name.localeCompare(b.name));
}

async function handleDashboardProducts() {
  const oneYearAgo = new Date();
  oneYearAgo.setDate(oneYearAgo.getDate() - 365);
  const { data, error } = await getSupabase().rpc("dashboard_product_summary", {
    p_since_date: oneYearAgo.toISOString().split("T")[0],
  });

  // Keep the endpoint usable while the additive migration is being rolled out
  // (or if the RPC is temporarily unavailable). The legacy response is more
  // expensive, but preserves the dashboard contract instead of returning 500.
  if (error || !data || !Array.isArray(data.rows) || data.requires_legacy) {
    // Existing queries do not define ordering for ties. Preserve that path
    // instead of silently picking a different metadata row/price/order.
    return (await handleProducts()).map(({ id, name, category, image, variant, origin, currentPrice, predictedPrice, unit }) =>
      ({ id, name, category, image, variant, origin, currentPrice, predictedPrice, unit }));
  }
  return mapDashboardSummary(data.rows, {
    slugify,
    defaultImage: DEFAULT_PRODUCT_IMAGE,
  });
}

let qualityCache: { key: string; expiresAt: number; metrics: ReturnType<typeof realizedForecastQuality> } | null = null
let qualityRequest: { modelRunId: string; promise: Promise<ReturnType<typeof realizedForecastQuality>> } | null = null

async function loadRealizedQuality(supabase: ReturnType<typeof getSupabase>, modelRunId: string) {
  if (qualityCache?.key.startsWith(`${modelRunId}|`) && qualityCache.expiresAt > Date.now()) return qualityCache.metrics
  const actualResponse = await supabase.from("food_prices").select("report_date")
    .order("report_date", { ascending: false }).limit(1).maybeSingle()
  if (actualResponse.error) throw actualResponse.error
  const latestActual = actualResponse.data?.report_date
  if (!latestActual) return null
  const since = new Date(`${latestActual}T00:00:00Z`)
  since.setUTCDate(since.getUTCDate() - 45)
  const sinceDate = since.toISOString().slice(0, 10)
  since.setUTCDate(since.getUTCDate() - 30)
  // All relevant vintages from this model; repeated publications must not
  // displace older evidence as they did under the eight-run limit.
  const runs = await fetchAllPaginated((s, e) => supabase.from("forecast_runs")
    .select("id, generated_at").eq("model_run_id", modelRunId)
    .gte("generated_at", since.toISOString()).order("generated_at", { ascending: false })
    .order("id").range(s, e))
  if (!runs.length) return null
  const cacheKey = `${modelRunId}|${latestActual}|${runs[0].id}`
  const firstRunDate = runs[runs.length - 1].generated_at.slice(0, 10)
  const evaluationStart = firstRunDate > sinceDate ? firstRunDate : sinceDate
  const runIds = runs.map((run) => run.id)
  const [forecasts, products, prices] = await Promise.all([
    fetchAllPaginated((s, e) => supabase.from("forecast_values")
      .select("run_id, product_id, prediction_date, predicted_price, lower_bound, upper_bound")
      .in("run_id", runIds).gte("prediction_date", evaluationStart).lte("prediction_date", latestActual)
      .order("prediction_date").order("run_id").order("product_id").range(s, e)),
    fetchAllPaginated((s, e) => supabase.from("products")
      .select("id, name, variant, origin, category, unit").order("id").range(s, e)),
    fetchAllPaginated((s, e) => supabase.from("food_prices")
      .select("product_name, product_category, product_variant, origin, unit, report_date, price_index, source_pdf")
      .gte("report_date", evaluationStart).lte("report_date", latestActual)
      .order("report_date").order("product_name").order("product_variant")
      .order("origin").order("unit").order("source_pdf")
      .order("price_index").range(s, e)),
  ])
  const metrics = realizedForecastQuality(runs, forecasts, products, prices)
  qualityCache = { key: cacheKey, expiresAt: Date.now() + 60_000, metrics }
  return metrics
}

async function handleForecastStatus() {
  const supabase = getSupabase()
  let response = await supabase
    .from("forecast_runs")
    .select("model_run_id, generated_at, horizon, row_count, metrics")
    .order("generated_at", { ascending: false })
    .limit(1)
    .maybeSingle()

  // Keep the timestamp endpoint usable during rollout before the additive
  // metrics migration has been applied.
  if (response.error && String(response.error.message).includes("metrics")) {
    response = await supabase
      .from("forecast_runs")
      .select("model_run_id, generated_at, horizon, row_count")
      .order("generated_at", { ascending: false })
      .limit(1)
      .maybeSingle()
  }
  if (response.error) throw response.error
  if (!response.data) return null

  let metrics = response.data.metrics && typeof response.data.metrics === "object"
    ? response.data.metrics
    : null
  const modelMetrics = metrics
  try {
    const modelRunId = response.data.model_run_id
    if (!qualityRequest || qualityRequest.modelRunId !== modelRunId) {
      const promise = loadRealizedQuality(supabase, modelRunId).finally(() => {
        if (qualityRequest?.promise === promise) qualityRequest = null
      })
      qualityRequest = { modelRunId, promise }
    }
    const realizedMetrics = await qualityRequest.promise
    if (realizedMetrics) {
      // Score each observed product/date once. Prefer realized vintages to
      // older holdout metrics for products with published forecasts.
      metrics = {
        processed_from: metrics?.processed_from,
        processed_through: metrics?.processed_through,
        processed_observed_rows: metrics?.processed_observed_rows,
        processed_series_count: metrics?.processed_series_count,
        ...realizedMetrics,
      }
    }
  } catch (error) {
    console.error("Unable to calculate realized forecast quality", error)
  }
  return {
    modelRunId: response.data.model_run_id,
    generatedAt: response.data.generated_at,
    horizon: response.data.horizon,
    rowCount: response.data.row_count,
    metrics,
    modelMetrics,
  }
}

// ── /news ────────────────────────────────────────────────
async function handleNews(url: URL) {
  const supabase = getSupabase()
  const limit = parseInt(url.searchParams.get("limit") || "10", 10);

  const { data, error } = await supabase
    .from("news_articles")
    .select("id, title, title_tl, content, content_tl, event_type, published_at, image_url, url, source, sentiment_score, keywords, affected_products, time_validity_days, probability, effect_magnitude")
    .order("published_at", { ascending: false })
    .limit(limit);

  if (error) throw error;

  return (data || []).map((article: any) => ({
    id: article.id,
    title: article.title,
    title_tl: article.title_tl,
    excerpt: article.content ? (article.content.substring(0, 150) + "...") : "",
    content: article.content || "",
    content_tl: article.content_tl || "",
    category: (article.event_type || "News").replace(/_/g, ' '),
    date: new Date(article.published_at).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" }),
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
async function handleCategories(url: URL) {
  const supabase = getSupabase()
  const type = url.searchParams.get("type") || "products" // 'products' or 'news'

  if (type === "news") {
    const { data, error } = await supabase.from('news_articles').select('event_type')
    if (error) throw error
    const uniqueTypes = Array.from(new Set(data.map((r: any) => r.event_type).filter(Boolean))) as string[]
    return ["All", ...uniqueTypes.sort()]
  } else {
    const { data, error } = await supabase.from('products').select('category')
    if (error) throw error
    const uniqueCats = Array.from(new Set(data.map((r: any) => r.category).filter(Boolean))) as string[]
    return ["All", ...uniqueCats.sort()]
  }
}

// ── Router ───────────────────────────────────────────────
serve(async (req) => {
  // Handle CORS preflight
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders })
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
        result = await handleProducts()
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
              "/foodcast/products",
              "/foodcast/dashboard-products",
              "/foodcast/forecast-status",
              "/foodcast/news",
              "/foodcast/comparisons",
              "/foodcast/recommendations",
              "/foodcast/categories",
            ],
            status: "FOODCAST Supabase Backend — running",
          }),
          {
            headers: { ...corsHeaders, "Content-Type": "application/json" },
            status: 200,
          }
        )
    }

    return new Response(JSON.stringify(result), {
      headers: { ...corsHeaders, "Content-Type": "application/json" },
      status: 200,
    })
  } catch (error: any) {
    return new Response(JSON.stringify({ error: error.message }), {
      headers: { ...corsHeaders, "Content-Type": "application/json" },
      status: 400,
    })
  }
})
