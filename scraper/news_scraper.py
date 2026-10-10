"""
News scraping pipeline for Philippine food-market intelligence.
Discovers relevant stories from trusted local and international publishers,
then requires article-level evidence before storing them.
"""

import asyncio
import hashlib
import json
import re
import io
import uuid
import mimetypes
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any
from urllib.parse import urlparse, urljoin, quote_plus

# Support both ``python -m scraper.news_scraper`` and the historical direct
# script command without masking ImportErrors raised inside the helper itself.
if __package__ in (None, ""):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scraper.publication_time import publication_metadata
else:
    from .publication_time import publication_metadata

import httpx
from supabase import create_client, Client


# Force UTF-8 encoding for Windows console (prevents UnicodeEncodeError when printing emojis)
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
# Crawl4AI stores its robots SQLite database under this base directory. Use a
# workspace temp path by default so sandboxed Windows runs do not depend on the
# user profile being writable; honor an explicit local or runner override.
os.environ.setdefault(
    "CRAWL4_AI_BASE_DIRECTORY",
    str(Path(__file__).resolve().parent.parent / ".tmp" / "crawl4ai"),
)
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Local section feeds plus targeted Google News searches across trusted sources
# ──────────────────────────────────────────────
ABSCBN_SECTIONS = [
    "https://www.abs-cbn.com/business",
    "https://www.abs-cbn.com/business/companies",
    "https://www.abs-cbn.com/business/economy",
    "https://www.abs-cbn.com/news/nation",
    "https://www.abs-cbn.com/news/regions",
]

# Keep discovery queries tied to Philippine food markets. Indirect drivers such
# as war, shipping, and fuel are included only when the query also names a food
# commodity or food supply chain.
GOOGLE_SEARCH_QUERIES = [
    "Philippines rice palay bigas food commodity prices supply shortage",
    "Philippines vegetable onion garlic tomato prices harvest supply",
    "Philippines chicken pork beef egg fish prices supply catch",
    "Philippines typhoon flood drought crop damage harvest food prices",
    "Philippines El Nino La Nina crops fisheries food supply prices",
    "Philippines rice sugar corn food import tariff export ban prices",
    "Philippines war conflict blockade grain rice food imports supply prices",
    "Philippines shipping disruption port closure food cargo rice imports prices",
    "Philippines diesel gasoline fuel price hike farm fishing food transport costs",
    "Philippines fuel price increase food distribution agriculture commodity prices",
    "Philippines fertilizer animal feed costs farm production food prices",
    "Philippines DA price monitoring rice meat fish vegetable commodity prices",
]

SUPPORTED_NEWS_DOMAINS = (
    "abs-cbn.com",
    "gmanetwork.com",
    "inquirer.net",
    "philstar.com",
    "mb.com.ph",
    "businessworld-online.com",
    "pna.gov.ph",
    "da.gov.ph",
    "doe.gov.ph",
    "reuters.com",
    "apnews.com",
)

# ──────────────────────────────────────────────
# Keyword Pre-filter (to save LLM tokens)
# ──────────────────────────────────────────────
AGRI_FOOD_TOPIC_TERMS = (
    "food commodity", "food commodities", "food price", "food prices", "food supply",
    "agri-fishery", "agri fishery", "agriculture", "agrikultura", "agricultural",
    "farm", "farms", "farmer", "farmers", "pagsasaka", "magsasaka", "crop", "crops",
    "harvest", "palay", "rice", "bigas", "corn", "mais", "vegetable", "vegetables", "gulay",
    "onion", "sibuyas", "garlic", "bawang", "tomato", "kamatis", "chicken", "manok",
    "pork", "baboy", "beef", "baka", "egg", "itlog", "fish", "isda", "fishery", "fisheries",
    "fishing", "fisherfolk", "aquaculture", "bangus", "tilapia", "galunggong", "sugar", "asukal",
    "cooking oil", "potato", "carrot", "banana", "calamansi", "livestock", "poultry",
    "food logistics", "food distribution", "food transport", "food imports", "food exports",
    "food supply chain", "farm input", "farm inputs", "fertilizer", "fertiliser", "animal feed",
    "fish feed", "cold storage", "grain shipment", "grain shipments", "food cargo",
)

MARKET_IMPACT_TERMS = (
    "price", "prices", "presyo", "presyuhan", "cost", "costs", "mahal", "mura", "hike", "surge",
    "increase", "increases", "increased", "rise", "rises", "rose", "higher", "decrease", "decline",
    "declined", "drop", "fell", "lower", "pagtaas", "tumaas", "bumaba", "pagbaba", "pumalo", "bawas",
    "dagdag", "ani", "naani", "nasira", "kakulangan", "naapektuhan", "market rate", "retail",
    "wholesale", "supply", "shortage", "scarcity", "oversupply", "surplus", "production", "yield",
    "catch", "harvest", "import", "imports", "export", "exports", "tariff", "quota", "price cap",
    "price ceiling", "hoarding", "smuggling", "stock", "stocks", "stockpile", "crop damage",
    "damaged crops", "destroyed crops", "farm damage", "fish kill", "bagyo", "drought", "flood",
    "el nino", "la nina", "typhoon", "fuel hike", "fuel price", "diesel", "gasoline",
    "fertilizer costs", "feed costs", "shipping disruption", "port closure", "blockade",
    "export ban", "trade restriction", "trade restrictions", "shipment disruption", "war",
    "conflict", "freight cost", "transport cost",
)

SUPPORTED_PRODUCTS = (
    "Avocado", "Baguio Beans", "Banana", "Beef", "Bell Pepper", "Bittergourd", "Broccoli",
    "Cabbage", "Calamansi", "Carrot", "Cauliflower", "Celery", "Chayote", "Chicken",
    "Chicken Egg", "Chili", "Coconut Oil", "Corn", "Corn Cracked", "Corn Grits", "Eggplant",
    "Garlic", "Ginger", "Lettuce", "Mango", "Melon", "Milkfish", "Mung Beans", "Palm Oil",
    "Papaya", "Pechay Baguio", "Pechay Tagalog", "Pomelo", "Pork", "Potato", "Red Onion",
    "Rice", "Round Scad", "Salmon Head", "Sardines", "Squash", "Squid", "String Beans",
    "Sugar", "Tilapia", "Tomato", "Watermelon", "White Onion", "Yellow Sweet Corn", "Alumahan",
    "Kangkong",
)
PRODUCT_EVIDENCE_TERMS = {
    "Rice": ("rice", "palay", "bigas"),
    "Avocado": ("avocado",),
    "Baguio Beans": ("baguio beans", "snap beans"),
    "Banana": ("banana", "bananas", "saging"),
    "Beef": ("beef", "cattle", "baka"),
    "Bell Pepper": ("bell pepper", "capsicum"),
    "Bittergourd": ("bitter gourd", "bitter melon", "ampalaya"),
    "Broccoli": ("broccoli",),
    "Cabbage": ("cabbage",),
    "Calamansi": ("calamansi",),
    "Carrot": ("carrot", "carrots"),
    "Cauliflower": ("cauliflower",),
    "Celery": ("celery",),
    "Chayote": ("chayote",),
    "Chicken": ("chicken", "poultry", "manok"),
    "Chicken Egg": ("chicken egg", "egg", "eggs", "itlog"),
    "Chili": ("chili", "chilli", "siling labuyo", "siling pangsigang"),
    "Coconut Oil": ("coconut oil",),
    "Corn": ("corn", "maize", "mais"),
    "Corn Cracked": ("cracked corn", "corn feed", "feed-grade corn"),
    "Corn Grits": ("corn grits",),
    "Eggplant": ("eggplant", "talong"),
    "Garlic": ("garlic", "bawang"),
    "Ginger": ("ginger", "luya"),
    "Lettuce": ("lettuce",),
    "Mango": ("mango",),
    "Melon": ("melon", "cantaloupe"),
    "Milkfish": ("milkfish", "bangus"),
    "Mung Beans": ("mung beans", "mungbean", "monggo"),
    "Palm Oil": ("palm oil",),
    "Papaya": ("papaya",),
    "Pechay Baguio": ("pechay baguio", "baguio pechay"),
    "Pechay Tagalog": ("pechay tagalog", "tagalog pechay", "pechay"),
    "Pomelo": ("pomelo",),
    "Pork": ("pork", "pig", "hog", "baboy"),
    "Potato": ("potato", "potatoes", "patatas"),
    "Red Onion": ("red onion", "onion", "sibuyas"),
    "Round Scad": ("round scad", "galunggong"),
    "Salmon Head": ("salmon head",),
    "Sardines": ("sardines", "sardine"),
    "Squash": ("squash", "kalabasa"),
    "Squid": ("squid",),
    "String Beans": ("string beans", "yardlong beans", "sitaw"),
    "Sugar": ("sugar", "asukal"),
    "Tilapia": ("tilapia",),
    "Tomato": ("tomato", "tomatoes", "kamatis"),
    "Watermelon": ("watermelon",),
    "White Onion": ("white onion", "onion", "sibuyas"),
    "Yellow Sweet Corn": ("sweet corn", "yellow corn", "corn cob"),
    "Alumahan": ("alumahan", "indian mackerel"),
    "Kangkong": ("kangkong", "water spinach"),
}
AGRI_FOOD_TOPIC_TERMS = tuple(dict.fromkeys(
    (*AGRI_FOOD_TOPIC_TERMS, *(term for aliases in PRODUCT_EVIDENCE_TERMS.values() for term in aliases))
))
SUPPORTED_EVENT_TYPES = {
    "supply_shock", "demand_spike", "policy_change", "import_export", "price_movement", "weather", "fuel_energy",
}
EVIDENCE_IMPACT_TERMS = (
    "price", "prices", "cost", "costs", "hike", "surge", "increase", "increased", "rise", "rose",
    "higher", "decrease", "decline", "drop", "fell", "lower", "shortage", "scarcity", "supply",
    "surplus", "production", "yield", "harvest", "crop damage", "destroyed", "damaged", "blocked",
    "disruption", "disrupted", "ban", "halted", "stopped", "import", "imports", "export", "exports",
    "tariff", "quota", "price cap", "hoarding", "smuggling", "pagtaas", "tumaas", "bumaba", "kakulangan",
)

# ──────────────────────────────────────────────
# Strict LLM prompt — rejects anything not directly impacting food prices
# ──────────────────────────────────────────────
LLM_SYSTEM_PROMPT = """You are a strict food-price intelligence filter for a Philippine food price forecasting system.

Your job: determine if a news article has a concrete, evidence-based connection to the prices, availability, or production of a Philippine agri-fishery food commodity.

RELEVANT articles include only stories with a clearly stated effect on at least one named Philippine food commodity. Examples:
- Direct price changes of food commodities (rice, vegetables, meat, fish, etc.)
- Government price caps, tariffs, or import/export policies on food
- Supply chain disruptions (typhoons destroying crops, floods, droughts, El Niño/La Niña)
- Fuel or transport costs only when the article explicitly connects them to farming, fishing, food processing, or distribution of a named food commodity
- War, conflict, blockade, shipping disruption, or trade restrictions only when the article identifies a concrete effect on Philippine food imports, exports, a named commodity's supply, or its price
- Inflation reports only when they report food or named food-commodity prices
- Smuggling or hoarding of food commodities
- Harvest reports, crop yield data, planting season updates

NOT RELEVANT (REJECT these):
- General inflation, fuel/oil (including LPG/cooking gas), currency, business, trade, war, weather, or political stories without a concrete Philippine food-commodity price, production, or supply impact
- Wildlife, animal rescue, marine conservation, reef protection, and fishing enforcement stories with no reported food supply or price effect
- Food safety incidents, recalls, nutrition programs, or food aid that do not report a commodity-market effect
- Celebrity news, sports, entertainment, unrelated politics, and crime near farms

Only mark an article relevant when its text explicitly supports at least one specific product from the supplied product list. Do not infer a product or market impact from a broad topic alone. Treat fuel as an indirect cause only; never list fuel as an affected food product. A fuel price change by itself is not food-market news. A war or conflict mention by itself is not food-market news. Reject LPG/cooking-gas stories unless they also state a direct impact on a named raw food commodity.

Respond with ONLY valid JSON, no markdown fences, no explanation.

If NOT relevant: {"relevant": false}

If relevant:
{
  "relevant": true,
  "sentiment_score": <float -1.0 to 1.0. Negative = prices will INCREASE (bad for consumers). Positive = prices will DECREASE (good for consumers). 0 = neutral/stable>,
  "event_type": "<supply_shock | demand_spike | policy_change | import_export | price_movement | weather | fuel_energy>",
  "affected_products": ["<exact product names from {SUPPORTED_PRODUCTS}>"],
  "impact_evidence": "<an exact short quote from the article supporting the named commodity's price, production, or supply effect>",
  "keywords": ["<MAXIMUM 3 broad market drivers, e.g.: Fuel Hike, Weather Disturbance, Import Policy, Typhoon, Price Surge. Avoid specific nouns like 'Meralco' or 'Diesel'>"],
  "time_validity_days": <integer. How long will this event affect the market? e.g., 7 for a quick spike, 30 for a seasonal issue, 90 for El Nino>,
  "probability": <float 0.0 to 1.0. How likely is this to actually affect prices? e.g., 0.9 for a confirmed tariff hike, 0.4 for a rumored shortage>,
  "effect_magnitude": "<low | medium | high. How strong is the expected price impact?>",
  "summary": "<1-2 sentence summary focused on the PRICE IMPACT in English>",
  "title_tl": "<Translate the article's title into natural Filipino, ensuring proper grammar and punctuation>",
  "summary_tl": "<Translate the 1-2 sentence summary into natural, conversational Filipino. PAY SPECIAL ATTENTION TO PUNCTUATION: ensure proper use of commas, periods, and quotation marks where appropriate to make the sentences read clearly.>"
}

The impact_evidence must be copied verbatim from the provided title or article text, including the named food commodity and its stated price, production, or supply effect. Do not paraphrase or infer an indirect impact."""


class NewsScraper:
    """
    Scrapes relevant news via local feeds + targeted Google News discovery,
    uses LLM for strict relevance filtering and structured extraction,
    deduplicates, and stores to Supabase.
    """

    def __init__(self):
        self._client: Client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
        self._table = "news_articles"
        self._groq_key = os.environ.get("GROQ_API_KEY_NEWS_SCRAPER", "")
        self._openai_key = os.environ.get("OPENAI_API_KEY", "")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def run_daily_scrape(self) -> Dict[str, int]:
        """Execute the full daily scraping pipeline."""
        stats = {
            "discovered": 0, "new": 0, "relevant": 0, "stored": 0,
            "discovery_attempts": 0, "discovery_successes": 0,
            "discovery_failures": 0, "processing_failures": 0,
            "storage_failures": 0,
        }
        self._run_stats = stats

        try:
            from crawl4ai import AsyncWebCrawler
        except ImportError:
            raise RuntimeError("crawl4ai is not installed; install scraper/requirements.txt")

        if not self._groq_key and not self._openai_key:
            raise RuntimeError(
                "Missing news-analysis credentials: set GROQ_API_KEY_NEWS_SCRAPER "
                "or OPENAI_API_KEY"
            )

        llm_name = "Groq (gpt-oss-120b)" if self._groq_key else "OpenAI (gpt-4o-mini)"
        log.info(f"=== NEWS SCRAPING PIPELINE (TRUSTED SOURCES) === LLM: {llm_name}")

        # Step 1: Discover article URLs
        article_urls = await self._discover_article_urls()
        stats["discovered"] = len(article_urls)
        log.info(f"Discovered {len(article_urls)} article URLs.")

        if not stats["discovery_successes"]:
            raise RuntimeError(
                "News discovery could not read any source feeds or Google News pages; "
                f"attempts={stats['discovery_attempts']} failures={stats['discovery_failures']}"
            )

        if not article_urls:
            log.warning("No article URLs discovered — skipping.")
            return stats

        # Step 2: Filter already-processed URLs
        new_urls = self._filter_existing_urls(article_urls)
        stats["new"] = len(new_urls)
        log.info(f"{len(new_urls)} new URLs to process.")

        if not new_urls:
            log.info("All articles already processed.")
            return stats

        # Step 3: Crawl, analyze with LLM, store relevant ones
        self._llm_exhausted = False
        async with AsyncWebCrawler() as crawler:
            for i, url in enumerate(new_urls):
                if self._llm_exhausted:
                    log.warning(f"LLM daily limit exhausted — skipping remaining {len(new_urls) - i} articles.")
                    break
                try:
                    log.info(f"[{i+1}/{len(new_urls)}] {url}")
                    article = await self._process_article(crawler, url)
                    if article:
                        stats["relevant"] += 1
                        if self._store_article(article):
                            stats["stored"] += 1
                        else:
                            stats["storage_failures"] += 1
                except Exception as e:
                    stats["processing_failures"] += 1
                    log.warning(f"  Error processing {url}: {e}")

        if stats["storage_failures"]:
            raise RuntimeError(
                f"Failed to store {stats['storage_failures']} relevant news article(s)"
            )
        if stats["processing_failures"]:
            raise RuntimeError(
                f"News scraping had {stats['processing_failures']} article processing failure(s)"
            )
        if self._llm_exhausted:
            raise RuntimeError("News scraping stopped because the LLM daily limit was exhausted")

        log.info(
            f"=== SCRAPE COMPLETE === "
            f"discovered={stats['discovered']} new={stats['new']} "
            f"relevant={stats['relevant']} stored={stats['stored']} "
            f"discovery_pages={stats['discovery_successes']}/{stats['discovery_attempts']}"
        )
        return stats

    # ------------------------------------------------------------------
    # URL Discovery (dual strategy)
    # ------------------------------------------------------------------
    async def _discover_article_urls(self) -> List[str]:
        """
        Two-pronged discovery:
        1. Crawl ABS-CBN business and local news sections
        2. Search Google News for targeted Philippine food-market stories from trusted publishers
        """
        urls = set()

        try:
            from crawl4ai import AsyncWebCrawler, CacheMode, CrawlerRunConfig

            async with AsyncWebCrawler() as crawler:
                config = CrawlerRunConfig(
                    cache_mode=CacheMode.BYPASS, page_timeout=30_000)

                # Strategy 1: ABS-CBN section pages
                for section_url in ABSCBN_SECTIONS:
                    self._run_stats["discovery_attempts"] += 1
                    try:
                        result = await self._crawl_with_retry(crawler, section_url, config)
                        if result and result.success:
                            self._run_stats["discovery_successes"] += 1
                            for link_info in result.links.get("internal", []):
                                href = link_info.get("href", "") if isinstance(link_info, dict) else str(link_info)
                                article_url = urljoin(section_url, href)
                                if self._is_article_url(article_url):
                                    urls.add(article_url)
                        else:
                            self._run_stats["discovery_failures"] += 1
                            log.warning(f"Section scan returned no page: {section_url}")
                    except Exception as e:
                        self._run_stats["discovery_failures"] += 1
                        log.warning(f"Section scan failed {section_url}: {e}")

                # Strategy 2: targeted Google News searches across trusted publishers
                for query in GOOGLE_SEARCH_QUERIES:
                    search_url = (
                        f"https://news.google.com/search?"
                        f"q={quote_plus(query + ' when:30d')}&hl=en-PH&gl=PH"
                    )
                    self._run_stats["discovery_attempts"] += 1
                    try:
                        result = await self._crawl_with_retry(crawler, search_url, config)
                        if result and result.success:
                            self._run_stats["discovery_successes"] += 1
                            # Google News uses ./read/ links that redirect to actual articles
                            for link_info in result.links.get("internal", []):
                                href = link_info.get("href", "") if isinstance(link_info, dict) else str(link_info)
                                candidate_url = urljoin(search_url, href)
                                candidate = urlparse(candidate_url)
                                if (
                                    candidate.hostname == "news.google.com"
                                    and (candidate.path.startswith("/read/") or candidate.path.startswith("/articles/"))
                                ):
                                    urls.add(candidate_url)
                        else:
                            self._run_stats["discovery_failures"] += 1
                            log.warning("Google News search returned no page")
                    except Exception as e:
                        self._run_stats["discovery_failures"] += 1
                        log.warning(f"Google News search failed: {e}")

        except ImportError:
            raise RuntimeError("crawl4ai is not installed")

        return list(urls)

    @staticmethod
    async def _crawl_with_retry(crawler, url: str, config):
        """Retry transient browser/network failures once before reporting failure."""
        last_error = "crawler returned no successful result"
        for attempt in range(2):
            try:
                result = await crawler.arun(url=url, config=config)
                if result and result.success:
                    return result
                last_error = getattr(result, "error_message", None) or last_error
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            if attempt == 0:
                await asyncio.sleep(1)
        raise RuntimeError(f"Could not crawl {url} after retry: {last_error}")

    @staticmethod
    def _is_supported_publisher(host: str) -> bool:
        host = (host or "").lower().rstrip(".").removeprefix("www.")
        return any(host == domain or host.endswith("." + domain) for domain in SUPPORTED_NEWS_DOMAINS)

    def _is_article_url(self, url: str) -> bool:
        """Check if a URL is a potentially food/price-relevant ABS-CBN article."""
        if not url:
            return False
        host = (urlparse(url).hostname or "").lower().removeprefix("www.")
        if host != "abs-cbn.com":
            return False
        if not re.search(r'/\d{4}/\d{1,2}/\d{1,2}/', url):
            return False
        # Skip sections that are NEVER food-price relevant
        skip_sections = [
            "/entertainment/", "/lifestyle/", "/sports/",
            "/lotto", "/horoscope", "/sudoku", "/weather-traffic",
            "/word-of-the-day", "/push/", "/halalan/",
        ]
        if any(s in url for s in skip_sections):
            return False
        # Avoid crawling every article from broad business/nation/region feeds.
        # Google News discovery still provides a second route for relevant stories
        # whose URL slug is vague.
        slug = urlparse(url).path.rsplit("/", 1)[-1].replace("-", " ").replace("_", " ")
        return self._pre_filter_content("", slug)

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------
    def _filter_existing_urls(self, urls: List[str]) -> List[str]:
        """Filter out URLs already stored in the database."""
        new_urls = []
        for url in urls:
            resp = (
                self._client.table(self._table)
                .select("id")
                .eq("url", url)
                .limit(1)
                .execute()
            )
            if not resp.data:
                new_urls.append(url)
        return new_urls

    def _check_content_hash(self, content_hash: str) -> bool:
        """Check if content hash already exists."""
        resp = (
            self._client.table(self._table)
            .select("id")
            .eq("content_hash", content_hash)
            .limit(1)
            .execute()
        )
        return len(resp.data) > 0

    # ------------------------------------------------------------------
    # Article Processing
    # ------------------------------------------------------------------
    async def _process_article(self, crawler, url: str) -> Optional[Dict[str, Any]]:
        """Crawl a single article and run strict LLM analysis."""
        from crawl4ai import CacheMode, CrawlerRunConfig

        config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS, page_timeout=30_000)
        result = await self._crawl_with_retry(crawler, url, config)

        if not result.markdown:
            raise RuntimeError(f"Article crawl returned no markdown: {url}")

        # Google News discovery links must resolve to a trusted publisher.
        resolved_url = result.url or url
        resolved_host = (urlparse(resolved_url).hostname or "").lower().removeprefix("www.")
        if not self._is_supported_publisher(resolved_host):
            log.info(f"  ✗ SKIP (untrusted publisher {resolved_host or 'unknown'}): {url}")
            return None

        # Clean content — extract article body
        content = self._clean_content(result.markdown)
        if len(content) < 200:
            log.info(f"  ✗ SKIP (content too short: {len(content)} chars): {url[-60:]}")
            return None

        # Content hash dedup
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if self._check_content_hash(content_hash):
            log.info(f"  ✗ SKIP (duplicate content hash): {url[-60:]}")
            return None

        # Extract title and image
        title = ""
        publication = publication_metadata(result.metadata, result.html, result.url or url)

        image_url = ""
        if result.metadata:
            title = result.metadata.get("title", "") or ""
            
        # 1. Highest priority: editorImage (raw high-res embedded image)
        if result.html:
            # Allow spaces in the regex because ABS-CBN sometimes has spaces in the filename
            editor_match = re.search(r'(https://[^"\'>]*?editorImage[^"\'>]+)', result.html)
            if editor_match:
                # Strip any query parameters or extra json escaping
                raw_url = editor_match.group(1).split('?')[0].split('&')[0].replace('\\', '')
                image_url = raw_url.replace(' ', '%20')
                
        # 2. Fallback: og:image or twitter:image
        if not image_url and result.metadata:
            image_url = result.metadata.get("og:image") or ""
            
        if not image_url and result.html:
            og_match = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', result.html)
            if not og_match:
                og_match = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', result.html)
            if og_match:
                image_url = og_match.group(1).replace("&amp;", "&")
            else:
                tw_match = re.search(r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']', result.html)
                if not tw_match:
                    tw_match = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']', result.html)
                if tw_match:
                    image_url = tw_match.group(1).replace("&amp;", "&")
                    
        # Clean query parameters from og:image to prevent blurry/compressed thumbnails
        if image_url and "od2-image-api" in image_url:
            image_url = image_url.split('?')[0]
                    
        # Fallback to YouTube iframe thumbnail if no image is found
        if not image_url and result.html:
            yt_match = re.search(r'youtube\.com/embed/([a-zA-Z0-9_-]+)', result.html)
            if yt_match:
                yt_img = f"https://img.youtube.com/vi/{yt_match.group(1)}/maxresdefault.jpg"
                image_url = self._verify_youtube_thumbnail(yt_img)
                
        # Fallback to video URL (if it's og:video)
        if not image_url and result.html:
            vid_match = re.search(r'<meta[^>]+property=["\']og:video["\'][^>]+content=["\']([^"\']+)["\']', result.html)
            if vid_match:
                image_url = vid_match.group(1).replace("&amp;", "&")
            
        title = re.sub(r'\s*\|\s*ABS-CBN.*$', '', title).strip()

        source = resolved_host

        # ── Pre-Filter (Keyword Check) ──
        if not self._pre_filter_content(title, content):
            log.info(f"  ✗ SKIP (no food-market topic and impact): {title[:60]}")
            return None

        # ── LLM Analysis (strict filter) ──
        llm_result = await self._analyze_with_llm(title, content)

        if not llm_result:
            log.warning(f"  ✗ SKIP (LLM call failed): {title[:60]}")
            return None

        if not self._has_supported_market_evidence(llm_result, title, content):
            log.info(f"  ✗ SKIP (no supported food-market evidence): {title[:60]}")
            return None

        log.info(
            f"  ✓ RELEVANT: {title[:60]}... "
            f"sentiment={llm_result.get('sentiment_score', 0):.2f} "
            f"type={llm_result.get('event_type')} "
            f"products={llm_result.get('affected_products', [])} "
            f"evidence={llm_result.get('impact_evidence', '')[:120]!r}"
        )

        return {
            "title": title[:500],
            "title_tl": llm_result.get("title_tl", "")[:500],
            "content": llm_result.get("summary", content[:5000]),
            "content_tl": llm_result.get("summary_tl", ""),
            "source": source,
            "url": resolved_url,
            "content_hash": content_hash,
            **publication,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "sentiment_score": llm_result.get("sentiment_score", 0.0),
            "keywords": llm_result.get("keywords", []),
            "affected_products": llm_result.get("affected_products", []),
            "event_type": llm_result.get("event_type", "general"),
            "image_url": image_url,
            "time_validity_days": llm_result.get("time_validity_days", 7),
            "probability": llm_result.get("probability", 1.0),
            "effect_magnitude": llm_result.get("effect_magnitude", "medium"),
        }

    # ------------------------------------------------------------------
    # Content Cleaning
    # ------------------------------------------------------------------
    def _clean_content(self, markdown: str) -> str:
        """Extract clean article body from ABS-CBN page markdown."""
        if not markdown:
            return ""

        lines = markdown.split("\n")

        # ── Strategy 1: Find body between "Published" date and "Read More:" ──
        body_start = None
        body_end = len(lines)

        for i, line in enumerate(lines):
            stripped = line.strip()
            # ABS-CBN pattern: "Published April 27, 2026 02:55 PM PHT"
            if body_start is None and re.match(
                r'Published\s+\w+\s+\d{1,2},?\s+\d{4}', stripped
            ):
                body_start = i + 1
                continue
            # End markers
            if body_start is not None:
                if stripped.startswith("Read More") or stripped == "Read More:":
                    body_end = i
                    break
                if any(m in stripped for m in [
                    "Privacy Preference Center", "NPC Seal of Registration",
                    "ABS-CBN is the leading media", "\u00a9 2026 ABS-CBN",
                    "\u00a9 2025 ABS-CBN",
                ]):
                    body_end = i
                    break

        if body_start is not None:
            article_lines = lines[body_start:body_end]
        else:
            # ── Fallback: filter out headline tickers and nav noise ──
            article_lines = []
            for line in lines:
                stripped = line.strip()
                # Skip headline ticker (concatenated headlines, no spaces)
                if len(stripped) > 150 and len(re.findall(r'[a-z][A-Z]', stripped)) >= 3:
                    continue
                # Skip nav items
                if stripped in [
                    "News", "Entertainment", "Lifestyle", "Sports",
                    "Metro.Style", "More", "ADVERTISEMENT", "Business",
                ]:
                    continue
                # Stop at footer
                if any(m in stripped for m in [
                    "Privacy Preference Center", "Cookie List",
                    "NPC Seal of Registration", "ABS-CBN is the leading media",
                    "Allow All", "Reject All",
                ]):
                    break
                if stripped.startswith("!") and "(" in stripped:
                    continue
                article_lines.append(line)

        content = "\n".join(article_lines)

        # Remove markdown artifacts
        content = re.sub(r'\[([^\]]*)\]\([^\)]*\)', r'\1', content)
        content = re.sub(r'!\[.*?\]\(.*?\)', '', content)
        content = re.sub(r'#{1,6}\s*', '', content)
        content = re.sub(r'\n{3,}', '\n\n', content)
        content = re.sub(r'[*_~`]{1,3}', '', content)
        content = re.sub(r'Featured:.*?\n', '', content)

        return content.strip()

    def _pre_filter_content(self, title: str, content: str) -> bool:
        """Require both a food/agri-fishery topic and a market-impact signal."""
        text = (title + " " + content).casefold()

        def contains_any(terms: tuple[str, ...]) -> bool:
            return any(
                re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text)
                for term in terms
            )

        return contains_any(AGRI_FOOD_TOPIC_TERMS) and contains_any(MARKET_IMPACT_TERMS)

    def _has_supported_market_evidence(
        self,
        result: Dict[str, Any],
        title: str,
        content: str,
    ) -> bool:
        """Require a verifiable article quote tied to a named supported product."""
        if not isinstance(result, dict) or result.get("relevant") is not True:
            return False

        event_type = result.get("event_type")
        if not isinstance(event_type, str) or event_type.strip().casefold() not in SUPPORTED_EVENT_TYPES:
            return False

        products = result.get("affected_products")
        if not isinstance(products, list):
            return False

        evidence = result.get("impact_evidence")
        if not isinstance(evidence, str):
            return False
        evidence = re.sub(r"\s+", " ", evidence).strip().strip("\"'")
        if len(evidence) < 12:
            return False

        def normalize_text(value: str) -> str:
            return re.sub(r"\s+", " ", value).strip().casefold()

        article_text = normalize_text(f"{title} {content}")
        normalized_evidence = normalize_text(evidence)
        if normalized_evidence not in article_text:
            return False
        if not any(
            re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", normalized_evidence)
            for term in EVIDENCE_IMPACT_TERMS
        ):
            return False
        if event_type.strip().casefold() == "fuel_energy" and not any(
            re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", normalized_evidence)
            for term in ("fuel", "diesel", "gasoline", "petrol", "kerosene", "lpg")
        ):
            return False

        canonical_products = {name.casefold(): name for name in SUPPORTED_PRODUCTS}
        matched = []
        for product in products:
            if isinstance(product, str):
                canonical = canonical_products.get(product.strip().casefold())
                product_terms = PRODUCT_EVIDENCE_TERMS.get(canonical, ()) if canonical else ()
                if (
                    canonical
                    and canonical not in matched
                    and any(
                        re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", normalized_evidence)
                        for term in product_terms
                    )
                ):
                    matched.append(canonical)
        if not matched:
            return False

        raw_keywords = result.get("keywords")
        keywords = []
        seen_keywords = set()
        if isinstance(raw_keywords, list):
            for keyword in raw_keywords:
                if not isinstance(keyword, str):
                    continue
                keyword = re.sub(r"\s+", " ", keyword).strip()
                if not keyword or re.search(r"\b(?:lpg|liquefied petroleum gas)\b", keyword, re.IGNORECASE):
                    continue
                normalized_keyword = keyword.casefold()
                if normalized_keyword in seen_keywords:
                    continue
                seen_keywords.add(normalized_keyword)
                keywords.append(keyword)
                if len(keywords) == 3:
                    break

        result["affected_products"] = matched
        result["event_type"] = event_type.strip().casefold()
        result["impact_evidence"] = evidence
        result["keywords"] = keywords
        return True

    # ------------------------------------------------------------------
    # LLM Analysis
    # ------------------------------------------------------------------
    async def _analyze_with_llm(self, title: str, content: str) -> Optional[Dict]:
        """Send article to LLM for strict relevance check and extraction."""
        import httpx

        # Rate limit: Groq free tier = 30 req/min
        await asyncio.sleep(2)

        truncated = content[:2500]
        user_prompt = f"TITLE: {title}\n\nARTICLE:\n{truncated}"
        system_prompt = LLM_SYSTEM_PROMPT.replace(
            "{SUPPORTED_PRODUCTS}", ", ".join(SUPPORTED_PRODUCTS)
        )

        # Choose provider
        if self._groq_key:
            api_url = "https://api.groq.com/openai/v1/chat/completions"
            api_key = self._groq_key
            model = "openai/gpt-oss-120b"
        else:
            api_url = "https://api.openai.com/v1/chat/completions"
            api_key = self._openai_key
            model = "gpt-4o-mini"

        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(
                        api_url,
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": model,
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt},
                            ],
                            "temperature": 0.0,
                            "max_tokens": 800,
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()

                    raw = data["choices"][0]["message"]["content"].strip()

                    # Clean potential markdown fences
                    if raw.startswith("```"):
                        raw = re.sub(r'^```(?:json)?\s*', '', raw)
                        raw = re.sub(r'\s*```$', '', raw)

                    return json.loads(raw)

            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if status == 429:
                    if "tokens per day" in e.response.text or "TPD" in e.response.text:
                        log.warning(f"  LLM daily token limit exhausted. Stopping.")
                        self._llm_exhausted = True
                        return None
                    if attempt < 2:
                        log.warning(f"  LLM rate limited (429), retrying in 10s...")
                        await asyncio.sleep(10)
                        continue
                if (status >= 500 or status == 408) and attempt < 2:
                    log.warning(f"  LLM service error ({status}), retrying...")
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                log.warning(f"  LLM API error ({status}): {e.response.text[:200]}")
                raise RuntimeError(f"News LLM request failed with HTTP {status}") from e
            except json.JSONDecodeError as e:
                log.warning(f"  LLM returned invalid JSON: {e}")
                if attempt < 2:
                    await asyncio.sleep(1)
                    continue
                raise RuntimeError("News LLM returned invalid JSON after retries") from e
            except Exception as e:
                if attempt < 2:
                    log.warning(f"  LLM request failed ({type(e).__name__}), retrying: {e}")
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                raise RuntimeError(
                    f"News LLM analysis failed after retries: {type(e).__name__}: {e}"
                ) from e

        return None

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------
    def _store_article(self, article: Dict[str, Any]) -> bool:
        """Store a processed article in Supabase."""
        try:
            resp = self._client.table(self._table).insert({
                "title": article["title"],
                "title_tl": article.get("title_tl", ""),
                "content": article["content"],
                "content_tl": article.get("content_tl", ""),
                "source": article["source"],
                "url": article["url"],
                "content_hash": article["content_hash"],
                "published_at": article["published_at"],
                "published_date": article["published_date"],
                "publication_precision": article["publication_precision"],
                "publication_source": article["publication_source"],
                "created_at": article["created_at"],
                "sentiment_score": article["sentiment_score"],
                "keywords": article["keywords"],
                "affected_products": article["affected_products"],
                "event_type": article["event_type"],
                "image_url": article.get("image_url", ""),
                "time_validity_days": article.get("time_validity_days", 7),
                "probability": article.get("probability", 1.0),
                "effect_magnitude": article.get("effect_magnitude", "medium"),
            }).execute()
            
            if not resp.data:
                log.warning("No data returned from article insert.")
                return False
            
            log.info(f"  ✓ Article and image URL saved to Supabase.")
            return True
        except Exception as e:
            log.warning(f"Failed to store news article {article.get('url', '')}: {e}")
            return False

    def _verify_youtube_thumbnail(self, image_url: str) -> str:
        """Checks if maxresdefault exists and is valid, otherwise returns hqdefault."""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            # We do a GET to check size, since maxresdefault sometimes returns a tiny 120x90 200 OK image
            resp = httpx.get(image_url, headers=headers, timeout=5.0)
            if resp.status_code == 404 or len(resp.content) < 2000:
                return image_url.replace("maxresdefault.jpg", "hqdefault.jpg")
            return image_url
        except Exception:
            return image_url.replace("maxresdefault.jpg", "hqdefault.jpg")



if __name__ == '__main__':
    import asyncio
    scraper = NewsScraper()
    stats = asyncio.run(scraper.run_daily_scrape())
    log.info("NEWS SCRAPE RESULT %s", json.dumps(stats, sort_keys=True))
