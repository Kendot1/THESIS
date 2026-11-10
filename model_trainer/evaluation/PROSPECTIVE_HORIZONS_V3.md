# Independent-horizon prospective scorer (schema 3)

Schema 3 is the additive 7/4/1 admission path for daily steps 1–7, four complete
future Monday-to-Sunday weeks, and one complete next calendar month. It does not
reinterpret schema-v2 14/4/1 contracts, receipts, or scores. The v2 modules and
their artifacts remain unchanged.

For each declared `category||product||variant||origin||unit` series, `forecasts.csv`
must contain exactly 12 unique `(series, origin, horizon, step)` keys with full
target-period bounds. Each row carries the candidate, matched incumbent, and
origin-known persistence (`anchor`) predictions. `prediction_status` is one of
`active`, `fallback`, or `missing`. A fallback row contains the locked fallback
value and a nonempty `status_reason`; a missing row keeps its expected key,
leaves `prediction` blank, and supplies a reason. Missing keys or unavailable
fallbacks cannot be hidden, and any missing candidate prediction blocks v3
admission. Numeric intervals are forbidden on missing predictions.

`prospective_freeze_v3` seals the model bundle, selection, source snapshot,
forecast file, and SHA-256 values for every v3 evaluation module. It uses the
actual timezone-aware clock and refuses a freeze after the first target day.
`prospective_horizons_v3` scores only after the final weekly/monthly target
closes. It reads and validates the sealed contract, clock, target closure, and
actuals-manifest metadata before opening actual row data. Every report contains
the canonical forecast keys, active/fallback/missing counts, missing target
counts, source and code hashes, and grouped results by product, series, horizon,
daily lead, and origin. Metric rows use the same candidate-available key mask
for candidate, incumbent, and persistence; missing keys remain in coverage and
prevent admission.

The `selection.json` must use `schema_version: 3` and
`promotion_policy_version: 12`, bind the candidate model ID and metadata hash,
forecast origin, timezone-aware `selected_at`, the declared/excluded series,
the exact `ACCEPTANCE_CRITERIA` in `prospective_freeze_v3`, and a SHA-256-bound
validation file plus a hash-bound, label-free `validation_scope.json`. Selection
also binds the complete sorted `validation_origins` list. The scope manifest
lists the exact canonical forecast keys (series, origin, horizon, step, and
period bounds), declared series, origin list, validation CSV path, and CSV hash.
It must enumerate the full 12-key matrix for every declared series and origin.
Every scope target must close before selection and strictly before 2026-10-06.
The freeze path checks this scope metadata before opening the validation CSV.
The validation CSV has the same 12 keys per series and origin,
plus `actual`, `is_observed`, `observed_days`, `period_days`, the three matched
predictions, `prediction_status`, and `status_reason`. Unobserved target keys
remain in the file with a blank actual and their observed-day count. Selection
cannot use any validation period that closes on or after its selection day.

Actual rows require an explicit observed flag. Zero values remain in MAE/RMSE;
MAPE excludes values below PHP 1e-8 and reports the exclusion count. Daily labels
use one observed day, weekly labels require at least four observed days in the
full week, and monthly labels require at least 15 observed days in the full
month. Unobserved rows are not imputed. The actuals manifest binds the sealed
contract hash and the reconciled data hash. If any target period ends on or
after 2026-10-06, the manifest must identify a prospective vintage and include
a hash-verified actuals-reconciliation receipt before the scorer opens actual
rows. The actuals manifest fields are `data_file`, `sha256`, `row_count`,
`target_date_min`, `target_date_max`, `reconciled_through`, `source`,
`is_observed_definition`, `contract_sha256`, `actuals_vintage_type`,
`reconciliation_manifest_file`, and `reconciliation_manifest_sha256`. The
reconciliation receipt binds the actuals file/hash, exact row count and date
range, contract hash, reconciliation time, source, and immutable source
snapshot plus manifest hashes. The scheduled source-only capture receipt is
not an actuals reconciliation and cannot satisfy this requirement.

`prospective_promotion_v3` verifies at least three separately frozen origins
with non-reused complete monthly targets, validates the same preselection
criteria, recomputes each score, and applies Policy 12. It returns an evidence
receipt only; it is not connected to model activation or serving.

## Schema-3 entry points

Run from `model_trainer` with the project environment configured:

```powershell
python -m evaluation.prospective_freeze_v3 <evidence_dir> <candidate_model_run_dir>
python -m evaluation.prospective_horizons_v3 <contract.json> <candidate_model_run_dir> <actuals_manifest.json>
```

The promotion verifier is invoked by an authorized reviewer through
`evaluation.prospective_promotion_v3.verify_promotion_evidence`. A score or
receipt alone never establishes causal forecast generation or authorizes
selection, activation, or promotion.
