"""Empirical product/lead probability of meeting the absolute PHP 5 tolerance.

Scores use isolated chronological validation outcomes and fail closed when
provenance, forecast paths, sample count, or forward checks are insufficient.
"""
import csv
import json
import math
from collections import defaultdict
from datetime import date, timedelta
from statistics import mean
from utils.prices import mean_price, round_price

HORIZONS = {1: "daily", 7: "weekly", 30: "monthly"}
METHOD = "chronological_within5_php_probability_v1"
MIN_SAMPLES = 8
MIN_ORIGINS = 8
MIN_FORMULA_CHECK_ORIGINS = 3
MIN_OBSERVED_LABEL_COVERAGE = 0.8
PUBLISHED_PATH_DAYS = 30
WITHIN5_PHP_TOLERANCE = 5.0
WITHIN10_TOLERANCE = 0.10  # retained as a separate diagnostic


def level(score):
    if score is None:
        return "Insufficient data"
    return next(label for threshold, label in (
        (90, "Very High"), (80, "High"), (70, "Moderate"),
        (60, "Low"), (0, "Very Low")) if score >= threshold)


def _smoothed_probability(successes, sample_count):
    """Beta(1, 1)-smoothed hit rate for the calibration sample."""
    if sample_count <= 0:
        return None
    return (successes + 1) / (sample_count + 2)


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

    Production training uses the default held-out validation calibration. A
    residual bundle identifies its calibration as held out from residual fitting.
    The explicit development_test mode supports offline diagnostics for legacy
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
            if (calibration.get("scope") not in {
                    "held_out_from_ensemble_fit", "held_out_from_residual_fit"} or
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
    """Score a smoothed PHP-5 hit probability and verify it forward-only."""
    group_checks = {}
    clean_groups = []
    for metric, group in metric_groups:
        valid_rows = [row for row in group if math.isfinite(row[2]) and row[2] >= 0]
        metric["invalid_sample_count"] = len(group) - len(valid_rows)
        clean_groups.append((metric, valid_rows))
    for metric, group in clean_groups:
        group_briers = []
        check_origins = set()
        valid_rows = group
        for row in sorted(valid_rows):
            origin, absolute_error = row[0], row[2]
            # Date-only outcomes closing on the origin are not yet eligible.
            past_rows = [r for r in valid_rows if r[4] < origin]
            if (len(past_rows) < MIN_SAMPLES or
                    len({r[0] for r in past_rows}) < MIN_ORIGINS):
                continue
            past = [r[2] for r in past_rows]
            check_origins.add(origin)
            past_successes = sum(error <= WITHIN5_PHP_TOLERANCE for error in past)
            probability = _smoothed_probability(past_successes, len(past))
            observed = float(absolute_error <= WITHIN5_PHP_TOLERANCE)
            group_briers.append((probability - observed) ** 2)
        group_checks[id(metric)] = (len(check_origins), group_briers)

    for metric, group in clean_groups:
        errors = [r[2] for r in group]
        percent_rows = [r for r in group if r[3] is not None
                        and math.isfinite(r[3]) and r[3] >= 0]
        apes = [r[3] for r in percent_rows]
        sample_origins = len({row[0] for row in group})
        formula_origins, group_briers = group_checks[id(metric)]
        successes = sum(error <= WITHIN5_PHP_TOLERANCE for error in errors)
        within10_successes = sum(ape <= WITHIN10_TOLERANCE * 100 for ape in apes)
        metric.update(mae=mean(errors) if errors else None,
                      rmse=math.sqrt(mean(e*e for e in errors)) if errors else None,
                      mape=mean(apes) if apes else None, sample_count=len(group),
                      percentage_sample_count=len(apes),
                      within5_php_success_count=successes,
                      within5_php_sample_count=len(errors),
                      within5_php_rate=successes / len(errors) if errors else None,
                      # Keep the former diagnostic available without using it
                      # for the displayed confidence score.
                      within10_success_count=within10_successes,
                      within10_sample_count=len(apes),
                      within10_rate=(within10_successes / len(apes)
                                    if apes else None),
                      excluded_near_zero=len(group)-len(apes),
                      sample_origin_count=sample_origins,
                      # Groups already isolate product/horizon/step; period end
                      # identifies a target period within that fixed frequency.
                      sample_target_period_count=len({row[4] for row in group}),
                      formula_validation_origins=formula_origins,
                      formula_validation_brier=mean(group_briers) if group_briers else None,
                      evaluation_start=min(r[1] for r in group).isoformat() if group else None,
                      evaluation_end=max(r[1] for r in group).isoformat() if group else None)
        reasons = []
        if len(errors) < MIN_SAMPLES:
            reasons.append(f"fewer than {MIN_SAMPLES} absolute errors")
        if sample_origins < MIN_ORIGINS:
            reasons.append(f"fewer than {MIN_ORIGINS} distinct forecast origins")
        if formula_origins < MIN_FORMULA_CHECK_ORIGINS:
            reasons.append(
                f"fewer than {MIN_FORMULA_CHECK_ORIGINS} forward formula-check origins")
        if reasons:
            metric.update(confidence_score=None, confidence_level="Insufficient data",
                          evidence_status="insufficient_data")
            metric["insufficient_data_reason"] = "; ".join(reasons)
            continue
        metric.pop("insufficient_data_reason", None)
        probability = _smoothed_probability(successes, len(errors))
        score = round(probability * 100, 1)
        metric.update(confidence_score=score, confidence_level=level(score),
                      confidence_definition=(
                          "Beta(1,1)-smoothed probability of absolute price error <= PHP 5"),
                      evidence_status="validated")
