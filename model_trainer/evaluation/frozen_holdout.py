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
from pathlib import Path

PHILIPPINE_TIME = timezone(timedelta(hours=8))
METRICS = ("mae", "rmse", "mape")


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
        raise ValueError("Nonfinite price or interval")
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
    required = {"series", "origin", "target_date", "horizon", "anchor",
                "prediction", "lower_80", "upper_80"}
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
        point, lower, upper, anchor = [finite_number(row[name]) for name in
                                      ("prediction", "lower_80", "upper_80", "anchor")]
        if anchor <= 0 or not 0 <= lower <= point <= upper:
            raise ValueError("Invalid forecast anchor or interval ordering")
        forecasts[key] = {"series": row["series"], "target_date": target.isoformat(),
                          "horizon": step, "prediction": point, "anchor": anchor,
                          "lower_80": lower, "upper_80": upper}
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
        return {"n": 0, "mae": None, "rmse": None, "mape": None}
    errors = [abs(row[column] - row["actual"]) for row in rows]
    metrics = {"n": len(rows), "mae": math.fsum(errors) / len(rows),
               "rmse": math.hypot(*errors) / math.sqrt(len(rows)),
               "mape": math.fsum(err / row["actual"] * 100
                                 for err, row in zip(errors, rows)) / len(rows)}
    if any(not math.isfinite(metrics[key]) for key in METRICS):
        raise ValueError("Error metric overflow; reconcile price units and values")
    return metrics


def summarize(rows):
    report = error_metrics(rows)
    report["range_hit_rate_80"] = (sum(row["lower_80"] <= row["actual"] <= row["upper_80"]
                                       for row in rows) / len(rows)) if rows else None
    report["mean_interval_width_80"] = (math.fsum(row["upper_80"] - row["lower_80"]
                                                  for row in rows) / len(rows)) if rows else None
    return report


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
        if value <= 0:
            raise ValueError("Observed prices must be positive; invalid labels cannot silently disappear")
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
    metric_pass = all(overall[key] <= 5 for key in METRICS)
    full_scope = (integrity["forecast_series"] == integrity["total_input_series"]
                  and not missing_forecasts and not unscored_series and not unknown)
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
        "overall": overall, "persistence_on_same_rows": error_metrics(matched, "anchor"),
        "thresholds": {key: 5 for key in METRICS},
        "metric_target_met_on_scored_rows": metric_pass,
        "full_declared_scope_observed": full_scope,
        "target_met_for_full_declared_scope": metric_pass and full_scope,
        "coverage": {
            "expected_forecast_rows": len(forecasts), "scored_rows": len(matched),
            "forecast_rows_with_observed_actual": len(matched) / len(forecasts),
            "observed_outcomes_in_declared_scope": len(in_scope),
            "observed_outcomes_with_forecasts": len(matched) / len(in_scope),
            "observed_outcomes_missing_forecasts": len(missing_forecasts),
            "series_missing_forecasts": sorted({key[0] for key in missing_forecasts}),
            "forecast_series_without_observed_outcomes": unscored_series,
            "observed_series_outside_declared_scope": unknown,
            "unobserved_rows_excluded": unobserved_count, "outside_period_rows_excluded": outside_period_count,
        },
        "groups": {name: {label: summarize(rows) for label, rows in sorted(blocks.items())}
                   for name, blocks in groups.items()},
        "interpretation": "MAE/RMSE use original price units; MAPE is percent. Range hit rate is measured coverage, not a future probability.",
        "promotion_decision": "Not determined: scores do not establish model-selection independence or sufficient scope by themselves.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="Verify frozen forecasts without opening actuals")
    inspect.add_argument("contract", type=Path)
    evaluate = commands.add_parser("score", help="Score only after the period is closed and reconciled")
    evaluate.add_argument("contract", type=Path)
    evaluate.add_argument("actuals_manifest", type=Path)
    evaluate.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.command == "inspect":
        _, _, integrity = load_contract(args.contract)
        print(json.dumps(integrity, indent=2))
        return
    if args.output.exists():
        raise FileExistsError("Evaluation output already exists; it cannot be overwritten")
    result = score(args.contract, args.actuals_manifest)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps({"report": str(args.output), "overall": result["overall"],
                      "target_met_for_full_declared_scope": result["target_met_for_full_declared_scope"]}, indent=2))


if __name__ == "__main__":
    main()
