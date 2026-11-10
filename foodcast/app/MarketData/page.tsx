import { fetchProducts } from "../lib/data";
import MarketData from "../client/MarketData";

export const revalidate = 3600; // ISR revalidation (1 hour)

export default async function MarketDataPage() {
  // Fetch products data on the server during SSG/ISR
  const products = await fetchProducts().catch(() => undefined);
  // Keep the build available during an upstream outage; SWR loads data on mount.
  if (!products) return <MarketData />;

  // Strip heavy forecast arrays to reduce HTML payload (MarketData doesn't show charts)
  const optimizedProducts = products.map((p) => {
    return { ...p, forecastData: [], dailyForecast: [] };
  });

  return <MarketData initialProducts={optimizedProducts} />;
}
