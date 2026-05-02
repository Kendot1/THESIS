import asyncio
from crawl4ai import AsyncWebCrawler, CacheMode, CrawlerRunConfig

async def main():
    async with AsyncWebCrawler() as crawler:
        config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)
        result = await crawler.arun(url="https://news.abs-cbn.com/business/2024/04/23/rice-prices-to-remain-high-until-mid-2024-da", config=config)
        import json
        with open("scratch_output.json", "w", encoding="utf-8") as f:
            json.dump({
                "metadata": result.metadata,
                "media": result.media
            }, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    asyncio.run(main())
