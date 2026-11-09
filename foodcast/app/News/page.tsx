import { fetchPaginatedUniqueNews, fetchNewsCategories, INITIAL_UNIQUE_NEWS_COUNT } from "../lib/data";
import News from "../client/News";

export const revalidate = 0;
export const dynamic = 'force-dynamic';

export default async function NewsPage() {
  // Fetch initial data on the server during SSG/ISR
  const [newsData, categories] = await Promise.all([
    fetchPaginatedUniqueNews(0, INITIAL_UNIQUE_NEWS_COUNT, "", "All", "All"),
    fetchNewsCategories()
  ]);

  return (
    <News 
      initialNews={newsData.data} 
      initialTotal={newsData.total} 
      initialOffset={newsData.rawCount}
      initialCategories={categories} 
    />
  );
}
