"""Version-3 prospective evidence for independent 7/4/1 forecast targets.

This module never generates predictions or reads outcomes before the final
target period closes. Legacy 30-day contracts belong to frozen_holdout.py.
"""
import argparse
from collections import defaultdict
import json
import math
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from statistics import mean

from .frozen_holdout import (
    PHILIPPINE_TIME, calendar_date, csv_rows, digest, error_metrics,
    finite_number, relative_file, series_parts,
)

SCHEMA_VERSION = 3
TARGET_DEFINITION = "daily7_fullweek4_fullmonth1"
STEPS = {"daily": 7, "weekly": 4, "monthly": 1}
MIN_OBSERVED_DAYS = {"daily": 1, "weekly": 4, "monthly": 15}
INTERVAL_LEVELS = (80, 95)
CLOSED_HOLDOUT_START = date(2026, 10, 6)


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
            if prediction is None:
                raise ValueError("A missing forecast cannot carry prediction intervals")
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
                "prediction_status", "status_reason", "champion", "anchor"}
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
        status = row["prediction_status"].strip().lower()
        if status not in {"active", "fallback", "missing"}:
            raise ValueError("prediction_status must be active, fallback, or missing")
        reason = row["status_reason"].strip()
        if status in {"fallback", "missing"} and not reason:
            raise ValueError("Fallback and missing rows require a status_reason")
        if status == "missing":
            if row["prediction"].strip():
                raise ValueError("A missing forecast must have a blank prediction")
            prediction = None
        else:
            prediction = finite_number(row["prediction"])
            if prediction <= 0:
                raise ValueError("Forecast price must be positive")
        champion, anchor = finite_number(row["champion"]), finite_number(row["anchor"])
        if champion <= 0 or anchor <= 0:
            raise ValueError("Comparison prices must be positive")
        if status == "fallback" and prediction != anchor:
            raise ValueError("Locked fallback must equal origin-known persistence on the same key")
        intervals = validated_intervals(row, prediction)
        forecasts[key] = {"series": series, "origin": origin.isoformat(),
                          "forecast_horizon": horizon, "forecast_step": step,
                          "target_period_start": start.isoformat(),
                          "target_period_end": end.isoformat(),
                          "prediction": prediction, "champion": champion,
                          "anchor": anchor, "prediction_status": status,
                          "status_reason": reason, "intervals": intervals}
    expected = {(series, horizon, step) for series in declared
                for horizon, count in STEPS.items() for step in range(1, count + 1)}
    if set(forecasts) != expected or contract["forecast_rows"] != len(expected):
        raise ValueError("Each declared series must have exactly 7/4/1 targets")
    status_counts = {status: sum(row["prediction_status"] == status
                                 for row in forecasts.values())
                     for status in ("active", "fallback", "missing")}
    if contract.get("prediction_status_counts") != status_counts:
        raise ValueError("Frozen prediction status counts do not match forecast rows")
    return forecasts


def load_contract(path):
    """Check freeze, declared scope, hashes, and exact 7/4/1 target alignment."""
    path = Path(path)
    raw = path.read_bytes()
    contract = json.loads(raw)
    if (contract.get("schema_version") != SCHEMA_VERSION
            or contract.get("target_definition") != TARGET_DEFINITION
            or contract.get("holdout_type") != "prospective"):
        raise ValueError("Not a version-3 independent-horizon prospective contract")
    origin = calendar_date(contract["forecast_origin"])
    frozen_at = _timestamp(contract["forecasts_frozen_at_utc"])
    if frozen_at > datetime.now(timezone.utc):
        raise ValueError("Forecast freeze timestamp is in the future")
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
    excluded = contract.get("excluded_series", [])
    if (not isinstance(excluded, list)
            or any(not isinstance(item, dict) or not str(item.get("reason", "")).strip()
                   or not isinstance(item.get("series"), str) for item in excluded)
            or len({item["series"] for item in excluded}) != len(excluded)
            or set(declared) & {item["series"] for item in excluded}):
        raise ValueError("Excluded forecast input series require unique identities and reasons")
    for item in excluded:
        series_parts(item["series"])
    total_input_series = contract.get("total_input_series")
    if (type(total_input_series) is not int
            or total_input_series != len(declared) + len(excluded)):
        raise ValueError("Declared and excluded series do not reconcile to input scope")
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
    status_counts = contract["prediction_status_counts"]
    return contract, forecasts, {
        "contract_sha256": digest(raw), "forecast_sha256": digest(forecast_bytes),
        "model_metadata_sha256": contract.get("model_metadata_sha256"),
        "model_bundle_sha256": contract.get("model_bundle_sha256"),
        "evaluation_code_sha256": contract.get("evaluation_code_sha256"),
        "selection_sha256": contract.get("selection_sha256"),
        "forecast_input_snapshot_sha256": contract.get("forecast_input_snapshot_sha256"),
        "forecast_rows": len(forecasts), "forecast_series": len(declared),
        "active_prediction_count": status_counts["active"],
        "fallback_count": status_counts["fallback"],
        "missing_prediction_count": status_counts["missing"],
        "total_input_series": total_input_series,
        "excluded_series_count": len(excluded),
        "series_coverage": len(declared) / total_input_series,
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
    """Score only rows with a candidate point; references use that same key mask."""
    scored = [row for row in rows if row.get("prediction") is not None]
    result = {name: error_metrics(scored, name) for name in
              ("prediction", "champion", "anchor")}
    result["mean_signed_error_php"] = {
        name: (mean(row[name] - row["actual"] for row in scored) if scored else None)
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
        str(level): _interval_report(scored, level) for level in INTERVAL_LEVELS}
    result["prediction_status_counts"] = {
        status: sum(row.get("prediction_status") == status for row in rows)
        for status in ("active", "fallback", "missing")}
    result["expected_key_count"] = len(rows)
    result["metric_key_count"] = len(scored)
    return result


def _validate_actuals_provenance(manifest_path, manifest, integrity, *, now, includes_holdout):
    """Validate hash-bound reconciliation metadata before opening target rows."""
    required = {
        "data_file", "sha256", "row_count", "target_date_min", "target_date_max",
        "reconciled_through", "source", "is_observed_definition", "contract_sha256",
        "actuals_vintage_type", "reconciliation_manifest_file",
        "reconciliation_manifest_sha256",
    }
    if not required.issubset(manifest):
        raise ValueError(f"Actuals manifest lacks required metadata: {sorted(required - set(manifest))}")
    if (manifest.get("contract_sha256") != integrity["contract_sha256"]
            or not str(manifest.get("source", "")).strip()
            or not str(manifest.get("is_observed_definition", "")).strip()):
        raise ValueError("Actuals source, label rule, or sealed-contract binding is invalid")
    if type(manifest["row_count"]) is not int or manifest["row_count"] <= 0:
        raise ValueError("Actuals manifest requires a positive exact row count")
    first_day = calendar_date(integrity["first_target_day"])
    last_day = calendar_date(integrity["last_target_day"])
    target_min = calendar_date(manifest["target_date_min"])
    target_max = calendar_date(manifest["target_date_max"])
    if target_min > target_max or target_min < first_day or target_max > last_day:
        raise ValueError("Actuals manifest target-date range is outside the frozen forecast window")
    reconciled_through = calendar_date(manifest["reconciled_through"])
    if reconciled_through < last_day:
        raise ValueError("Actuals have not been reconciled through all target periods")
    vintage = manifest["actuals_vintage_type"]
    if includes_holdout:
        if vintage != "prospective":
            raise ValueError("Closed-holdout targets require a prospective actuals vintage")
    elif vintage not in {"historical_development", "prospective"}:
        raise ValueError("Actuals vintage must be historical_development or prospective")

    reconciliation_path = relative_file(manifest_path.parent, manifest["reconciliation_manifest_file"])
    reconciliation_bytes = reconciliation_path.read_bytes()
    if digest(reconciliation_bytes) != manifest["reconciliation_manifest_sha256"]:
        raise ValueError("Actuals reconciliation manifest SHA-256 mismatch")
    reconciliation = json.loads(reconciliation_bytes)
    if type(reconciliation.get("row_count")) is not int or reconciliation["row_count"] <= 0:
        raise ValueError("Reconciliation receipt requires a positive exact row count")
    expected_kind = ("prospective_actuals_reconciliation" if includes_holdout
                     else "historical_actuals_reconciliation"
                     if vintage == "historical_development"
                     else "prospective_actuals_reconciliation")
    if (reconciliation.get("schema_version") != 1
            or reconciliation.get("capture_kind") != expected_kind
            or reconciliation.get("promotion_or_selection_eligible") is not True):
        raise ValueError("Source-only or unapproved capture is not an actuals reconciliation")
    if (reconciliation.get("contract_sha256") != integrity["contract_sha256"]
            or reconciliation.get("actuals_file") != manifest["data_file"]
            or reconciliation.get("actuals_sha256") != manifest["sha256"]
            or reconciliation.get("row_count") != manifest["row_count"]
            or reconciliation.get("target_date_min") != manifest["target_date_min"]
            or reconciliation.get("target_date_max") != manifest["target_date_max"]
            or reconciliation.get("reconciled_through") != manifest["reconciled_through"]
            or reconciliation.get("source") != manifest["source"]):
        raise ValueError("Reconciliation receipt does not bind actuals, contract, and date scope")
    reconciled_at = _timestamp(reconciliation["reconciled_at_utc"])
    if reconciled_at > now or reconciled_at < _timestamp(integrity["period_closes_at"]):
        raise ValueError("Actuals reconciliation chronology is invalid")
    source_manifest_file = reconciliation.get("source_snapshot_manifest_file")
    source_manifest_sha = reconciliation.get("source_snapshot_manifest_sha256")
    source_snapshot_file = reconciliation.get("source_snapshot_file")
    source_snapshot_sha = reconciliation.get("source_snapshot_sha256")
    if (not source_manifest_file or not source_snapshot_file
            or not isinstance(source_manifest_sha, str) or len(source_manifest_sha) != 64
            or not isinstance(source_snapshot_sha, str) or len(source_snapshot_sha) != 64):
        raise ValueError("Reconciliation receipt lacks an immutable source-snapshot binding")
    source_manifest_path = relative_file(reconciliation_path.parent, source_manifest_file)
    source_manifest_bytes = source_manifest_path.read_bytes()
    if digest(source_manifest_bytes) != source_manifest_sha:
        raise ValueError("Reconciled source-snapshot manifest hash mismatch")
    source_manifest = json.loads(source_manifest_bytes)
    if (source_manifest.get("snapshot_sha256") != source_snapshot_sha
            or source_manifest.get("capture_kind") != expected_kind
            or source_manifest.get("promotion_or_selection_eligible") is not True
            or source_manifest.get("target_actuals_reconciled") is not True
            or calendar_date(source_manifest.get("report_date_max", "0001-01-01"))
                < calendar_date(integrity["last_target_day"])):
        raise ValueError("Source snapshot is not eligible or does not match the reconciliation receipt")
    source_captured_at = _timestamp(source_manifest["capture_ended_at_utc"])
    if (source_captured_at > now
            or source_captured_at < _timestamp(integrity["period_closes_at"])
            or source_captured_at > reconciled_at):
        raise ValueError("Actuals source capture chronology is invalid")
    source_snapshot_path = relative_file(reconciliation_path.parent, source_snapshot_file)
    if digest(source_snapshot_path.read_bytes()) != source_snapshot_sha:
        raise ValueError("Reconciled source-snapshot hash mismatch")
    return reconciliation, digest(reconciliation_bytes)


def score(contract_path, model_run_dir, actuals_manifest_path, *, include_rows=False):
    """Score verified closed targets; all provenance checks precede actual-row access."""
    contract_path, model_run_dir = Path(contract_path), Path(model_run_dir)
    contract, forecasts, integrity = load_contract(contract_path)
    from .prospective_freeze_v3 import verify_seal
    verify_seal(contract_path, model_run_dir)
    now = datetime.now(timezone.utc)
    if now < _timestamp(integrity["period_closes_at"]):
        raise ValueError("Target periods remain open; actuals manifest was not opened")

    manifest_path = Path(actuals_manifest_path)
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    end = calendar_date(integrity["last_target_day"])
    target_dates = [calendar_date(row["target_period_end"]) for row in forecasts.values()]
    includes_closed_holdout = any(target >= CLOSED_HOLDOUT_START for target in target_dates)
    reconciliation, reconciliation_sha = _validate_actuals_provenance(
        manifest_path, manifest, integrity, now=now,
        includes_holdout=includes_closed_holdout)

    # Actual row data is opened only after contract, clock, closure, and manifest checks.
    actual_path = relative_file(manifest_path.parent, manifest["data_file"])
    actual_bytes = actual_path.read_bytes()
    if digest(actual_bytes) != manifest["sha256"]:
        raise ValueError("Actuals SHA-256 mismatch")
    origin = calendar_date(contract["forecast_origin"])
    declared = set(contract["declared_series"])
    actuals, seen = {}, set()
    counts = {"unobserved_rows": 0, "outside_window_rows": 0, "outside_scope_rows": 0}
    actual_rows = list(csv_rows(actual_bytes, {"series", "target_date", "actual", "is_observed"}))
    actual_dates = [calendar_date(row["target_date"]) for row in actual_rows]
    if (len(actual_rows) != manifest["row_count"] or not actual_dates
            or min(actual_dates).isoformat() != manifest["target_date_min"]
            or max(actual_dates).isoformat() != manifest["target_date_max"]):
        raise ValueError("Actuals rows differ from the trusted count/date-range manifest")
    if any(target < calendar_date(integrity["first_target_day"])
           or target > end for target in actual_dates):
        raise ValueError("Actuals rows contain dates outside the frozen target window")
    for row in actual_rows:
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

    matched, missing = [], defaultdict(int)
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
              ("horizon", "series", "product", "horizon_step", "daily_lead", "origin",
               "horizon_origin")}
    for row in matched:
        category, product, _, _, _ = series_parts(row["series"])
        labels = {"horizon": row["forecast_horizon"], "series": row["series"],
                  "product": f"{category}||{product}",
                  "horizon_step": f"{row['forecast_horizon']}:{row['forecast_step']}",
                  "daily_lead": str(row["forecast_step"])
                  if row["forecast_horizon"] == "daily" else None,
                  "origin": row["origin"],
                  "horizon_origin": f"{row['forecast_horizon']}:{row['origin']}"}
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

    all_target_keys = [
        {"series": row["series"], "origin": row["origin"],
         "forecast_horizon": row["forecast_horizon"], "forecast_step": row["forecast_step"],
         "target_period_start": row["target_period_start"],
         "target_period_end": row["target_period_end"],
         "prediction_status": row["prediction_status"]}
        for row in sorted(forecasts.values(), key=lambda item: (
            item["series"], item["forecast_horizon"], item["forecast_step"]))]
    report = {"schema_version": SCHEMA_VERSION, "model_run_id": contract["model_run_id"],
            "target_definition": TARGET_DEFINITION,
            "scored_at_utc": now.astimezone(timezone.utc).isoformat(),
            "integrity": integrity,
            "actuals_manifest_sha256": digest(manifest_bytes),
            "actuals_sha256": digest(actual_bytes),
            "actuals_reconciliation_manifest_sha256": reconciliation_sha,
            "actuals_reconciliation_kind": reconciliation["capture_kind"],
            "actuals_source_snapshot_sha256": reconciliation["source_snapshot_sha256"],
            "actuals_source_snapshot_manifest_sha256": reconciliation["source_snapshot_manifest_sha256"],
            "actuals_source": manifest["source"],
            "reconciled_through": manifest["reconciled_through"],
            "overall": _summary(matched),
            "macro_equal_product": {"n_products": len(product_reports), **macro},
            "groups": {name: {label: _summary(block) for label, block in sorted(blocks.items())}
                       for name, blocks in groups.items()},
            "forecast_keys": all_target_keys,
            "coverage": {"expected_forecast_count": len(forecasts),
                         "forecast_rows": len(forecasts),
                         "target_matched_rows": len(matched),
                         "total_input_series": integrity["total_input_series"],
                         "forecast_series": integrity["forecast_series"],
                         "excluded_series": contract.get("excluded_series", []),
                         "excluded_series_count": integrity["excluded_series_count"],
                         "series_coverage": integrity["series_coverage"],
                         "missing_target_rows_by_horizon": dict(sorted(missing.items())),
                         "active_prediction_count": contract["prediction_status_counts"]["active"],
                         "fallback_count": contract["prediction_status_counts"]["fallback"],
                         "missing_prediction_count": contract["prediction_status_counts"]["missing"],
                         "missing_prediction_keys": [key for key in all_target_keys
                                                     if key["prediction_status"] == "missing"],
                         "metric_rows_with_prediction": sum(
                             row["prediction"] is not None for row in matched),
                         **counts},
            "label_rule": "Observed original-PHP daily price; full calendar weeks require >=4 observed days, full calendar month >=15; no imputation. Near-zero actuals are excluded only from MAPE, with counts reported.",
            "promotion_decision": "Not determined by scores alone; provenance and selection independence require separate review."}
    if include_rows:
        report["matched_rows"] = matched
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", type=Path)
    parser.add_argument("model_run_dir", type=Path)
    parser.add_argument("actuals_manifest", type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(score(args.contract, args.model_run_dir, args.actuals_manifest),
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
