import { fetchDashboardProducts, fetchNews } from "./lib/data";
import Home from "./client/Home";

export const revalidate = 0;
export const dynamic = "force-dynamic";

export default async function HomePage() {
  // Render current dashboard data; the client also refreshes it every minute.
  const [products, news] = await Promise.all([
    fetchDashboardProducts(),
    fetchNews(10),
  ]);

  return <Home initialProducts={products} initialNews={news} />;
}
