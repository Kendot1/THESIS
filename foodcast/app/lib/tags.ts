import { NewsArticle } from "./data";

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

      if (article.keywords) {
        // Limit to 3 tags maximum per article to prevent UI clutter
        article.keywords.slice(0, 3).forEach((kw) => tags.add(kw.toUpperCase())); // Normalize to uppercase to make filtering easier
      }
    }
  });
  
  let finalTags = Array.from(tags);

  // Filter mutually exclusive alerts (keep only the most severe)
  if (finalTags.includes("RED ALERT") && finalTags.includes("YELLOW ALERT")) {
    finalTags = finalTags.filter((t) => t !== "YELLOW ALERT");
  }

  return finalTags.slice(0, 5); // Return a maximum of 5 distinct tags per product
}
