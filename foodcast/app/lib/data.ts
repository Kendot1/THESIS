import { supabase } from "../../lib/supabase";

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
}

export interface NewsArticle {
  id: string;
  title: string;
  excerpt: string;
  content: string;
  category: string;
  date: string;
  image: string;
  url: string;
  source: string;
  sentimentScore?: number;
  keywords?: string[];
  affectedProducts?: string[];
}

// ─── Supabase Edge Function Base URL ───────────────────────

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;
const EDGE_FN_BASE = `${SUPABASE_URL}/functions/v1/foodcast`;

const memoryCache: Record<string, { data: any; expiry: number }> = {};

const LOCAL_CACHE_PREFIX = "foodcast_cache_";
const CACHE_TTL = 1000 * 60 * 60; // 1 hour persistent cache

async function fetchFromNetwork<T>(path: string): Promise<T> {
  const now = Date.now();
  const res = await fetch(`${EDGE_FN_BASE}/${path}`, {
    headers: {
      "Authorization": `Bearer ${SUPABASE_ANON_KEY}`,
      "Content-Type": "application/json",
    },
    cache: 'no-store',
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || `Edge function error: ${res.status}`);
  }

  const data = await res.json();
  
  // Update memory cache (1 minute)
  memoryCache[path] = { data, expiry: now + 60 * 1000 };
  
  // Update localStorage (1 hour)
  if (typeof window !== "undefined") {
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
  return fetchFromNetwork<T>(path);
}

// ─── Data Fetching (calls Supabase Edge Function) ──────────

export async function fetchProducts(): Promise<Product[]> {
  try {
    return await edgeFetch<Product[]>("products");
  } catch (e) {
    console.error("Error fetching products:", e);
    return [];
  }
}

// Fetch trending views from Supabase
export async function fetchTrendingInteractions(): Promise<Record<string, number>> {
  try {
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
    let query = supabase.from("news_articles").select("id, title, content, event_type, published_at, image_url, url, source, sentiment_score, keywords, affected_products", { count: "exact" });

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
      excerpt: article.content ? (article.content.substring(0, 150) + "...") : "",
      content: article.content || "",
      category: (article.event_type || "News").replace(/_/g, ' '),
      date: new Date(article.published_at).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" }),
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
