import TagClientView from "../../client/TagClientView";
import { fetchProducts, fetchNews } from "../../lib/data";
import { getInheritedTags } from "../../lib/tags";

export const dynamic = 'force-static';
export const revalidate = 3600;

export async function generateStaticParams() {
  const newsList = await fetchNews(50);
  const tags = new Set<string>();
  
  newsList.forEach((article) => {
    article.keywords?.forEach((kw) => tags.add(kw));
  });

  return Array.from(tags).map((tag) => ({
    id: encodeURIComponent(tag),
  }));
}

export default async function TagPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const tag = decodeURIComponent(id);
  const tagUpper = tag.trim().toUpperCase();
  
  const [products, newsList] = await Promise.all([
    fetchProducts(),
    fetchNews(50),
  ]);

  // Compute related news
  const relatedNews = newsList.filter((n) => 
    n.keywords?.some((k) => k.trim().toUpperCase() === tagUpper)
  );

  // Compute grouped products
  const productsWithThisTag = new Set<string>();
  products.forEach((p) => {
    if (productsWithThisTag.has(p.name)) return;
    const tags = getInheritedTags(p.name, newsList);
    if (tags.some((t) => t === tagUpper)) {
      productsWithThisTag.add(p.name);
    }
  });

  const allProductNames = new Set<string>(productsWithThisTag);
  relatedNews.forEach((n) => {
    n.affectedProducts?.forEach((name) => allProductNames.add(name));
  });

  const groupedMap = new Map<string, any>();
  products
    .filter((p) => allProductNames.has(p.name))
    .forEach((p) => {
      if (!groupedMap.has(p.name)) {
        groupedMap.set(p.name, {
          name: p.name,
          category: p.category,
          image: p.image,
          unit: p.unit,
          variants: [],
        });
      }
      groupedMap.get(p.name)!.variants.push({
        id: p.id,
        variant: p.variant,
        origin: p.origin,
        image: p.image,
        currentPrice: p.currentPrice,
        predictedPrice: p.predictedPrice,
      });
    });

  const groupedProducts = Array.from(groupedMap.values());

  return <TagClientView tagId={id} precomputedNews={relatedNews} precomputedProducts={groupedProducts} />;
}
