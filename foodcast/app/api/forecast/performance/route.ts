import { homepagePerformance } from "../../../lib/historical-performance.server";

export const dynamic = "force-dynamic";
export async function GET() {
  return Response.json(await homepagePerformance(), { headers: { "Cache-Control": "no-store" } });
}
