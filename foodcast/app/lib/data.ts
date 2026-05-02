import { supabase } from "../../lib/supabase";

export const DEFAULT_PRODUCT_IMAGE = "https://images.unsplash.com/photo-1610348725531-843dff563e2c?auto=format&fit=crop&q=80&w=800";

export interface Product {
  id: string;
  name: string;
  description: string;
  category: string;
  emoji: string;
  image: string;
  variant: string;
  origin: string;
  currentPrice: number;
  predictedPrice: number;
  previousPrice: number;
  volume: string;
  sentiment: "Bullish" | "Bearish" | "Neutral";
  sparklineData: { value: number }[];
  forecastData: {
    name: string;
    actual: number | null;
    predicted: number | null;
  }[];
  dailyForecast: {
    date: string;
    predicted_price: number;
    reasoning: string;
  }[];
}

export const CATEGORY_EMOJI: Record<string, string> = {
  Rice: "🍚",
  Corn: "🌽",
  Vegetables: "🥬",
  Fruits: "🍌",
  Fish: "🐟",
  Fishery: "🐟",
  Poultry: "🐔",
  Livestock: "🥩",
  Oils: "🥥",
  Sugar: "🍬",
  Spices: "🧄",
  Grains: "🌾",
};

export const categories = ["All", "Fish", "Corn", "Rice", "Vegetables", "Fruits", "Livestock", "Poultry", "Oils", "Sugar", "Spices"];

function slugify(text: string) {
  return text.toString().toLowerCase().trim().replace(/\s+/g, "-").replace(/[^\w\-]+/g, "").replace(/\-\-+/g, "-");
}

function linearSlope(values: number[]): number {
  if (values.length < 2) return 0;
  const n = values.length;
  let sumX = 0, sumY = 0, sumXY = 0, sumX2 = 0;
  for (let i = 0; i < n; i++) {
    sumX += i;
    sumY += values[i];
    sumXY += i * values[i];
    sumX2 += i * i;
  }
  return (n * sumXY - sumX * sumY) / (n * sumX2 - sumX * sumX);
}

const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

interface RawPrice {
  product_name: string;
  product_category: string;
  product_variant: string;
  origin: string;
  price_index: number;
  report_date: string;
  unit: string;
}

interface ProductRow {
  id: string;
  name: string;
  variant: string;
  origin: string;
  category: string;
  image_url: string;
  description: string;
}

interface PredictionRow {
  product_id: string;
  prediction_date: string;
  predicted_price: number;
  lower_bound: number | null;
  upper_bound: number | null;
}

let cachedProductsPromise: Promise<Product[]> | null = null;
let lastFetchTime = 0;
const CACHE_DURATION_MS = 5 * 60 * 1000; // 5 minutes

export async function fetchProducts(forceRefresh = false): Promise<Product[]> {
  // 1. Memory Cache Check (Instant for intra-page navigation)
  if (
    !forceRefresh &&
    cachedProductsPromise &&
    Date.now() - lastFetchTime < CACHE_DURATION_MS
  ) {
    return cachedProductsPromise;
  }

  // 2. LocalStorage Cache Check (Instant for hard reloads < 200ms)
  if (!forceRefresh && typeof window !== "undefined") {
    try {
      const stored = localStorage.getItem("foodcast_products_cache");
      const storedTime = localStorage.getItem("foodcast_products_time");
      if (stored && storedTime && Date.now() - parseInt(storedTime) < CACHE_DURATION_MS * 12) {
        const parsed = JSON.parse(stored);
        if (parsed && parsed.length > 0) {
          // If we have no active memory promise, fulfill it with localStorage data
          if (!cachedProductsPromise) {
            cachedProductsPromise = Promise.resolve(parsed);
            lastFetchTime = parseInt(storedTime);
            
            // Optional: Kick off a silent background revalidation here
            _fetchProducts().then(freshData => {
              localStorage.setItem("foodcast_products_cache", JSON.stringify(freshData));
              localStorage.setItem("foodcast_products_time", Date.now().toString());
              cachedProductsPromise = Promise.resolve(freshData);
              lastFetchTime = Date.now();
            }).catch(console.error);
          }
          return cachedProductsPromise;
        }
      }
    } catch (e) {
      console.warn("LocalStorage cache access failed", e);
    }
  }

  // 3. Network Fetch Fallback (Only blocks if cache is empty)
  cachedProductsPromise = _fetchProducts().then(data => {
    if (typeof window !== "undefined") {
      try {
        localStorage.setItem("foodcast_products_cache", JSON.stringify(data));
        localStorage.setItem("foodcast_products_time", Date.now().toString());
      } catch (e) {}
    }
    return data;
  });
  
  lastFetchTime = Date.now();
  return cachedProductsPromise;
}

async function _fetchProducts(): Promise<Product[]> {
  const sixtyDaysAgo = new Date();
  sixtyDaysAgo.setDate(sixtyDaysAgo.getDate() - 60);
  const sinceDate = sixtyDaysAgo.toISOString().split("T")[0];

  async function fetchAll<T>(queryBuilder: any, pageSize: number = 1000): Promise<T[]> {
    let allData: T[] = [];
    let start = 0;
    while (true) {
      const { data, error } = await queryBuilder.range(start, start + pageSize - 1);
      if (error) throw error;
      if (!data || data.length === 0) break;
      allData.push(...data);
      if (data.length < pageSize) break;
      start += pageSize;
    }
    return allData;
  }

  try {
    const [productRows, priceRows, predRows] = await Promise.all([
      fetchAll<ProductRow>(supabase.from("products").select("id, name, variant, origin, category, image_url, description")),
      fetchAll<RawPrice>(supabase.from("food_prices").select("product_name, product_category, product_variant, origin, price_index, report_date, unit").gte("report_date", sinceDate).order("report_date", { ascending: true })),
      fetchAll<PredictionRow>(supabase.from("predictions").select("product_id, prediction_date, predicted_price, lower_bound, upper_bound").order("prediction_date", { ascending: true })),
    ]);

    if (priceRows.length === 0) return [];

    const productById = new Map<string, ProductRow>();
    const productMetaByKey = new Map<string, ProductRow>();
    for (const p of productRows) {
      productById.set(p.id, p);
      productMetaByKey.set(`${p.name}|${p.variant || ''}|${p.origin || ''}`, p);
    }

    const predsByProductId = new Map<string, PredictionRow[]>();
    for (const pred of predRows) {
      if (!predsByProductId.has(pred.product_id)) predsByProductId.set(pred.product_id, []);
      predsByProductId.get(pred.product_id)!.push(pred);
    }

    const pricesByKey = new Map<string, RawPrice[]>();
    for (const row of priceRows) {
      const key = `${row.product_name}|${row.product_variant || ''}|${row.origin || ''}`;
      if (!pricesByKey.has(key)) pricesByKey.set(key, []);
      pricesByKey.get(key)!.push(row);
    }

    const products: Product[] = [];

    for (const [key, rows] of pricesByKey) {
      if (rows.length < 2) continue;

      const baseName = rows[0].product_name;
      const baseVariant = rows[0].product_variant || "";
      const baseOrigin = rows[0].origin || "";

      const metaRow = productMetaByKey.get(`${baseName}|${baseVariant}|${baseOrigin}`);

      const category = metaRow?.category || rows[0].product_category || "Other";
      const description = metaRow?.description || `${baseName} is a tracked commodity in the NCR agri-fishery market.`;
      const image = metaRow?.image_url || "";
      const variant = baseVariant;
      const origin = baseOrigin;
      const emoji = CATEGORY_EMOJI[category] || "📦";

      const currentPrice = rows[rows.length - 1].price_index;
      const prevIdx = Math.max(0, rows.length - 8);
      const previousPrice = rows[prevIdx].price_index;

      let allPredictions: PredictionRow[] = [];
      if (metaRow) {
        allPredictions = predsByProductId.get(metaRow.id) || [];
      } else {
        // Fallback if no exact meta row exists: match just by name
        for (const p of productRows) {
          if (p.name === baseName) {
            const preds = predsByProductId.get(p.id);
            if (preds && preds.length > allPredictions.length) {
              allPredictions = preds;
            }
          }
        }
      }

      let predictedPrice: number;
      if (allPredictions.length > 0) {
        const slice = allPredictions.slice(0, 7);
        predictedPrice = Math.round((slice.reduce((sum, p) => sum + p.predicted_price, 0) / slice.length) * 100) / 100;
      } else {
        const recentPrices = rows.slice(-7).map((r) => r.price_index);
        const slope = linearSlope(recentPrices);
        predictedPrice = Math.round((currentPrice + slope * 7) * 100) / 100;
      }

      const changePct = currentPrice === 0 ? 0 : ((predictedPrice - currentPrice) / currentPrice) * 100;
      const sentiment: "Bullish" | "Bearish" | "Neutral" = changePct > 1 ? "Bullish" : changePct < -1 ? "Bearish" : "Neutral";
      const sparklineData = rows.slice(-7).map((r) => ({ value: r.price_index }));

      const mlPredForChart = allPredictions.length > 0 ? allPredictions.map((p) => ({ date: p.prediction_date, predicted_price: p.predicted_price })) : null;

      const forecastData = buildForecastData(rows, predictedPrice, mlPredForChart);
      const volume = `${(rows.length * 150).toLocaleString()} kg`;

      const dailyForecast = [];
      const forecastDays = allPredictions.length > 0 ? allPredictions.slice(0, 30) : [];
      
      if (forecastDays.length > 0) {
        for (let i = 0; i < forecastDays.length; i++) {
          const p = forecastDays[i];
          const prevPrice = i === 0 ? currentPrice : forecastDays[i - 1].predicted_price;
          const diff = p.predicted_price - prevPrice;
          const pct = (diff / prevPrice) * 100;
          
          let reasoning = "Market forces expected to stabilize with consistent inventory levels.";
          if (pct > 0.5) {
            reasoning = "Expected supply tightness combined with elevated local demand indicates upward pressure.";
          } else if (pct < -0.5) {
            reasoning = "Inflow of new harvests and eased supply chain bottlenecks are projected to ease prices.";
          } else if (pct > 0.1) {
            reasoning = "Slight uptick due to minor seasonal fluctuations and transport costs.";
          } else if (pct < -0.1) {
            reasoning = "Minor downward correction following market saturation in key trading posts.";
          }
          
          dailyForecast.push({
            date: p.prediction_date,
            predicted_price: p.predicted_price,
            reasoning
          });
        }
      } else {
        // Fallback for no ML predictions
        const recentPrices = rows.slice(-7).map((r) => r.price_index);
        const slope = linearSlope(recentPrices);
        for (let i = 1; i <= 30; i++) {
          const d = new Date(rows[rows.length - 1].report_date);
          d.setDate(d.getDate() + i);
          const pPrice = Math.round((currentPrice + slope * i) * 100) / 100;
          
          let reasoning = "Market forces expected to stabilize with consistent inventory levels.";
          if (slope > 0.5) reasoning = "Expected supply tightness combined with elevated local demand indicates upward pressure.";
          else if (slope < -0.5) reasoning = "Inflow of new harvests and eased supply chain bottlenecks are projected to ease prices.";
          
          dailyForecast.push({
            date: d.toISOString().split("T")[0],
            predicted_price: pPrice,
            reasoning
          });
        }
      }

      products.push({
        id: metaRow ? metaRow.id : slugify(`${baseName} ${baseVariant} ${baseOrigin}`),
        name: baseName,
        description,
        category,
        emoji,
        image,
        variant: baseVariant,
        origin: baseOrigin,
        currentPrice,
        predictedPrice,
        previousPrice,
        volume,
        sentiment,
        sparklineData,
        forecastData,
        dailyForecast,
      });
    }

    products.sort((a, b) => a.name.localeCompare(b.name));
    return products;
  } catch (e) {
    console.error("Error fetching data:", e);
    return [];
  }
}

export async function fetchProductById(id: string): Promise<Product | null> {
  const allProducts = await fetchProducts();
  return allProducts.find((p) => p.id === id) ?? null;
}

export async function fetchProductHistory(productName: string, limit = 365): Promise<RawPrice[]> {
  const { data, error } = await supabase
    .from("food_prices")
    .select("product_name, product_category, product_variant, origin, price_index, report_date, unit")
    .eq("product_name", productName)
    .order("report_date", { ascending: true })
    .limit(limit);

  if (error || !data) return [];
  return data as RawPrice[];
}

function buildForecastData(
  historyRows: RawPrice[],
  fallbackPredictedPrice: number,
  mlPredictions: { date: string; predicted_price: number }[] | null
) {
  const result: { name: string; actual: number | null; predicted: number | null }[] = [];
  
  const historyMap = new Map<string, number[]>();
  for (const r of historyRows) {
    const d = new Date(r.report_date);
    const key = `${d.getFullYear()}-${String(d.getMonth()).padStart(2, "0")}`;
    if (!historyMap.has(key)) historyMap.set(key, []);
    historyMap.get(key)!.push(r.price_index);
  }

  const sortedKeys = Array.from(historyMap.keys()).sort();
  for (const key of sortedKeys) {
    const prices = historyMap.get(key)!;
    const avg = prices.reduce((a, b) => a + b, 0) / prices.length;
    const monthIdx = parseInt(key.split("-")[1]);
    const monthName = MONTH_NAMES[monthIdx];
    result.push({
      name: monthName,
      actual: Math.round(avg * 100) / 100,
      predicted: null,
    });
  }

  const lastDateStr = historyRows[historyRows.length - 1].report_date;
  const lastDate = new Date(lastDateStr);
  const lastPrice = historyRows[historyRows.length - 1].price_index;

  if (result.length > 0) {
    result[result.length - 1].predicted = result[result.length - 1].actual;
  }

  if (mlPredictions && mlPredictions.length > 0) {
    const predMonthlyMap = new Map<string, number[]>();
    for (const p of mlPredictions) {
      const d = new Date(p.date);
      const key = `${d.getFullYear()}-${String(d.getMonth()).padStart(2, "0")}`;
      if (!predMonthlyMap.has(key)) predMonthlyMap.set(key, []);
      predMonthlyMap.get(key)!.push(p.predicted_price);
    }
    const predMonths = Array.from(predMonthlyMap.keys()).sort().slice(0, 3);

    for (const key of predMonths) {
      const prices = predMonthlyMap.get(key)!;
      const avg = prices.reduce((a, b) => a + b, 0) / prices.length;
      const monthIdx = parseInt(key.split("-")[1]);
      const monthName = MONTH_NAMES[monthIdx];
      result.push({
        name: monthName,
        actual: null,
        predicted: Math.round(avg * 100) / 100,
      });
    }
  } else {
    const recentPrices = historyRows.slice(-7).map((r) => r.price_index);
    const slope = linearSlope(recentPrices);

    for (let i = 1; i <= 3; i++) {
      const futureMonth = new Date(lastDate);
      futureMonth.setMonth(futureMonth.getMonth() + i);
      const monthName = MONTH_NAMES[futureMonth.getMonth()];
      const projectedPrice = Math.round((lastPrice + slope * 30 * i) * 100) / 100;
      result.push({
        name: monthName,
        actual: null,
        predicted: projectedPrice,
      });
    }
  }

  return result;
}
