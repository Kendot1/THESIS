import { fetchDashboardProducts, fetchNews } from "./lib/data";
import Home from "./client/Home";
import { homepagePerformance } from "./lib/historical-performance.server";

// Serve the last rendered dashboard immediately and refresh it in the
// background once a minute. A hard reload should not wait on Supabase/Edge.
export const revalidate = 60;

export default async function HomePage() {
  // Render current dashboard data; the client also refreshes it every minute.
  // Live data loads through the existing client hooks, never blocking first paint.
  const products: Awaited<ReturnType<typeof fetchDashboardProducts>> = [];
  const news: Awaited<ReturnType<typeof fetchNews>> = [];

  return <Home initialProducts={products} initialNews={news} historical_forecast_accuracy_pct={(await homepagePerformance()).historical_forecast_accuracy_pct} />;
}
