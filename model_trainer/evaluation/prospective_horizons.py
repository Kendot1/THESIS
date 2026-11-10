"""Version-2 prospective evidence for independent 14/4/1 forecast targets.

This module never generates predictions or reads outcomes before the final
target period closes. Legacy 30-day contracts belong to frozen_holdout.py.
"""
import argparse
from collections import defaultdict
import json
import math
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from statistics import mean

from .frozen_holdout import (
    PHILIPPINE_TIME, calendar_date, csv_rows, digest, error_metrics,
    finite_number, relative_file, series_parts,
)

SCHEMA_VERSION = 2
TARGET_DEFINITION = "daily14_fullweek4_fullmonth1"
STEPS = {"daily": 14, "weekly": 4, "monthly": 1}
MIN_OBSERVED_DAYS = {"daily": 1, "weekly": 4, "monthly": 15}
INTERVAL_LEVELS = (80, 95)


def _timestamp(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Evidence timestamps require a timezone")
    return parsed


def _month_start_after(origin):
    return origin.replace(day=1, month=origin.month % 12 + 1,
                          year=origin.year + (origin.month == 12))


def _month_end(start):
    return _month_start_after(start) - timedelta(days=1)


def target_bounds(origin, horizon, step):
    """Return the full, non-overlapping target period for one published step."""
    if horizon not in STEPS or type(step) is not int or not 1 <= step <= STEPS[horizon]:
        raise ValueError("Unsupported horizon or forecast step")
    if horizon == "daily":
        start = origin + timedelta(days=step)
        return start, start
    if horizon == "weekly":
        start = origin + timedelta(days=7 - origin.weekday() + 7 * (step - 1))
        return start, start + timedelta(days=6)
    start = _month_start_after(origin)
    return start, _month_end(start)


def validated_intervals(row, prediction):
    """Parse supported nominal bounds without inventing missing intervals."""
    intervals = {}
    for level in INTERVAL_LEVELS:
        low, high = f"lower_{level}", f"upper_{level}"
        if low not in row and high not in row:
            continue
        if bool(row.get(low)) != bool(row.get(high)):
            raise ValueError("Prediction interval requires both bounds")
        if row.get(low):
            lower, upper = finite_number(row[low]), finite_number(row[high])
            if lower < 0 or upper < lower or not lower <= prediction <= upper:
                raise ValueError("Invalid prediction interval bounds")
            intervals[level] = (lower, upper)
    if 80 in intervals and 95 in intervals:
        if not (intervals[95][0] <= intervals[80][0]
                and intervals[80][1] <= intervals[95][1]):
            raise ValueError("Nominal 95% interval must contain the 80% interval")
    return intervals


def _validated_forecast_rows(contract, forecast_bytes):
    """Validate the complete typed forecast population without reading actuals."""
    origin = calendar_date(contract["forecast_origin"])
    declared = contract["declared_series"]
    required = {"series", "origin", "forecast_horizon", "forecast_step",
                "target_period_start", "target_period_end", "prediction",
                "champion", "anchor"}
    forecasts = {}
    declared_set = set(declared)
    for row in csv_rows(forecast_bytes, required):
        series = row["series"]
        if series not in declared_set or calendar_date(row["origin"]) != origin:
            raise ValueError("Forecast series or origin differs from frozen scope")
        horizon = row["forecast_horizon"]
        try:
            step = int(row["forecast_step"])
        except ValueError as exc:
            raise ValueError("Invalid forecast step") from exc
        if str(step) != row["forecast_step"]:
            raise ValueError("Forecast step must be a canonical positive integer")
        start, end = target_bounds(origin, horizon, step)
        if (calendar_date(row["target_period_start"]) != start
                or calendar_date(row["target_period_end"]) != end):
            raise ValueError("Forecast target period differs from the full published period")
        key = (series, horizon, step)
        if key in forecasts:
            raise ValueError("Duplicate frozen series/horizon/step")
        values = {name: finite_number(row[name]) for name in
                  ("prediction", "champion", "anchor")}
        if any(value <= 0 for value in values.values()):
            raise ValueError("Forecast and comparison prices must be positive")
        intervals = validated_intervals(row, values["prediction"])
        forecasts[key] = {"series": series, "origin": origin.isoformat(),
                          "forecast_horizon": horizon, "forecast_step": step,
                          "target_period_start": start.isoformat(),
                          "target_period_end": end.isoformat(), **values,
                          "intervals": intervals}
    expected = {(series, horizon, step) for series in declared
                for horizon, count in STEPS.items() for step in range(1, count + 1)}
    if set(forecasts) != expected or contract["forecast_rows"] != len(expected):
        raise ValueError("Each declared series must have exactly 14/4/1 targets")
    return forecasts


def load_contract(path):
    """Check freeze, declared scope, hashes, and exact 14/4/1 target alignment."""
    path = Path(path)
    raw = path.read_bytes()
    contract = json.loads(raw)
    if (contract.get("schema_version") != SCHEMA_VERSION
            or contract.get("target_definition") != TARGET_DEFINITION
            or contract.get("holdout_type") != "prospective"):
        raise ValueError("Not a version-2 independent-horizon prospective contract")
    origin = calendar_date(contract["forecast_origin"])
    frozen_at = _timestamp(contract["forecasts_frozen_at_utc"])
    first_day = origin + timedelta(days=1)
    deadline = datetime.combine(first_day, time.min, PHILIPPINE_TIME)
    if frozen_at >= deadline:
        raise ValueError("Forecasts were not frozen before the first target day")
    declared = contract["declared_series"]
    if (not isinstance(declared, list) or not declared
            or len(set(declared)) != len(declared)):
        raise ValueError("Contract requires a unique, nonempty declared series scope")
    for series in declared:
        series_parts(series)
    if not str(contract.get("model_run_id", "")).strip():
        raise ValueError("A model run ID is required")
    forecast_path = relative_file(path.parent, contract["forecast_file"])
    forecast_bytes = forecast_path.read_bytes()
    if digest(forecast_bytes) != contract["forecast_sha256"]:
        raise ValueError("Frozen forecast SHA-256 mismatch")
    forecasts = _validated_forecast_rows(contract, forecast_bytes)
    last_day = max(target_bounds(origin, horizon, step)[1]
                   for horizon, count in STEPS.items() for step in range(1, count + 1))
    close = datetime.combine(last_day + timedelta(days=1), time.min, PHILIPPINE_TIME)
    return contract, forecasts, {
        "contract_sha256": digest(raw), "forecast_sha256": digest(forecast_bytes),
        "forecast_rows": len(forecasts), "forecast_series": len(declared),
        "first_target_day": first_day.isoformat(), "last_target_day": last_day.isoformat(),
        "period_closes_at": close.isoformat(), "frozen_before_first_target_day": True,
    }


def _interval_report(rows, level):
    supported = [row for row in rows if level in row["intervals"]]
    if not supported:
        return {"n": 0, "nominal_level_pct": level, "empirical_coverage_pct": None,
                "mean_width_php": None}
    hits = sum(row["intervals"][level][0] <= row["actual"] <= row["intervals"][level][1]
               for row in supported)
    width = mean(row["intervals"][level][1] - row["intervals"][level][0]
                 for row in supported)
    return {"n": len(supported), "nominal_level_pct": level,
            "empirical_coverage_pct": 100 * hits / len(supported), "mean_width_php": width}


def _summary(rows):
    result = {name: error_metrics(rows, name) for name in
              ("prediction", "champion", "anchor")}
    result["mean_signed_error_php"] = {
        name: (mean(row[name] - row["actual"] for row in rows) if rows else None)
        for name in ("prediction", "champion", "anchor")}
    result["error_reduction_pct"] = {
        baseline: {
            metric: ((reference[metric] - result["prediction"][metric])
                     / reference[metric] * 100
                     if reference[metric] not in (None, 0)
                     and result["prediction"][metric] is not None else None)
            for metric in ("mae", "rmse", "mape")}
        for baseline, reference in ((name, result[name]) for name in ("champion", "anchor"))}
    result["prediction_intervals"] = {
        str(level): _interval_report(rows, level) for level in INTERVAL_LEVELS}
    return result


def score(contract_path, actuals_manifest_path, *, now=None, include_rows=False):
    """Score observed targets after all three horizons close; never fill labels."""
    contract, forecasts, integrity = load_contract(contract_path)
    now = datetime.now(timezone.utc) if now is None else now
    if now.tzinfo is None:
        raise ValueError("Scoring clock requires a timezone")
    if now < _timestamp(integrity["period_closes_at"]):
        raise ValueError("Holdout still open; actuals manifest was not opened")
    manifest_path = Path(actuals_manifest_path)
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    end = calendar_date(integrity["last_target_day"])
    if calendar_date(manifest["reconciled_through"]) < end:
        raise ValueError("Actuals have not been reconciled through all target periods")
    if not manifest.get("source") or not manifest.get("is_observed_definition"):
        raise ValueError("Actuals source and observed-label definition are required")
    actual_path = relative_file(manifest_path.parent, manifest["data_file"])
    actual_bytes = actual_path.read_bytes()
    if digest(actual_bytes) != manifest["sha256"]:
        raise ValueError("Actuals SHA-256 mismatch")
    origin = calendar_date(contract["forecast_origin"])
    declared = set(contract["declared_series"])
    actuals, seen = {}, set()
    counts = {"unobserved_rows": 0, "outside_window_rows": 0, "outside_scope_rows": 0}
    for row in csv_rows(actual_bytes, {"series", "target_date", "actual", "is_observed"}):
        series_parts(row["series"])
        target = calendar_date(row["target_date"])
        if not origin < target <= end:
            counts["outside_window_rows"] += 1
            continue
        key = row["series"], target
        if key in seen:
            raise ValueError("Duplicate actual series/date; reconcile source first")
        seen.add(key)
        if row["series"] not in declared:
            counts["outside_scope_rows"] += 1
            continue
        flag = row["is_observed"].strip().lower()
        if flag in {"false", "0"}:
            counts["unobserved_rows"] += 1
            continue
        if flag not in {"true", "1"}:
            raise ValueError("is_observed must be true/false or 1/0")
        value = finite_number(row["actual"])
        if value < 0:
            raise ValueError("Observed prices must be nonnegative")
        actuals[key] = value
    matched = []
    missing = defaultdict(int)
    for key, forecast in sorted(forecasts.items()):
        start = calendar_date(forecast["target_period_start"])
        period_end = calendar_date(forecast["target_period_end"])
        days = (period_end - start).days + 1
        values = [actuals[(key[0], start + timedelta(days=offset))]
                  for offset in range(days)
                  if (key[0], start + timedelta(days=offset)) in actuals]
        if len(values) < MIN_OBSERVED_DAYS[key[1]]:
            missing[key[1]] += 1
            continue
        matched.append({**forecast, "actual": math.fsum(values) / len(values),
                        "observed_days": len(values), "period_days": days})
    if not matched:
        raise ValueError("No sufficiently observed target matches a frozen forecast")
    groups = {name: defaultdict(list) for name in
              ("horizon", "series", "product", "horizon_step", "daily_half")}
    for row in matched:
        category, product, _, _, _ = series_parts(row["series"])
        labels = {"horizon": row["forecast_horizon"], "series": row["series"],
                  "product": f"{category}||{product}",
                  "horizon_step": f"{row['forecast_horizon']}:{row['forecast_step']}",
                  "daily_half": ("01-07" if row["forecast_step"] <= 7 else "08-14")
                  if row["forecast_horizon"] == "daily" else None}
        for name, label in labels.items():
            if label is not None:
                groups[name][label].append(row)
    product_reports = [_summary(rows) for rows in groups["product"].values()]
    macro = {}
    for reference in ("prediction", "champion", "anchor"):
        macro[reference] = {}
        for metric in ("mae", "rmse", "mape"):
            values = [report[reference][metric] for report in product_reports
                      if report[reference][metric] is not None]
            macro[reference][metric] = mean(values) if values else None
    report = {"schema_version": SCHEMA_VERSION, "model_run_id": contract["model_run_id"],
            "target_definition": TARGET_DEFINITION,
            "scored_at_utc": now.astimezone(timezone.utc).isoformat(),
            "integrity": integrity,
            "actuals_manifest_sha256": digest(manifest_bytes),
            "actuals_sha256": digest(actual_bytes),
            "actuals_source": manifest["source"],
            "reconciled_through": manifest["reconciled_through"],
            "overall": _summary(matched),
            "macro_equal_product": {"n_products": len(product_reports), **macro},
            "groups": {name: {label: _summary(rows) for label, rows in sorted(blocks.items())}
                       for name, blocks in groups.items()},
            "coverage": {"forecast_rows": len(forecasts), "scored_rows": len(matched),
                         "missing_target_rows_by_horizon": dict(sorted(missing.items())),
                         **counts},
            "label_rule": "Observed original-PHP daily price; full calendar weeks require >=4 observed days, full calendar month >=15; no imputation. Near-zero actuals are excluded only from MAPE, with counts reported.",
            "promotion_decision": "Not determined by scores alone; provenance and selection independence require separate review."}
    if include_rows:
        report["matched_rows"] = matched
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", type=Path)
    parser.add_argument("actuals_manifest", type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(score(args.contract, args.actuals_manifest), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
