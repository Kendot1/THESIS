"""Predeclared policy-12 metric screen for matched 14/4/1 evidence."""
from collections import defaultdict
from statistics import mean

from .prospective_freeze import ACCEPTANCE_CRITERIA
from .prospective_horizons import STEPS, _summary

ERRORS = ("mae", "rmse", "mape")


def _better(summary):
    candidate = summary["prediction"]
    for reference_name in ("champion", "anchor"):
        reference = summary[reference_name]
        if (any(candidate[metric] is None or reference[metric] is None
                or candidate[metric] >= reference[metric] for metric in ERRORS)
                or candidate["within_5_php_accuracy_pct"] is None
                or reference["within_5_php_accuracy_pct"] is None
                or candidate["within_5_php_accuracy_pct"]
                    < reference["within_5_php_accuracy_pct"]):
            return False
    return True


def _intervals(summary, label):
    for level, minimum in ((80, ACCEPTANCE_CRITERIA["minimum_interval_coverage_80_pct"]),
                           (95, ACCEPTANCE_CRITERIA["minimum_interval_coverage_95_pct"])):
        item = summary["prediction_intervals"][str(level)]
        if (item["n"] < ACCEPTANCE_CRITERIA["minimum_interval_rows_per_horizon"]
                or item["empirical_coverage_pct"] is None
                or item["empirical_coverage_pct"] < minimum
                or item["mean_width_php"] is None):
            raise ValueError(f"Insufficient or undercovered {level}% intervals: {label}")


def _macro(rows):
    series = defaultdict(list)
    for row in rows:
        series[row["series"]].append(row)
    reports = [_summary(block) for block in series.values()]
    macro = {}
    for reference in ("prediction", "champion", "anchor"):
        macro[reference] = {}
        for metric in ERRORS:
            values = [report[reference][metric] for report in reports]
            macro[reference][metric] = mean(values) if all(v is not None for v in values) else None
        values = [report[reference]["within_5_php_accuracy_pct"] for report in reports]
        macro[reference]["within_5_php_accuracy_pct"] = (
            mean(values) if all(v is not None for v in values) else None)
    return macro


def _regressions(report, maximum_pct):
    regressions = []
    for metric in ERRORS:
        candidate = report["prediction"][metric]
        references = [report[name][metric] for name in ("champion", "anchor")]
        if candidate is None or any(value is None for value in references):
            regressions.append(metric)
            continue
        best = min(references)
        if candidate > best * (1 + maximum_pct / 100):
            regressions.append(metric)
    return regressions


def screen(validation, final_rows, declared_series):
    """Reject unqualified accuracy, product, lead, or interval evidence."""
    if not final_rows or not _better(validation["overall"]):
        raise ValueError("Validation pooled candidate fails matched references")
    if any(validation["missing_selected_series_by_horizon"].values()):
        raise ValueError("Validation lacks a selected series/horizon")
    supported, limited = set(), set()
    for label, report in validation["groups"]["series_horizon"].items():
        periods = validation["target_periods_by_series_horizon"].get(label, 0)
        origins = validation["origins_by_series_horizon"].get(label, 0)
        if (periods < ACCEPTANCE_CRITERIA["minimum_product_interval_validation_periods"]
                or origins < ACCEPTANCE_CRITERIA["minimum_product_interval_validation_origins"]):
            limited.add(label)
            if any(report["prediction_intervals"][str(level)]["n"] for level in (80, 95)):
                raise ValueError(f"Unsupported numeric product-level intervals: {label}")
        else:
            supported.add(label)
            for level, minimum in (
                (80, ACCEPTANCE_CRITERIA["minimum_product_interval_coverage_80_pct"]),
                (95, ACCEPTANCE_CRITERIA["minimum_product_interval_coverage_95_pct"]),
            ):
                item = report["prediction_intervals"][str(level)]
                if (item["n"] != report["prediction"]["n"]
                        or item["empirical_coverage_pct"] < minimum):
                    raise ValueError(f"Product-level validation interval undercoverage: {label}")
        if _regressions(report, ACCEPTANCE_CRITERIA["maximum_product_error_deterioration_pct"]):
            raise ValueError(f"Validation product/horizon regression: {label}")
    for horizon in STEPS:
        block = validation["groups"]["horizon"].get(horizon)
        if block is None or not _better(block):
            raise ValueError(f"Validation horizon does not improve: {horizon}")
        if not any(label.endswith(f"::{horizon}") for label in supported):
            raise ValueError(f"No interval-supported validation series for {horizon}")
        if any(label.endswith(f"::{horizon}") for label in supported):
            _intervals(block, f"validation {horizon}")
        origin_blocks = [report for label, report in
                         validation["groups"]["horizon_origin"].items()
                         if label.startswith(f"{horizon}:")]
        wins = sum(_better(report) for report in origin_blocks)
        if wins * 3 < len(origin_blocks) * 2:
            raise ValueError(f"Validation gains are unstable across {horizon} origins")
    by_horizon = defaultdict(list)
    by_series_horizon = defaultdict(list)
    by_daily_lead = defaultdict(list)
    for row in final_rows:
        horizon = row["forecast_horizon"]
        status = f"{row['series']}::{horizon}"
        intervals = row["intervals"]
        if status in supported and set(intervals) != {80, 95}:
            raise ValueError(f"Missing supported product-level intervals: {status}")
        if status in limited and intervals:
            raise ValueError(f"Unsupported numeric product-level intervals: {status}")
        by_horizon[horizon].append(row)
        by_series_horizon[(row["series"], horizon)].append(row)
        if horizon == "daily":
            by_daily_lead[row["forecast_step"]].append(row)
    origins = {row["origin"] for row in final_rows}
    if len(origins) < ACCEPTANCE_CRITERIA["minimum_prospective_origins"]:
        raise ValueError("Fewer than three independent prospective origins")
    if any((series, horizon) not in by_series_horizon
           for series in declared_series for horizon in STEPS):
        raise ValueError("Prospective evidence lacks a declared series/horizon")
    overall = _summary(final_rows)
    if not _better(overall):
        raise ValueError("Prospective pooled candidate fails matched references")
    horizons = {}
    for horizon in STEPS:
        rows = by_horizon[horizon]
        report = _summary(rows)
        if not _better(report) or not _better(_macro(rows)):
            raise ValueError(f"Prospective {horizon} or equal-series macro metrics regress")
        if any(label.endswith(f"::{horizon}") for label in supported):
            _intervals(report, f"prospective {horizon}")
        horizons[horizon] = report
    product_regressions = []
    for (series, horizon), rows in sorted(by_series_horizon.items()):
        if len(rows) < 3:
            raise ValueError(f"Too few prospective outcomes for {series} {horizon}")
        report = _summary(rows)
        metrics = _regressions(report,
                               ACCEPTANCE_CRITERIA["maximum_product_error_deterioration_pct"])
        if metrics:
            product_regressions.append((series, horizon, len(rows), metrics))
        if f"{series}::{horizon}" in supported and horizon == "daily" and len(rows) >= 30:
            for level, minimum in (
                (80, ACCEPTANCE_CRITERIA["minimum_product_interval_coverage_80_pct"]),
                (95, ACCEPTANCE_CRITERIA["minimum_product_interval_coverage_95_pct"]),
            ):
                item = report["prediction_intervals"][str(level)]
                if item["n"] != len(rows) or item["empirical_coverage_pct"] < minimum:
                    raise ValueError(f"Product daily {level}% interval undercoverage: {series}")
    if product_regressions:
        raise ValueError(f"Unacceptable product/horizon MAE regressions: {product_regressions[:5]}")
    lead_regressions = []
    for lead in range(1, STEPS["daily"] + 1):
        rows = by_daily_lead[lead]
        if len(rows) < ACCEPTANCE_CRITERIA["minimum_interval_rows_per_horizon"]:
            raise ValueError(f"Too few prospective observations for daily lead {lead}")
        report = _summary(rows)
        metrics = _regressions(report,
                               ACCEPTANCE_CRITERIA["maximum_daily_lead_error_deterioration_pct"])
        if metrics:
            lead_regressions.append((lead, metrics))
    if lead_regressions:
        raise ValueError(f"Daily lead MAE regressions: {lead_regressions}")
    return {"passed": True, "criteria": ACCEPTANCE_CRITERIA,
            "prospective_origins": len(origins), "overall": overall,
            "horizons": horizons, "equal_series_macro": {
                horizon: _macro(by_horizon[horizon]) for horizon in STEPS},
            "interval_reliability_by_series_horizon": {
                label: ("historical_support_only" if label in supported
                        else "limited_unavailable")
                for label in sorted(supported | limited)}}
