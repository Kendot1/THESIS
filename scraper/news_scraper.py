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
import xml.etree.ElementTree as ET
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
# Database dependencies are loaded only for an explicitly non-dry run.


# Force UTF-8 encoding for Windows console (prevents UnicodeEncodeError when printing emojis)
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Do not read local credential files on import or during dry-run execution.
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

RSS_FEEDS = ()  # Legacy RSS collector retained for replay tests only.

SUPPORTED_NEWS_DOMAINS = ("abs-cbn.com",)

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
    "Red Onion": ("red onion", "red onions", "pulang sibuyas"),
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
    "White Onion": ("white onion", "white onions", "puting sibuyas"),
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
# Ingestion and backfill use news_context.CONTEXT_PROMPT.


class NewsScraper:
    """
    Scrapes relevant news via local feeds + targeted Google News discovery,
    uses LLM for strict relevance filtering and structured extraction,
    deduplicates, and stores to Supabase.
    """

    def __init__(self, *, dry_run=False, max_articles=20, provider=None,
                 start_date=None, end_date=None):
        from datetime import date
        if bool(start_date) != bool(end_date):
            raise ValueError('start_date and end_date must be supplied together')
        self.start_date = date.fromisoformat(start_date) if start_date else None
        self.end_date = date.fromisoformat(end_date) if end_date else None
        if self.start_date and self.start_date > self.end_date:
            raise ValueError('start_date must not exceed end_date')
        if self.start_date and not dry_run:
            raise ValueError('Backfill is local dry-run only')
        self.exclusions = []
        if not 1 <= max_articles <= 100:
            raise ValueError("max_articles must be between 1 and 100")
        self.dry_run = dry_run
        self.provider = provider or "june"
        if self.provider not in {"june", "rss"}:
            raise ValueError("provider must be june or rss")
        if not dry_run and self.provider != "june":
            raise ValueError("RSS is a dry-run fallback only")
        self.max_articles = max_articles
        self.articles = []
        self.provenance = []
        self._client = None
        if not dry_run:
            expected = "https://zhwhnnxbodzrklhgsurn.supabase.co"
            if os.environ.get("SUPABASE_URL", "").rstrip("/") != expected:
                raise ValueError("News writes restricted to exact TEST project zhwhnnxbodzrklhgsurn")
            from supabase import create_client
            self._client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
        self._table = "news_articles"
        self._groq_key = ""
        self._openai_key = ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def _publication_exclusion(self, publication):
        """Range uses publisher timing in Manila, never URL or crawl date."""
        if not self.start_date:
            return None
        from datetime import date, timedelta
        if publication.get('publication_source', 'unknown') in {'unknown', 'url_date'}:
            return 'unknown_publication'
        try:
            if publication.get('published_at'):
                stamp = datetime.fromisoformat(publication['published_at'].replace('Z', '+00:00'))
                if stamp.tzinfo is None:
                    return 'unknown_publication_timezone'
                day = stamp.astimezone(timezone(timedelta(hours=8))).date()
            else:
                day = date.fromisoformat(publication['published_date'])
        except (ValueError, TypeError, KeyError):
            return 'invalid_publication'
        return None if self.start_date <= day <= self.end_date else 'publication_outside_range'

    def _candidate_in_range(self, url):
        from datetime import date
        match = re.search(r'/(\d{4})/(\d{1,2})/(\d{1,2})/', url)
        if not match or not self.start_date:
            return True
        try:
            day = date(*map(int, match.groups()))
        except ValueError:
            return False
        return self.start_date <= day <= self.end_date

    def _backfill_search_queries(self):
        from datetime import timedelta
        queries = []
        start = self.start_date
        while start <= self.end_date:
            end = min(start + timedelta(days=6), self.end_date)
            for terms in ('rice palay bigas prices supply', 'vegetable onion fish pork chicken agriculture prices supply'):
                queries.append(f'site:abs-cbn.com {terms} after:{start - timedelta(days=1)} before:{end + timedelta(days=1)}')
            start = end + timedelta(days=1)
        return queries

    async def run_daily_scrape(self) -> Dict[str, int]:
        """Execute the full daily scraping pipeline."""
        if self.provider == "rss":
            raise RuntimeError("RSS fallback archived only; new acquisitions must be ABS-CBN June crawler")
        self._groq_key = "" if self.dry_run else os.environ.get("GROQ_API_KEY_NEWS_SCRAPER", "")
        self._openai_key = "" if self.dry_run else os.environ.get("OPENAI_API_KEY", "")
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

        if not self.dry_run and not self._groq_key and not self._openai_key:
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
            raise RuntimeError("No ABS-CBN article URLs discovered; source access/discovery failed")

        # Step 2: Filter already-processed URLs
        new_urls = article_urls if self.dry_run else self._filter_existing_urls(article_urls)
        stats["new"] = len(new_urls)
        log.info(f"{len(new_urls)} new URLs to process.")

        if not new_urls:
            log.info("All articles already processed.")
            return stats

        # Step 3: Crawl, analyze with LLM, store relevant ones
        self._llm_exhausted = False
        async with AsyncWebCrawler() as crawler:
            for i, url in enumerate(new_urls[:self.max_articles]):
                if self._llm_exhausted:
                    log.warning(f"LLM daily limit exhausted — skipping remaining {len(new_urls) - i} articles.")
                    break
                try:
                    log.info(f"[{i+1}/{len(new_urls)}] {url}")
                    article = await self._process_article(crawler, url)
                    if article:
                        stats["relevant"] += 1
                        self.articles.append(article)
                        if self.dry_run:
                            continue
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
                                text = link_info.get("text", "") if isinstance(link_info, dict) else ""
                                article_url = urljoin(section_url, href)
                                if self._is_article_url(article_url, text):
                                    urls.add(article_url)
                        else:
                            self._run_stats["discovery_failures"] += 1
                            log.warning(f"Section scan returned no page: {section_url}")
                    except Exception as e:
                        self._run_stats["discovery_failures"] += 1
                        log.warning(f"Section scan failed {section_url}: {e}")

                # Strategy 2: targeted Google News searches across trusted publishers
                for query in ["site:abs-cbn.com " + q for q in GOOGLE_SEARCH_QUERIES]:
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

        return sorted(urls, key=lambda u: ("news.google.com" in u, u), reverse=False)

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
    def _has_philippine_scope(title: str, content: str) -> bool:
        return bool(re.search(r'\b(philippines?|filipinos?|manila|phl|nfa|palay|department of agriculture)\b',
                              title + ' ' + content, re.I))

    def _deterministic_evidence(self, title: str, content: str) -> Optional[Dict]:
        """Classify only verbatim commodity/market evidence in one sentence."""
        for quote in [title, *re.split(r'(?<=[.!?])\s+|\n+', content)]:
            if not self._pre_filter_content("", quote):
                continue
            text = quote.casefold()
            products = [product for product, aliases in PRODUCT_EVIDENCE_TERMS.items()
                        if any(re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', text)
                               for term in aliases)]
            result = {"relevant": True, "event_type": "price_movement",
                      "affected_products": products, "impact_evidence": quote,
                      "keywords": []}
            if re.search(r'\b(imports?|exports?|tariffs?|quota)\b', text):
                result['event_type'] = 'import_export'
            elif not re.search(r'\b(prices?|costs?|presyo)\b', text):
                result['event_type'] = 'supply_shock'
            if self._has_supported_market_evidence(result, title, content):
                return result
        return None

    async def _run_rss_dry_run(self) -> Dict[str, int]:
        """Bounded credential-free collection; never creates or uses a DB client.

        Content is a source excerpt, NOT a generated summary. Unknown analytical
        fields remain null; provenance is separate from insertion candidates.
        """
        from bs4 import BeautifulSoup
        self.articles, self.provenance = [], []
        stats = {"discovered": 0, "relevant": 0, "collected": 0, "stored": 0,
                 "discovery_attempts": 0, "discovery_successes": 0,
                 "discovery_failures": 0, "processing_failures": 0}
        seen = set()
        async with httpx.AsyncClient(timeout=20, follow_redirects=True,
                                     headers={"User-Agent": "FOODCAST-news-audit/1.0"}) as client:
            for feed in RSS_FEEDS:
                if len(self.articles) >= self.max_articles:
                    break
                stats['discovery_attempts'] += 1
                try:
                    response = await client.get(feed)
                    response.raise_for_status()
                    items = self.feed_items(response.text)
                    stats['discovery_successes'] += 1
                except (httpx.HTTPError, ET.ParseError) as exc:
                    stats['discovery_failures'] += 1
                    log.warning('Feed unavailable: %s (%s)', feed, type(exc).__name__)
                    continue
                for item in items[:60]:
                    if len(self.articles) >= self.max_articles:
                        break
                    if item['url'] in seen:
                        continue
                    seen.add(item['url'])
                    stats['discovered'] += 1
                    try:
                        response = await client.get(item['url'])
                        response.raise_for_status()
                        url = str(response.url)
                        host = urlparse(url).hostname or ''
                        if not self._is_supported_publisher(host):
                            continue
                        soup = BeautifulSoup(response.text, 'html.parser')
                        body = soup.select_one('.entry-content, .td-post-content, .article__content, .article-content, .article-body, [itemprop="articleBody"], article')
                        paragraphs = []
                        if body:
                            for node in body.select('script,style,nav,aside,footer,.related-posts'):
                                node.decompose()
                            paragraphs = [p.get_text(' ', strip=True) for p in body.select('p')]
                        content = '\n'.join(p for p in paragraphs if p)
                        # Some feeds provide the complete article; descriptions
                        # remain valid source excerpts even behind publisher walls.
                        if not content:
                            content = item['description']
                        evidence = self._deterministic_evidence(item['title'], content)
                        if not evidence or not content or not self._has_philippine_scope(item['title'], content):
                            continue
                        publication = publication_metadata(None, response.text, url)
                        if publication['publication_precision'] == 'unknown' or publication['publication_source'] == 'url_date':
                            publication = item['publication']
                        row = {"title": item['title'][:500], "content": content,
                               "source": host.removeprefix('www.'), "url": url,
                               "content_hash": hashlib.sha256(content.encode('utf-8')).hexdigest(),
                               **publication, "created_at": datetime.now(timezone.utc).isoformat(),
                               "sentiment_score": None, "keywords": evidence['keywords'],
                               "affected_products": evidence['affected_products'],
                               "event_type": evidence['event_type'], "image_url": None,
                               "title_tl": None, "content_tl": None,
                               "time_validity_days": None, "probability": None, "effect_magnitude": None}
                        image = soup.select_one('meta[property="og:image"]')
                        if image:
                            row['image_url'] = image.get('content') or None
                        self.articles.append(row)
                        self.provenance.append({"url": url, "feed_url": feed,
                            "feed_title": item['title'], "feed_published_raw": item['publication_raw'],
                            "feed_publication": item['publication'],
                            "content_origin": 'article_paragraphs' if paragraphs else 'rss_description',
                            "impact_evidence": evidence['impact_evidence'],
                            "analysis_method": 'deterministic_verbatim_evidence',
                            "article_http_status": response.status_code})
                    except (httpx.HTTPError, ValueError) as exc:
                        stats['processing_failures'] += 1
                        log.warning('Article unavailable: %s (%s)', item['url'], type(exc).__name__)
        stats['relevant'] = stats['collected'] = len(self.articles)
        if not self.articles:
            raise RuntimeError('No evidenced food-market articles collected; no database writes attempted')
        return stats

    def feed_items(self, xml_text: str) -> List[Dict[str, Any]]:
        """Read only RSS/Atom entries, never channel navigation or Google wrappers."""
        from bs4 import BeautifulSoup
        from urllib.parse import parse_qsl, urlencode, urlunsplit

        root = ET.fromstring(xml_text)
        items, seen = [], set()
        for entry in root.iter():
            if entry.tag.rsplit("}", 1)[-1] not in {"item", "entry"}:
                continue
            fields = {}
            for child in entry:
                name = child.tag.rsplit("}", 1)[-1]
                value = child.text or ""
                if name == "link":
                    value = child.get("href") or value
                fields.setdefault(name, value)
            url = fields.get("link", "").strip()
            parts = urlparse(url)
            if parts.scheme not in {"https", "http"} or not self._is_supported_publisher(parts.hostname):
                continue
            query = urlencode([(k, v) for k, v in parse_qsl(parts.query)
                               if not k.startswith("utm_") and k not in {"fbclid", "gclid"}])
            url = urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))
            title = BeautifulSoup(fields.get("title", ""), "html.parser").get_text(" ", strip=True)
            description = BeautifulSoup(fields.get("description", fields.get("summary", "")), "html.parser").get_text(" ", strip=True)
            if url in seen or not self._pre_filter_content(title, description):
                continue
            seen.add(url)
            raw = fields.get("pubDate", fields.get("published", ""))
            items.append({"url": url, "title": title, "description": description,
                          "publication_raw": raw,
                          "publication": publication_metadata({"published_at": raw}, None, url)})
        return items

    @staticmethod
    def _publisher_feed_urls(xml_text: str) -> set[str]:
        """Extract direct supported-publisher article links from RSS/Atom."""
        urls: set[str] = set()
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return urls
        for element in root.iter():
            if element.tag.rsplit("}", 1)[-1] not in {"link", "guid"}:
                continue
            value = (element.get("href") or element.text or "").strip()
            if not value or not value.startswith(("http://", "https://")):
                continue
            host = (urlparse(value).hostname or "").lower().removeprefix("www.")
            if host and NewsScraper._is_supported_publisher(host):
                urls.add(value.split("#", 1)[0])
        return urls


    @staticmethod
    def _is_supported_publisher(host: str) -> bool:
        host = (host or "").lower().rstrip(".").removeprefix("www.")
        return host == "abs-cbn.com" or host.endswith(".abs-cbn.com")

    def _is_article_url(self, url: str, link_text: str = "") -> bool:
        """Check if a URL is a potentially food/price-relevant ABS-CBN article."""
        if not url:
            return False
        host = (urlparse(url).hostname or "").lower().removeprefix("www.")
        if urlparse(url).scheme not in {"https", "http"} or not self._is_supported_publisher(host):
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
        slug = urlparse(url).path.rsplit("/", 1)[-1].replace("-", " ").replace("_", " ")
        text = (link_text + " " + slug).casefold()
        def contains_any(terms: tuple[str, ...]) -> bool:
            return any(
                re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text)
                for term in terms
            )
        return contains_any(AGRI_FOOD_TOPIC_TERMS) or contains_any(MARKET_IMPACT_TERMS)

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
        if urlparse(resolved_url).scheme not in {"http", "https"} or not self._is_supported_publisher(resolved_host):
            log.info(f"  ✗ SKIP (untrusted publisher {resolved_host or 'unknown'}): {url}")
            return None

        # Clean content — extract article body
        content = self._clean_content(result.markdown)
        if len(content) < 200:
            raise RuntimeError(f"Article body too short ({len(content)} chars): {url}")

        # Content hash dedup
        source_content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        content_hash = source_content_hash
        if (not self.dry_run and self._check_content_hash(source_content_hash)) or any(
            a["content_hash"] == source_content_hash or a["url"] == resolved_url for a in self.articles
        ):
            log.info(f"  ✗ SKIP (duplicate content hash): {url[-60:]}")
            return None

        # Extract title and image
        title = ""
        publication = publication_metadata(result.metadata, result.html, result.url or url)
        if self.start_date and publication['publication_source'] in {'unknown', 'url_date'}:
            # Visible Published text is publisher evidence; URL dates are not.
            visible = re.search(r'Published\s+([A-Za-z]+\s+\d{1,2},?\s+\d{4})(?:\s+(\d{1,2}:\d{2}\s*[AP]M)\s+PHT)?', result.markdown)
            if visible:
                try:
                    from datetime import timedelta
                    stamp = datetime.strptime(visible.group(1).replace(',', ''), '%B %d %Y')
                    if visible.group(2):
                        clock = datetime.strptime(visible.group(2), '%I:%M %p')
                        stamp = stamp.replace(hour=clock.hour, minute=clock.minute, tzinfo=timezone(timedelta(hours=8)))
                    publication = {'published_at': stamp.isoformat() if visible.group(2) else None,
                        'published_date': stamp.date().isoformat(),
                        'publication_precision': 'timestamp' if visible.group(2) else 'date',
                        'publication_source': 'publisher_visible_published'}
                except ValueError:
                    pass
        reason = self._publication_exclusion(publication)
        if reason:
            self.exclusions.append({'url': resolved_url, 'reason': reason, 'publication': publication})
            return None

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

        # Dry runs exercise June extraction without invoking credentials or LLMs.
        if self.dry_run:
            evidence = self._deterministic_evidence(title, content)
            if not evidence or not self._has_philippine_scope(title, content):
                return None
            self.provenance.append({"url": resolved_url, "discovery_url": url,
                "content_origin": "june_crawler_cleaned_body",
                "impact_evidence": evidence["impact_evidence"],
                "analysis_method": "deterministic_verbatim_evidence"})
            return {"title": title[:500], "content": content,
                "source": source, "url": resolved_url, "content_hash": content_hash,
                **publication, "created_at": datetime.now(timezone.utc).isoformat(),
                "title_tl": None, "content_tl": None, "sentiment_score": None,
                "keywords": evidence["keywords"], "affected_products": evidence["affected_products"],
                "event_type": evidence["event_type"], "image_url": image_url,
                "time_validity_days": None, "probability": None, "effect_magnitude": None}

        # June Groq/OpenAI bilingual enrichment with stricter evidence safeguards.
        llm_result = await self._analyze_with_llm(title, content)

        if not llm_result:
            raise RuntimeError(f"LLM returned no analysis: {title[:60]}")

        from scraper.news_context import validate_context
        if llm_result.get('relevant') and validate_context(llm_result, title, content):
            raise RuntimeError('LLM context failed strict validation')
        if not self._has_supported_market_evidence(llm_result, title, content):
            log.info(f"  ✗ SKIP (no supported food-market evidence): {title[:60]}")
            return None
        from scraper.news_context import validate_context
        context_errors = validate_context(llm_result, title, content)
        if context_errors:
            raise RuntimeError('LLM context failed validation: ' + ', '.join(context_errors))

        log.info(
            f"  ✓ RELEVANT: {title[:60]}... "
            f"sentiment={llm_result.get('sentiment_score', 0):.2f} "
            f"type={llm_result.get('event_type')} "
            f"products={llm_result.get('affected_products', [])} "
            f"evidence={llm_result.get('impact_evidence', '')[:120]!r}"
        )

        self.provenance.append({'url': resolved_url, 'source_content_sha256': source_content_hash,
            'analysis_provenance': self._context_provenance})
        return {
            "title": title[:500],
            "title_tl": llm_result.get("title_tl", "")[:500],
            "content": llm_result["summary"],
            "content_tl": llm_result["summary_tl"],
            "source": source,
            "url": resolved_url,
            "content_hash": source_content_hash,
            **publication,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "sentiment_score": llm_result.get("sentiment_score"),
            "keywords": llm_result.get("keywords", []),
            "affected_products": llm_result.get("affected_products", []),
            "event_type": llm_result.get("event_type", "general"),
            "image_url": image_url,
            "time_validity_days": llm_result.get("time_validity_days"),
            "probability": llm_result.get("probability"),
            "effect_magnitude": llm_result.get("effect_magnitude"),
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
            stripped = re.sub(r'^[#*_\s]+|[*_\s]+$', '', line)
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
        content = re.sub(r'!\[.*?\]\(.*?\)', '', content)
        content = re.sub(r'\[([^\]]*)\]\([^\)]*\)', r'\1', content)
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
    async def _analyze_with_llm(self, title: str, content: str, *, contextualize=True) -> Optional[Dict]:
        """Shared full-body bilingual contract for ingestion and backfill."""
        from scraper.news_context import request_context
        result, provenance = await request_context(
            title, content, self._groq_key, self._openai_key, SUPPORTED_PRODUCTS)
        self._context_provenance = {**provenance,
            'impact_analysis': result.get('impact_analysis') if isinstance(result, dict) else None}
        if isinstance(result, dict):
            result['relevant'] = not bool(result.get('error')) and result.get('relevant', True) is True
        return result

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------
    def _store_article(self, article: Dict[str, Any]) -> bool:
        """Store only an ABS-CBN article, including at the final write boundary."""
        parsed_url = urlparse(str(article.get("url", "")))
        if parsed_url.scheme not in {"https", "http"} or not self._is_supported_publisher(parsed_url.hostname):
            log.warning("Rejected news storage: publisher is not ABS-CBN")
            return False
        if self.dry_run:
            return False
        try:
            from scraper.news_context import validate_impact_fields, IMPACT_FIELDS
            if validate_impact_fields(article):
                raise ValueError('Invalid or missing impact estimates in storage payload')
            if not self._filter_existing_urls([article['url']]) or self._check_content_hash(article['content_hash']):
                return True  # Existing exact URL/hash: no duplicate insert.
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
                "time_validity_days": article.get("time_validity_days"),
                "probability": article.get("probability"),
                "effect_magnitude": article.get("effect_magnitude"),
            }).execute()
            
            if not resp.data:
                log.warning("No data returned from article insert.")
                return False
            
            verified = (self._client.table(self._table).select('id,url,content_hash,' + ','.join(IMPACT_FIELDS))
                        .eq('url', article['url']).limit(1).execute())
            if (not verified.data or verified.data[0].get('content_hash') != article['content_hash']
                    or any(verified.data[0].get(field) != article[field] for field in IMPACT_FIELDS)):
                raise RuntimeError('News insert read-back mismatch')
            log.info("Article saved and exact URL/content hash/impact estimates read back.")
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



def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run', action='store_true', help='Collect locally; no database or LLM access')
    mode.add_argument('--write-db', action='store_true', help='Explicitly use configured database and LLM pipeline')
    parser.add_argument('--provider', choices=('june', 'rss'), default='june',
                        help='June ABS-CBN crawler (default); RSS dry-run fallback')
    parser.add_argument('--max-articles', type=int, default=20)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--start-date', help='Inclusive publication date YYYY-MM-DD; dry-run only')
    parser.add_argument('--end-date', help='Inclusive publication date YYYY-MM-DD in Manila')
    parser.add_argument('--batch-dir', type=Path)
    parser.add_argument('--discovery-file', type=Path, help='Saved search-tool discovery results; still crawls real June bodies')
    parser.add_argument('--max-candidates', type=int, default=200)
    parser.add_argument('--runtime-seconds', type=int, default=850)
    args = parser.parse_args(argv)
    if not 1 <= args.max_articles <= 100:
        parser.error('--max-articles must be between 1 and 100')
    try:
        scraper = NewsScraper(dry_run=args.dry_run, max_articles=args.max_articles, provider=args.provider,
                              start_date=args.start_date, end_date=args.end_date)
        if not 1 <= args.max_candidates <= 200 or not 1 <= args.runtime_seconds <= 900:
            raise ValueError('max-candidates must be 1..200 and runtime-seconds 1..900')
    except ValueError as exc:
        parser.error(str(exc))
    if args.start_date:
        from scraper.news_backfill import run_backfill
        directory = args.batch_dir or (args.output.parent if args.output else Path('audits/news_backfill'))
        result = asyncio.run(run_backfill(scraper, directory, args.max_candidates, args.runtime_seconds, args.discovery_file))
        if args.output and args.output != directory / 'final.json':
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print('NEWS BACKFILL RESULT ' + json.dumps({k:result[k] for k in ('stats','min_date','max_date','days_with_articles','date_histogram')},sort_keys=True))
        return 0 if result['articles'] else 1
    stats = asyncio.run(scraper.run_daily_scrape())
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({"schema_version": 1, "dry_run": args.dry_run,
            "stats": stats, "articles": scraper.articles, "provenance": scraper.provenance},
            ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for article in scraper.articles:
        print(json.dumps({k: article[k] for k in ('title', 'url', 'published_at', 'published_date',
                         'publication_precision', 'publication_source')}, ensure_ascii=False))
    print('NEWS SCRAPE RESULT ' + json.dumps(stats, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
