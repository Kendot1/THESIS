"use client";
import { SWRConfig } from "swr";
import { ReactNode } from "react";

/**
 * Global SWR Provider that shares an in-memory cache across all pages.
 * Without this, each page navigation resets the SWR cache, causing
 * re-fetches of data that was already loaded on the previous page.
 *
 * This is the #1 fix for the ~10s product card click delay — the Product
 * detail page no longer needs to re-fetch all products from the Edge
 * Function because the data is already warm in the shared cache.
 */
export default function SWRProvider({ children }: { children: ReactNode }) {
  return (
    <SWRConfig
      value={{
        provider: () => new Map(),
        revalidateOnFocus: false,
        revalidateIfStale: false,
        keepPreviousData: true, // Prevent flash of empty state during revalidation
        dedupingInterval: 5 * 60 * 1000, // 5 min dedup
      }}
    >
      {children}
    </SWRConfig>
  );
}
