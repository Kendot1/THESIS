import { createClient } from "https://esm.sh/@supabase/supabase-js@2.42.0"

const DEFAULT_REQUEST_DEADLINE_MS = 25_000

export function runWithDeadline<T>(operation: (signal: AbortSignal) => Promise<T>, timeoutMs = DEFAULT_REQUEST_DEADLINE_MS, parentSignal?: AbortSignal): Promise<T> {
  const controller = new AbortController()
  let timedOut = false
  const abortFromParent = () => controller.abort(parentSignal?.reason)
  if (parentSignal?.aborted) abortFromParent()
  else parentSignal?.addEventListener("abort", abortFromParent, { once: true })
  const timer = setTimeout(() => { timedOut = true; controller.abort(new Error("Supabase request deadline exceeded")) }, timeoutMs)
  const request = Promise.resolve().then(() => operation(controller.signal))
  let onAbort: (() => void) | undefined
  const deadline = new Promise<never>((_, reject) => {
    onAbort = () => reject(timedOut ? new Error(`Supabase request deadline exceeded after ${timeoutMs}ms`) : controller.signal.reason ?? new Error("Supabase request aborted"))
    controller.signal.addEventListener("abort", onAbort, { once: true })
  })
  return Promise.race([request, deadline]).finally(() => { clearTimeout(timer); if (onAbort) controller.signal.removeEventListener("abort", onAbort); parentSignal?.removeEventListener("abort", abortFromParent) })
}

export function createDeadlineFetch(fetchImpl: typeof fetch = fetch, timeoutMs = DEFAULT_REQUEST_DEADLINE_MS): typeof fetch {
  return ((input: RequestInfo | URL, init?: RequestInit) => runWithDeadline(signal => fetchImpl(input, { ...init, signal }), timeoutMs, init?.signal ?? undefined)) as typeof fetch
}

export function createSupabaseClient(fetchImpl: typeof fetch = fetch) {
  return createClient(Deno.env.get("SUPABASE_URL") ?? "", Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "", { global: { fetch: createDeadlineFetch(fetchImpl) } })
}

export function statusForError(error: unknown): number {
  const status = typeof error === "object" && error !== null && "status" in error ? Number((error as { status?: unknown }).status) : NaN
  return Number.isInteger(status) && status >= 400 && status <= 599 ? status : 500
}

export function publicError(error: unknown): string {
  if (typeof error === "object" && error !== null) {
    const details = error as { message?: unknown; details?: unknown; hint?: unknown; code?: unknown; cause?: unknown }
    const parts = [details.message, details.details, details.hint, details.code]
      .filter((value): value is string => typeof value === "string" && value.length > 0)
    if (details.cause !== undefined) parts.push(publicError(details.cause))
    if (parts.length) return parts.join("; ")
  }
  return error instanceof Error ? error.message : "Unexpected server error"
}

// ── Rate Limiter ──────────────────────────────────────────
interface RateLimitRecord {
  count: number;
  resetAt: number;
}

const rateLimitMap = new Map<string, RateLimitRecord>();
const RATE_LIMIT_WINDOW_MS = 60_000;
const RATE_LIMIT_MAX_REQUESTS = 120;

export function checkRateLimit(
  clientIp: string,
  maxRequests = RATE_LIMIT_MAX_REQUESTS,
  windowMs = RATE_LIMIT_WINDOW_MS
): {
  allowed: boolean;
  limit: number;
  remaining: number;
  resetSeconds: number;
} {
  const now = Date.now();
  if (rateLimitMap.size > 2000) {
    for (const [key, record] of rateLimitMap.entries()) {
      if (record.resetAt <= now) rateLimitMap.delete(key);
    }
  }

  const record = rateLimitMap.get(clientIp);
  if (!record || record.resetAt <= now) {
    rateLimitMap.set(clientIp, { count: 1, resetAt: now + windowMs });
    return {
      allowed: true,
      limit: maxRequests,
      remaining: maxRequests - 1,
      resetSeconds: Math.ceil(windowMs / 1000),
    };
  }

  record.count += 1;
  const remaining = Math.max(0, maxRequests - record.count);
  const resetSeconds = Math.ceil((record.resetAt - now) / 1000);
  return {
    allowed: record.count <= maxRequests,
    limit: maxRequests,
    remaining,
    resetSeconds,
  };
}

// ── Memory Cache with Stale-While-Revalidate ──────────────
interface CacheEntry<T> {
  data: T;
  expiresAt: number;
  staleUntil: number;
}

export class MemoryCache<T> {
  private cache: CacheEntry<T> | null = null;
  private pending: Promise<T> | null = null;
  private ttlMs: number;
  private swrMs: number;

  constructor(ttlMs = 300_000, swrMs = 600_000) {
    this.ttlMs = ttlMs;
    this.swrMs = swrMs;
  }

  async getOrFetch(fetcher: () => Promise<T>): Promise<T> {
    const now = Date.now();

    if (this.cache && this.cache.expiresAt > now) {
      return this.cache.data;
    }

    if (this.cache && this.cache.staleUntil > now) {
      if (!this.pending) {
        this.pending = fetcher()
          .then((fresh) => {
            this.set(fresh);
            return fresh;
          })
          .catch((err) => {
            console.error("Background SWR refresh error:", err);
            return this.cache!.data;
          })
          .finally(() => {
            this.pending = null;
          });
      }
      return this.cache.data;
    }

    if (!this.pending) {
      this.pending = fetcher()
        .then((data) => {
          this.set(data);
          return data;
        })
        .finally(() => {
          this.pending = null;
        });
    }

    return this.pending;
  }

  set(data: T): void {
    const now = Date.now();
    this.cache = {
      data,
      expiresAt: now + this.ttlMs,
      staleUntil: now + this.ttlMs + this.swrMs,
    };
  }

  clear(): void {
    this.cache = null;
    this.pending = null;
  }
}

