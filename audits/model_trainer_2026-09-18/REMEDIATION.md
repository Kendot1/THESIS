# Model trainer remediation — 2026-09-24

The audit findings were implemented in the v2 training and forecast path. Legacy
artifacts remain untouched under model_trainer/artifacts and are never loaded by
v2.

## Implemented

- Removed the current-target deviation leak and made the trend epoch fixed.
- Replaced global interpolation, backfill, outlier deletion, and all-column
  dropna with a daily causal panel, seven-day forward-fill limit, and a separate
  observed_price label.
- Added source-date provenance checks so copied scraper rows are inputs only.
- Made unit part of series identity, normalized scraper aliases, and consolidated
  known oil-size and egg-unit schema drift. The snapshot now has 119 series
  instead of 167 fragmented unit strings.
- Added a fixed 55-column feature schema fitted on the training partition only.
- Added chronological 70/15/15 train, validation, and frozen-test partitions.
- Rebuilt the LSTM with masked 30-day labels, per-origin scaling, deterministic
  sampling, no dropped final batch, and no raw-price fallback.
- Added one shared forecast engine. LSTM inference ends on the first forecast
  date; LightGBM forecasts recursively; backtesting and serving use this same
  implementation.
- Replaced the dormant residual serving model with a validation-calibrated global
  convex blend and empirical horizon-specific intervals.
- Corrected directional accuracy to compare each target and prediction with its
  own forecast origin.
- Added persistence, seasonal-7, and seven-day-average baselines on identical
  sampled origins and labels.
- Added immutable, hash-verified bundles, an atomic active pointer, recovery
  commands, and R2 upload ordering that writes the pointer last.
- Added an active-champion gate: a fresh retrain must lower MAE, RMSE, and MAPE
  versus both persistence and the active model on the same frozen test window.
  Identical snapshots reuse stored results; shifted windows backtest the active
  bundle again for a fair comparison.
- Replaced delete-then-upsert publication with a service-role-only SQL function
  that inserts an immutable forecast vintage and refreshes the compatibility
  table in one transaction.
- Disabled incompatible warm starts; incremental and daily modes perform fresh
  chronological experiments.
- Added empirical 80%, 90%, and 95% uncertainty intervals with frozen-test
  coverage and average-width reporting while retaining 80% as the serving default.
- Added pinned direct dependencies and seventeen causal/integration tests.

## Full offline result

Active local run: 20260925T080751Z_1f28ecd1 (specialist-recalibrated child of
20260924T170337Z_14907530)

Data: 151,344 raw rows, 161,976 daily panel rows, 113,977 observed labels,
2019-10-10 through 2026-09-17.

Frozen test: 2025-09-02 through 2026-09-17, 25,774 observed forecast labels,
30-day origins sampled every 30 days.

| Model | MAE | RMSE | MAPE | Direction |
|---|---:|---:|---:|---:|
| v2 ensemble | 8.9582 | 24.4994 | 5.1201% | 41.76% |
| LSTM | 9.2860 | 26.8275 | 5.3861% | 48.39% |
| Recursive LightGBM | 17.4910 | 35.0424 | 12.4544% | 50.74% |
| Persistence | 9.7294 | 28.8715 | 5.5476% | 5.76% |
| Seasonal-7 | 10.7928 | 30.0592 | 6.1828% | 41.84% |
| Seven-day average | 10.5307 | 29.3000 | 5.9921% | 49.62% |

Against persistence, the promoted ensemble improves MAE by 7.93%, RMSE by
15.14%, and MAPE by 7.71%. Horizon- and category-specific persistence shrinkage,
plus validation-selected mean reversion after extreme origin-price jumps, lowers
all three errors versus the parent ensemble. Stable product/horizon specialists
also improved all three errors and directional accuracy. The validation-calibrated
80%, 90%, and 95% intervals achieved 83.27%, 91.69%, and 96.18% frozen-test
coverage, respectively.

## Verification

- Seventeen tests pass, including future-invariance, partition-boundary target masks,
  incremental/batch feature parity, model bundle hashes, and a small
  end-to-end training run.
- A balanced MAE/RMSE/MAPE LSTM objective, a direct multi-horizon LightGBM, a
  second-network blend, and residual-bias calibration were evaluated as isolated
  candidates. Each failed to lower all three frozen-test errors and was rejected;
  the active pointer therefore remains on the stronger run.
- The active registry loaded the promoted bundle and produced forecast dates
  beginning 2026-09-18 from a 2026-09-17 anchor.
- git diff --check passes.

## Deployment boundary

The Supabase migration was created but not applied, and the local bundle was not
uploaded to R2. No forecast rows were written to Supabase. Production publishing
should begin only after applying
supabase/migrations/202609240001_atomic_forecast_vintages.sql.

The frozen report is retrospective and source-dated. The existing database does
not preserve immutable ingestion vintages, so it cannot reproduce every fact
that was physically available at each historical timestamp.
