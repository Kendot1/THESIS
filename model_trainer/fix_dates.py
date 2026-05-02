import os
import httpx
import re
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
client = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

res = client.table('news_articles').select('id, url').execute()

for r in res.data:
    url = r['url']
    resp = httpx.get(url, headers={'User-Agent': 'Mozilla/5.0'})
    pub_match = re.search(r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=["\']([^"\']+)["\']', resp.text, re.I)
    if not pub_match:
        pub_match = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']article:published_time["\']', resp.text, re.I)
        
    date_val = None
    if pub_match:
        date_val = pub_match.group(1)
    else:
        ld_match = re.search(r'"datePublished"\s*:\s*"([^"]+)"', resp.text, re.I)
        if ld_match:
            date_val = ld_match.group(1)
        else:
            url_date_match = re.search(r'/(\d{4})/(\d{1,2})/(\d{1,2})/', url)
            if url_date_match:
                y, m, d = url_date_match.groups()
                date_val = f"{y}-{int(m):02d}-{int(d):02d}T00:00:00Z"
                
    if date_val:
        client.table('news_articles').update({'published_at': date_val}).eq('id', r['id']).execute()
        print(f"Updated {r['id']} with date {date_val}")
