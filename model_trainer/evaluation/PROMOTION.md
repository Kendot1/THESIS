# Reviewed local model activation

New `ModelStore.activate(run_id, evidence_dir=...)` calls require reviewed final
evidence. Missing or failing evidence leaves the active pointer unchanged.
`finalize(..., activate=True)` and `rollback(...)` cannot bypass this check.
Stage new bundles with `activate=False`, then evaluate them independently before
requesting activation. Reading an existing legacy active bundle remains possible;
this compatibility is not a retrospective certification of its accuracy.

## Admission policy version 2

Policy version 1 evidence does not qualify under version 2. Existing prospective
contracts must not be retagged or rewritten; the new checks apply to a newly
selected model and its own forecasts frozen before their target dates.

The policy is an operational threshold, not a statistical theorem. Record its
version at selection, before final forecasts are frozen.

- Exactly 30 days of prospective forecasts, frozen before the first target day.
- Complete declared series coverage; selection and forecast populations agree.
- Exact six model-component hashes and finalized metadata hash match the bundle.
- Model creation precedes selection; selection precedes freeze; review follows
  final scoring. Every timestamp includes a timezone.
- Matched validation forecasts finish before selection and the holdout. Recompute
  Within-10 accuracy and MAE, RMSE, and MAPE against champion and persistence on
  identical rows. Require strict aggregate improvement on all four metrics and
  improvement on all four at at least two thirds of at least three origins.
- A closed, fully reconciled final period with scores recomputed by
  `frozen_holdout.score`. Require Within-10 >= 90%, MAE <= PHP 5, RMSE <= PHP 5,
  MAPE <= 5%, full declared scope under the scorer's observed-label rules, and
  no Within-10 regression plus strict improvement on all three errors over
  matched persistence. The saved score report must reproduce exactly apart from
  the scoring clock field.
- Identified reviewer attests to checking selection provenance, actual-source
  provenance and non-use of the final holdout for selection.

This is not a mechanism to relabel development data as final evidence. The current
October replay is late-frozen, covers 86/119 series and has no pre-freeze selection
record in this format; it cannot satisfy this admission policy. Do not amend that
historical contract to manufacture missing evidence. No current research candidate
has qualifying evidence.

## Evidence directory

Keep these files and their referenced data within one evidence directory:

1. `contract.json` and its frozen forecast CSV, following the frozen scorer
   contract. In addition to its existing fields, the contract requires:
   `holdout_type: "prospective"`, `model_metadata_sha256`,
   `selection_record_sha256`, and exact `model_bundle_sha256` entries for
   `categorical_mappings.json`, `lightgbm_model.txt`, `lightgbm_meta.json`,
   `lstm_model.pt`, `lstm_meta.json`, and `ensemble.json`.
2. `selection.json`, sealed before the holdout:

```json
{
  "promotion_policy_version": 2,
  "model_run_id": "<exact bundle directory name>",
  "model_metadata_sha256": "<finalized metadata digest>",
  "selected_at": "<actual timezone-aware selection timestamp>",
  "declared_series": ["<category||product||variant||origin||unit>"] ,
  "validation_forecasts_sha256": "<matched validation CSV digest>"
}
```

3. `validation.csv` with columns
   `series,origin,target_date,actual,prediction,champion,anchor`. Each row is one
   observed validation outcome with candidate, incumbent and persistence prices.
   Preserve every eligible matched outcome; do not select rows based on errors.
   Duplicate keys, nonfinite/nonpositive prices and overlapping dates are rejected.
4. An actuals manifest and CSV following [the scoring guide](README.md), exported
   only after the full period is reconciled.
5. `score.json`, the unmodified scorer output for those exact inputs.
6. `promotion_review.json`, prepared only after provenance review:

```json
{
  "schema_version": 1,
  "promotion_policy_version": 2,
  "model_run_id": "<exact bundle directory name>",
  "reviewed_by": "<identified reviewer>",
  "reviewed_at": "<actual timezone-aware review timestamp>",
  "selection_provenance_checked": true,
  "actuals_provenance_checked": true,
  "holdout_not_used_for_selection": true,
  "contract": {"file": "contract.json", "sha256": "<digest>"},
  "actuals_manifest": {"file": "actuals.json", "sha256": "<digest>"},
  "score_report": {"file": "score.json", "sha256": "<digest>"},
  "selection_record": {"file": "selection.json", "sha256": "<digest>"},
  "validation_forecasts": {"file": "validation.csv", "sha256": "<digest>"}
}
```

These examples are schemas, not completed reviews. Do not set attestations from
metric success alone. Validation prediction provenance, frozen source/code
vintages and genuine selection independence require supporting records and review.

## Verify before activation

The standard-library function `evaluation.promotion.verify_promotion_evidence`
returns a digest-bound receipt or raises an error. It does not write a pointer or
change any artifact. Its optional `now` argument is for synthetic tests; real
`ModelStore.activate` always uses the current clock and exposes no override.

Only after a concrete passing evidence package has been reviewed should the
local application call `store.activate(run_id, evidence_dir=path)`. The pointer
records evidence and metadata digests. Later metadata modification invalidates
the newly promoted bundle. All required bundle hashes must be present.

## Limits and deployment scope

Hashes prove file consistency, not truthful timestamps or absence of label access.
Reviewer fields are attestations, not signatures or an authorization service.
The validation CSV is recomputed but its forecasts are not regenerated from model
weights by this verifier; provenance review must establish their origin and scope.
Coverage depends on the actuals export's reconciliation attestation.

This change enforces the local model-store API. R2 synchronization restores a
remote pointer through a separate path; its release trust/receipt handling has
not been changed here. Direct filesystem edits also remain outside the API.
Do not describe this as an end-to-end deployment authorization system. No remote
model, job, migration or forecast was changed by implementing these checks.
