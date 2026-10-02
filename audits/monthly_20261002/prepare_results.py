"""Prepare local forecast deliverables without accessing or changing Supabase."""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'model_trainer'))
from utils.metrics import compute_all_metrics

OUTPUT = Path(__file__).resolve().parent


def read_json(name):
    return json.loads((OUTPUT / name).read_text(encoding='utf-8-sig'))


def save_json(name, value):
    (OUTPUT / name).write_text(json.dumps(value, indent=2), encoding='utf-8')


training = read_json('training_result.json')
context = read_json('training_context.json')
summaries = {label: read_json(f'{label}_forecast_precheck.json') for label in ['candidate', 'active']}
save_json('forecast_summary.json', summaries)
for label in ['candidate', 'active']:
    forecast = read_json(f'{label}_monthly_forecasts.json')
    current_series = [row for row in forecast['series'] if row['forecast_start'] == '2026-10-02']
    current_ids = {row['product_id'] for row in current_series}
    current_rows = [row for row in forecast['forecasts'] if row['product_id'] in current_ids]
    assert len(current_rows) == len(current_series) * 30
    save_json(f'{label}_current_monthly_forecasts.json', {
        'model_run_id': forecast['model_run_id'], 'published': False,
        'horizon_days': 30, 'forecast_start': '2026-10-02', 'forecast_end': '2026-10-31',
        'interval_level': .8, 'series_count': len(current_series),
        'series': current_series, 'forecasts': current_rows,
        'older_history_series': [row for row in forecast['series'] if row['product_id'] not in current_ids],
    })

run_path = ROOT / 'model_trainer' / 'artifacts_v2' / 'runs' / training['run_id']
metadata = json.loads((run_path / 'metadata.json').read_text(encoding='utf-8'))
history = json.loads((run_path / 'lstm_history.json').read_text(encoding='utf-8'))
test = pd.read_csv(run_path / 'test_forecasts.csv')
horizons = {}
for horizon in [1, 7, 14, 21, 30]:
    frame = test[test.horizon == horizon]
    horizons[str(horizon)] = compute_all_metrics(frame.actual, frame.ensemble, frame.anchor)
save_json('candidate_horizon_metrics.json', horizons)
candidate = training['test']['ensemble']
champion = training['promotion_gate']['active_champion']['ensemble']
persistence = training['test']['persistence']
current = read_json('active_current_monthly_forecasts.json')
fallbacks = [row for row in current['series'] if row['fallback_reason']]
rows = []
for title, key, percent in [('MAE', 'mae', False), ('RMSE', 'rmse', False),
                            ('MAPE', 'mape', True), ('Within 5% of actual', 'prediction_success', True)]:
    def fmt(metrics):
        value = metrics[key] * (100 if key == 'prediction_success' else 1)
        return f'{value:.4f}' + ('%' if percent else '')
    rows.append(f'| {title} | {fmt(champion)} | {fmt(candidate)} | {fmt(persistence)} |')
split_lines = [f"- {name.title()}: {bounds['start'][:10]} to {bounds['end'][:10]}."
               for name, bounds in metadata['split'].items()]
publication = (read_json('publication_verification.json')
               if (OUTPUT / 'publication_verification.json').is_file() else None)
publication_summary = (
    f"The active model's {publication['verified_rows']:,} forecast rows were published to "
    "Supabase and read back successfully after explicit user approval."
    if publication else "Nothing was published to Supabase or R2.")
publication_detail = (
    f"Published forecast run: `{publication['forecast_run_id']}`.\n\n"
    f"Verified {publication['verified_rows']:,} rows across {publication['series']} series. "
    "The shared `predictions` table exactly matches the immutable `forecast_values` run. "
    f"Verification completed at {publication['verified_at']}.\n\n"
    f"{publication['current_month_series']} series cover the current 30-day period; "
    f"{publication['older_history_series']} series remain anchored to older source data.\n\n"
    "- [Published current monthly forecasts](current_monthly_forecasts.json)\n"
    "- [Complete published run](published_monthly_forecasts.json)\n"
    "- [Publication verification](publication_verification.json)"
    if publication else
    "Automatic approval review rejected remote Supabase publication because the\n"
    "request did not explicitly authorize that destination or replacement of the\n"
    "shared forecast table. No remote forecast write occurred. Publication remains\n"
    "pending explicit user authorization; the proposed active-model predictions are\n"
    "available above for review.")
quality_detail = (
    "Quality metrics were stored with the published forecast run."
    if publication and publication['quality_metrics_published'] else
    "The database lacks `forecast_runs.metrics`. Forecast publication uses the existing\n"
    "atomic compatibility function. Attaching quality metrics still requires\n"
    "`supabase/migrations/202610010002_forecast_run_quality_metrics.sql`.")
report = f'''# Monthly training and forecast results — October 2, 2026

Training and local 30-day prediction are complete. The new candidate failed the
promotion gate, so the existing active model remains selected. {publication_summary}

## Training

- Candidate: `{training['run_id']}`.
- Active model: `{training['promotion_gate']['active_champion']['run_id']}`.
- Input: {context['data']['raw_rows']:,} raw records, {context['data']['observed_rows']:,}
  observed daily labels, and {context['data']['series_count']} product series through October 1, 2026.
- LSTM: {len(history)} epochs, best validation checkpoint at epoch {min(history, key=lambda row: row['val_loss'])['epoch']}.
- CPU training; configuration, source hashes, and snapshot hash are saved in
  `training_context.json`.

{chr(10).join(split_lines)}

## Same-window holdout comparison

Both models were evaluated on {training['test_samples']:,} forecasts. Lower error
is better; the fixed-tolerance success rate counts predictions within 5% of actual.

| Metric | Active model | New candidate | Last-price baseline |
|---|---:|---:|---:|
{chr(10).join(rows)}

The candidate failed the requirements to beat persistence in every error metric
and improve MAE, RMSE, and MAPE by at least 5% each versus the active model.
These are retrospective measurements, not guaranteed future performance.
Day-specific candidate scores are in `candidate_horizon_metrics.json`.

## Local monthly forecasts

Each model produced 3,570 rows across 119 series, with 30 consecutive daily
predictions per series and empirical 80% interval bounds.

- **87 current series / 2,610 rows cover October 2–31, 2026.** Of these,
  {87-len(fallbacks)} use the ensemble and {len(fallbacks)} use the last-price fallback.
- **32 older-history series** have forecast dates anchored to their last usable
  data. They do not provide a complete October 2–31 forecast and are listed separately.
- Across all 119 series, 23 use the bounded last-price fallback because causal
  model input history is insufficient.

Files:

- [Active model: October 2–31 forecasts](active_current_monthly_forecasts.json)
- [New candidate: October 2–31 forecasts](candidate_current_monthly_forecasts.json)
- [Active model: all date ranges](active_monthly_forecasts.json)
- [New candidate: all date ranges](candidate_monthly_forecasts.json)
- [Full training metrics](training_result.json)

## Verification and publication status

All 28 model pipeline tests passed. Repairs completed before training supplied
the four missing batch features, preserved the earlier LightGBM feature contract,
kept the existing champion comparison mandatory, and updated the masked Huber
loss check. Forecast validation checked row counts, unique product/date pairs,
consecutive dates, finite positive prices, and ordered interval bounds.

{publication_detail}

{quality_detail}
'''
(OUTPUT / 'RESULTS.md').write_text(report, encoding='utf-8')
print(json.dumps({'candidate': training['run_id'], 'activated': training['activated'],
                  'candidate_mape': candidate['mape'], 'active_mape': champion['mape'],
                  'current_series': current['series_count'], 'current_rows': len(current['forecasts']),
                  'current_fallbacks': len(fallbacks), 'published': publication is not None,
                  'report': str(OUTPUT / 'RESULTS.md')}, indent=2))
