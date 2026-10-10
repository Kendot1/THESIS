# Frozen holdout scoring

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
Within-10 accuracy and MAPE use observed prices of at least 1e-8 PHP; zero and
near-zero observations remain in MAE/RMSE and are explicitly counted as
excluded from percentage metrics. Negative and nonfinite observed prices are
errors rather than silently removed labels. The report includes Daily,
publisher-rounded Weekly and Monthly forecasts, per-product and per-step
breakdowns, matched persistence, partial-period counts, and missing coverage.
A passing score on observed rows is distinct from a passing result for the
entire declared population. The report never activates a model.

All outputs are created exclusively and cannot overwrite a previous score. The
scorer also atomically reserves one attempt in `.contract.score-attempt.json`
beside the contract after the close-time guard and before opening actuals. This
blocks a second score even if it requests a different output filename. A failed
or interrupted attempt remains reserved; reconcile and inspect that state rather
than retrying under another filename.
Do not tune or select models using the final holdout report.

Synthetic integrity tests, which never open real holdout observations:

```powershell
.\model_trainer\.venv\Scripts\python.exe -B -m unittest model_trainer.tests.test_frozen_holdout -v
```
