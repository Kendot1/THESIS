# FOODCAST model trainer

FOODCAST uses a recursive one-step LightGBM model trained on price movement
relative to the latest observed price, plus a direct 30-day attention LSTM.
The scale-normalized tree target generalizes across products with very different
price ranges. Validation first blends those models, then learns how strongly each
horizon and product category should move away from the persistence forecast.
When the latest price is an extreme departure from its trailing seven-day mean,
a validation-calibrated reversion rule prevents that single regime jump from
anchoring the entire 30-day path. Serving publishes point predictions only.
Product confidence is a historical validation accuracy score, shown only when
its validation provenance is verified; it is not a probability for an individual
forecast. Base-model early stopping and ensemble fitting use chronological
validation data, with overlapping target dates purged at the boundary.

Two-way chronological validation can also admit conservative product/horizon
specialists using the LSTM, persistence, or seven-day mean only when all three
error metrics improve in both validation halves.

New LSTM bundles also consume additional available lag, volatility, and annual
seasonality signals. Only currency-valued inputs are divided by the sample price
anchor; dimensionless indicators such as RSI, volatility, and percentage changes
remain on their natural scales. Existing bundles retain their original input
contract. Training and recalibration currently stage candidates without automatic
activation: the internal chronological test has been repeatedly inspected during
development. Relative error improvements on that split are diagnostics only.
Production promotion requires independently verified final-holdout Within-10
accuracy >= 90%, MAE/RMSE <= PHP 5, MAPE <= 5%, stable improvement on all four
metrics, and explicit product coverage. The standalone
[frozen holdout scorer](evaluation/README.md) verifies sealed forecasts and
reports realized errors; it does not itself activate models.

The pipeline enforces one causal contract from training through serving:

- a series is (category, product, variant, origin, unit);
- copied scraper rows can provide a bounded forward-filled input, but are never
  treated as observed labels;
- lag, rolling, indicator, and trend features use data available before the
  target date;
- train, validation, and retrospective test partitions are chronological;
- the current 86/7/7 date split reserves about six months each for validation
  and retrospective testing while using the earlier 86% for fitting;
- training metadata audits fetched rows against their source-PDF dates, so
  forward-copied gap-fill rows are visible in counts but never treated as new
  observed-price labels;
- LightGBM early stopping and ensemble weights use validation only;
- new LightGBM bundles predict relative price movement; legacy absolute-price
  bundles remain loadable;
- an internal test comparison cannot authorize automatic promotion;
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
redeploy the Edge function to publish validation quality metrics with each
forecast run. Apply supabase/migrations/202610090001_multi_period_point_forecasts.sql
before publishing the daily path and saved calendar-week/calendar-month point
forecasts. The dashboard refreshes those metrics and the actual forecast
publication age every minute; it does not display a fabricated live accuracy.

Prediction success means a point forecast within 5% of the observed price.
The status endpoint reads evaluation metadata persisted with the latest forecast
run. Both `metrics` and `modelMetrics` contain that saved evaluation, including
its source and sample count. Page requests never score live outcomes: doing so
would scan historical tables and could consume reserved holdout dates. Calculate
new performance metadata only in the evaluation pipeline with its declared data
scope. The headline **Prediction Success** uses historical chronological
validation capability, not a claim of current live accuracy. A version-matched
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

    # Train from Supabase and stage the candidate for independent final evaluation.
    python main.py train --mode full

    # Bound a research run to the declared development period at the database.
    python main.py train --mode full --through 2025-09-12 --no-activate

    # Reproducible offline run against a JSON or CSV snapshot.
    python main.py train --mode full --data ../audits/model_trainer_2026-09-18/food_prices_snapshot.json

    # Build a candidate without changing the active model pointer.
    python main.py train --mode full --data snapshot.json --no-activate

    # Resume calibration/evaluation after a post-training interruption.
    python main.py train --data snapshot.json --resume <run_id> --no-activate

    # Refit only the validation blend from a completed run's saved forecasts.
    python main.py train --recalibrate <run_id> --no-activate

    # Print retrospective test point-error metrics for diagnosis only.
    python main.py evaluate

    # Preview current forecasts locally without resolving product IDs or publishing.
    python main.py preview --horizon weekly --product Corn

    # Preview from a reproducible offline snapshot instead of Supabase history.
    python main.py preview --horizon weekly --product Corn --data ../audits/model_trainer_2026-09-18/food_prices_snapshot.json

    # Generate and atomically publish a complete forecast vintage.
    python main.py predict --horizon monthly

    # Upload the active immutable bundle; the remote pointer is written last.
    python -m utils.r2_sync upload

Incremental mode intentionally performs a fresh fit. Warm-starting a model after
recomputing categorical mappings and normalization would mix incompatible
training contracts.

`train` and `preview` accept `--through YYYY-MM-DD`. Supabase applies this
inclusive report-date bound on every page; local snapshots are filtered before
preprocessing. Resume/recalibration retain their original scope and reject this
option. The bound limits observation dates; it does not reconstruct historical
database revisions or prove when source data became public. Keep declared final
holdout dates outside research inputs and retain verified publication vintages
for external features.

## Verification

    python -m unittest discover -s tests -v

The suite covers future-invariance, observed/imputed target separation,
chronological split isolation, masked LSTM targets, exact incremental-feature
parity, ensemble endpoint selection, directional metrics, champion promotion,
bundle hashes, and a small end-to-end train/serialize/backtest run.

Bundles live under artifacts_v2/runs/<run_id>/. The active pointer is
artifacts_v2/manifest.json; legacy artifacts under artifacts/ are never loaded
by v2.

Fresh GitHub runners restore the serving bundle from R2 before publication. The
daily workflow performs inference only; unrestricted daily training/evaluation
would consume reserved prospective holdout outcomes. Run new candidate training
separately with an explicitly reviewed development cutoff. A
completed training candidate does not create an active pointer: promotion still
requires independent reviewed evidence. If R2 has no `model_artifacts_v2/manifest.json`,
restore the existing production champion from a machine with its intact active
bundle by running `python -m utils.r2_sync upload` from `model_trainer`. This
uploads the bundle first and its active pointer last. Then run
`python -m utils.r2_sync download` and `python main.py predict --horizon monthly`
on the runner. The restore command fails immediately if the remote pointer is
missing, so a daily run fails before attempting publication when it cannot
serve forecasts. Retain the incumbent when a retrained candidate is not promoted.

External observation vintages can be checked with
`features.external_vintages.ObservationArchive`. The default lookup excludes
unverified availability dates and selects only revisions known at the forecast
origin. Retain the exact source artifact and publication evidence before marking
a vintage verified. The diagnostic-only opt-in is not production authorization.
The source research and conditional PAGASA experiment are documented in
`../audits/target5_20261002/PAGASA_FINDINGS.md`; those inputs are not enabled in the
production feature builder.
