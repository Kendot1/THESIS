import httpx
import re

r = httpx.get('https://news.abs-cbn.com/business/2024/04/23/rice-prices-to-remain-high-until-mid-2024-da', headers={'User-Agent': 'Mozilla/5.0'})
matches = set(re.findall(r'([^"\'\s>]+od2-image-api\.abs-cbn\.com[^"\'\s>]+)', r.text))
print('IMAGE URLS FOUND:')
for m in matches:
    print(m)
