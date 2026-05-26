"use client";
import useSWR from "swr";
import { fetchProducts, fetchNews, Product, NewsArticle } from "./data";

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
  return useSWR<Product[]>("supabase_products", fetchProducts, {
    revalidateOnFocus: false,
    revalidateIfStale: false,
    dedupingInterval: 5 * 60 * 1000, // 5 min dedup
    fallbackData: fallbackData || getSyncCache<Product[]>("products"),
  });
}

export function useNews(limit = 10, fallbackData?: NewsArticle[]) {
  return useSWR<NewsArticle[]>(`supabase_news_${limit}`, () => fetchNews(limit), {
    revalidateOnFocus: false,
    revalidateIfStale: false,
    dedupingInterval: 5 * 60 * 1000,
    fallbackData: fallbackData || getSyncCache<NewsArticle[]>(`news?limit=${limit}`),
  });
}
