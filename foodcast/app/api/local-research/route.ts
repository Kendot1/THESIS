import "server-only";
import type { StagingForecast } from "../../research-model-test/staging";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
const REF = "zhwhnnxbodzrklhgsurn";
const RUN = "03aaf1ae-3a5b-4262-9c4c-705ec0d6b196";
const BASE = `https://${REF}.supabase.co/rest/v1/`;

export async function GET(request: Request) {
  if (process.env.NODE_ENV === "development" && ["rolling-research", "current-hybrid"].includes(process.env.FOODCAST_LOCAL_RESEARCH ?? '') && process.env.FOODCAST_LOCAL_READ_ONLY === "1") {
    const params = new URL(request.url).searchParams;
    if (params.get('catalog') === '1' && params.get('vintage') === 'daily-average') {
      try {
        const { readDailyAverageCatalog } = await import('../../lib/local-rolling');
        return Response.json({items: await readDailyAverageCatalog()}, {headers: {'Cache-Control':'no-store'}});
      } catch {
        return Response.json({error:'Local catalog unavailable; no incumbent substitution'}, {status:503});
      }
    }
    const id = params.get("productId");
    if (!id || !/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(id)) return Response.json({ error: "Valid productId required" }, { status: 400 });
    try {
      const { readLocalRolling, readFreshRolling, readDailyAverage } = await import("../../lib/local-rolling");
      const vintage = new URL(request.url).searchParams.get('vintage');
      return Response.json(await (vintage === 'daily-average' || ((vintage === 'fresh' || vintage == null) && process.env.FOODCAST_LOCAL_RESEARCH === 'current-hybrid') ? readDailyAverage(id) : vintage === 'fresh' ? readFreshRolling(id) : readLocalRolling(id)), { headers: { "Cache-Control": "no-store" } });
    } catch {
      return Response.json({ error: "Local rolling research unavailable; no incumbent substitution" }, { status: 503 });
    }
  }
  if (process.env.NODE_ENV !== "development" || process.env.FOODCAST_LOCAL_RESEARCH !== REF) {
    return Response.json({ error: "Not found" }, { status: 404 });
  }
  const id = new URL(request.url).searchParams.get("productId");
  if (!id || !/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(id)) {
    return Response.json({ error: "Valid productId required" }, { status: 400 });
  }
  const key = process.env.FOODCAST_RESEARCH_SERVICE_KEY;
  if (!key) return Response.json({ error: "Local research access unavailable" }, { status: 503 });
  try {
    const read = async (path: string) => {
      const response = await fetch(BASE + path, {
        method: "GET", headers: { apikey: key, Authorization: `Bearer ${key}` },
        cache: "no-store", signal: AbortSignal.timeout(45000),
      });
      if (!response.ok) throw new Error("Research read failed");
      return response.json();
    };
    const [products, runs] = await Promise.all([
      read(`products?id=eq.${id}&select=id,name,category,variant,origin,unit`),
      read(`research_model_test_runs?id=eq.${RUN}&select=id,model_name,evidence_class,forecast_origin,predictions`),
    ]);
    const product = products[0];
    const run = runs[0];
    if (!product || products.length !== 1) return Response.json({ error: "Product unavailable" }, { status: 404 });
    if (runs.length !== 1 || run.id !== RUN || run.model_name !== "calendar_hybrid_7_4_1"
      || run.evidence_class !== "RETROSPECTIVE_RESEARCH_TEST" || run.forecast_origin !== "2026-01-01"
      || !Array.isArray(run.predictions)) throw new Error("Unexpected research contract");
    const predictions = (run.predictions as StagingForecast[]).filter(row => {
      const identity = row.product_series;
      return identity.product_name === product.name && identity.product_category === product.category
        && identity.product_variant === product.variant && identity.origin === product.origin && identity.unit === product.unit;
    }).map(row => ({ ...row, confidence_score: null, confidence_level: "Insufficient data" }));
    if (predictions.some(row => row.forecast_origin !== "2026-01-01")) throw new Error("Unexpected origin");
    return Response.json({ project_ref: REF, run_id: RUN, source: "remote_research_model_test_runs",
      forecast_origin: run.forecast_origin, product, confidence_score: null, metrics: null, predictions,
      unavailable_reason: predictions.length ? null : "No exact full-identity match in this research run" },
    { headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ error: "Remote research read unavailable; no incumbent substitution" }, { status: 503 });
  }
}
