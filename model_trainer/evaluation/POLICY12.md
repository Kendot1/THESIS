# Policy 12: independent-horizon prospective promotion

This is the current admission policy for new 14-daily/4-full-week/1-full-month
candidate bundles. It supersedes policy 11 **before any real policy-11 package
was sealed**. The freeze/scorer schema and provenance review are described in
[the prospective guide](PROSPECTIVE_HORIZONS.md); no October 2026 legacy
30-day package can be retrofitted.

Before any first target date, selection must bind the exact
`ACCEPTANCE_CRITERIA` from `evaluation.prospective_freeze`, including policy
version 12, to a candidate model and matched validation forecast digest.
Every prospective vintage must be sealed with the actual clock before its
first daily target, and the three or more vintages must have non-reused full
monthly targets. After all target periods close, a reviewer must reconcile
source/actuals provenance and model replay. `ModelStore.activate` does not
change the pointer if any review, arithmetic, hash, or screen check fails.

Point accuracy still needs strict matched MAE/RMSE/MAPE improvement over both
incumbent and origin-known persistence, with no Within-PHP-5 regression,
pooled and per horizon in validation and prospective evidence. Equal-series
macro prospective performance must improve. Product/horizon and daily-lead
errors may not deteriorate more than 10% relative to the better reference.
At least two thirds of validation origins per horizon must win. Missing
series, sparse leads, or incomplete labels do not silently disappear.

Numeric 80%/95% product/horizon intervals require **both** 20 distinct
pre-selection target periods and 20 distinct forecast origins for that series
and horizon. This prevents a few overlapping daily paths from masquerading
as independent calibration experience. Less-supported series remain in every
point-accuracy comparison, but their numeric bounds must be absent and their
interval status is `limited_unavailable`. At least one series in **each**
horizon must have interval support; an all-unavailable candidate cannot pass
by skipping every uncertainty check.

For supported series, matched validation coverage must be at least 70% at
nominal 80% and 85% at nominal 95%. Pooled validation and prospective
horizon coverage must be at least 75%/90%, respectively, on at least 30
supported rows per horizon. Prospective daily product coverage is checked at
70%/85% where at least 30 supported rows exist. The screen records width in
PHP, and a reviewer must reject intervals too wide to be useful. These are
minimum admission screens, **not** claims that every product/lead is
calibrated to exactly 80% or 95%. Receipts call supported intervals
`historical_support_only`; independent prospective reliability remains to
be established and described with sample counts and widths.

The thresholds are predeclared before the new policy's first live vintage.
No candidate has passed this policy, no model was promoted, and the sealed
October 6-November 4 holdout remains unavailable until after November 5
Philippine time.
