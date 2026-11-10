# Frozen holdout scoring

## Current published horizon contract

New forecast vintages contain exactly 14 daily rows, 4 independent
Monday-Sunday weekly target rows, and 1 independent next-calendar-month target
row per supported product series. Weekly and monthly rows are not averages or
relabels of the daily forecast path. Until a direct horizon candidate passes
the promotion policy, the publisher uses the completed-period persistence
baseline for those two period targets and records that source in the run
metrics.

Daily prediction intervals use a finite-sample order statistic of absolute
residuals from chronological validation forecasts. The split-conformal rank is
`ceil((n+1)*nominal_level)`; bounds are unavailable if that rank exceeds the
calibration sample count. With the default minimum of eight residuals, an 80%
interval needs at least eight distinct origins; a 95% interval needs at least
19. Otherwise bounds are null and reliability is unavailable. This rank rule
has finite-sample coverage under exchangeability; temporal dependence in prices
means that assumption is not guaranteed. Validation-only production bounds are
labeled limited until out-of-sample product/lead coverage is established. The
interval report below evaluates validation-calibrated bounds on the separate
chronological test split and reports nominal level, empirical coverage, and
PHP width. It does not turn a model score or a Within-PHP-5 rate into a
probability of individual correctness:

```powershell
.\.venv\Scripts\python.exe -B -m evaluation.interval_calibration `
  --bundle artifacts_v2/runs/<run_id> `
  --output ..\audits\<date>\interval_calibration\report.json
```

## Current prospective evidence

`audits/target5_20261002/prospective_20261005/contract.json` contains incumbent
forecasts sealed on October 5 before the October 6–November 4 target period.
The period closes **November 5, 2026, 00:00 UTC+08:00**. Its 86 forecastable
series and 28 skipped series remain separate; partial scores cannot establish
complete-scope accuracy. Inspect without opening outcomes:

```powershell
.\model_trainer\.venv\Scripts\python.exe -B model_trainer/evaluation/frozen_holdout.py inspect audits/target5_20261002/prospective_20261005/contract.json
```

`freeze.py` creates a new prospective evidence directory directly from Supabase.
It uses the actual Philippine issue date, a supplied inclusive input cutoff,
and the configured seven-day causal fill limit. It never backdates issuance,
overwrites evidence, trains, activates, or publishes. Every unsupported series
stays in the declared population. The October 5 freeze used `--through 2026-10-01`
to preserve the earlier replay's reserved outcomes. The evidence directory
contains the exact input snapshot for reproducibility, not a production input
dependency. Preserve it and its source copies until final scoring and review.

Local model activation now separately requires [reviewed promotion evidence](PROMOTION.md).
Scoring alone never authorizes a model change, and the existing October replay
does not satisfy that prospective promotion contract.

Run from the repository root. This evaluator uses the standard library and never
loads model weights, fits models, or updates the active model pointer.

Verify forecast integrity without opening actual observations:

```powershell
.\model_trainer\.venv\Scripts\python.exe -B model_trainer/evaluation/frozen_holdout.py inspect audits/target5_20261002/prospective_holdout_20261002.json
```

The October replay has 2,580 predictions for 86 of 119 input series. Its period
closes on **2026-11-01 at 00:00 UTC+08:00**. It was generated on Oct 3 from an
Oct 1 snapshot, so the report identifies it as a late-frozen replay. The hashes
verify file consistency; they do not establish independence from label access
or reconstruct missing model-selection provenance.
The existing contract's legacy `snapshot_fingerprint` is the model training
fingerprint; `snapshot_sha256` identifies the exact forecast-input snapshot.
No inference source-code hash was recorded at that original freeze.

After the complete period has been ingested and reconciled, export canonical
actual observations to CSV. Do not fill gaps, clip price spikes, rescale prices,
or convert imputed prices into observed labels. Reconcile duplicate series/date
records before export. `series` consists of category, product, variant, origin,
and unit, separated by `||`, exactly matching the frozen forecast keys.

To prepare an export from Supabase **after November 5, 00:00 Philippine time**:

```powershell
.\model_trainer\.venv\Scripts\python.exe -B model_trainer/evaluation/export_actuals.py audits/target5_20261002/prospective_20261005/contract.json audits/target5_20261002/actuals_20261006_20261104
```

The exporter checks the real closing time before constructing a database client.
It queries only the target dates, preserves the raw export, rejects conflicting
or invalid observed prices, and exports observed labels without imputed prices.
It writes `actuals_manifest.draft.json` without `reconciled_through`, so it cannot
be passed directly to the scorer as reconciled evidence. Review the underlying
DA reports, ingestion completeness, units, missing observations and identity
changes; then copy the draft to `actuals_manifest.json` with the actual verified
reconciliation date. Never infer completeness from the latest row alone.

After that review, score the new holdout once:

```powershell
.\model_trainer\.venv\Scripts\python.exe -B model_trainer/evaluation/frozen_holdout.py score audits/target5_20261002/prospective_20261005/contract.json audits/target5_20261002/actuals_20261006_20261104/actuals_manifest.json audits/target5_20261002/prospective_20261005/score.json
```

```csv
series,target_date,actual,is_observed
Rice||Rice||Regular Milled||Local||kg,2026-10-02,45,true
```

Create a manifest beside the CSV using its actual SHA-256 hash:

```json
{
  "data_file": "actuals.csv",
  "sha256": "<SHA-256 of exact CSV bytes>",
  "reconciled_through": "2026-10-31",
  "source": "<observation source and export provenance>",
  "is_observed_definition": "<how source observations were distinguished from copied or imputed rows>"
}
```

The reconciliation date is an export attestation: populate it only after verifying
that the source period is complete. The scorer cannot verify the upstream source
from this declaration alone. It opens neither this manifest nor its observations
until the holdout closes; the CLI provides no date override.

```powershell
.\model_trainer\.venv\Scripts\python.exe -B model_trainer/evaluation/frozen_holdout.py score audits/target5_20261002/prospective_holdout_20261002.json path/to/actuals_manifest.json path/to/new_score_report.json
```

Scores use distinct observed series/date outcomes in original price units.
Within-5-PHP accuracy counts every observed nonnegative outcome once and marks
an inclusive hit when the absolute error is at most PHP 5. Within-5% accuracy,
Within-10 accuracy, and MAPE use observed prices of at least 1e-8 PHP; zero and
near-zero observations remain in MAE/RMSE and are explicitly counted as
excluded from percentage metrics. Negative and nonfinite observed prices are
errors rather than silently removed labels. The report includes Daily,
publisher-rounded Weekly and Monthly forecasts, per-product and per-step
breakdowns, matched persistence, partial-period counts, and missing coverage.
A passing score on observed rows is distinct from a passing result for the
entire declared population. The report never activates a model.

The existing frozen-holdout/promotion policy v10 has a PHP-specific legacy gate:
Within-5-PHP accuracy >=95%, MAPE <=5%, MAE <=PHP 5, and RMSE <=PHP 5. Do not
rewrite or relabel an already sealed v10 contract. An earlier aspirational
target of 95% of rows within 5% relative error, alongside MAPE <=5% and
MAE/RMSE <=PHP 5, is retained as a historical diagnostic, not a current
promotion rule. Within-5-PHP and Within-10% remain separately reported;
`100 - MAPE` is not forecast accuracy. Do not retrofit a new criterion into
the incumbent's sealed holdout evidence.

For the current independent 14/4/1 production targets, use
[policy 12](POLICY12.md): predeclared matched improvements over both incumbent
and persistence, product/lead regression limits, and supported 80%/95%
prediction-interval evidence. The preceding fixed PHP/relative percentages
are not policy-12 admission criteria or a guarantee that any candidate can
reach them.

All outputs are created exclusively and cannot overwrite a previous score. The
scorer also atomically reserves one attempt in `.contract.score-attempt.json`
beside the contract after the close-time guard and before opening actuals. This
blocks a second score even if it requests a different output filename. A failed
or interrupted attempt remains reserved; reconcile and inspect that state rather
than retrying under another filename.
Do not tune or select models using the final holdout report.

## Horizon-specific candidate artifact verification

The daily, weekly, and monthly research models are separate candidate bundles;
they are not production models. `HorizonModelBundle` loads the saved LightGBM
weights and runs origin-bounded direct forecasts. Schema-2 manifests declare
the target/calendar rule, feature columns and categories, causal input-age
limit, relative-price transform, source snapshot, and model SHA-256 hashes.
Older schema-1 bundles can be given an additive `inference_manifest.json`
sidecar; the original manifest and weights are left unchanged, and the loader
checks the sidecar against its parent manifest and every model file.

Run from `model_trainer` to upgrade only the legacy v1 audit candidates (the
command refuses to replace an existing sidecar):

```powershell
.\.venv\Scripts\python.exe -B -m evaluation.seal_horizon_manifests --run-dir ..\audits\foodcast_accuracy_20261015\horizon_models_v2
```

Then verify all saved weights reproduce their final recorded test-origin
predictions. This check loads the pre-holdout source snapshot for causal input
features and reads only saved prediction columns, not saved actuals. It is an
artifact consistency check, not an accuracy or promotion test:

```powershell
.\.venv\Scripts\python.exe -B -m evaluation.verify_horizon_artifacts --run-dir ..\audits\foodcast_accuracy_20261015\horizon_models_v2
```

New runs write schema-2 candidate manifests directly. Neither command activates
a model, publishes predictions, or reads the sealed prospective holdout.

### Validation selection aligned to the user's Within-5%-relative target

The isolated `evaluation.horizon_specific_relative5` experiment changes only
the validation strategy-selection rule: choose the shared or per-lead model
with the higher Within-5%-relative hit-rate, breaking ties by MAPE, MAE, then
RMSE. Feature construction, training parameters, and chronological cutoffs are
unchanged. The output is written to a unique candidate directory and is never
activated. Its historical test scores are diagnostic only; test rows do not
choose the strategy and the reused test period is not final promotion evidence.

```powershell
.\.venv\Scripts\python.exe -B -m evaluation.horizon_specific_relative5 `
  --data ..\audits\accuracy_goal_20261011\supabase_food_prices_through_20261005.json `
  --output-dir ..\audits\foodcast_accuracy_20261015\horizon_models_v4_relative5
```

To reproduce the user's acceptance metrics and the app-visible rates across the
active validation snapshot and saved horizon candidates, run this diagnostic.
It reports Within-5%-relative (the current >=95% user target), the legacy
Within-PHP-5 gate, Within-10%-relative, MAE, RMSE, and MAPE separately by
horizon, lead, and product. It reads no sealed holdout labels and does not
select or promote a model:

```powershell
.\.venv\Scripts\python.exe -B -m evaluation.within10_diagnostic
```

To retain a report, pass a new, not-yet-existing path with `--output`; the
command refuses to overwrite an earlier diagnostic.

For the incumbent comparison on weekly/monthly targets, use
`evaluation.compare_horizon_periods_active`. It replays the active bundle at
the candidate's exact origins, preserves the incumbent engine's emitted
recursive ensemble path, and applies the production publisher's calendar-period
rounding/aggregation before scoring only complete, matched target periods. The
historical test windows were already used during development, so these outputs
are diagnostic rather than independent promotion evidence. The replay can be
computationally expensive because every origin requires a multi-week/month
daily path.

```powershell
.\.venv\Scripts\python.exe -B -m evaluation.compare_horizon_periods_active --horizon weekly --output-dir ..\audits\foodcast_accuracy_20261015\horizon_models_v2\active_period_weekly
```

Synthetic integrity tests, which never open real holdout observations:

```powershell
.\model_trainer\.venv\Scripts\python.exe -B -m unittest model_trainer.tests.test_frozen_holdout -v
```
