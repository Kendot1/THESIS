import httpx
import re

r = httpx.get('https://www.abs-cbn.com/news/business/2026/4/28/government-fintech-work-together-through-crisis-1229', headers={'User-Agent': 'Mozilla/5.0'})
print('META:', re.findall(r'<meta[^>]+(?:published_time|datePublished|published)[^>]+>', r.text, re.I))
print('LDJSON:', re.findall(r'"datePublished"\s*:\s*"([^"]+)"', r.text, re.I))
