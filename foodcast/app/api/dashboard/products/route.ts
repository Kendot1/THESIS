import { fetchDashboardProducts } from "../../../lib/data";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET() {
  const products = await fetchDashboardProducts();
  // fetchProducts returns [] on upstream failure. Do not cache that failure;
  // let SWR retry when the build-time dashboard data was unavailable.
  if (products.length === 0) {
    return Response.json([], { status: 503 });
  }
  return Response.json(products, {
    headers: { "Cache-Control": "no-store, max-age=0" },
  });
}
