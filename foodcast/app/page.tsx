import { fetchDashboardProducts, fetchNews } from "./lib/data";
import Home from "./client/Home";
import { homepagePerformance } from "./lib/historical-performance.server";

// Serve the last rendered dashboard immediately and refresh it in the
// background once a minute. A hard reload should not wait on Supabase/Edge.
export const revalidate = 60;

export default async function HomePage() {
  // Pre-populate dashboard products and news during SSR / ISR so the page
  // renders instantly without showing cold full-page skeleton loaders.
  const [products, news, perf] = await Promise.all([
    fetchDashboardProducts().catch(() => []),
    fetchNews(10).catch(() => []),
    homepagePerformance().catch(() => ({ historical_forecast_accuracy_pct: null })),
  ]);

  return <Home initialProducts={products} initialNews={news} historical_forecast_accuracy_pct={perf.historical_forecast_accuracy_pct} />;
}
