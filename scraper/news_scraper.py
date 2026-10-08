"""
News scraping pipeline — ABS-CBN focused.
Crawls abs-cbn.com sections for articles, uses Groq/OpenAI LLM to
strictly filter for food-price relevance and extract structured intelligence.
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
from urllib.parse import urlparse, quote_plus

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
# ABS-CBN sections + Google News site-restricted search
# ──────────────────────────────────────────────
ABSCBN_SECTIONS = [
    "https://www.abs-cbn.com/business",
    "https://www.abs-cbn.com/business/companies",
    "https://www.abs-cbn.com/business/economy",
    "https://www.abs-cbn.com/news/nation",
    "https://www.abs-cbn.com/news/regions",
]

# Google News queries restricted to abs-cbn.com (last 30 days)
GOOGLE_SEARCH_QUERIES = [
    "abs-cbn.com rice price Philippines",
    "abs-cbn.com food prices Philippines",
    "abs-cbn.com vegetable price Philippines",
    "abs-cbn.com chicken pork price Philippines",
    "abs-cbn.com oil fuel price Philippines",
    "abs-cbn.com inflation Philippines",
    "abs-cbn.com typhoon crop damage Philippines",
    "abs-cbn.com agriculture supply Philippines",
    "abs-cbn.com import tariff food Philippines",
    "abs-cbn.com price cap Philippines",
    "abs-cbn.com war conflict food supply Philippines",
    "abs-cbn.com El Nino drought agriculture Philippines",
    "abs-cbn.com La Nina flood agriculture Philippines",
]

# ──────────────────────────────────────────────
# Keyword Pre-filter (to save LLM tokens)
# ──────────────────────────────────────────────
PRE_FILTER_KEYWORDS = [
    "price", "presyo", "agriculture", "agrikultura", "food supply",
    "inflation", "import", "export", "crop", "harvest", "drought",
    "flood", "typhoon", "bagyo", "vegetable", "gulay", "rice", "bigas",
    "onion", "sibuyas", "chicken", "manok", "pork", "baboy", "fish", "isda",
    "sugar", "asukal", "corn", "mais", "department of agriculture",
    "supply shortage", "kakulangan", "price hike", "price increase",
    "surplus", "smuggling", "fuel", "diesel", "gasoline", "oil price",
    "el nino", "la nina", "war", "conflict"
]

# ──────────────────────────────────────────────
# Strict LLM prompt — rejects anything not directly impacting food prices
# ──────────────────────────────────────────────
LLM_SYSTEM_PROMPT = """You are a strict food-price intelligence filter for a Philippine food price forecasting system.

Your job: determine if a news article DIRECTLY impacts food commodity prices in the Philippines.

RELEVANT articles include:
- Direct price changes of food commodities (rice, vegetables, meat, fish, etc.)
- Government price caps, tariffs, or import/export policies on food
- Supply chain disruptions (typhoons destroying crops, floods, droughts, El Niño/La Niña)
- Fuel/oil price changes (these affect transportation and food costs)
- War or geopolitical events affecting imports/exports of food or fuel
- Inflation reports mentioning food prices
- Smuggling or hoarding of food commodities
- Harvest reports, crop yield data, planting season updates

NOT RELEVANT (REJECT these):
- Wildlife stories (snakes, animals) even if they mention food animals
- Marine conservation or reef protection stories
- Food safety warnings about specific incidents (poisoned food, recalls)
- Celebrity news, sports, entertainment, politics unrelated to food policy
- General economic news not specifically about food/fuel prices
- Crime stories even if they happen near farms

Respond with ONLY valid JSON, no markdown fences, no explanation.

If NOT relevant: {"relevant": false}

If relevant:
{
  "relevant": true,
  "sentiment_score": <float -1.0 to 1.0. Negative = prices will INCREASE (bad for consumers). Positive = prices will DECREASE (good for consumers). 0 = neutral/stable>,
  "event_type": "<supply_shock | demand_spike | policy_change | import_export | price_movement | weather | fuel_energy | general>",
  "affected_products": ["<from: Rice, Well Milled Rice, Regular Milled Rice, Chicken, Pork, Beef, Egg, Bangus, Tilapia, Galunggong, Red Onion, White Onion, Garlic, Tomato, Cabbage, Eggplant, Squash, String Beans, Kangkong, Pechay Tagalog, Ampalaya, Siling Labuyo, Ginger, Potato, Carrot, Banana, Calamansi, Sugar, Cooking Oil, Corn>"],
  "keywords": ["<MAXIMUM 3 broad market drivers, e.g.: Fuel Hike, Weather Disturbance, Import Policy, Typhoon, Price Surge. Avoid specific nouns like 'Meralco' or 'Diesel'>"],
  "time_validity_days": <integer. How long will this event affect the market? e.g., 7 for a quick spike, 30 for a seasonal issue, 90 for El Nino>,
  "probability": <float 0.0 to 1.0. How likely is this to actually affect prices? e.g., 0.9 for a confirmed tariff hike, 0.4 for a rumored shortage>,
  "effect_magnitude": "<low | medium | high. How strong is the expected price impact?>",
  "summary": "<1-2 sentence summary focused on the PRICE IMPACT in English>",
  "title_tl": "<Translate the article's title into natural Filipino, ensuring proper grammar and punctuation>",
  "summary_tl": "<Translate the 1-2 sentence summary into natural, conversational Filipino. PAY SPECIAL ATTENTION TO PUNCTUATION: ensure proper use of commas, periods, and quotation marks where appropriate to make the sentences read clearly.>"
}"""


class NewsScraper:
    """
    Scrapes ABS-CBN news via direct crawling + Google News discovery,
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
        stats = {"discovered": 0, "new": 0, "relevant": 0, "stored": 0}

        try:
            from crawl4ai import AsyncWebCrawler
        except ImportError:
            log.error("crawl4ai not installed. Run: pip install crawl4ai")
            return stats

        if not self._groq_key and not self._openai_key:
            log.error("No LLM API key set. Add GROQ_API_KEY_NEWS_SCRAPER or OPENAI_API_KEY to .env")
            return stats

        llm_name = "Groq (gpt-oss-120b)" if self._groq_key else "OpenAI (gpt-4o-mini)"
        log.info(f"=== NEWS SCRAPING PIPELINE (ABS-CBN) === LLM: {llm_name}")

        # Step 1: Discover article URLs
        article_urls = await self._discover_article_urls()
        stats["discovered"] = len(article_urls)
        log.info(f"Discovered {len(article_urls)} article URLs.")

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
                except Exception as e:
                    log.warning(f"  Error processing {url}: {e}")

        log.info(
            f"=== SCRAPE COMPLETE === "
            f"discovered={stats['discovered']} new={stats['new']} "
            f"relevant={stats['relevant']} stored={stats['stored']}"
        )
        return stats

    # ------------------------------------------------------------------
    # URL Discovery (dual strategy)
    # ------------------------------------------------------------------
    async def _discover_article_urls(self) -> List[str]:
        """
        Two-pronged discovery:
        1. Crawl ABS-CBN section pages for today's articles
        2. Search Google News for ABS-CBN food/price articles from last 30 days
        """
        urls = set()

        try:
            from crawl4ai import AsyncWebCrawler, CacheMode, CrawlerRunConfig

            async with AsyncWebCrawler() as crawler:
                config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)

                # Strategy 1: ABS-CBN section pages
                for section_url in ABSCBN_SECTIONS:
                    try:
                        result = await crawler.arun(url=section_url, config=config)
                        if result and result.success:
                            for link_info in result.links.get("internal", []):
                                href = link_info.get("href", "") if isinstance(link_info, dict) else str(link_info)
                                if self._is_article_url(href):
                                    urls.add(href)
                    except Exception as e:
                        log.debug(f"Section scan failed {section_url}: {e}")

                # Strategy 2: Google News search for ABS-CBN articles
                for query in GOOGLE_SEARCH_QUERIES:
                    search_url = (
                        f"https://news.google.com/search?"
                        f"q={quote_plus(query + ' when:30d')}&hl=en-PH&gl=PH"
                    )
                    try:
                        result = await crawler.arun(url=search_url, config=config)
                        if result and result.success:
                            # Google News uses ./read/ links that redirect to actual articles
                            for link_info in result.links.get("internal", []):
                                href = link_info.get("href", "") if isinstance(link_info, dict) else str(link_info)
                                if href.startswith("./read/") or href.startswith("./articles/"):
                                    full_link = f"https://news.google.com{href[1:]}"
                                    urls.add(full_link)
                    except Exception as e:
                        log.debug(f"Google News search failed: {e}")

        except ImportError:
            log.warning("crawl4ai not available.")

        return list(urls)

    def _is_article_url(self, url: str) -> bool:
        """Check if a URL is a potentially food/price-relevant ABS-CBN article."""
        if not url or "abs-cbn.com" not in url:
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
        # URL slug keyword boost — accept business/news URLs,
        # or any URL whose slug contains a food/price keyword
        always_relevant_sections = ["/business/", "/news/nation/", "/news/regions/"]
        if any(s in url for s in always_relevant_sections):
            return True
        slug = url.split("/")[-1].lower()
        slug_keywords = [
            "price", "presyo", "food", "agri", "rice", "bigas",
            "vegetable", "gulay", "chicken", "pork", "fish",
            "fuel", "diesel", "oil", "inflation", "import",
            "export", "tariff", "typhoon", "drought", "flood",
            "supply", "harvest", "crop", "onion", "sugar",
        ]
        return any(kw in slug for kw in slug_keywords)

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------
    def _filter_existing_urls(self, urls: List[str]) -> List[str]:
        """Filter out URLs already stored in the database."""
        new_urls = []
        for url in urls:
            try:
                resp = (
                    self._client.table(self._table)
                    .select("id")
                    .eq("url", url)
                    .limit(1)
                    .execute()
                )
                if not resp.data:
                    new_urls.append(url)
            except Exception:
                new_urls.append(url)
        return new_urls

    def _check_content_hash(self, content_hash: str) -> bool:
        """Check if content hash already exists."""
        try:
            resp = (
                self._client.table(self._table)
                .select("id")
                .eq("content_hash", content_hash)
                .limit(1)
                .execute()
            )
            return len(resp.data) > 0
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Article Processing
    # ------------------------------------------------------------------
    async def _process_article(self, crawler, url: str) -> Optional[Dict[str, Any]]:
        """Crawl a single article and run strict LLM analysis."""
        from crawl4ai import CacheMode, CrawlerRunConfig

        config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)
        result = await crawler.arun(url=url, config=config)

        if not result or not result.success or not result.markdown:
            log.warning(f"  ✗ SKIP (crawl failed): {url}")
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

        # Extract source domain
        parsed = urlparse(url)
        source = parsed.netloc.replace("www.", "")
        if "news.google.com" in source:
            source = "abs-cbn.com (via Google News)"

        # ── Pre-Filter (Keyword Check) ──
        if not self._pre_filter_content(title, content):
            log.info(f"  ✗ SKIP (no food/price keywords): {title[:60]}")
            return None

        # ── LLM Analysis (strict filter) ──
        llm_result = await self._analyze_with_llm(title, content)

        if not llm_result:
            log.warning(f"  ✗ SKIP (LLM call failed): {title[:60]}")
            return None

        if not llm_result.get("relevant", False):
            log.info(f"  ✗ SKIP (LLM: not relevant): {title[:60]}")
            return None

        log.info(
            f"  ✓ RELEVANT: {title[:60]}... "
            f"sentiment={llm_result.get('sentiment_score', 0):.2f} "
            f"type={llm_result.get('event_type')} "
            f"products={llm_result.get('affected_products', [])}"
        )

        return {
            "title": title[:500],
            "title_tl": llm_result.get("title_tl", "")[:500],
            "content": llm_result.get("summary", content[:5000]),
            "content_tl": llm_result.get("summary_tl", ""),
            "source": source,
            "url": url,
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
        """Check if article contains at least one relevant keyword to save LLM tokens."""
        text = (title + " " + content).lower()
        for kw in PRE_FILTER_KEYWORDS:
            if kw in text:
                return True
        return False

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
                                {"role": "system", "content": LLM_SYSTEM_PROMPT},
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
                log.warning(f"  LLM API error ({status}): {e.response.text[:200]}")
                return None
            except json.JSONDecodeError as e:
                log.warning(f"  LLM returned invalid JSON: {e}")
                return None
            except Exception as e:
                log.warning(f"  LLM analysis failed: {type(e).__name__}: {e}")
                return None

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
            log.debug(f"Failed to store: {e}")
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
    asyncio.run(scraper.run_daily_scrape())
