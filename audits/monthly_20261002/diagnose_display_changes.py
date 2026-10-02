"""Read-only trace of large dashboard changes to model components and source data."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'model_trainer'))
from data.preprocessor import DataPreprocessor, SERIES_KEY
from models.model_store import ModelStore
from models.registry import ModelRegistry
from pipeline.prediction_writer import PredictionWriter
from utils.metrics import compute_all_metrics

OUTPUT = Path(__file__).resolve().parent
NAMES = ['Broccoli', 'Cabbage', 'Bittergourd']
raw = pd.read_json(OUTPUT / 'training_snapshot.json')
clean = DataPreprocessor().validate(raw[raw.product_name.isin(NAMES)])
registry = ModelRegistry.get().load_all()
ensemble = registry.engine.ensemble
store = ModelStore()
holdout = pd.read_csv(store.active_path() / 'test_forecasts.csv')
published = pd.DataFrame(json.loads((OUTPUT / 'published_monthly_forecasts.json').read_text(
    encoding='utf-8'))['forecasts'])
writer = PredictionWriter()
latest_runs = writer.db.table('forecast_runs').select(
    'id,model_run_id,generated_at,horizon,row_count').order('generated_at', desc=True).limit(2).execute().data
live_dashboard = writer.db.rpc('dashboard_product_summary', {'p_since_date': '2025-10-02'}).execute().data
live_dashboard = [row for row in live_dashboard.get('rows', []) if row['last_row']['product_name'] in NAMES]
diagnoses = []
for key, series in clean.groupby(SERIES_KEY, sort=True):
    if series.report_date.max() != clean.report_date.max():
        continue
    path = registry.engine.forecast(series, 30)
    anchor = path.anchor
    reference = float(series.price_index.dropna().tail(7).mean())
    base = (1-ensemble.weights)*path.lstm + ensemble.weights*path.lgbm
    horizon = anchor + ensemble.trust_weights*(base-anchor)
    category = anchor + ensemble.category_trust_weights.get(key[0], np.ones(30))*(horizon-anchor)
    anomaly_active = bool(abs(np.log(anchor/reference)) > ensemble.anomaly_threshold)
    product_key = f'{key[0]}||{key[1]}'
    identity = '||'.join(key)
    scored = holdout[holdout.series.eq(identity)]
    source_rows = published[(published.name == key[1]) & (published.variant.fillna('Standard') == key[2])
                            & (published.origin.fillna('Unknown') == key[3]) & (published.unit == key[4])]
    source_rows = source_rows.sort_values('prediction_date')
    def path_summary(values):
        values = np.asarray(values)
        return {'day_1': float(values[0]), 'first_week_mean': float(values[:7].mean()),
                'day_30': float(values[-1]), 'first_week_change_percent': float(100*(values[:7].mean()/anchor-1)),
                'largest_daily_step_percent': float(np.max(np.abs(np.diff(values)/values[:-1]))*100)}
    diagnoses.append({
        'identity': dict(zip(SERIES_KEY, key)), 'anchor': anchor,
        'trailing_7_day_mean': reference, 'trailing_30_day_mean': float(series.price_index.dropna().tail(30).mean()),
        'last_14_daily_inputs': [{'date': str(row.report_date.date()), 'price': float(row.price_index),
                                 'observed': bool(row.is_observed)} for row in series.tail(14).itertuples()],
        'lstm': path_summary(path.lstm), 'lightgbm': path_summary(path.lgbm),
        'base_blend': path_summary(base), 'after_horizon_shrinkage': path_summary(horizon),
        'after_category_shrinkage': path_summary(category), 'final_ensemble': path_summary(path.point),
        'published_week_mean': float(source_rows.predicted_price.head(7).mean()),
        'matches_published': bool(np.allclose(np.round(path.point, 2), source_rows.predicted_price.to_numpy())),
        'lgbm_weights_first_week': ensemble.weights[:7].tolist(),
        'horizon_trust_first_week': ensemble.trust_weights[:7].tolist(),
        'category_trust_first_week': ensemble.category_trust_weights.get(key[0], np.ones(30))[:7].tolist(),
        'anomaly_reversion_active': anomaly_active,
        'specialist_blends': {name: value for name, value in ensemble.specialist_blends.items()
                              if name.startswith(product_key+'##')},
        'holdout': {model: compute_all_metrics(scored.actual, scored[model], scored.anchor)
                    for model in ['ensemble', 'lstm', 'lgbm', 'persistence']} if len(scored) else {},
        'forecast': [{'day': i+1, 'date': str(pd.Timestamp(date).date()),
                      'point': float(path.point[i]), 'lstm': float(path.lstm[i]), 'lgbm': float(path.lgbm[i])}
                     for i, date in enumerate(path.dates)],
    })
live_summary = []
for row in live_dashboard:
    last = row['last_row']
    points = row['prediction_prices']
    live_summary.append({'name': last['product_name'], 'variant': last['product_variant'],
                         'origin': last['origin'], 'current_price': last['price_index'],
                         'last_date': last['report_date'], 'predicted_price': round(float(np.mean(points)), 2) if points else None,
                         'prediction_count': len(points)})
result = {'model_run_id': registry.run_id, 'latest_forecast_runs': latest_runs,
          'dashboard_horizon_days': 7, 'live_dashboard': live_summary,
          'diagnoses': diagnoses}
(OUTPUT / 'volatility_diagnosis.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps({**result, 'diagnoses': [{key: value for key, value in row.items()
                  if key not in ['forecast', 'last_14_daily_inputs']} for row in diagnoses]}, indent=2))
