import About from "../client/About";
import { fetchDashboardProducts, fetchForecastStatus } from "../lib/data";
import { withModelCapability } from "../lib/model-quality";
import capabilitySnapshot from "../lib/model-quality.json";

export const revalidate = 60;

export default async function AboutPage() {
  const [products, rawForecastStatus] = await Promise.all([
    fetchDashboardProducts(),
    fetchForecastStatus().catch(() => null),
  ]);
  const forecastStatus = withModelCapability(rawForecastStatus, capabilitySnapshot);
  return <About initialProducts={products} initialForecastStatus={forecastStatus} />;
}
