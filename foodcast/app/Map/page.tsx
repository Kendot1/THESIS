import MapClient from "../client/Map";
import { fetchProducts } from "../lib/data";
import { MarketLocation, ncrMarkets } from "../lib/markets";

export const revalidate = 3600; // ISR revalidation (1 hour)
export const dynamic = 'force-static';

export const metadata = {
  title: "Market Map | FOODCAST",
  description: "Interactive map of NCR wet markets tracking agricultural commodities and fish prices.",
};

export default async function MapPage() {
  const products = await fetchProducts();
  
  // Use ALL known NCR markets — no dynamic geocoding of unknown origins
  const markets: MarketLocation[] = [...ncrMarkets];
  
  // Compute aggregate product statistics
  let totalProducts = 0;
  let totalChange = 0;

  products.forEach(p => {
    if (!p.origin) return;
    totalProducts += 1;
    if (p.currentPrice > 0) {
      const change = ((p.predictedPrice - p.currentPrice) / p.currentPrice) * 100;
      totalChange += change;
    }
  });

  const avgChange = totalProducts > 0 ? totalChange / totalProducts : 0;
  const productsPerMarket = totalProducts > 0 ? Math.round(totalProducts / markets.length) : 0;

  // Distribute aggregate stats evenly across all known markets for consistent display
  const normalizedStats: Record<string, { count: number; avgChange: number }> = {};
  
  markets.forEach(market => {
    normalizedStats[market.name] = {
      count: productsPerMarket,
      avgChange: avgChange,
    };
  });

  return <MapClient marketStats={normalizedStats} initialMarkets={markets} />;
}
