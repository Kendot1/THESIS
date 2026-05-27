import { fetchProducts, fetchNews } from "./lib/data";
import Home from "./client/Home";

export const revalidate = 3600; // ISR revalidation (1 hour)
export const dynamic = 'force-static';

export default async function HomePage() {
  // Fetch data on the server at build time (SSG) and revalidate hourly (ISR)
  const [products, news] = await Promise.all([
    fetchProducts(),
    fetchNews(10),
  ]);

  // Strip heavy forecast arrays from products that aren't daily movers
  // This reduces the initial HTML payload size drastically (e.g., 4MB -> 200KB)
  // SWR will fetch the full data in the background on the client.
  const dailyMoversIds = [...products]
    .sort((a, b) => {
      const changeA = a.currentPrice === 0 ? 0 : Math.abs((a.predictedPrice - a.currentPrice) / a.currentPrice);
      const changeB = b.currentPrice === 0 ? 0 : Math.abs((b.predictedPrice - b.currentPrice) / b.currentPrice);
      return changeB - changeA;
    })
    .slice(0, 15)
    .map(p => p.id);

  const optimizedProducts = products.map(p => {
    if (dailyMoversIds.includes(p.id)) return p;
    return { ...p, forecastData: [], dailyForecast: [] };
  });

  return <Home initialProducts={optimizedProducts} initialNews={news} />;
}