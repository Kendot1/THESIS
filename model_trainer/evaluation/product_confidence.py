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

HORIZONS = {1: "daily", 7: "weekly", 30: "monthly"}
METHOD = "chronological_mape_reliability_v1"
MIN_SAMPLES = 8


def level(score):
    if score is None:
        return "Insufficient data"
    return next(label for threshold, label in (
        (90, "Very High"), (80, "High"), (70, "Moderate"),
        (60, "Low"), (0, "Very Low")) if score >= threshold)


def _score(errors, conservative=False):
    penalty = stdev(errors) / math.sqrt(len(errors)) if conservative and len(errors) > 1 else 0
    return max(0.0, min(100.0, 100 - mean(errors) - penalty))


def validation_confidence(bundle, product_ids):
    result = {pid: {name: {
        "forecast_horizon_days": lead, "confidence_score": None,
        "confidence_level": "Insufficient data", "mae": None, "rmse": None,
        "mape": None, "sample_count": 0, "model_version": bundle.name,
        "evaluation_source": "chronological_validation", "confidence_method": METHOD,
        "evidence_status": "unverified_provenance",
    } for lead, name in HORIZONS.items()} for pid in set(product_ids.values())}
    try:
        calibration = json.loads((bundle / "ensemble.json").read_text(encoding="utf-8")).get("calibration", {})
        if (calibration.get("scope") != "held_out_from_ensemble_fit" or
                calibration.get("base_model_scope") != "calibration_excluded_from_early_stopping"):
            return result
        # A boundary reconstructed from metadata is accepted only if the complete
        # calibration row count and target span exactly match the sealed bundle.
        start = date.fromisoformat(calibration["start"][:10])
        end = date.fromisoformat(calibration["end"][:10])
        cutoff = start - timedelta(days=1)
        with (bundle / "validation_forecasts.csv").open(newline="", encoding="utf-8") as stream:
            rows = [r for r in csv.DictReader(stream) if date.fromisoformat(r["origin"][:10]) >= cutoff]
        if (len(rows) != calibration["sample_count"] or not rows or
                min(r["date"][:10] for r in rows) != start.isoformat() or
                max(r["date"][:10] for r in rows) != end.isoformat()):
            return result
    except (OSError, ValueError, KeyError, TypeError):
        return result
    for horizons in result.values():
        for metric in horizons.values():
            metric["evidence_status"] = "insufficient_data"

    samples, conflicts = {}, set()
    for row in rows:
        pid = product_ids.get(tuple(row.get("series", "").split("||")))
        try:
            lead = int(row["horizon"])
            origin, target = (date.fromisoformat(row[key][:10]) for key in ("origin", "date"))
            actual, predicted = float(row["actual"]), float(row["ensemble"])
        except (KeyError, ValueError, TypeError):
            continue
        if (pid is None or lead not in HORIZONS or (target-origin).days != lead
                or not all(math.isfinite(x) and x > 0 for x in (actual, predicted))):
            continue
        key = (pid, lead, target)
        sample = (origin, target, abs(predicted-actual), abs(predicted-actual)/actual*100)
        if key in samples and samples[key] != sample:
            conflicts.add(key)
        samples[key] = sample
    groups = defaultdict(list)
    for key, sample in samples.items():
        if key not in conflicts:
            groups[key[:2]].append(sample)

    return score_groups(result, groups)


def score_groups(result, groups):
    """Shared chronological formula check; optional fifth field is availability date."""
    # Only two fixed candidates, assessed forward in time. A sample's outcome
    # becomes usable after its target date, never merely after its origin date.
    losses = {False: [], True: []}
    check_origins = set()
    for group in groups.values():
        for row in sorted(group):
            origin, ape = row[0], row[3]
            past = [r[3] for r in group if (r[4] if len(r) > 4 else r[1]) <= origin]
            if len(past) < MIN_SAMPLES:
                continue
            check_origins.add(origin)
            for conservative in losses:
                losses[conservative].append(abs(_score(past, conservative) - max(0, 100-ape)))
    validated_method = len(check_origins) >= 3
    conservative = bool(validated_method and mean(losses[True]) < mean(losses[False]))
    for (pid, lead), group in groups.items():
        errors, apes = [r[2] for r in group], [r[3] for r in group]
        metric = result[pid][HORIZONS[lead]]
        metric.update(mae=mean(errors), rmse=math.sqrt(mean(e*e for e in errors)),
                      mape=mean(apes), sample_count=len(group),
                      evaluation_start=min(r[1] for r in group).isoformat(),
                      evaluation_end=max(r[1] for r in group).isoformat())
        if not validated_method or len(group) < MIN_SAMPLES:
            continue
        score = round(_score(apes, conservative), 1)
        metric.update(confidence_score=score, confidence_level=level(score),
                      evidence_status="validated", consistency_penalty=conservative,
                      formula_validation_mae=mean(losses[conservative]),
                      formula_validation_origins=len(check_origins))
    return result
