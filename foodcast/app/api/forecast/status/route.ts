import { fetchForecastStatus } from "../../../lib/data";
import { withModelCapability } from "../../../lib/model-quality";
import capabilitySnapshot from "../../../lib/model-quality.json";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET() {
  try {
    const status = withModelCapability(await fetchForecastStatus(), capabilitySnapshot);
    return Response.json(status, {
      headers: { "Cache-Control": "no-store, max-age=0" },
    });
  } catch (error) {
    console.error("Failed to fetch forecast status:", error);
    return Response.json({ error: "Forecast status unavailable" }, { status: 503 });
  }
}
