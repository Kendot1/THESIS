"""
FOODCAST Synchronize Database: Copy data from Dev (oahacalovdvyzgqfrfii) to Prod (zhwhnnxbodzrklhgsurn)
"""

import os
import sys
import json
import subprocess
from pathlib import Path

SRC_REF = 'oahacalovdvyzgqfrfii'
DST_REF = 'zhwhnnxbodzrklhgsurn'

def get_service_key(ref):
    work = Path(os.environ['LOCALAPPDATA'])/'hermes/private-backups'/(f'foodcast-destination-{ref}' if ref==DST_REF else f'foodcast-source-{ref}')/'cli-workspace'
    r = subprocess.run(['npx.cmd','--yes','supabase','projects','api-keys','--remote='+ref,'--reveal','--output','json','--workdir',str(work)], capture_output=True, text=True)
    keys = json.loads(r.stdout)
    return next(x['api_key'] for x in keys if x.get('name')=='service_role')

print("Fetching credentials...")
src_key = get_service_key(SRC_REF)
dst_key = get_service_key(DST_REF)

from supabase import create_client
src = create_client(f'https://{SRC_REF}.supabase.co', src_key)
dst = create_client(f'https://{DST_REF}.supabase.co', dst_key)

print("1. Syncing products...")
src_prods = src.table('products').select('*').limit(300).execute().data
dst.table('products').upsert(src_prods).execute()
print(f"Products in Prod: {len(src_prods)}")

print("2. Syncing forecast_runs...")
src_runs = src.table('forecast_runs').select('*').limit(100).execute().data
dst.table('forecast_runs').upsert(src_runs).execute()
print(f"Forecast runs synced: {len(src_runs)}")

print("3. Syncing missing forecast_values...")
missing_run_ids = [
    'de41ebaf-2c64-44fa-bc2b-2f9c36193b24',
    'b06f015a-c8b6-48ce-bbde-6161032bfaa8',
    '4a033e43-3c3d-4c1f-b6b4-72c4aaed9c94',
    'b8322edb-2a65-4c40-a1e9-4e11333ecaee',
    '47a11232-23d1-4c60-a559-7fbb8a507b13'
]

total_synced_fv = 0
for rid in missing_run_ids:
    print(f"  Fetching run {rid}...")
    offset = 0
    batch_size = 1000
    while True:
        rows = src.table('forecast_values').select('*').eq('run_id', rid).range(offset, offset + batch_size - 1).execute().data
        if not rows:
            break
        dst.table('forecast_values').upsert(rows).execute()
        total_synced_fv += len(rows)
        offset += batch_size
        if len(rows) < batch_size:
            break
    print(f"  Synced run {rid} (cumulative: {total_synced_fv})")

print(f"Forecast values synced: {total_synced_fv}")

print("4. Syncing model_confidence_evaluations...")
src_conf = src.table('model_confidence_evaluations').select('*').limit(1000).execute().data
if src_conf:
    for i in range(0, len(src_conf), 100):
        chunk = src_conf[i:i+100]
        dst.table('model_confidence_evaluations').upsert(chunk).execute()
print(f"Model confidence evaluations synced: {len(src_conf)}")

print("5. Syncing news_articles...")
src_news = src.table('news_articles').select('*').limit(1000).execute().data
if src_news:
    for i in range(0, len(src_news), 100):
        chunk = src_news[i:i+100]
        dst.table('news_articles').upsert(chunk).execute()
print(f"News articles synced: {len(src_news)}")

print("6. Syncing product_daily_views...")
src_views = src.table('product_daily_views').select('*').limit(2000).execute().data
if src_views:
    for i in range(0, len(src_views), 200):
        chunk = src_views[i:i+200]
        dst.table('product_daily_views').upsert(chunk).execute()
print(f"Product daily views synced: {len(src_views)}")

print("=== FINAL SYNC AUDIT ===")
tables = [
    'products',
    'forecast_runs',
    'forecast_values',
    'model_confidence_evaluations',
    'news_articles',
    'product_daily_views'
]

for t in tables:
    sc = src.table(t).select('*', count='exact').limit(0).execute().count
    dc = dst.table(t).select('*', count='exact').limit(0).execute().count
    print(f"  {t:<30} Dev: {sc:<7} | Prod: {dc:<7}")

print("Synchronization complete!")
