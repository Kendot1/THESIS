import type { NewsArticle } from "./data";

const LPG_MENTION = /\b(?:lpg|liquefied petroleum gas)\b/i;
const MAX_NEWS_TAGS = 3;
const MAX_PRODUCT_TAGS = 3;

function decodeTagKeyword(keyword: string): string {
  try {
    return decodeURIComponent(keyword);
  } catch {
    return keyword;
  }
}

/** Hide LPG-specific keywords while retaining other price-impact tags on the article. */
export function getNewsTagKeywords(article: Pick<NewsArticle, "keywords">): string[] {
  const seen = new Set<string>();

  return (article.keywords || [])
    .map(decodeTagKeyword)
    .map(keyword => keyword.trim().replace(/\s+/g, " "))
    .filter(keyword => {
      if (!keyword || LPG_MENTION.test(keyword)) return false;

      const normalized = keyword.toLowerCase();
      if (seen.has(normalized)) return false;

      seen.add(normalized);
      return true;
    })
    .slice(0, MAX_NEWS_TAGS);
}

export function getInheritedTags(productName: string, allNews: NewsArticle[]): string[] {
  const tags = new Set<string>();
  const now = new Date();

  allNews.forEach((article) => {
    if (article.affectedProducts && article.affectedProducts.includes(productName)) {
      // 1. Check probability (must be at least 60%)
      const probability = article.probability !== undefined ? article.probability : 1.0;
      if (probability < 0.60) return;

      // 2. Check time validity (is the news still affecting the market?)
      if (article.date && article.timeValidityDays !== undefined) {
        const publishedDate = new Date(article.date);
        const expirationDate = new Date(publishedDate);
        expirationDate.setDate(expirationDate.getDate() + article.timeValidityDays);
        
        if (now > expirationDate) {
          return; // Skip expired news tags
        }
      }

      const keywords = getNewsTagKeywords(article);
      if (keywords.length > 0) {
        // Keep each article's tag contribution compact and consistent.
        keywords.forEach((kw) => tags.add(kw.toUpperCase())); // Normalize to uppercase to make filtering easier
      }
    }
  });
  
  let finalTags = Array.from(tags);

  // Filter mutually exclusive alerts (keep only the most severe)
  if (finalTags.includes("RED ALERT") && finalTags.includes("YELLOW ALERT")) {
    finalTags = finalTags.filter((t) => t !== "YELLOW ALERT");
  }

  return finalTags.slice(0, MAX_PRODUCT_TAGS);
}
