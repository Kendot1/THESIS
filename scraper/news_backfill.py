"""Bounded ABS-CBN discovery; reuses restored NewsScraper article extraction."""
import asyncio
import json
import re
import time
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import quote_plus, urljoin, urlparse, parse_qsl, urlencode, urlunsplit
import xml.etree.ElementTree as ET
import httpx


def canonical(url):
    p = urlparse(url)
    return urlunsplit((p.scheme, p.netloc.lower(), p.path, urlencode([(k,v) for k,v in parse_qsl(p.query) if not k.startswith('utm_') and k not in {'fbclid','gclid'}]), ''))


async def run_backfill(scraper, output_dir, max_candidates=200, runtime_seconds=850, discovery_file=None):
    from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
    from scraper.news_scraper import ABSCBN_SECTIONS
    if not scraper.dry_run or not scraper.start_date or scraper.provider != 'june':
        raise ValueError('Backfill requires June dry-run and both dates')
    if not 1 <= max_candidates <= 200 or not 1 <= runtime_seconds <= 900:
        raise ValueError('Bounds: candidates <=200; runtime <=900 seconds')
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    discoveries, failures, candidates = [], [], {}
    processed = set()
    batch_number = len(list(root.glob('batch*.json')))
    for file in sorted(root.glob('batch*.json')):
        saved = json.loads(file.read_text(encoding='utf-8'))
        scraper.articles.extend(saved['articles'])
        scraper.provenance.extend(saved['provenance'])
    timed_out = False
    def persist_batch(rows, provenance):
        nonlocal batch_number
        batch_number += 1
        (root / f'batch{batch_number:03d}.json').write_text(json.dumps({'articles':rows,'provenance':provenance},ensure_ascii=False,indent=2),encoding='utf-8')
    def add(url, source):
        url = canonical(url)
        if not scraper._is_supported_publisher(urlparse(url).hostname):
            return
        if not re.search(r'/\d{4}/\d{1,2}/\d{1,2}/',url):
            return
        if not scraper._candidate_in_range(url):
            scraper.exclusions.append({'url':url,'reason':'url_date_prefilter_outside_range','discovery_url':source})
            return
        if scraper._is_article_url(url) and len(candidates) < max_candidates:
            candidates.setdefault(url,source)
    async def acquire():
        async with AsyncWebCrawler() as crawler:
            config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS,page_timeout=20000)
            async def discover(url):
                try:
                    result = await asyncio.wait_for(crawler.arun(url=url,config=config),30)
                    if not result.success:
                        raise RuntimeError(str(result.error_message)[:250])
                    if 'unusual traffic' in str(result.markdown).lower():
                        raise RuntimeError('Google unusual-traffic interstitial, not discovery results')
                    before = len(candidates)
                    for group in result.links.values():
                        for link in group:
                            href = link.get('href','') if isinstance(link,dict) else str(link)
                            target = urljoin(url,href)
                            if target.startswith('https://www.google.com/url?'):
                                target = dict(parse_qsl(urlparse(target).query)).get('q',target)
                            add(target,url)
                    # Search pages may encode direct publisher URLs in their HTML.
                    for target in re.findall(r'https?://(?:www\.|news\.)?abs-cbn\.com/[^\s<>"\\]+',result.html or ''):
                        add(target.replace('&amp;','&'),url)
                    discoveries.append({'url':url,'success':True,'new_candidates':len(candidates)-before,'page_title':(result.metadata or {}).get('title'),'text_excerpt':str(result.markdown)[:600]})
                except Exception as exc:
                    discoveries.append({'url':url,'success':False,'error':type(exc).__name__+': '+str(exc)[:300]})
                (root/'discovery.json').write_text(json.dumps({'discoveries':discoveries,'candidates':candidates},ensure_ascii=False,indent=2),encoding='utf-8')
            # Official robots/sitemap/feed indexes can expose archived links.
            async with httpx.AsyncClient(timeout=12,follow_redirects=True) as client:
                queue = ['https://www.abs-cbn.com/robots.txt','https://www.abs-cbn.com/sitemap.xml','https://www.abs-cbn.com/rss']
                for url in queue:
                    if len(queue)>10: queue[:] = queue[:10]
                    try:
                        response = await client.get(url)
                        response.raise_for_status()
                        discoveries.append({'url':url,'success':True,'http_status':response.status_code})
                        for target in re.findall(r'https?://[^\s<>"\']+',response.text):
                            add(target,url)
                            if scraper._is_supported_publisher(urlparse(target).hostname) and 'sitemap' in target and target not in queue and len(queue)<10:
                                queue.append(target)
                    except Exception as exc:
                        discoveries.append({'url':url,'success':False,'error':type(exc).__name__+': '+str(exc)[:200]})
            for url in ABSCBN_SECTIONS:
                await discover(url)
            # Weekly windows cover the requested range, without claiming completeness.
            for query in scraper._backfill_search_queries():
                await discover('https://news.google.com/search?q='+quote_plus(query)+'&hl=en-PH&gl=PH')
                # General Google often returns direct canonical publisher links.
                await discover('https://www.google.com/search?q='+quote_plus(query)+'&num=20')
            if discovery_file:
                entries = json.loads(Path(discovery_file).read_text(encoding='utf-8'))
                for entry in entries:
                    before = len(candidates)
                    for hit in entry.get('result',{}).get('data',{}).get('web',[]):
                        # Search is discovery only; June body and date gates remain mandatory.
                        target = hit.get('url','')
                        if any(section in urlparse(target).path for section in ('/lifestyle/','/entertainment/','/sports/','/fashion/')):
                            continue
                        if scraper._is_supported_publisher(urlparse(target).hostname) and scraper._candidate_in_range(target) and re.search(r'/\d{4}/\d{1,2}/\d{1,2}/',target) and len(candidates)<max_candidates:
                            candidates.setdefault(canonical(target),'search_tool: '+entry['query'])
                    discoveries.append({'url':'search_tool: '+entry['query'],'success':True,'new_candidates':len(candidates)-before,'discovery_file':str(discovery_file)})
            # Browser fallback for official indexes that returned direct HTTP 403.
            for index in ('https://www.abs-cbn.com/robots.txt','https://www.abs-cbn.com/sitemap.xml','https://www.abs-cbn.com/rss'):
                await discover(index)
            for url in sorted(candidates):
                if len(processed)>=max_candidates or len(scraper.articles)>=scraper.max_articles:
                    break
                processed.add(url)
                before = len(scraper.provenance)
                try:
                    article = await asyncio.wait_for(scraper._process_article(crawler,url),65)
                    if article:
                        scraper.articles.append(article)
                        persist_batch([article],scraper.provenance[before:])
                    elif not any(e['url']==url for e in scraper.exclusions):
                        scraper.exclusions.append({'url':url,'reason':'no_supported_domestic_market_evidence_or_duplicate'})
                except Exception as exc:
                    failures.append({'url':url,'error':type(exc).__name__+': '+str(exc)[:400]})
                (root/'progress.json').write_text(json.dumps({'processed':len(processed),'collected':len(scraper.articles),'failures':failures,'exclusions':scraper.exclusions},ensure_ascii=False,indent=2),encoding='utf-8')
    try:
        await asyncio.wait_for(acquire(),runtime_seconds)
    except asyncio.TimeoutError:
        timed_out = True
    except Exception as exc:
        failures.append({'stage':'acquire','error':type(exc).__name__+': '+str(exc)[:500]})
    # Aggregate durable batches, not in-memory counters.
    rows, provenance, urls, hashes = [], [], set(), set()
    for file in sorted(root.glob('batch*.json')):
        data = json.loads(file.read_text(encoding='utf-8'))
        for row in data['articles']:
            if any(section in urlparse(row['url']).path for section in ('/lifestyle/','/entertainment/','/sports/','/fashion/')):
                scraper.exclusions.append({'url':row['url'],'reason':'excluded_non_market_section'})
                continue
            if row['url'] not in urls and row['content_hash'] not in hashes:
                urls.add(row['url']); hashes.add(row['content_hash']); rows.append(row)
        provenance.extend(data['provenance'])
    provenance = [p for p in provenance if p['url'] in urls]
    histogram = Counter()
    for row in rows:
        assert scraper._publication_exclusion(row) is None
        assert scraper._is_supported_publisher(urlparse(row['url']).hostname)
        day = datetime.fromisoformat(row['published_at']).astimezone(timezone(timedelta(hours=8))).date().isoformat() if row['published_at'] else row['published_date']
        histogram[day]+=1
    result = {'schema_version':1,'dry_run':True,'provider':'june','requested_range':{'start_date':str(scraper.start_date),'end_date':str(scraper.end_date),'timezone':'Asia/Manila','inclusive':True},'coverage_complete':False,'coverage_note':'Bounded discovery only; no guarantee of all articles or days. Unknown publication dates excluded.','stats':{'discovered':len(candidates),'processed':len(processed),'collected':len(rows),'stored':0,'discovery_attempts':len(discoveries),'discovery_successes':sum(d.get('success',False) for d in discoveries),'processing_failures':len(failures),'excluded':len(scraper.exclusions),'runtime_seconds':round(time.monotonic()-started,2),'timed_out':timed_out},'date_histogram':dict(sorted(histogram.items())),'min_date':min(histogram,default=None),'max_date':max(histogram,default=None),'days_with_articles':len(histogram),'articles':rows,'provenance':provenance,'discoveries':discoveries,'candidates':candidates,'failures':failures,'exclusions':scraper.exclusions}
    (root/'final.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    scraper.articles, scraper.provenance = rows, provenance
    return result
