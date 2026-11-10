"""Validate matched, pre-selection 7/4/1 historical comparison rows."""
from collections import defaultdict
from pathlib import Path

from .frozen_holdout import PHILIPPINE_TIME, calendar_date, csv_rows, finite_number, series_parts
from .prospective_horizons_v3 import (
    CLOSED_HOLDOUT_START, MIN_OBSERVED_DAYS, STEPS, _summary, _timestamp, target_bounds,
    validated_intervals,
)


def compare_validation(path, selection, *, min_origins=3):
    """Recompute 7/4/1 candidate/reference errors on a complete expected key mask."""
    path = Path(path)
    selected_at = _timestamp(selection["selected_at"])
    selection_origin = calendar_date(selection["forecast_origin"])
    last_allowed = min(selection_origin, selected_at.astimezone(PHILIPPINE_TIME).date())
    declared = set(selection["declared_series"])
    selected_origins = selection.get("validation_origins")
    if (not isinstance(selected_origins, list) or selected_origins != sorted(set(selected_origins))):
        raise ValueError("Selection must carry the sorted predeclared validation origins")
    expected_origins = {calendar_date(value) for value in selected_origins}
    required = {"series", "origin", "forecast_horizon", "forecast_step",
                "target_period_start", "target_period_end", "actual",
                "prediction", "prediction_status", "status_reason", "champion", "anchor",
                "is_observed", "observed_days", "period_days"}
    with path.open("rb") as stream:
        rows = list(csv_rows(stream.read(), required))
    if not rows:
        raise ValueError("Validation has no expected forecast keys")

    matched, seen = [], set()
    origins = set()
    grouped = {name: defaultdict(list) for name in
               ("horizon", "series", "series_horizon", "product", "horizon_step", "origin",
                "horizon_origin")}
    origins_by_horizon = defaultdict(set)
    targets_by_horizon = defaultdict(set)
    targets_by_series_horizon = defaultdict(set)
    origins_by_series_horizon = defaultdict(set)
    missing_labels = defaultdict(int)
    status_counts = {status: 0 for status in ("active", "fallback", "missing")}
    exact_keys = []
    for row in rows:
        series = row["series"]
        series_parts(series)
        if row["series"] not in declared:
            raise ValueError("Validation series differs from selected scope")
        origin = calendar_date(row["origin"])
        origins.add(origin)
        horizon = row["forecast_horizon"]
        try:
            step = int(row["forecast_step"])
        except ValueError as exc:
            raise ValueError("Invalid validation forecast step") from exc
        if str(step) != row["forecast_step"]:
            raise ValueError("Validation step must be a canonical integer")
        start, end = target_bounds(origin, horizon, step)
        if (origin >= selection_origin or end >= last_allowed
                or end >= CLOSED_HOLDOUT_START
                or calendar_date(row["target_period_start"]) != start
                or calendar_date(row["target_period_end"]) != end):
            raise ValueError("Validation target overlaps selection or has wrong period bounds")
        key = row["series"], origin, horizon, step
        if key in seen:
            raise ValueError("Duplicate validation forecast key")
        seen.add(key)

        status = row["prediction_status"].strip().lower()
        if status not in status_counts:
            raise ValueError("Validation prediction_status must be active, fallback, or missing")
        status_counts[status] += 1
        reason = row["status_reason"].strip()
        if status in {"fallback", "missing"} and not reason:
            raise ValueError("Validation fallback or missing row requires a status_reason")
        if status == "missing":
            if row["prediction"].strip():
                raise ValueError("Missing validation forecast must have a blank prediction")
            prediction = None
        else:
            prediction = finite_number(row["prediction"])
            if prediction <= 0:
                raise ValueError("Validation prediction must be positive")
        champion, anchor = finite_number(row["champion"]), finite_number(row["anchor"])
        if champion <= 0 or anchor <= 0:
            raise ValueError("Validation references must be positive")
        if status == "fallback" and prediction != anchor:
            raise ValueError("Validation fallback must equal origin-known persistence on the same key")
        intervals = validated_intervals(row, prediction)

        period_days = (end - start).days + 1
        try:
            observed_days = int(row["observed_days"])
            stated_period_days = int(row["period_days"])
        except ValueError as exc:
            raise ValueError("Invalid validation observation coverage") from exc
        if (str(observed_days) != row["observed_days"]
                or str(stated_period_days) != row["period_days"]
                or stated_period_days != period_days):
            raise ValueError("Validation target has incorrect period length")
        flag = row["is_observed"].strip().lower()
        if flag in {"false", "0"}:
            if row["actual"].strip() or not 0 <= observed_days <= period_days:
                raise ValueError("Unobserved validation keys need a blank actual and valid coverage")
            missing_labels[horizon] += 1
            exact_keys.append({"series": series, "origin": origin.isoformat(),
                               "forecast_horizon": horizon, "forecast_step": step,
                               "target_period_start": start.isoformat(),
                               "target_period_end": end.isoformat(),
                               "prediction_status": status, "is_observed": False})
            continue
        if flag not in {"true", "1"}:
            raise ValueError("is_observed must be true/false or 1/0")
        if not MIN_OBSERVED_DAYS[horizon] <= observed_days <= period_days:
            raise ValueError("Validation target lacks required observed-day coverage")
        actual = finite_number(row["actual"])
        if actual < 0:
            raise ValueError("Validation actual must be nonnegative")
        item = {"series": series, "origin": origin.isoformat(),
                "forecast_horizon": horizon, "forecast_step": step,
                "target_period_start": start.isoformat(),
                "target_period_end": end.isoformat(), "prediction": prediction,
                "champion": champion, "anchor": anchor,
                "prediction_status": status, "status_reason": reason,
                "intervals": intervals, "actual": actual,
                "observed_days": observed_days, "period_days": period_days}
        matched.append(item)
        category, product, _, _, _ = series_parts(series)
        labels = {"horizon": horizon, "series": series,
                  "series_horizon": f"{series}::{horizon}",
                  "product": f"{category}||{product}",
                  "horizon_step": f"{horizon}:{step}", "origin": origin.isoformat(),
                  "horizon_origin": f"{horizon}:{origin.isoformat()}"}
        for name, label in labels.items():
            grouped[name][label].append(item)
        origins_by_horizon[horizon].add(origin)
        targets_by_horizon[horizon].add((start, end))
        targets_by_series_horizon[(series, horizon)].add((start, end))
        origins_by_series_horizon[(series, horizon)].add(origin)
        exact_keys.append({"series": series, "origin": origin.isoformat(),
                           "forecast_horizon": horizon, "forecast_step": step,
                           "target_period_start": start.isoformat(),
                           "target_period_end": end.isoformat(),
                           "prediction_status": status, "is_observed": True})

    if origins != expected_origins:
        raise ValueError("Validation origin population differs from the predeclared selection")
    expected = {(series, origin, horizon, step) for series in declared for origin in expected_origins
                for horizon, count in STEPS.items() for step in range(1, count + 1)}
    if seen != expected:
        raise ValueError("Validation keys do not cover the full declared 7/4/1 forecast mask")
    if any(len(origins_by_horizon[horizon]) < min_origins
           or len(targets_by_horizon[horizon]) < min_origins for horizon in STEPS):
        raise ValueError("Validation requires at least three observed origins and target periods per horizon")
    return {"n": len(matched), "predeclared_origins": sorted(value.isoformat()
                                                                for value in expected_origins),
            "origins_by_horizon": {
                horizon: len(origins_by_horizon[horizon]) for horizon in STEPS},
            "target_periods_by_horizon": {
                horizon: len(targets_by_horizon[horizon]) for horizon in STEPS},
            "target_periods_by_series_horizon": {
                f"{series}::{horizon}": len(periods)
                for (series, horizon), periods in sorted(targets_by_series_horizon.items())},
            "origins_by_series_horizon": {
                f"{series}::{horizon}": len(origins)
                for (series, horizon), origins in sorted(origins_by_series_horizon.items())},
            "overall": _summary(matched),
            "groups": {name: {label: _summary(block) for label, block in sorted(buckets.items())}
                       for name, buckets in grouped.items()},
            "missing_selected_series_by_horizon": {
                horizon: sorted(declared - {row["series"] for row in grouped["horizon"][horizon]})
                for horizon in STEPS},
            "coverage": {"expected_key_count": len(expected),
                         "observed_label_count": len(matched),
                         "missing_label_count_by_horizon": dict(sorted(missing_labels.items())),
                         "prediction_status_counts": status_counts,
                         "forecast_keys": exact_keys},
            "interpretation": "Matched observed original-PHP validation outcomes with complete expected 7/4/1 forecast masks; target periods close before selection. Arithmetic and alignment only; forecast provenance requires review."}
