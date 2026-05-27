import { fetchPaginatedNews, fetchNewsCategories } from "../lib/data";
import News from "../client/News";

export const revalidate = 3600; // ISR revalidation (1 hour)
export const dynamic = 'force-static';

export default async function NewsPage() {
  // Fetch initial data on the server during SSG/ISR
  const [newsData, categories] = await Promise.all([
    fetchPaginatedNews(0, 10, "", "All", "All"),
    fetchNewsCategories()
  ]);

  return (
    <News 
      initialNews={newsData.data} 
      initialTotal={newsData.total} 
      initialCategories={categories} 
    />
  );
}
