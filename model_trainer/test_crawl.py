import asyncio
from crawl4ai import AsyncWebCrawler, CacheMode, CrawlerRunConfig

async def main():
    async with AsyncWebCrawler() as crawler:
        config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)
        result = await crawler.arun(url="https://www.abs-cbn.com/news/business/2026/4/28/government-fintech-work-together-through-crisis-1229", config=config)
        
        print("METADATA KEYS:", result.metadata.keys() if result.metadata else "No metadata")
        if result.metadata:
            for k, v in result.metadata.items():
                if "image" in k.lower():
                    print(f"FOUND IMAGE IN METADATA {k}: {v}")
                    
        import re
        if result.html:
            og_match = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', result.html)
            if og_match:
                url = og_match.group(1).replace("&amp;", "&")
                print("REGEX OG:IMAGE:", url)
                
            matches = set(re.findall(r'([^"\'\s>]+editorImage[^"\'\s>]+)', result.html))
            matches_enc = set(re.findall(r'([^"\'\s>]+editorImage%2F[^"\'\s>]+)', result.html))
            print("EDITOR IMAGES FOUND:", matches)
            print("ENCODED EDITOR IMAGES FOUND:", matches_enc)
        
        print("MEDIA:", "Found" if result.media else "Not Found")
        if result.media and "images" in result.media:
            for img in result.media["images"][:3]:
                print(f"IMAGE MEDIA: {img.get('src')}")

if __name__ == "__main__":
    asyncio.run(main())
