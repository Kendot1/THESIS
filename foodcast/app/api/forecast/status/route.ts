import { fetchForecastStatus } from "../../../lib/data";
import { withModelCapability } from "../../../lib/model-quality";
import capabilitySnapshot from "../../../lib/model-quality.json";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET() {
  try {
    const rawStatus = await fetchForecastStatus();
    const status = withModelCapability(rawStatus, capabilitySnapshot);
    return Response.json(status, {
      headers: { "Cache-Control": "public, s-maxage=60, stale-while-revalidate=300" },
    });
  } catch (error) {
    console.error("Failed to fetch forecast status:", error);
    return Response.json({ error: "Forecast status unavailable" }, { status: 503 });
  }
}
