# Policy 11: superseded independent-horizon proposal

Policy 11 was superseded before any real prospective candidate package was
sealed. It could skip interval checks when no series had calibration support,
and daily rows from two overlapping forecast origins could satisfy its
20-target-period support count. It is retained for audit history only; new
packages must use [policy 12](POLICY12.md). No policy-11 evidence qualifies
for new production activation.

This is the admission path for a **new** model serving 14 daily, four full
calendar-week, and one full calendar-month targets per forecast origin. It
cannot retroactively qualify the sealed October 2026 legacy 30-day contract,
which lacks independent weekly/monthly forecasts and complete series scope.
The active model remains unchanged until real, reproducible evidence passes.

## Freeze before observing outcomes

Select and finalize the candidate on chronological development data. Record
the exact policy-11 `acceptance_criteria` from
`prospective_freeze.ACCEPTANCE_CRITERIA` in `selection.json` **before** the
first prospective target. The criteria are relative to the matched incumbent
and origin-known persistence baselines: strict improvement in MAE, RMSE, and
MAPE, and no Within-PHP-5 regression, pooled and per horizon. There is no
unsupported guarantee of a fixed PHP error target or gain percentage.

For each of at least three separate forecast origins, prepare a self-contained
directory following [the schema-2 guide](PROSPECTIVE_HORIZONS.md), then run
`python -m evaluation.prospective_freeze <vintage_dir> <model_run_dir>` before
the first target day (Philippine time). Each vintage must use the same model,
selection timestamp, validation digest, and declared series. Its 19 forecasts
per declared series and raw forecast-input snapshot are hash-bound. Daily,
weekly, and monthly target periods must not be reused across vintages. The
source snapshot, model hashes, and row alignment are rechecked at promotion;
file timestamps and reviewer attestations alone are not cryptographic proof
of causal forecast generation. Reproduce the frozen forecasts from the frozen
inputs and model as part of provenance review.

After a vintage's latest target period closes and actuals are reconciled,
export observed daily rows and their manifest. Score with
`python -m evaluation.prospective_horizons <contract.json> <actuals.json>`;
save its complete JSON output as `score.json` without editing data-derived
fields. Do not inspect future windows while selecting or tuning a candidate.
The verifier refuses to open **any** package's actuals manifest until all
listed windows have closed.

## Reviewed evidence package

Place the vintage directories under one evidence root and create
`promotion_review.json` only after independent provenance and interval-width
review. The top-level schema is:

```json
{
  "schema_version": 2,
  "promotion_policy_version": 11,
  "model_run_id": "<exact candidate bundle directory>",
  "reviewed_by": "<identified reviewer>",
  "reviewed_at": "<actual timezone-aware timestamp>",
  "selection_provenance_checked": true,
  "source_snapshot_provenance_checked": true,
  "forecast_replay_checked": true,
  "actuals_provenance_checked": true,
  "holdout_not_used_for_selection": true,
  "interval_width_reviewed": true,
  "packages": [
    {
      "directory": "vintage1",
      "contract": {"file": "contract.json", "sha256": "<digest>"},
      "actuals_manifest": {"file": "actuals.json", "sha256": "<digest>"},
      "score_report": {"file": "score.json", "sha256": "<digest>"}
    }
  ]
}
```

The example shows one package for brevity; three or more are required. Never
set review flags from metric success alone. `ModelStore.activate(run_id,
evidence_dir=...)` uses the real clock, verifies policy 11, and changes the
pointer only if the verifier returns a receipt. Failed evidence leaves the
active pointer unchanged. Keep the previous bundle and evidence for rollback.

## Predeclared admission screen

The verifier recomputes every saved score after checking the exact contract,
model, selection, forecast-input snapshot, and actuals hashes. It combines
only observed outcomes, aligned on the same series/horizon/step/period for
candidate, incumbent, and persistence. Before prospective scoring, the
validation CSV must contain correctly aligned observed targets closing before
selection, at least three distinct origins and target periods per horizon,
and **20 distinct pre-selection target periods per selected series/horizon**
to support numeric product-level intervals. A selected series with fewer
periods remains in all point-forecast comparisons, but its validation and
prospective interval bounds for that horizon must be absent. The receipt marks
its interval reliability `limited_unavailable`. This is a conservative
minimum, not a claim that 20 observations prove perfect calibration.

Promotion requires matched MAE, RMSE, and MAPE improvement over **both**
references and no Within-PHP-5 regression, pooled and for every horizon, in
validation and prospective evidence. At least two thirds of validation
origins per horizon must win by those same metrics. Equal-series macro
performance must also improve on each prospective horizon. Product/horizon
and daily-lead MAE, RMSE, or MAPE deterioration above 10% relative to the
better reference blocks admission. Three independent prospective origins,
coverage of every declared series/horizon, and at least 30 scored rows per
daily lead are required; sparse products remain visible and do not qualify
by shrinking or silently filling labels.

Every scored row with sufficient product/horizon calibration support must
carry 80% and 95% prediction intervals; unsupported rows must carry neither.
Where any series supports intervals for a horizon, validation and prospective
pooled interval coverage must reach at least 70% for nominal 80% and 85% for
nominal 95%, with at least 30 interval-supported rows per horizon.
Daily product-level coverage with at least 30 final rows must reach 60%/75%;
validation product/horizon coverage must also reach 60%/75%. Interval support,
coverage, and mean width in PHP remain visible; a reviewer must assess
whether intervals are too wide to be useful. These broad tolerances are
screening limits, not proof of perfect 80% or 95% calibration. Missing bounds
or evidence are not converted to a confidence percentage.

## Limits

The verifier checks hashes, date order, exact target definitions, observed
label policy, arithmetic, and the predeclared screen. It cannot independently
prove source-PDF authenticity, absence of prior outcome access, or that each
CSV forecast came from the named model; `forecast_replay_checked` records a
reviewer determination, not a cryptographic proof. Independent data-source
reconciliation and replay are mandatory. The existing policy-10 compatibility
path still exists for legacy evidence; it is **not** policy-11 certification
of current 14/4/1 outputs. No real candidate has passed policy 11 as of
2026-10-17.
