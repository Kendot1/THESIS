# FOODCAST model trainer

FOODCAST uses a recursive one-step LightGBM model trained on price movement
relative to the latest observed price, plus a direct 30-day attention LSTM.
The scale-normalized tree target generalizes across products with very different
price ranges. Validation first blends those models, then learns how strongly each
horizon and product category should move away from the persistence forecast.
When the latest price is an extreme departure from its trailing seven-day mean,
a validation-calibrated reversion rule prevents that single regime jump from
anchoring the entire 30-day path. Empirical uncertainty bands support 80%, 90%,
and 95% confidence levels; the existing forecast response remains 80% by default.
The last third of validation origins is reserved for interval calibration.
Base-model early stopping and ensemble fitting use only the earlier validation
period; overlapping target dates are purged at the boundary. Category/horizon
bands require 100 calibration residuals per group, otherwise they use global
horizon bands. Persistence fallbacks have their own residual bands. The finite
sample rank correction follows [split-conformal calibration](https://statgrades.berkeley.edu/~ryantibs/statlearn-s24/lectures/conformal.pdf),
but these dependent time-series residuals do not provide a guaranteed coverage
probability. Evaluate measured coverage, average width, interval score (lower is
better), and category coverage together. Recalibrated legacy bundles explicitly
record that their base models already used validation for early stopping.

Two-way chronological validation can also admit conservative product/horizon
specialists using the LSTM, persistence, or seven-day mean only when all three
error metrics improve in both validation halves.

New LSTM bundles also consume additional available lag, volatility, and annual
seasonality signals. Only currency-valued inputs are divided by the sample price
anchor; dimensionless indicators such as RSI, volatility, and percentage changes
remain on their natural scales. Existing bundles retain their original input
contract. A candidate must beat persistence and reduce MAE, RMSE, and MAPE by at
least 5% each versus the active champion on the same frozen holdout to activate.

The pipeline enforces one causal contract from training through serving:

- a series is (category, product, variant, origin, unit);
- copied scraper rows can provide a bounded forward-filled input, but are never
  treated as observed labels;
- lag, rolling, indicator, and trend features use data available before the
  target date;
- train, validation, and frozen test partitions are chronological;
- LightGBM early stopping and ensemble weights use validation only;
- new LightGBM bundles predict relative price movement; legacy absolute-price
  bundles remain loadable;
- promotion requires frozen-test ensemble MAE, RMSE, and MAPE to beat both
  persistence and the active champion on the same test window;
- live prediction uses the same recursive forecast engine used in backtesting.

## Setup

Use Python 3.11 and install the pinned direct dependencies:

    python -m pip install -r requirements.txt

Database operations require SUPABASE_URL and a service-role SUPABASE_KEY. R2
synchronization additionally requires the CLOUDFLARE_R2_* variables defined in
config/settings.py.

Apply supabase/migrations/202609240001_atomic_forecast_vintages.sql before
publishing forecasts. It adds unit-aware product identity, immutable forecast
vintages, and the service-role-only atomic publication function.
Projects that already applied the original migration must also apply
supabase/migrations/202609250001_fix_forecast_safe_delete.sql so Supabase's
safe-update enforcement accepts the atomic compatibility-table refresh.
Apply supabase/migrations/202609250002_unit_aware_dashboard_summary.sql and
redeploy the `foodcast` Edge function so dashboard prices join predictions by
the same category/product/variant/origin/unit identity used by the model.
Apply supabase/migrations/202610010002_forecast_run_quality_metrics.sql and
redeploy the Edge function to publish frozen-holdout quality metrics with each
forecast run. The dashboard refreshes those metrics and the actual forecast
publication age every minute; it does not display a fabricated live accuracy.

Prediction success now means a point forecast within 5% of the observed price;
range coverage is reported separately. Each product/date is counted once using
its latest forecast published before that Philippine calendar date. Copied,
conflicting, and invalid observations are excluded. Realized metrics use the
current model's vintages and a 45-day observation window, including all relevant
runs rather than an arbitrary eight-run limit. All error metrics and their sample
counts come from the same evaluation population. The headline **Prediction
Success** uses `modelMetrics`, the current model's historical holdout capability,
while `metrics` holds recent realized results when available. A version-matched
snapshot generated with `export-quality` supports the existing model during the
database migration; it is never used for a different model ID. The website requires
30 observations before showing a point-success rate and never substitutes range
coverage for it. Deploy the Edge function and frontend together to expose the new
definition; old bundles remain loadable. The existing quality-metrics migration
listed above is required before running the updated GitHub daily workflow.

## Commands

    # Read-only publication preflight; fails clearly if the metrics migration is missing.
    python main.py check

    # Regenerate the measured capability snapshot for this exact active model.
    python main.py export-quality --output ../foodcast/app/lib/model-quality.json

    # Train from Supabase. A candidate activates only after passing the test gate.
    python main.py train --mode full

    # Reproducible offline run against a JSON or CSV snapshot.
    python main.py train --mode full --data ../audits/model_trainer_2026-09-18/food_prices_snapshot.json

    # Build a candidate without changing the active model pointer.
    python main.py train --mode full --data snapshot.json --no-activate

    # Resume calibration/evaluation after a post-training interruption.
    python main.py train --data snapshot.json --resume <run_id> --no-activate

    # Refit only the validation blend from a completed run's saved forecasts.
    python main.py train --recalibrate <run_id> --no-activate

    # Print frozen-test errors plus observed 80%, 90%, and 95% interval coverage.
    python main.py evaluate

    # Preview current forecasts locally without resolving product IDs or publishing.
    python main.py preview --horizon weekly --confidence 0.95 --product Corn

    # Preview from a reproducible offline snapshot instead of Supabase history.
    python main.py preview --horizon weekly --confidence 0.95 --product Corn --data ../audits/model_trainer_2026-09-18/food_prices_snapshot.json

    # Generate and atomically publish a complete forecast vintage.
    python main.py predict --horizon monthly

    # Upload the active immutable bundle; the remote pointer is written last.
    python -m utils.r2_sync upload

Incremental mode intentionally performs a fresh fit. Warm-starting a model after
recomputing categorical mappings and normalization would mix incompatible
training contracts.

## Verification

    python -m unittest discover -s tests -v

The suite covers future-invariance, observed/imputed target separation,
chronological split isolation, masked LSTM targets, exact incremental-feature
parity, ensemble endpoint selection, directional metrics, champion promotion,
bundle hashes, and a small end-to-end train/serialize/backtest run.

Bundles live under artifacts_v2/runs/<run_id>/. The active pointer is
artifacts_v2/manifest.json; legacy artifacts under artifacts/ are never loaded
by v2.
