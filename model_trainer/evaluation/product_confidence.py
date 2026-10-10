"""Product/lead reliability from the untouched part of chronological validation.

This is a historical accuracy score, not a probability or a price interval.
Legacy bundles without explicit early-stopping isolation fail closed.
"""
import csv
import json
import math
from collections import defaultdict
from datetime import date, timedelta
from statistics import mean, stdev
from utils.prices import mean_price, round_price

HORIZONS = {1: "daily", 7: "weekly", 30: "monthly"}
METHOD = "chronological_mape_reliability_v1"
MIN_SAMPLES = 8
MIN_ORIGINS = 8
MIN_FORMULA_CHECK_ORIGINS = 3
MIN_OBSERVED_LABEL_COVERAGE = 0.8
PUBLISHED_PATH_DAYS = 30


def level(score):
    if score is None:
        return "Insufficient data"
    return next(label for threshold, label in (
        (90, "Very High"), (80, "High"), (70, "Moderate"),
        (60, "Low"), (0, "Very Low")) if score >= threshold)


def _score(errors, conservative=False):
    penalty = stdev(errors) / math.sqrt(len(errors)) if conservative and len(errors) > 1 else 0
    return max(0.0, min(100.0, 100 - mean(errors) - penalty))


def _empty_metric(bundle, lead, step=None):
    metric = {
        "forecast_horizon_days": lead, "confidence_score": None,
        "confidence_level": "Insufficient data", "mae": None, "rmse": None,
        "mape": None, "sample_count": 0, "model_version": bundle.name,
        "evaluation_source": "chronological_validation", "confidence_method": METHOD,
        "evidence_status": "unverified_provenance",
    }
    if step is not None:
        metric["forecast_step"] = step
    return metric


def _period_bounds(target, horizon):
    if horizon == "weekly":
        start = target - timedelta(days=target.weekday())
        return start, start + timedelta(days=6)
    start = target.replace(day=1)
    next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return start, next_month - timedelta(days=1)


def _period_step(origin, start, horizon):
    first_start, _ = _period_bounds(origin + timedelta(days=1), horizon)
    if horizon == "weekly":
        return (start - first_start).days // 7 + 1
    return (start.year - first_start.year) * 12 + start.month - first_start.month + 1


def _path_records(bundle, forecast_paths):
    if forecast_paths is None:
        path = bundle / "validation_paths.csv"
        if not path.exists():
            return None
        with path.open(newline="", encoding="utf-8") as stream:
            return list(csv.DictReader(stream))
    if hasattr(forecast_paths, "to_dict"):
        return forecast_paths.to_dict("records")
    return list(forecast_paths)


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def _calibration_paths(path_rows, validation_rows, cutoff):
    selected = [row for row in path_rows
                if date.fromisoformat(str(row["origin"])[:10]) >= cutoff]
    groups = defaultdict(list)
    for row in selected:
        groups[(str(row["series"]), str(row["origin"])[:10])].append(row)
    if not groups:
        raise ValueError("No full forecast paths cover the confidence calibration window")
    for (series, origin), group in groups.items():
        leads = []
        for row in group:
            lead = int(row["horizon"])
            target = date.fromisoformat(str(row["date"])[:10])
            if (lead < 1 or lead > PUBLISHED_PATH_DAYS
                    or (target - date.fromisoformat(origin)).days != lead):
                raise ValueError("Forecast path dates do not match their origin and lead")
            leads.append(lead)
        if len(group) != PUBLISHED_PATH_DAYS or set(leads) != set(range(1, PUBLISHED_PATH_DAYS + 1)):
            raise ValueError(f"Incomplete 30-day forecast path for {series} at {origin}")

    def key(row):
        return (str(row["series"]), str(row["origin"])[:10], str(row["date"])[:10])

    path_observed = {}
    for row in selected:
        actual = _number(row.get("actual"))
        if not math.isfinite(actual):
            continue
        identity = key(row)
        if identity in path_observed:
            raise ValueError("Duplicate observed forecast-path label")
        path_observed[identity] = row
    validation_observed = {key(row): row for row in validation_rows}
    if len(validation_observed) != len(validation_rows) or set(path_observed) != set(validation_observed):
        raise ValueError("Full paths do not cover the sealed calibration labels exactly")
    for identity, path_row in path_observed.items():
        validation_row = validation_observed[identity]
        for column in ("actual", "ensemble"):
            if not math.isclose(float(path_row[column]), float(validation_row[column]),
                                rel_tol=1e-10, abs_tol=1e-8):
                raise ValueError(f"Forecast path {column} differs from sealed calibration rows")
    return selected, len(groups)


def validation_confidence(bundle, product_ids, forecast_paths=None,
                          evaluation_partition="validation"):
    """Score product confidence from a verified chronological model partition.

    Production training uses the default held-out validation calibration. The
    explicit development_test mode supports offline diagnostics for legacy
    bundles whose test partition is out of model fit but lacks saved full paths.
    """
    result = {pid: {
        "confidence_by_horizon": {
            name: _empty_metric(bundle, lead) for lead, name in HORIZONS.items()},
        "confidence_by_step": {name: {} for name in HORIZONS.values()},
    } for pid in set(product_ids.values())}
    path_rows = None
    evaluation_source = "chronological_validation"
    try:
        if evaluation_partition == "validation":
            calibration = json.loads(
                (bundle / "ensemble.json").read_text(encoding="utf-8")
            ).get("calibration", {})
            if (calibration.get("scope") != "held_out_from_ensemble_fit" or
                    calibration.get("base_model_scope") != "calibration_excluded_from_early_stopping"):
                return result
            # A boundary reconstructed from metadata is accepted only if the complete
            # calibration row count and target span exactly match the sealed bundle.
            start = date.fromisoformat(calibration["start"][:10])
            end = date.fromisoformat(calibration["end"][:10])
            cutoff = start - timedelta(days=1)
            forecast_file = bundle / "validation_forecasts.csv"
            expected_count = int(calibration["sample_count"])
        elif evaluation_partition == "development_test":
            metadata = json.loads((bundle / "metadata.json").read_text(encoding="utf-8"))
            split = metadata["split"]
            train_end = date.fromisoformat(split["train"]["end"][:10])
            validation_end = date.fromisoformat(split["validation"]["end"][:10])
            test_start = date.fromisoformat(split["test"]["start"][:10])
            test_end = date.fromisoformat(split["test"]["end"][:10])
            if not train_end < validation_end < test_start <= test_end:
                return result
            forecast_file = bundle / "test_forecasts.csv"
            expected_count = int(metadata["metrics"]["test"]["ensemble"]["n"])
            evaluation_source = "chronological_development_test"
        else:
            raise ValueError("Unsupported confidence evaluation partition")

        with forecast_file.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        if evaluation_partition == "validation":
            rows = [r for r in rows if date.fromisoformat(r["origin"][:10]) >= cutoff]
            if (len(rows) != expected_count or not rows or
                    min(r["date"][:10] for r in rows) != start.isoformat() or
                    max(r["date"][:10] for r in rows) != end.isoformat()):
                return result
        else:
            if (len(rows) != expected_count or not rows or
                    min(date.fromisoformat(r["date"][:10]) for r in rows) < test_start or
                    max(date.fromisoformat(r["date"][:10]) for r in rows) > test_end or
                    any(date.fromisoformat(r["origin"][:10]) < test_start - timedelta(days=1)
                        for r in rows)):
                return result
            start = min(date.fromisoformat(r["date"][:10]) for r in rows)
            cutoff = start - timedelta(days=1)
        path_rows = _path_records(bundle, forecast_paths)
        if path_rows is None:
            for product in result.values():
                for metric in product["confidence_by_horizon"].values():
                    metric["path_evidence_issue"] = (
                        "Complete 30-day validation paths are required to verify label coverage")
            return result
        try:
            path_rows, _ = _calibration_paths(path_rows, rows, cutoff)
        except (KeyError, ValueError, TypeError) as exc:
            path_issue = str(exc)
            for product in result.values():
                for metric in product["confidence_by_horizon"].values():
                    metric["path_evidence_issue"] = path_issue
            return result
    except (OSError, ValueError, KeyError, TypeError):
        return result
    for product in result.values():
        for metric in product["confidence_by_horizon"].values():
            metric["evidence_status"] = "insufficient_data"

    daily_all, daily_steps = defaultdict(list), defaultdict(list)
    coverage = defaultdict(lambda: {"observed": 0, "covered": 0, "calendar": 0,
                                    "partial_periods": 0})
    product_path_counts = defaultdict(int)
    path_groups = defaultdict(list)
    for row in path_rows:
        path_groups[(str(row["series"]), str(row["origin"])[:10])].append(row)
    for (series, origin_text), group in path_groups.items():
        pid = product_ids.get(tuple(series.split("||")))
        if pid is None:
            continue
        product_path_counts[pid] += 1
        origin = date.fromisoformat(origin_text)
        periods = {"weekly": defaultdict(list), "monthly": defaultdict(list)}
        for row in sorted(group, key=lambda item: int(item["horizon"])):
            lead = int(row["horizon"])
            target = date.fromisoformat(str(row["date"])[:10])
            actual = _number(row.get("actual"))
            predicted = _number(row.get("ensemble"))
            daily_coverage = coverage[(pid, "daily", None)]
            daily_step_coverage = coverage[(pid, "daily", lead)]
            daily_coverage["covered"] += 1
            daily_step_coverage["covered"] += 1
            if math.isfinite(actual) and actual >= 0:
                daily_coverage["observed"] += 1
                daily_step_coverage["observed"] += 1
            daily_predicted = round_price(predicted)
            if (math.isfinite(actual) and actual >= 0 and
                    math.isfinite(daily_predicted) and daily_predicted > 0):
                ape = abs(daily_predicted-actual)/actual*100 if actual >= 1e-8 else None
                daily_sample = (origin, target, abs(daily_predicted-actual), ape,
                                target, False)
                daily_all[(pid, "daily")].append(daily_sample)
                daily_steps[(pid, "daily", lead)].append(daily_sample)
            for horizon in ("weekly", "monthly"):
                start, end = _period_bounds(target, horizon)
                periods[horizon][(start, end)].append((target, actual, daily_predicted))

        for horizon, period_groups in periods.items():
            for (start, end), period in period_groups.items():
                covered_days = len(period)
                observed = [row[1] for row in period
                            if math.isfinite(row[1]) and row[1] >= 0]
                step = _period_step(origin, start, horizon)
                counters = coverage[(pid, horizon, None)]
                step_counters = coverage[(pid, horizon, step)]
                for counters_for_group in (counters, step_counters):
                    counters_for_group["covered"] += covered_days
                    counters_for_group["observed"] += len(observed)
                    counters_for_group["calendar"] += (end-start).days+1
                    counters_for_group["partial_periods"] += (
                        covered_days < (end-start).days+1 or len(observed) < covered_days)
                if not observed:
                    continue
                actual = mean(observed)
                published_values = [row[2] for row in period]
                if not all(math.isfinite(value) and value > 0 for value in published_values):
                    continue
                # PredictionWriter rounds each daily point, then rounds the
                # average for its published weekly/monthly row.
                predicted = mean_price(published_values)
                if predicted <= 0:
                    continue
                ape = abs(predicted-actual)/actual*100 if actual >= 1e-8 else None
                target = max(row[0] for row in period)
                sample = (origin, target, abs(predicted-actual), ape, end,
                          covered_days < (end-start).days+1 or len(observed) < covered_days)
                daily_all[(pid, horizon)].append(sample)
                daily_steps[(pid, horizon, step)].append(sample)

    metric_groups = []
    for (pid, horizon), group in daily_all.items():
        metric_groups.append((result[pid]["confidence_by_horizon"][horizon], group))
    for (pid, horizon, step), group in daily_steps.items():
        lead = {"daily": 1, "weekly": 7, "monthly": 30}[horizon]
        metric = _empty_metric(bundle, lead, step)
        result[pid]["confidence_by_step"][horizon][step] = metric
        metric["evidence_status"] = "insufficient_data"
        metric_groups.append((metric, group))
    score_metrics(metric_groups)
    if evaluation_source != "chronological_validation":
        for product in result.values():
            for metric in product["confidence_by_horizon"].values():
                metric["evaluation_source"] = evaluation_source
            for steps in product["confidence_by_step"].values():
                for metric in steps.values():
                    metric["evaluation_source"] = evaluation_source
    for (pid, horizon, step), counts in coverage.items():
        metric = (result[pid]["confidence_by_horizon"][horizon] if step is None else
                  result[pid]["confidence_by_step"][horizon].get(str(step)) or
                  result[pid]["confidence_by_step"][horizon].get(step))
        if metric is None:
            continue
        metric.update(
            observed_label_coverage=(counts["observed"] / counts["covered"]
                                     if counts["covered"] else 0.0),
            observed_label_count=counts["observed"],
            forecast_covered_day_count=counts["covered"],
            calendar_day_count=counts["calendar"],
            mean_calendar_coverage=(counts["covered"] / counts["calendar"]
                                    if counts["calendar"] else 0.0),
            partial_period_count=counts["partial_periods"],
            forecast_path_count=(product_path_counts[pid] if path_rows is not None else None),
            forecast_path_days=(PUBLISHED_PATH_DAYS if path_rows is not None else None),
        )
        if (path_rows is not None and counts["covered"] and
                counts["observed"] / counts["covered"] < MIN_OBSERVED_LABEL_COVERAGE):
            metric["confidence_score"] = None
            metric["confidence_level"] = "Insufficient data"
            metric["evidence_status"] = "insufficient_data"
            metric["insufficient_data_reason"] = (
                f"Observed label coverage is below {MIN_OBSERVED_LABEL_COVERAGE:.0%}")
    return result


def score_metrics(metric_groups):
    """Shared chronological formula check; optional fifth field is availability date."""
    # Only two fixed candidates, assessed forward in time. A sample's outcome
    # becomes usable after its target date, never merely after its origin date.
    losses = {False: [], True: []}
    group_checks = {}
    for metric, group in metric_groups:
        group_losses = {False: [], True: []}
        check_origins = set()
        percent_rows = [row for row in group if row[3] is not None]
        for row in sorted(percent_rows):
            origin, ape = row[0], row[3]
            past = [r[3] for r in percent_rows if r[4] <= origin]
            if len(past) < MIN_SAMPLES:
                continue
            check_origins.add(origin)
            for conservative in losses:
                loss = abs(_score(past, conservative) - max(0, 100-ape))
                losses[conservative].append(loss)
                group_losses[conservative].append(loss)
        group_checks[id(metric)] = (len(check_origins), group_losses)
    validated_method = any(losses.values()) and min(len(losses[False]), len(losses[True])) > 0
    conservative = bool(validated_method and mean(losses[True]) < mean(losses[False]))
    for metric, group in metric_groups:
        errors = [r[2] for r in group]
        percent_rows = [r for r in group if r[3] is not None]
        apes = [r[3] for r in percent_rows]
        formula_origins, group_losses = group_checks[id(metric)]
        metric.update(mae=mean(errors), rmse=math.sqrt(mean(e*e for e in errors)),
                      mape=mean(apes) if apes else None, sample_count=len(group),
                      percentage_sample_count=len(apes),
                      excluded_near_zero=len(group)-len(apes),
                      sample_origin_count=len({row[0] for row in percent_rows}),
                      formula_validation_origins=formula_origins,
                      evaluation_start=min(r[1] for r in group).isoformat(),
                      evaluation_end=max(r[1] for r in group).isoformat())
        reasons = []
        if not validated_method:
            reasons.append("forward confidence-formula comparison is unavailable")
        if len(apes) < MIN_SAMPLES:
            reasons.append(f"fewer than {MIN_SAMPLES} percentage errors")
        if len({row[0] for row in percent_rows}) < MIN_ORIGINS:
            reasons.append(f"fewer than {MIN_ORIGINS} distinct forecast origins")
        if formula_origins < MIN_FORMULA_CHECK_ORIGINS:
            reasons.append(
                f"fewer than {MIN_FORMULA_CHECK_ORIGINS} forward formula-check origins")
        if reasons:
            metric["insufficient_data_reason"] = "; ".join(reasons)
            continue
        score = round(_score(apes, conservative), 1)
        metric.update(confidence_score=score, confidence_level=level(score),
                      evidence_status="validated", consistency_penalty=conservative,
                      formula_validation_mae=mean(group_losses[conservative]))
