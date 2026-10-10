"""Score sealed forecasts once a complete, reconciled observation period exists.

This module uses only the standard library. It neither regenerates predictions
nor trains, selects, activates, or modifies a model. Actuals must be exported as
canonical series/date observations, with an explicit observed/imputed flag.
"""
import argparse
import csv
import hashlib
import io
import json
import math
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path
from statistics import mean

PHILIPPINE_TIME = timezone(timedelta(hours=8))
METRICS = ("mae", "rmse", "mape")
PERCENTAGE_ACTUAL_FLOOR = 1e-8
WITHIN_10_TARGET_PERCENT = 90.0


def digest(data):
    return hashlib.sha256(data).hexdigest()


def relative_file(parent, name):
    child = (parent / name).resolve()
    if Path(name).is_absolute() or not child.is_relative_to(parent.resolve()):
        raise ValueError("Input filenames must stay inside their manifest directory")
    return child


def calendar_date(value):
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("Calendar dates must use YYYY-MM-DD")
    return parsed


def finite_number(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Nonfinite price")
    return result


def series_parts(series):
    parts = series.split("||")
    if len(parts) != 5 or any(not part.strip() for part in parts):
        raise ValueError("Series must contain category, product, variant, origin, and unit")
    return parts


def csv_rows(data, required):
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
    if not required.issubset(reader.fieldnames or []):
        raise ValueError(f"CSV requires columns {sorted(required)}")
    if len(reader.fieldnames) != len(set(reader.fieldnames)):
        raise ValueError("Duplicate CSV column names")
    for row in reader:
        if None in row or any(row[key] is None for key in required):
            raise ValueError("Malformed CSV row")
        yield row


def load_contract(path):
    path = Path(path)
    contract_bytes = path.read_bytes()
    contract = json.loads(contract_bytes)
    origin = calendar_date(contract["forecast_origin"])
    start, end = map(calendar_date, (contract["holdout_start"], contract["holdout_end"]))
    horizon = contract["horizon_days"]
    if (type(horizon) is not int or horizon <= 0 or start != origin + timedelta(days=1)
            or end != origin + timedelta(days=horizon)):
        raise ValueError("Contract origin, target dates, and horizon disagree")
    frozen_at = datetime.fromisoformat(contract["forecasts_frozen_at_utc"])
    if frozen_at.tzinfo is None:
        raise ValueError("Freeze timestamp must include a timezone")
    forecast_path = relative_file(path.parent, contract["forecast_file"])
    forecast_bytes = forecast_path.read_bytes()
    if digest(forecast_bytes) != contract["forecast_sha256"]:
        raise ValueError("Frozen forecast SHA-256 mismatch")
    forecasts = {}
    by_series = defaultdict(set)
    required = {"series", "origin", "target_date", "horizon", "anchor", "prediction"}
    for row in csv_rows(forecast_bytes, required):
        series_parts(row["series"])
        target = calendar_date(row["target_date"])
        step = int(row["horizon"])
        if (calendar_date(row["origin"]) != origin or not 1 <= step <= horizon
                or target != origin + timedelta(days=step)):
            raise ValueError("Forecast row origin/date/horizon mismatch")
        key = (row["series"], target)
        if key in forecasts:
            raise ValueError("Duplicate frozen series/date forecast")
        point, anchor = [finite_number(row[name]) for name in ("prediction", "anchor")]
        if anchor <= 0 or point <= 0:
            raise ValueError("Invalid forecast anchor or point prediction")
        forecasts[key] = {"series": row["series"], "target_date": target.isoformat(),
                          "horizon": step, "prediction": point, "anchor": anchor}
        by_series[row["series"]].add(step)
    if not forecasts or any(steps != set(range(1, horizon + 1)) for steps in by_series.values()):
        raise ValueError("Every frozen series must have the full forecast horizon")
    if len(forecasts) != contract["forecast_rows"] or len(by_series) != contract["forecast_series"]:
        raise ValueError("Frozen forecast counts disagree with the contract")
    skipped = [item["series"] for item in contract["skipped_series"]]
    for series in skipped:
        series_parts(series)
    total = contract["total_input_series"]
    if (len(set(skipped)) != len(skipped) or set(skipped) & set(by_series)
            or len(skipped) != contract["skipped_series_count"]
            or total != len(by_series) + len(skipped)
            or not math.isclose(contract["series_coverage"], len(by_series) / total)):
        raise ValueError("Forecast and skipped-series population does not reconcile")
    close = datetime.combine(end + timedelta(days=1), time.min, PHILIPPINE_TIME)
    return contract, forecasts, {
        "contract_sha256": digest(contract_bytes), "forecast_sha256": digest(forecast_bytes),
        "forecast_rows": len(forecasts), "forecast_series": len(by_series),
        "total_input_series": total, "series_coverage": len(by_series) / total,
        "period_closes_at": close.isoformat(),
        "frozen_before_first_target_day": frozen_at <= datetime.combine(start, time.min, PHILIPPINE_TIME),
    }


def error_metrics(rows, column="prediction"):
    if not rows:
        return {"n": 0, "percentage_n": 0, "excluded_near_zero": 0,
                "within_10_count": 0, "within_10_accuracy_pct": None,
                "mae": None, "rmse": None, "mape": None}
    errors = [abs(row[column] - row["actual"]) for row in rows]
    percentage_rows = [row for row in rows
                       if row["actual"] >= PERCENTAGE_ACTUAL_FLOOR]
    percentage_errors = [abs(row[column] - row["actual"]) / row["actual"]
                         for row in percentage_rows]
    within_10_count = sum(error <= 0.10 for error in percentage_errors)
    metrics = {"n": len(rows), "mae": math.fsum(errors) / len(rows),
               "rmse": math.hypot(*errors) / math.sqrt(len(rows)),
               "mape": (math.fsum(percentage_errors) * 100 / len(percentage_errors)
                        if percentage_errors else None),
               "percentage_n": len(percentage_rows),
               "excluded_near_zero": len(rows) - len(percentage_rows),
               "within_10_count": within_10_count,
               "within_10_accuracy_pct": (
                   within_10_count * 100 / len(percentage_rows) if percentage_rows else None)}
    if any(metrics[key] is not None and not math.isfinite(metrics[key]) for key in METRICS):
        raise ValueError("Error metric overflow; reconcile price units and values")
    return metrics


def summarize(rows):
    return error_metrics(rows)


def _period_bounds(target, horizon):
    if horizon == "weekly":
        start = target - timedelta(days=target.weekday())
        return start, start + timedelta(days=6)
    start = target.replace(day=1)
    next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return start, next_month - timedelta(days=1)


def _round_price(value):
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN))


def _mean_price(values):
    values = [Decimal(str(value)) for value in values]
    if not values:
        raise ValueError("Cannot average an empty price period")
    return float((sum(values, Decimal("0")) / len(values)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_EVEN))


def _timeframe_rows(forecasts, actuals):
    """Build published Daily/Weekly/Monthly rows from each frozen 30-day path."""
    result = {name: [] for name in ("daily", "weekly", "monthly")}
    by_series = defaultdict(list)
    for forecast in forecasts.values():
        series = forecast["series"]
        target = date.fromisoformat(forecast["target_date"])
        actual = actuals.get((series, target))
        result["daily"].append({
            "series": series, "actual": actual,
            "prediction": _round_price(forecast["prediction"]),
            "anchor": _round_price(forecast["anchor"]),
            "step": forecast["horizon"], "target_date": target.isoformat(),
            "covered_days": 1, "observed_days": int(actual is not None),
            "period_days": 1, "partial_period": False,
        })
        by_series[series].append((target, forecast))

    for series, path in by_series.items():
        path.sort(key=lambda pair: pair[0])
        for timeframe in ("weekly", "monthly"):
            periods = defaultdict(list)
            for target, forecast in path:
                bounds = _period_bounds(target, timeframe)
                periods[bounds].append((target, forecast))
            for step, ((start, end), period) in enumerate(sorted(periods.items()), start=1):
                observed = [actuals[(series, target)] for target, _ in period
                            if (series, target) in actuals]
                covered_days = len(period)
                period_days = (end - start).days + 1
                published_daily = [_round_price(forecast["prediction"])
                                   for _, forecast in period]
                published_anchor = [_round_price(forecast["anchor"])
                                    for _, forecast in period]
                prediction = _mean_price(published_daily)
                anchor = _mean_price(published_anchor)
                result[timeframe].append({
                    "series": series,
                    "actual": mean(observed) if observed else None,
                    "prediction": prediction, "anchor": anchor, "step": step,
                    "target_date": max(target for target, _ in period).isoformat(),
                    "target_period_start": start.isoformat(),
                    "target_period_end": end.isoformat(),
                    "covered_days": covered_days, "observed_days": len(observed),
                    "period_days": period_days,
                    "partial_period": (covered_days < period_days or
                                       len(observed) < covered_days),
                })
    return result


def _targets_met(metrics):
    return (
        metrics["within_10_accuracy_pct"] is not None
        and metrics["within_10_accuracy_pct"] >= WITHIN_10_TARGET_PERCENT
        and all(metrics[name] is not None and metrics[name] <= 5 for name in METRICS)
    )


def _timeframe_report(expected_rows):
    scored = [row for row in expected_rows if row["actual"] is not None]
    by_product, by_series, by_step = defaultdict(list), defaultdict(list), defaultdict(list)
    by_series_step = defaultdict(lambda: defaultdict(list))
    for row in scored:
        category, product, _, _, _ = series_parts(row["series"])
        by_product[f"{category}||{product}"].append(row)
        by_series[row["series"]].append(row)
        by_step[str(row["step"])].append(row)
        by_series_step[row["series"]][str(row["step"])].append(row)
    expected_series = {row["series"] for row in expected_rows}
    scored_series = {row["series"] for row in scored}
    covered_days = sum(row["covered_days"] for row in expected_rows)
    observed_days = sum(row["observed_days"] for row in expected_rows)
    calendar_days = sum(row["period_days"] for row in expected_rows)
    return {
        "overall": summarize(scored),
        "persistence_on_same_rows": error_metrics(scored, "anchor"),
        "product": {label: summarize(rows) for label, rows in sorted(by_product.items())},
        "series": {label: summarize(rows) for label, rows in sorted(by_series.items())},
        "forecast_step": {label: summarize(rows) for label, rows in sorted(by_step.items())},
        "series_forecast_step": {
            series: {step: summarize(rows) for step, rows in sorted(steps.items())}
            for series, steps in sorted(by_series_step.items())},
        "metric_target_met_on_scored_rows": _targets_met(summarize(scored)),
        "coverage": {
            "expected_forecast_periods": len(expected_rows),
            "periods_with_observed_actual": len(scored),
            "periods_without_observed_actual": len(expected_rows) - len(scored),
            "forecast_period_coverage": len(scored) / len(expected_rows) if expected_rows else 0.0,
            "forecast_series": len(expected_series),
            "series_with_observed_outcomes": len(scored_series),
            "series_without_observed_outcomes": sorted(expected_series - scored_series),
            "partial_periods": sum(row["partial_period"] for row in expected_rows),
            "mean_forecast_fraction_of_calendar_period": (
                covered_days / calendar_days if calendar_days else 0.0),
            "observed_label_coverage": observed_days / covered_days if covered_days else 0.0,
        },
        "target_definition": (
            "Daily points use the frozen price for each date; Weekly is the Monday-Sunday "
            "mean and Monthly is the calendar-month mean of centavo-rounded daily forecasts. "
            "Period actuals average observed labels on the same forecast-covered dates."
        ),
    }


def score(contract_path, actuals_manifest_path, *, now=None):
    contract, forecasts, integrity = load_contract(contract_path)
    now = datetime.now(timezone.utc) if now is None else now
    if now.tzinfo is None:
        raise ValueError("Scoring clock must include a timezone")
    if datetime.fromisoformat(contract["forecasts_frozen_at_utc"]) > now:
        raise ValueError("Freeze timestamp is later than the scoring clock")
    # Check time before even opening an actuals manifest or an observation file.
    if now < datetime.fromisoformat(integrity["period_closes_at"]):
        raise ValueError(f"Holdout still open until {integrity['period_closes_at']}; actuals were not opened")
    manifest_path = Path(actuals_manifest_path)
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    start, end = map(calendar_date, (contract["holdout_start"], contract["holdout_end"]))
    if calendar_date(manifest["reconciled_through"]) < end:
        raise ValueError("Actual observations have not been reconciled through the complete holdout")
    if not manifest.get("source") or not manifest.get("is_observed_definition"):
        raise ValueError("Actuals manifest must describe its source and observed-label definition")
    actual_path = relative_file(manifest_path.parent, manifest["data_file"])
    actual_bytes = actual_path.read_bytes()
    if digest(actual_bytes) != manifest["sha256"]:
        raise ValueError("Actuals SHA-256 mismatch")
    actuals, seen = {}, set()
    unobserved_count = outside_period_count = 0
    for row in csv_rows(actual_bytes, {"series", "target_date", "actual", "is_observed"}):
        target = calendar_date(row["target_date"])
        if not start <= target <= end:
            outside_period_count += 1
            continue
        series_parts(row["series"])
        key = (row["series"], target)
        if key in seen:
            raise ValueError("Duplicate actual series/date; reconcile before scoring")
        seen.add(key)
        flag = row["is_observed"].strip().lower()
        if flag in {"false", "0"}:
            unobserved_count += 1
            continue
        if flag not in {"true", "1"}:
            raise ValueError("is_observed must be true/false or 1/0")
        value = finite_number(row["actual"])
        if value < 0:
            raise ValueError("Observed prices must be nonnegative; invalid labels cannot silently disappear")
        actuals[key] = value
    declared_series = {key[0] for key in forecasts} | {item["series"] for item in contract["skipped_series"]}
    in_scope = {key: value for key, value in actuals.items() if key[0] in declared_series}
    matched = [{**forecasts[key], "actual": value} for key, value in sorted(in_scope.items()) if key in forecasts]
    if not matched:
        raise ValueError("No observed holdout outcomes match the frozen predictions")
    unknown = sorted({key[0] for key in actuals if key[0] not in declared_series})
    missing_forecasts = sorted(key for key in in_scope if key not in forecasts)
    scored_series = {row["series"] for row in matched}
    unscored_series = sorted({key[0] for key in forecasts} - scored_series)
    overall = summarize(matched)
    timeframe_rows = _timeframe_rows(forecasts, in_scope)
    timeframes = {name: _timeframe_report(rows) for name, rows in timeframe_rows.items()}
    combined_published_rows = [row for rows in timeframe_rows.values()
                               for row in rows if row["actual"] is not None]
    metric_pass = all(report["metric_target_met_on_scored_rows"]
                      for report in timeframes.values())
    full_scope = (integrity["forecast_series"] == integrity["total_input_series"]
                  and not missing_forecasts and not unscored_series and not unknown
                  and not unobserved_count and len(matched) == len(forecasts))
    groups = {name: defaultdict(list) for name in ("category", "product", "series", "unit", "horizon", "category_horizon")}
    for row in matched:
        category, product, _, _, unit = series_parts(row["series"])
        step = row["horizon"]
        bucket = "01-07" if step <= 7 else "08-14" if step <= 14 else "15-21" if step <= 21 else "22-30"
        labels = {"category": category, "product": f"{category}||{product}", "series": row["series"],
                  "unit": unit, "horizon": str(step), "category_horizon": f"{category}||{bucket}"}
        for group, label in labels.items():
            groups[group][label].append(row)
    return {
        "schema_version": 1, "model_run_id": contract["model_run_id"],
        "holdout_type": contract["holdout_type"], "scored_at_utc": now.astimezone(timezone.utc).isoformat(),
        "holdout_start": start.isoformat(), "holdout_end": end.isoformat(), "integrity": integrity,
        "actuals_manifest_sha256": digest(manifest_bytes), "actuals_sha256": digest(actual_bytes),
        "actuals_source": manifest["source"], "reconciled_through": manifest["reconciled_through"],
        "overall": overall,
        "overall_basis": "Daily frozen points across all 30 forecast steps.",
        "published_outputs_overall": summarize(combined_published_rows),
        "persistence_on_same_rows": error_metrics(matched, "anchor"),
        "thresholds": {"within_10_accuracy_pct_min": WITHIN_10_TARGET_PERCENT,
                       **{key: 5 for key in METRICS}},
        "metric_target_met_on_scored_rows": metric_pass,
        "metric_target_met_by_timeframe": {
            name: report["metric_target_met_on_scored_rows"]
            for name, report in timeframes.items()},
        "full_declared_scope_observed": full_scope,
        "target_met_for_full_declared_scope": metric_pass and full_scope,
        "timeframes": timeframes,
        "coverage": {
            "expected_forecast_rows": len(forecasts), "scored_rows": len(matched),
            "forecast_rows_with_observed_actual": len(matched) / len(forecasts),
            "observed_outcomes_in_declared_scope": len(in_scope),
            "observed_outcomes_with_forecasts": len(matched) / len(in_scope),
            "observed_outcomes_missing_forecasts": len(missing_forecasts),
            "near_zero_observed_forecasts_excluded_from_percentage_metrics": sum(
                row["actual"] < PERCENTAGE_ACTUAL_FLOOR for row in matched),
            "series_missing_forecasts": sorted({key[0] for key in missing_forecasts}),
            "forecast_series_without_observed_outcomes": unscored_series,
            "observed_series_outside_declared_scope": unknown,
            "unobserved_rows_excluded": unobserved_count, "outside_period_rows_excluded": outside_period_count,
        },
        "groups": {name: {label: summarize(rows) for label, rows in sorted(blocks.items())}
                   for name, blocks in groups.items()},
        "interpretation": (
            "Within-10 accuracy and MAPE exclude actual prices below 1e-8 PHP and report "
            "that count; MAE/RMSE retain all observed nonnegative actuals. Weekly/monthly "
            "metrics aggregate the frozen daily path using the publisher's rounding rules."
        ),
        "promotion_decision": "Not determined: scores do not establish model-selection independence or sufficient scope by themselves.",
    }


def scoring_attempt_path(contract_path):
    contract_path = Path(contract_path)
    return contract_path.parent / f".{contract_path.stem}.score-attempt.json"


def reserve_scoring_attempt(contract_path, *, now=None):
    """Atomically reserve this contract's single scoring attempt before reading actuals."""
    contract, _, integrity = load_contract(contract_path)
    now = datetime.now(timezone.utc) if now is None else now
    if now.tzinfo is None:
        raise ValueError("Scoring clock must include a timezone")
    if datetime.fromisoformat(contract["forecasts_frozen_at_utc"]) > now:
        raise ValueError("Freeze timestamp is later than the scoring clock")
    close = datetime.fromisoformat(integrity["period_closes_at"])
    if now < close:
        raise ValueError(f"Holdout still open until {close.isoformat()}; actuals were not opened")

    attempt_path = scoring_attempt_path(contract_path)
    attempt = {
        "schema_version": 1,
        "status": "reserved",
        "contract_sha256": integrity["contract_sha256"],
        "reserved_at_utc": now.astimezone(timezone.utc).isoformat(),
    }
    try:
        # Exclusive creation is the cross-process, contract-level one-time gate.
        with attempt_path.open("x", encoding="utf-8") as stream:
            json.dump(attempt, stream, indent=2)
    except FileExistsError as exc:
        raise FileExistsError(
            "A scoring attempt is already reserved for this contract; do not rescore "
            "to another output path"
        ) from exc
    return attempt_path


def _write_attempt_state(attempt_path, state):
    attempt_path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def main(argv=None, *, now=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="Verify frozen forecasts without opening actuals")
    inspect.add_argument("contract", type=Path)
    evaluate = commands.add_parser("score", help="Score only after the period is closed and reconciled")
    evaluate.add_argument("contract", type=Path)
    evaluate.add_argument("actuals_manifest", type=Path)
    evaluate.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    if args.command == "inspect":
        _, _, integrity = load_contract(args.contract)
        print(json.dumps(integrity, indent=2))
        return
    if args.output.exists():
        raise FileExistsError("Evaluation output already exists; it cannot be overwritten")
    if not args.output.parent.is_dir():
        raise FileNotFoundError(f"Evaluation output directory does not exist: {args.output.parent}")
    attempt_path = scoring_attempt_path(args.contract)
    if args.output.resolve() == attempt_path.resolve():
        raise ValueError("Evaluation output cannot replace the contract scoring-attempt marker")

    scoring_clock = datetime.now(timezone.utc) if now is None else now
    attempt_path = reserve_scoring_attempt(args.contract, now=scoring_clock)
    try:
        result = score(args.contract, args.actuals_manifest, now=scoring_clock)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
    except Exception as exc:
        _write_attempt_state(attempt_path, {
            "schema_version": 1,
            "status": "failed_closed",
            "contract_sha256": load_contract(args.contract)[2]["contract_sha256"],
            "reserved_at_utc": scoring_clock.astimezone(timezone.utc).isoformat(),
            "failure_type": type(exc).__name__,
        })
        raise
    _write_attempt_state(attempt_path, {
        "schema_version": 1,
        "status": "completed",
        "contract_sha256": digest(Path(args.contract).read_bytes()),
        "reserved_at_utc": scoring_clock.astimezone(timezone.utc).isoformat(),
        "output_path": str(args.output),
        "output_sha256": digest(args.output.read_bytes()),
    })
    print(json.dumps({
        "report": str(args.output),
        "published_outputs_overall": result["published_outputs_overall"],
        "by_timeframe": {name: report["overall"]
                         for name, report in result["timeframes"].items()},
        "target_met_for_full_declared_scope": result["target_met_for_full_declared_scope"],
    }, indent=2))


if __name__ == "__main__":
    main()
