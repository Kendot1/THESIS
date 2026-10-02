"""Read-only export for checking the revised API scorer against published vintages."""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'model_trainer'))
from config.settings import get_settings
from pipeline.prediction_writer import PredictionWriter
from models.model_store import ModelStore
from supabase import create_client


def fetch(query):
    rows = []
    while True:
        page = query.range(len(rows), len(rows)+999).execute().data
        rows.extend(page)
        if len(page) < 1000:
            return rows


if __name__ == '__main__':
    cfg = get_settings()
    db = create_client(cfg.supabase_url, cfg.supabase_key)
    output = Path(__file__).resolve().parent
    prices = json.loads((output/'training_snapshot.json').read_text(encoding='utf-8'))
    latest = max(row['report_date'][:10] for row in prices)
    since = (datetime.fromisoformat(latest)-timedelta(days=45)).date().isoformat()
    runs_since = (datetime.fromisoformat(latest)-timedelta(days=75)).date().isoformat()
    current = db.table('forecast_runs').select('model_run_id,generated_at').order(
        'generated_at', desc=True).limit(1).execute().data[0]
    runs = fetch(db.table('forecast_runs').select('id,generated_at').eq(
        'model_run_id', current['model_run_id']).gte('generated_at', runs_since).order('id'))
    products = fetch(db.table('products').select('id,name,variant,origin,category,unit').order('id'))
    forecasts = fetch(db.table('forecast_values').select(
        'run_id,product_id,prediction_date,predicted_price,lower_bound,upper_bound').in_(
        'run_id', [row['id'] for row in runs]).gte('prediction_date', since).lte(
        'prediction_date', latest).order('run_id').order('product_id').order('prediction_date')) if runs else []
    payload = {'model_run_id': current['model_run_id'], 'runs': runs, 'forecasts': forecasts,
               'products': products, 'prices': [row for row in prices if row['report_date'][:10] >= since]}
    (output/'live_quality_inputs.json').write_text(json.dumps(payload), encoding='utf-8')
    product_ids = {(row['category'], row['name'], row['variant'] or 'Standard',
                    row['origin'] or 'Unknown', row['unit'] or 'unknown'): row['id'] for row in products}
    quality = PredictionWriter._quality_metrics(ModelStore().active_path().name, product_ids)
    (output/'active_holdout_quality.json').write_text(json.dumps(quality, indent=2), encoding='utf-8')
    print(json.dumps({'model_run_id': current['model_run_id'], 'runs': len(runs),
                      'forecasts': len(forecasts), 'active_holdout_success': quality['prediction_success']}))
