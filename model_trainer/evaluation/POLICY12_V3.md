# Policy 12 admission profile for schema 3

Schema 3 changes the prospective target scope to daily 7 days, weekly 4 complete
weeks, and monthly 1 complete calendar month. It keeps `promotion_policy_version`
12 and every existing Policy 12 comparison, coverage, regression, interval,
origin-win, and prospective-evidence gate. Schema-v2 14/4/1 evidence keeps its
original reader, scorer, criteria, and interpretation.

Schema-3 selection records bind these additional mission goals as strict gates:

- For each of daily, weekly, and monthly, candidate MAE must be below PHP 5.00.
- For each of daily, weekly, and monthly, candidate RMSE must be below PHP 5.00.
- For each of daily, weekly, and monthly, candidate MAPE must be below 5.00%.

Equality does not pass. These thresholds apply to each horizon's candidate
summary in both matched validation and prospective evidence. They do not replace
or weaken the existing requirement for strict MAE, RMSE, and MAPE gains against
both the matched incumbent and origin-known persistence where Policy 12
requires those gains. Within-PHP-5 performance, equal-series macro performance,
product/horizon and daily-lead regression caps, two-thirds validation-origin
wins, complete forecast-key coverage, interval support and coverage, and the
three independent prospective vintage requirements remain in force.

Numeric interval support still requires at least 20 distinct preselection
target periods and 20 distinct forecast origins per series and horizon. Every
horizon still needs interval-supported validation evidence; unavailable
intervals stay explicitly unavailable. A forecast key marked `missing` blocks
admission; a locked persistence fallback remains a scored prediction and is
counted separately from active model predictions.

This profile does not authorize training, holdout-label selection, serving
changes, activation, or promotion. The 2026-10-06-and-later holdout remains
closed for model selection. A future target in that period may be scored only
from a genuinely pre-target sealed prospective vintage after its complete
target periods close and its source capture is reconciled.
