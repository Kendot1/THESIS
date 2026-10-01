import { fetchDashboardProducts, fetchNews } from "./lib/data";
import Home from "./client/Home";

// Serve the last rendered dashboard immediately and refresh it in the
// background once a minute. A hard reload should not wait on Supabase/Edge.
export const revalidate = 60;

export default async function HomePage() {
  // Render current dashboard data; the client also refreshes it every minute.
  const [products, news] = await Promise.all([
    fetchDashboardProducts(),
    fetchNews(10),
  ]);

  return <Home initialProducts={products} initialNews={news} />;
}
