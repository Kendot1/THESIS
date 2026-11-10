# FOODCAST model trainer

FOODCAST uses a recursive one-step LightGBM model trained on price movement
relative to the latest observed price, plus a direct 30-day attention LSTM
internally. The production publication contract is horizon-specific: exactly
7 daily target dates, 4 independent Monday-Sunday weekly target means, and 1
independent next-calendar-month target mean per supported series.
The scale-normalized tree target generalizes across products with very different
price ranges. Validation first blends those models, then learns how strongly each
horizon and product category should move away from the persistence forecast.
When the latest price is an extreme departure from its trailing seven-day mean,
a validation-calibrated reversion rule prevents that single regime jump from
anchoring the entire 30-day path. Serving publishes the 7-day daily model
path plus independent period rows; weekly/monthly currently use a completed-
period persistence baseline because no direct candidate passed the promotion
gates. Daily empirical residual intervals are published only where validation
support is sufficient; unsupported horizons remain explicitly unbounded.
Product confidence is a Beta-smoothed historical probability that absolute price
error will be at most PHP 5, shown only when its chronological provenance is
verified; it is not a probability for an individual forecast. The legacy
Within-10% rate remains a separate diagnostic. Base-model early stopping and
ensemble fitting use chronological validation data, with overlapping target
dates purged at the boundary.

Two-way chronological validation can also admit conservative product/horizon
specialists using the LSTM, persistence, or seven-day mean only when all three
error metrics improve in both validation halves.

The LightGBM trainer also supports an opt-in `mape_pseudo_huber` objective for
relative targets. It weights the smooth loss by inverse actual price and uses
validation MAPE for early stopping; set `FOODCAST_LGBM_MAPE_DELTA` to tune its
smoothing. This objective remains experimental because its current chronological
test screen did not improve MAPE over production.

The offline challenger path also supports `mape_weighted_l1`, which applies
inverse-actual weights to absolute relative-return error and selects rounds by
actual-price MAPE. Its matched test screen also failed to improve MAPE over the
incumbent. Neither experimental objective changes the production default.

The offline challenger can also opt into feature schema v6 with 30/60/90-day
relative price changes and 60-day volatility/deviation features using
`--long-memory`. These are calculated from prior observations only. The initial
screen improved pooled validation metrics slightly but did not exceed the
leading L1 challenger on the reused chronological test; the default remains v4.

The LightGBM implementation also has explicit `residual_absolute` and
`residual_relative` target modes for the requested LSTM-plus-residual
architecture. In those modes the learner requires aligned out-of-sample LSTM
base predictions during training, and the forecast engine passes the recursive
LSTM path into LightGBM so the returned point is `LSTM + residual`. The opt-in
`TrainingPipeline(lgbm_role="residual_relative")` path creates recursively
advanced LSTM-only OOF features, separates residual fit and selection dates,
purges crossing target dates, and refits the selected iteration count on all
eligible OOF rows. Residual inference advances price, peer, and LSTM feature
state with the same LSTM-only path used during training; direct LightGBM retains
corrected-price feedback. Both the initial screen and stricter recursive rollout
benchmark regressed the active bundle on the reused development test, so the
production bundle remains the direct-relative mode. See
`audits/accuracy_goal_20261011/residual_recursive_architecture_candidate.py`
and `score_recursive_residual_candidate.py` for the causal rollout and matched
comparison; full findings are in `audits/accuracy_goal_20261011/RESULTS.md`.

The standard training CLI exposes this existing candidate architecture with
`train --lgbm-role residual_relative --no-activate` (or `residual_absolute`).
This is an architecture selector, not training authorization: an approved bounded
fit allowance and eligible local snapshot are still required. Residual selection
is limited to new full candidate runs; resume/recalibration cannot relabel an
existing model, and source-as-of residual training still needs a separate OOF
plan. When no blend is supplied, the residual engine emits the complete
`LSTM + correction`, rather than averaging that result with the LSTM and halving
the correction. Existing direct-model blend behavior is unchanged.
This does not replace the independent weekly/monthly persistence serving paths
or establish a trained 7/4/1 hybrid bundle. Those horizons need separately
specified period targets, causal residual evidence, and admission evaluation;
averaging the daily path is not a substitute.

New LSTM bundles also consume additional available lag, volatility, and annual
seasonality signals. Only currency-valued inputs are divided by the sample price
anchor; dimensionless indicators such as RSI, volatility, and percentage changes
remain on their natural scales. Existing bundles retain their original input
contract. Training and recalibration currently stage candidates without automatic
activation: the internal chronological test has been repeatedly inspected during
development. Relative error improvements on that split are diagnostics only.
Promotion policy v10 defines primary accuracy as the share of valid predictions
within PHP 5 of the observed price and requires it to be >=95%, alongside
MAPE/MAE/RMSE <=5, stable validation improvement, and complete declared product
coverage. It checks the targets pooled and separately for Daily, Weekly, and
Monthly forecasts. Within-5% accuracy is reported separately; `100 - MAPE` is
only a MAPE complement. Within-10 remains a separate diagnostic. The standalone
[frozen holdout scorer](evaluation/README.md) verifies sealed forecasts and
reports realized errors; it does not itself activate models.
This v10 gate is legacy and does not qualify the current independent 7/4/1
targets. New candidate activation uses the predeclared matched-reference
[Policy 12 schema-3 profile](evaluation/POLICY12_V3.md), including strict
per-horizon MAE/RMSE/MAPE targets and all existing interval-support checks.
Legacy schema-2 14/4/1 evidence retains its original readers and interpretation;
it is not rewritten as schema-3 evidence.

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
and supabase/migrations/202610170001_prediction_interval_calibration.sql before
publishing the horizon-specific rows and calibrated bounds. The dashboard
refreshes those metrics and the actual forecast
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

The repository-root `AGENTS.md` governs execution permissions. The recorded
training allowance is exhausted: the training and recalibration commands below
are reference usage, not authorization to run them. This mission permits local
no-fit engineering and checks only until a new fit allowance is explicitly
granted. Do not publish, activate, upload, deploy, or mutate Supabase under the
read-only mission.

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

    # Write a read-only baseline report with per-model, per-lead, per-series,
    # category, bias, and naive-baseline comparisons.
    python main.py baseline-report --output-dir ../audits/<date>/baseline

    # Preview current forecasts locally without resolving product IDs or publishing.
    python main.py preview --horizon weekly --product Corn

    # Preview from a reproducible offline snapshot instead of Supabase history.
    python main.py preview --horizon weekly --product Corn --data ../audits/model_trainer_2026-09-18/food_prices_snapshot.json

    # Generate and atomically publish a complete 7/4/1 forecast vintage.
    # Reference only; publication is prohibited under the read-only mission.
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

Interval calibration can be reproduced without changing a model pointer:

    python -m evaluation.interval_calibration \
      --bundle artifacts_v2/runs/<run_id> \
      --output ../audits/<date>/interval_calibration/report.json

It calibrates a finite-sample order statistic of absolute residuals on
validation forecasts and scores coverage and width on the chronological test
split. An 80% interval requires at least eight distinct origins; a 95% interval
requires at least 19. Coverage outside five percentage points of nominal is
reported as limited. The order-statistic guarantee assumes exchangeable
residuals, which is not assured for time-dependent prices. A saved interval is
not a probability that an individual forecast is correct.

`baseline-report` reads only the selected bundle's saved `test_forecasts.csv`;
it does not fetch data, train models, score the pending holdout, or modify model
artifacts. Its MAPE and percentage-accuracy denominators explicitly exclude
zero/near-zero actual prices, while absolute PHP metrics retain them.

Bundles live under artifacts_v2/runs/<run_id>/. The active pointer is
artifacts_v2/manifest.json; legacy artifacts under artifacts/ are never loaded
by v2.

New training runs archive the exact raw input DataFrame in
`source_snapshot.json.gz` before fitting and hash-bind it, together with
`source_snapshot_manifest.json`, into the candidate bundle. The archive is
checked for row order, index, values, dtypes, and the training fingerprint;
an incomplete file pair is rejected. Recalibrated child bundles carry a
verified parent snapshot when one exists. Legacy bundles remain readable
without these files, but their original data vintage cannot be inferred from
today's source. The snapshot preserves available source rows, not historical
database revisions or immutable ingestion timestamps. To inspect a new bundle,
call `data.snapshot.read_snapshot(bundle_path, fingerprint_fn=TrainingPipeline._fingerprint)`
from Python; the function verifies both archive and fingerprint before use.

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
