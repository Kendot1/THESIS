import { fetchProducts } from "../lib/data";
import Predict from "../client/Predict";

export const revalidate = 3600; // ISR revalidation (1 hour)
export const dynamic = 'force-static';

export default async function PredictPage() {
  // Fetch products data on the server during SSG/ISR
  const products = await fetchProducts();

  // Strip heavy forecast arrays from products that aren't featured
  // This reduces the initial HTML payload size drastically
  // SWR will fetch the full data in the background on the client.
  const uniqueMap = new Map();
  for (const p of products) {
    if (!uniqueMap.has(p.name)) {
      uniqueMap.set(p.name, p);
    } else if (p.sentiment === "Bullish" && uniqueMap.get(p.name).sentiment !== "Bullish") {
      uniqueMap.set(p.name, p);
    }
  }
  const uniqueProducts = Array.from(uniqueMap.values());
  const featuredIds = uniqueProducts
    .sort((a, b) => {
      const isBullishA = a.sentiment === "Bullish" ? 1 : 0;
      const isBullishB = b.sentiment === "Bullish" ? 1 : 0;
      if (isBullishA !== isBullishB) return isBullishB - isBullishA;

      const changeA = a.currentPrice ? ((a.predictedPrice - a.currentPrice) / a.currentPrice) * 100 : 0;
      const changeB = b.currentPrice ? ((b.currentPrice === 0 ? 0 : (b.predictedPrice - b.currentPrice) / b.currentPrice)) * 100 : 0;
      return changeB - changeA;
    })
    .slice(0, 6)
    .map((p: any) => p.id);

  const optimizedProducts = products.map(p => {
    if (featuredIds.includes(p.id)) return p;
    return { ...p, forecastData: [], dailyForecast: [] };
  });

  return <Predict initialProducts={optimizedProducts} />;
}
