import { fetchDashboardProducts } from "../../../lib/data";

export const dynamic = "force-dynamic";
export const revalidate = 120;

export async function GET() {
  try {
    const products = await fetchDashboardProducts();
    return Response.json(products, {
      headers: { "Cache-Control": "public, s-maxage=120, stale-while-revalidate=300" },
    });
  } catch {
    return Response.json({ error: "Dashboard data is temporarily unavailable" }, {
      status: 503,
      headers: { "Cache-Control": "no-store, max-age=0", "Retry-After": "30" },
    });
  }
}
