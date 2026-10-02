# FOODCAST push readiness — October 2, 2026

The source changes are ready for review and push after the checks below. Pushing
source alone does **not** complete the production migration. No repository push,
database migration, Edge deployment, or R2 upload was performed during this audit.

## Confirmed cause

[GitHub run 36909038009](https://github.com/Kendot1/THESIS/actions/runs/36909038009)
used commit `3c56dd0c7aaa1ba3d09773e336aad9c4e708be21`. Its logs show incremental
training, legacy model `v214_2026-10-01T19-56-12`, publication to Supabase, and
uploads under `model_artifacts/`. Those writes can replace the compatibility
prediction table even while the v2 `forecast_runs` table still identifies an
earlier v2 publication. This explains why local model changes did not fix the
live product predictions.

The replacement workflow restores only `model_artifacts_v2/`, runs a fresh causal
training experiment, applies the existing promotion gate, publishes forecasts
and their quality metrics atomically, and persists the active v2 bundle. It no
longer waits for an unrelated news-scraping job. Publication runs cannot overlap.
A separate validation workflow tests source changes on pushes and pull requests.

## Required rollout steps

1. Apply `supabase/migrations/202610010002_forecast_run_quality_metrics.sql` in the
   linked Supabase project. The read-only preflight confirmed that
   `forecast_runs.metrics` is currently missing. The updated daily job deliberately
   stops before training when this migration is absent.
2. Deploy the complete `supabase/functions/foodcast/` directory, including the
   new `quality.ts`, `dashboard.ts`, and `forecast.ts` modules. Pushing GitHub does
   not deploy this Edge function; the repository has no Edge deployment workflow.
3. Bootstrap the known active local v2 bundle to R2 if it should be retained as
   the champion/fallback: from `model_trainer`, run `python -m utils.r2_sync upload`.
   The remote `model_artifacts_v2/manifest.json` was absent during verification.
   Without this bootstrap, the first updated daily run trains a new v2 model and
   can publish only if that model beats persistence; legacy bundles are not used.
4. Push the source changes and deploy the frontend. All required database and R2
   secret **names** are configured on GitHub; their local equivalents passed
   read-only database and R2 authentication. Secret values on GitHub were not read.
5. Run the updated daily workflow manually. Verify the new run reports a v2 run
   ID, publishes quality metrics, and writes an R2 v2 manifest. Avoid running a
   workflow from an older commit, which can write legacy forecasts again.

The quality migration is additive. The earlier atomic publication and unit-aware
dashboard migrations are also required as documented in `model_trainer/README.md`.

## Prediction Success

The visible label is **Prediction Success** with **Measured model performance**
as its caption. It represents the current model's measured historical capability:
the fraction of point predictions within 5% of the actual price. The tooltip
states that definition. Range coverage is a separate metric; widening intervals
cannot improve this success score.

The existing v2 model's result is **73.94% across 25,889 unique product/date checks**,
with **5.16% MAPE**. `foodcast/app/lib/model-quality.json` is generated from that
model's saved test forecasts and is used only when the upstream model ID matches.
It is a rollout fallback, not a score reused for future model versions. New
publications supply their own measured capability through `modelMetrics`.
Recent realized results remain separate in `metrics`.

To regenerate the version-specific snapshot:

```text
cd model_trainer
python main.py export-quality --output ../foodcast/app/lib/model-quality.json
```

## Verification

- 27 Python tests passed, including a complete small training run, chronological
  calibration isolation, category intervals, serialization/serving parity, and
  fixed-tolerance point success. They also passed with the offline credentials
  configured in the new validation workflow.
- 20 frontend/API tests passed, including legacy dashboard and forecast tests.
- Frontend TypeScript check passed.
- An isolated Next.js production build compiled, type-checked, and generated all
  165 pages. The local Windows certificate store was required to fetch fonts.
- The built production API returned HTTP 200 with 73.9387% Prediction Success,
  25,889 checks, and the matching model ID. The temporary test server was stopped.
- Both workflow YAML files parsed; frontend installation uses the existing pnpm
  lockfile. Pinned model dependencies exist and support Python 3.11. Local model
  execution used Python 3.14; the new GitHub validation job uses Python 3.11.
- `git diff --check` passed under the repository's normal line-ending settings.
- All 119 local product series produced a forecast or bounded persistence fallback
  in the prediction diagnosis.

## Include in the push

Include both workflow files, the changed Python source and requirements,
`model_trainer/features/builder.py`, `model_trainer/models/forecast_engine.py`, all
model tests, the complete Edge function directory and migrations, the changed
frontend source and tests, `app/api/forecast/status/route.ts`, and all three
`app/lib/model-quality.*` files. Several of these required source files are still
untracked; committing only already-tracked changes would break the new pipeline.

Do not include local `.env` files, dependency/build directories, model binaries,
training snapshots, or runtime logs. Ignore rules now cover these generated
directories. Python bytecode already tracked by older commits is still tracked;
select source paths when staging instead of staging changed `.pyc` files.

## Latest completed retrain

The final retrain used **152,304 raw records through October 1, 2026** and produced
candidate `20261002T023852Z_6b175258`. The active model was backtested again on the
candidate's exact updated evaluation window, with 25,934 scored forecasts:

| Metric | Existing champion | Retrained candidate |
|---|---:|---:|
| MAE | 8.9275 | 8.8820 |
| RMSE | 25.6451 | 25.7681 |
| MAPE | 5.1082% | 5.0413% |
| Prediction Success (within 5%) | 73.9223% | 73.6639% |

The candidate was **not activated**. It improved MAE and MAPE, but worsened RMSE
and point-success rate, and failed the existing requirement for at least 5%
improvement in each error metric. The verified existing champion remains active;
no weaker model was forced into production. The version-specific UI snapshot
continues to report the champion's original saved evaluation (73.94%, which also
rounds to 73.9%), separately from this updated comparison.

These are retrospective evaluations, not guaranteed future success probabilities.
The completed earlier calibration experiment reduced category coverage error for
80% ranges from 16.66 to 4.45 percentage points and improved interval score from
66.92 to 57.83, but also remained an unpromoted candidate.

Retraining results and comparisons are stored beside this report, including
`training_result.json`, `candidate_comparison.json`, and `latest/training_result.json`.
