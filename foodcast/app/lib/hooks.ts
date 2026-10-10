"use client";
import { useEffect, useState } from "react";
import useSWR from "swr";
import { fetchProducts, fetchNews, isPriceImpactNews, Product, NewsArticle, DashboardProduct, ForecastStatus } from "./data";

const LOCAL_CACHE_PREFIX = "foodcast_cache_";

function getSyncCache<T>(key: string): T | undefined {
  if (typeof window !== "undefined") {
    try {
      const cached = localStorage.getItem(LOCAL_CACHE_PREFIX + key);
      if (cached) {
        const parsed = JSON.parse(cached);
        if (parsed.expiry > Date.now()) {
          return parsed.data as T;
        }
      }
    } catch (e) {
      // Ignore errors (e.g., quota exceeded, privacy mode)
    }
  }
  return undefined;
}

export function useProducts(fallbackData?: Product[]) {
  return useSWR<Product[]>("supabase_products_v6_horizons", fetchProducts, {
    revalidateOnFocus: false,
    revalidateIfStale: false,
    // Static pages may still contain the previous API contract or stripped
    // chart arrays. Hydrate with the versioned full-product cache on mount.
    revalidateOnMount: true,
    dedupingInterval: 5 * 60 * 1000, // 5 min dedup
    fallbackData: fallbackData || getSyncCache<Product[]>("products"),
  });
}

async function fetchDashboardProducts(): Promise<DashboardProduct[]> {
  const response = await fetch("/api/dashboard/products", { cache: "no-store" });
  if (!response.ok) throw new Error("Failed to fetch dashboard products");
  return response.json();
}

export function useDashboardProducts(fallbackData: DashboardProduct[]) {
  return useSWR<DashboardProduct[]>("dashboard_products_v2_live", fetchDashboardProducts, {
    // Never seed the full-product cache with summaries: detail pages need history.
    fallbackData,
    // The homepage server snapshot is revalidated every minute. Use it on
    // reload instead of making first paint wait for a second Edge round-trip.
    revalidateOnMount: fallbackData.length === 0,
    revalidateOnFocus: true,
    revalidateIfStale: fallbackData.length === 0,
    refreshInterval: 60 * 1000,
    dedupingInterval: 10 * 1000,
  });
}

async function fetchForecastStatus(): Promise<ForecastStatus | null> {
  const response = await fetch("/api/forecast/status", { cache: "no-store" });
  if (!response.ok) throw new Error("Failed to fetch forecast status");
  return response.json();
}

export function useForecastStatus() {
  return useSWR<ForecastStatus | null>("forecast_status_v1", fetchForecastStatus, {
    revalidateOnFocus: true,
    refreshInterval: 60_000,
    dedupingInterval: 30_000,
    shouldRetryOnError: true,
    errorRetryInterval: 30_000,
  });
}

export function useClock(interval = 60_000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), interval);
    return () => window.clearInterval(timer);
  }, [interval]);
  return now;
}

export function useNews(limit = 10, fallbackData?: NewsArticle[]) {
  const cachedNews = fallbackData || getSyncCache<NewsArticle[]>(`news?limit=${limit}`);
  const result = useSWR<NewsArticle[]>(`supabase_news_${limit}`, () => fetchNews(limit), {
    revalidateOnFocus: false,
    revalidateIfStale: false,
    dedupingInterval: 5 * 60 * 1000,
    fallbackData: cachedNews?.filter(isPriceImpactNews),
  });
  return { ...result, data: result.data?.filter(isPriceImpactNews) };
}

import { fetchTrendingInteractions } from "./data";

export function useTrendingInteractions() {
  return useSWR<Record<string, number>>("trending_interactions", fetchTrendingInteractions, {
    revalidateOnFocus: false,
    dedupingInterval: 60 * 1000, // 1 minute dedup for trending views
  });
}
