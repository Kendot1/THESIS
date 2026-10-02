"""Export 30-day forecasts and optionally publish/verify the active model."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'model_trainer'))

from data.preprocessor import DataPreprocessor, SERIES_KEY
from features.builder import FeatureBuilder
from models.ensemble import EnsembleModel
from models.forecast_engine import ForecastEngine
from models.lightgbm_model import LightGBMModel
from models.lstm_model import LSTMModel
from models.model_store import ModelStore
from pipeline.prediction_writer import PredictionWriter

OUTPUT = Path(__file__).resolve().parent


def save_json(name, value):
    (OUTPUT / name).write_text(json.dumps(value, indent=2), encoding='utf-8')


def check_rows(frame, expected_series):
    assert len(frame) == expected_series * 30, 'Incomplete monthly forecast'
    assert not frame.duplicated(['product_id', 'prediction_date']).any()
    values = frame[['predicted_price', 'lower_bound', 'upper_bound']].to_numpy(float)
    assert np.isfinite(values).all() and (values > 0).all()
    assert (frame.lower_bound <= frame.predicted_price).all()
    assert (frame.predicted_price <= frame.upper_bound).all()
    for _, series in frame.groupby('product_id'):
        dates = pd.to_datetime(series.prediction_date).sort_values()
        assert len(dates) == 30 and dates.diff().dropna().eq(pd.Timedelta(days=1)).all()


def export_forecasts(run_id, clean, product_ids, label):
    path = ModelStore().runs / run_id
    builder = FeatureBuilder(path).load()
    tree = LightGBMModel(path)
    tree.load()
    lstm = LSTMModel(path)
    lstm.load()
    ensemble = EnsembleModel(path)
    ensemble.load()
    engine = ForecastEngine(tree, lstm, ensemble, builder)
    rows, series_details = [], []
    for key, history in clean.groupby(SERIES_KEY, sort=True):
        identity = dict(zip(SERIES_KEY, key))
        fallback = None
        try:
            forecast = engine.forecast(history, 30)
            dates, point, lower, upper = (
                forecast.dates, forecast.point, forecast.lower, forecast.upper)
            anchor = forecast.anchor
        except ValueError as exc:
            if not PredictionWriter._is_history_shortfall(exc):
                raise
            fallback = str(exc)
            dates, point, lower, upper = PredictionWriter._persistence_fallback(engine, history, 30)
            anchor = float(point[0])
        observed = history.loc[history.is_observed, 'report_date']
        detail = {**identity, 'product_id': product_ids[tuple(key)],
                  'latest_observed_date': str(observed.max().date()),
                  'anchor': round(anchor, 2),
                  'forecast_start': str(np.datetime_as_string(dates[0], unit='D')),
                  'forecast_end': str(np.datetime_as_string(dates[-1], unit='D')),
                  'fallback_reason': fallback}
        series_details.append(detail)
        forecast_rows = PredictionWriter._rows(product_ids[tuple(key)], dates, point, lower, upper)
        rows.extend({**row, **identity, 'horizon_day': i,
                     'method': 'persistence_fallback' if fallback else 'ensemble'}
                    for i, row in enumerate(forecast_rows, 1))
    check_rows(pd.DataFrame(rows), len(series_details))
    result = {'model_run_id': run_id, 'horizon_days': 30, 'interval_level': .8,
              'published': False, 'series': series_details, 'forecasts': rows}
    save_json(f'{label}_monthly_forecasts.json', result)
    return {'model_run_id': run_id, 'series': len(series_details), 'rows': len(rows),
            'fallback_series': sum(row['fallback_reason'] is not None for row in series_details),
            'forecast_start_counts': pd.Series([row['forecast_start'] for row in series_details])
                                      .value_counts().sort_index().to_dict(),
            'forecast_end_counts': pd.Series([row['forecast_end'] for row in series_details])
                                    .value_counts().sort_index().to_dict()}


def read_all(db, table, run_id=None):
    rows = []
    while True:
        query = db.table(table).select('*')
        if run_id:
            query = query.eq('run_id', run_id)
        page = query.order('product_id').order('prediction_date').range(len(rows), len(rows)+999).execute().data
        rows.extend(page)
        if len(page) < 1000:
            return rows


def publish_and_verify():
    writer = PredictionWriter()
    result = writer.run('monthly')
    save_json('publication_result.json', result)
    run_id = result['forecast_run_id']
    run = writer.db.table('forecast_runs').select('*').eq('id', run_id).single().execute().data
    values = read_all(writer.db, 'forecast_values', run_id)
    check_rows(pd.DataFrame(values), result['series'])
    assert run['model_run_id'] == result['model_run_id']
    assert run['horizon'] == 30 and run['row_count'] == len(values) == result['rows_written']
    compatibility = read_all(writer.db, 'predictions')
    fields = ['product_id', 'prediction_date', 'predicted_price', 'lower_bound', 'upper_bound']
    canonical = lambda rows: sorted(tuple(row[field] for field in fields) for row in rows)
    assert canonical(values) == canonical(compatibility), 'Live compatibility table differs from published run'
    products = writer.db.table('products').select('id,name,variant,origin,category,unit').execute().data
    identities = {row['id']: {key: value for key, value in row.items() if key != 'id'} for row in products}
    fallback_keys = {tuple(item['series']) for item in result['fallback_details']}
    readable_values = []
    for row in values:
        identity = identities[row['product_id']]
        key = (identity['category'], identity['name'], identity['variant'] or 'Standard',
               identity['origin'] or 'Unknown', identity['unit'] or 'unknown')
        readable_values.append({**row, **identity,
                                'method': 'persistence_fallback' if key in fallback_keys else 'ensemble'})
    save_json('published_monthly_forecasts.json', {
        'forecast_run': run, 'interval_level': .8,
        'forecasts': readable_values})
    today = datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
    starts = pd.DataFrame(values).groupby('product_id').prediction_date.min()
    current_products = set(starts.index[starts.eq(today)])
    current_rows = [row for row in readable_values if row['product_id'] in current_products]
    save_json('current_monthly_forecasts.json', {
        'forecast_run': run, 'as_of_date': today, 'interval_level': .8,
        'series_count': len(current_products), 'forecasts': current_rows,
        'older_history_series': [
            {'product_id': product_id, **identities[product_id], 'forecast_start': start}
            for product_id, start in starts.items() if product_id not in current_products]})
    result['verified_at'] = datetime.now(timezone.utc).isoformat()
    result['verified_rows'] = len(values)
    result['compatibility_table_matches'] = True
    result['current_month_series'] = len(current_products)
    result['current_month_rows'] = len(current_rows)
    result['current_month_fallback_series'] = len({row['product_id'] for row in current_rows
                                                  if row['method'] == 'persistence_fallback'})
    result['older_history_series'] = result['series'] - len(current_products)
    save_json('publication_verification.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    if args.publish:
        print(json.dumps(publish_and_verify(), indent=2))
    else:
        training = json.loads((OUTPUT / 'training_result.json').read_text(encoding='utf-8'))
        clean = DataPreprocessor().validate(pd.read_json(OUTPUT / 'training_snapshot.json'))
        product_ids = PredictionWriter()._product_ids()
        active = ModelStore().active_path().name
        summary = {'candidate': export_forecasts(training['run_id'], clean, product_ids, 'candidate')}
        summary['active'] = (summary['candidate'] if active == training['run_id'] else
                             export_forecasts(active, clean, product_ids, 'active'))
        save_json('forecast_summary.json', summary)
        print(json.dumps(summary, indent=2))
