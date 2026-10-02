# Monthly training and forecast results — October 2, 2026

Training and local 30-day prediction are complete. The new candidate failed the
promotion gate, so the existing active model remains selected. The active model's 3,570 forecast rows were published to Supabase and read back successfully after explicit user approval.

## Training

- Candidate: `20261002T042133Z_81639341`.
- Active model: `20261001T025925Z_0661960a`.
- Input: 152,304 raw records, 114,980
  observed daily labels, and 119 product series through October 1, 2026.
- LSTM: 22 epochs, best validation checkpoint at epoch 10.
- CPU training; configuration, source hashes, and snapshot hash are saved in
  `training_context.json`.

- Train: 2019-10-10 to 2024-08-27.
- Validation: 2024-08-28 to 2025-09-13.
- Test: 2025-09-14 to 2026-10-01.

## Same-window holdout comparison

Both models were evaluated on 25,934 forecasts. Lower error
is better; the fixed-tolerance success rate counts predictions within 5% of actual.

| Metric | Active model | New candidate | Last-price baseline |
|---|---:|---:|---:|
| MAE | 8.9275 | 9.3680 | 9.3336 |
| RMSE | 25.6451 | 26.8057 | 26.9964 |
| MAPE | 5.1082% | 5.3284% | 5.3805% |
| Within 5% of actual | 73.9223% | 72.9429% | 73.4287% |

The candidate failed the requirements to beat persistence in every error metric
and improve MAE, RMSE, and MAPE by at least 5% each versus the active model.
These are retrospective measurements, not guaranteed future performance.
Day-specific candidate scores are in `candidate_horizon_metrics.json`.

## Local monthly forecasts

Each model produced 3,570 rows across 119 series, with 30 consecutive daily
predictions per series and empirical 80% interval bounds.

- **87 current series / 2,610 rows cover October 2–31, 2026.** Of these,
  86 use the ensemble and 1 use the last-price fallback.
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

Published forecast run: `33b3eb2e-8b6b-4b37-bfe4-6e8b46bbbf20`.

Verified 3,570 rows across 119 series. The shared `predictions` table exactly matches the immutable `forecast_values` run. Verification completed at 2026-10-02T04:45:48.310462+00:00.

87 series cover the current 30-day period; 32 series remain anchored to older source data.

- [Published current monthly forecasts](current_monthly_forecasts.json)
- [Complete published run](published_monthly_forecasts.json)
- [Publication verification](publication_verification.json)

The database lacks `forecast_runs.metrics`. Forecast publication uses the existing
atomic compatibility function. Attaching quality metrics still requires
`supabase/migrations/202610010002_forecast_run_quality_metrics.sql`.
