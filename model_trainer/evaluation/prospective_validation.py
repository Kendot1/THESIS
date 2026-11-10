"""Validate matched, pre-selection 14/4/1 historical comparison rows."""
from collections import defaultdict
from pathlib import Path

from .frozen_holdout import PHILIPPINE_TIME, calendar_date, csv_rows, finite_number, series_parts
from .prospective_horizons import (
    MIN_OBSERVED_DAYS, STEPS, _summary, _timestamp, target_bounds,
    validated_intervals,
)


def compare_validation(path, selection, *, min_origins=3):
    """Recompute candidate/incumbent/persistence errors on identical observed rows.

    This checks dates, target definitions, scope, and arithmetic. It cannot
    prove predictions were generated causally; that remains provenance review.
    """
    path = Path(path)
    selected_at = _timestamp(selection["selected_at"])
    selection_origin = calendar_date(selection["forecast_origin"])
    last_allowed = min(selection_origin, selected_at.astimezone(PHILIPPINE_TIME).date())
    declared = set(selection["declared_series"])
    required = {"series", "origin", "forecast_horizon", "forecast_step",
                "target_period_start", "target_period_end", "actual",
                "prediction", "champion", "anchor", "is_observed",
                "observed_days", "period_days"}
    with path.open("rb") as stream:
        rows = list(csv_rows(stream.read(), required))
    if not rows:
        raise ValueError("Validation has no observed matched rows")
    matched, seen = [], set()
    grouped = {name: defaultdict(list) for name in
               ("horizon", "series", "series_horizon", "product", "horizon_step", "origin",
                "horizon_origin")}
    origins_by_horizon = defaultdict(set)
    targets_by_horizon = defaultdict(set)
    targets_by_series_horizon = defaultdict(set)
    origins_by_series_horizon = defaultdict(set)
    for row in rows:
        series_parts(row["series"])
        if row["series"] not in declared:
            raise ValueError("Validation series differs from selected scope")
        origin = calendar_date(row["origin"])
        horizon = row["forecast_horizon"]
        try:
            step = int(row["forecast_step"])
        except ValueError as exc:
            raise ValueError("Invalid validation forecast step") from exc
        if str(step) != row["forecast_step"]:
            raise ValueError("Validation step must be a canonical integer")
        start, end = target_bounds(origin, horizon, step)
        if (origin >= selection_origin or end >= last_allowed
                or calendar_date(row["target_period_start"]) != start
                or calendar_date(row["target_period_end"]) != end):
            raise ValueError("Validation target overlaps selection or has wrong period bounds")
        key = row["series"], origin, horizon, step
        if key in seen:
            raise ValueError("Duplicate matched validation key")
        seen.add(key)
        if row["is_observed"].strip().lower() not in {"true", "1"}:
            raise ValueError("Validation rows must have observed, non-imputed labels")
        period_days = (end - start).days + 1
        try:
            observed_days = int(row["observed_days"])
            stated_period_days = int(row["period_days"])
        except ValueError as exc:
            raise ValueError("Invalid validation observation coverage") from exc
        if (str(observed_days) != row["observed_days"]
                or str(stated_period_days) != row["period_days"]
                or stated_period_days != period_days
                or not MIN_OBSERVED_DAYS[horizon] <= observed_days <= period_days):
            raise ValueError("Validation target lacks the required observed-day coverage")
        values = {name: finite_number(row[name]) for name in
                  ("actual", "prediction", "champion", "anchor")}
        if values["actual"] < 0 or any(values[name] <= 0 for name in
                                    ("prediction", "champion", "anchor")):
            raise ValueError("Invalid validation actual or point price")
        item = {"series": row["series"], "origin": origin.isoformat(),
                "forecast_horizon": horizon, "forecast_step": step,
                "target_period_start": start.isoformat(),
                "target_period_end": end.isoformat(),
                "intervals": validated_intervals(row, values["prediction"]), **values}
        matched.append(item)
        category, product, _, _, _ = series_parts(row["series"])
        labels = {"horizon": horizon, "series": row["series"],
                  "series_horizon": f"{row['series']}::{horizon}",
                  "product": f"{category}||{product}",
                  "horizon_step": f"{horizon}:{step}", "origin": origin.isoformat(),
                  "horizon_origin": f"{horizon}:{origin.isoformat()}"}
        for name, label in labels.items():
            grouped[name][label].append(item)
        origins_by_horizon[horizon].add(origin)
        targets_by_horizon[horizon].add((start, end))
        targets_by_series_horizon[(row["series"], horizon)].add((start, end))
        origins_by_series_horizon[(row["series"], horizon)].add(origin)
    if any(len(origins_by_horizon[horizon]) < min_origins
           or len(targets_by_horizon[horizon]) < min_origins for horizon in STEPS):
        raise ValueError("Validation requires at least three origins and target periods per horizon")
    return {"n": len(matched), "origins_by_horizon": {
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
            "interpretation": "Matched observed original-PHP validation outcomes; target periods close before selection. Arithmetic and alignment only; forecast provenance requires review."}
