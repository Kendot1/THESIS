"""Research-only fixed, expanding and recent-residual daily intervals.

The active-weight replay is not source-vintage-parity clean and its historical
evaluation period has been reused. This comparison cannot promote intervals.
At each origin, only residual target dates on/before that origin may update the
recent calibration window. Source ingestion timestamps are unavailable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from evaluation.dense_active_interval_replay import (
    HOLDOUT_START, KEYS, origin_schedule,
)
from evaluation.interval_calibration import (
    calibrate_residual_interval, interval_from_calibration, interval_metrics,
)


LEVELS = (0.80, 0.95)
RECENT_ORIGINS = 20  # Fixed before reading the evaluation comparison.


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def eligible_history(calibration: pd.DataFrame, earlier_evaluation: pd.DataFrame,
                     origin: pd.Timestamp, *, recent_origins: int = RECENT_ORIGINS
                     ) -> pd.DataFrame:
    """Select only already observed residuals and then the latest origins."""
    if recent_origins < 19:
        raise ValueError("95% finite-sample intervals require at least 19 origins")
    origin = pd.Timestamp(origin).normalize()
    history = pd.concat([calibration, earlier_evaluation], ignore_index=True)
    history = history.loc[(history.origin < origin) & (history.date <= origin)]
    if history.duplicated("origin").any():
        raise ValueError("Calibration series/lead has duplicate forecast origins")
    return history.sort_values("origin").tail(recent_origins)


def _metrics(rows: pd.DataFrame, prefix: str, level: float) -> dict:
    return interval_metrics(rows.actual, rows[f"{prefix}_lower"],
                            rows[f"{prefix}_upper"], nominal_level=level)


def compare(observed: pd.DataFrame, *, recent_origins: int = RECENT_ORIGINS
            ) -> tuple[dict, pd.DataFrame]:
    required = set(KEYS + ["actual", "ensemble_path"])
    if not required.issubset(observed.columns):
        raise ValueError(f"Observed replay lacks {sorted(required - set(observed.columns))}")
    observed = observed.copy()
    observed["origin"] = pd.to_datetime(observed.origin).dt.normalize()
    observed["date"] = pd.to_datetime(observed.date).dt.normalize()
    if (observed.empty or observed.duplicated(KEYS).any()
            or observed.date.max() >= HOLDOUT_START
            or not observed.date.eq(observed.origin + pd.to_timedelta(observed.horizon, unit="D")).all()
            or not np.isfinite(observed.actual.to_numpy(dtype=float)).all()
            or not np.isfinite(observed.ensemble_path.to_numpy(dtype=float)).all()):
        raise ValueError("Replay has duplicate, noncausal, nonfinite, or holdout targets")
    calibration_origins, evaluation_origins = origin_schedule()
    calibration = observed.loc[observed.origin.isin(calibration_origins)]
    evaluation = observed.loc[observed.origin.isin(evaluation_origins)]
    if (calibration.empty or evaluation.empty
            or calibration.date.max() >= evaluation.date.min()):
        raise ValueError("Calibration/evaluation windows overlap or are empty")

    scored = []
    for (series, lead), later in evaluation.groupby(["series", "horizon"], sort=True):
        earlier = calibration.loc[calibration.series.eq(series)
                                  & calibration.horizon.eq(lead)].sort_values("origin")
        fixed = calibrate_residual_interval(
            earlier.actual, earlier.ensemble_path, origins=earlier.origin,
            nominal_level=LEVELS[0])
        if fixed is None:
            continue
        later = later.sort_values("origin")
        for level in LEVELS:
            fixed = calibrate_residual_interval(
                earlier.actual, earlier.ensemble_path, origins=earlier.origin,
                nominal_level=level)
            if fixed is None:
                continue
            for _, row in later.iterrows():
                available = eligible_history(
                    earlier, later, row.origin,
                    recent_origins=max(19, len(earlier) + len(later)))
                history = available.tail(recent_origins)
                recent = calibrate_residual_interval(
                    history.actual, history.ensemble_path, origins=history.origin,
                    nominal_level=level)
                expanding = calibrate_residual_interval(
                    available.actual, available.ensemble_path, origins=available.origin,
                    nominal_level=level)
                if recent is None or expanding is None:
                    continue
                fixed_bounds = interval_from_calibration(row.ensemble_path, fixed)
                recent_bounds = interval_from_calibration(row.ensemble_path, recent)
                expanding_bounds = interval_from_calibration(row.ensemble_path, expanding)
                scored.append({
                    "series": series, "origin": row.origin, "date": row.date,
                    "horizon": int(lead), "actual": float(row.actual),
                    "point": float(row.ensemble_path), "nominal_level": level,
                    "fixed_lower": fixed_bounds[0], "fixed_upper": fixed_bounds[1],
                    "recent_lower": recent_bounds[0], "recent_upper": recent_bounds[1],
                    "expanding_lower": expanding_bounds[0],
                    "expanding_upper": expanding_bounds[1],
                    "recent_calibration_origins": int(recent["origin_count"]),
                    "recent_latest_target_date": history.date.max(),
                    "expanding_calibration_origins": int(expanding["origin_count"]),
                    "expanding_latest_target_date": available.date.max(),
                })
    if not scored:
        raise ValueError("No comparable supported interval rows")
    scored = pd.DataFrame(scored)
    if ((scored.recent_latest_target_date > scored.origin).any()
            or (scored.expanding_latest_target_date > scored.origin).any()):
        raise AssertionError("Future residual reached recent calibration")
    summary = {}
    for level, level_rows in scored.groupby("nominal_level", sort=True):
        by_product = {}
        for series, rows in level_rows.groupby("series", sort=True):
            by_product[str(series)] = {
                "fixed": _metrics(rows, "fixed", level),
                "recent": _metrics(rows, "recent", level),
                "expanding": _metrics(rows, "expanding", level),
            }
        by_quarter = {}
        quarter = level_rows.date.dt.to_period("Q").astype(str)
        for label, rows in level_rows.groupby(quarter, sort=True):
            by_quarter[label] = {
                "fixed": _metrics(rows, "fixed", level),
                "recent": _metrics(rows, "recent", level),
                "expanding": _metrics(rows, "expanding", level),
            }
        summary[f"{level:.2f}"] = {
            "sample_count": int(len(level_rows)),
            "series_count": len(by_product),
            "fixed": _metrics(level_rows, "fixed", level),
            "recent": _metrics(level_rows, "recent", level),
            "expanding": _metrics(level_rows, "expanding", level),
            "by_product": by_product,
            "by_quarter": by_quarter,
            "by_lead": {
                str(int(lead)): {
                    "fixed": _metrics(rows, "fixed", level),
                    "recent": _metrics(rows, "recent", level),
                    "expanding": _metrics(rows, "expanding", level),
                }
                for lead, rows in level_rows.groupby("horizon", sort=True)
            },
        }
    return summary, scored


def run(replay_dir: Path, output_dir: Path) -> dict:
    replay_dir, output_dir = Path(replay_dir), Path(output_dir)
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite adaptation output: {output_dir}")
    replay = json.loads((replay_dir / "report.json").read_text(encoding="utf-8"))
    if (replay.get("holdout_labels_used") is not False
            or not isinstance(replay.get("saved_active_forecast_parity_passed"), bool)):
        raise ValueError("Expected a verified pre-holdout replay report")
    path = replay_dir / "replay_observed_targets.csv"
    observed = pd.read_csv(path, float_precision="round_trip")
    summary, scored = compare(observed)
    for level, values in summary.items():
        reference = replay["levels"][level]["pooled"]
        fixed = values["fixed"]
        if (fixed["sample_count"] != reference["sample_count"]
                or not np.isclose(fixed["coverage"], reference["coverage"], atol=1e-12)
                or not np.isclose(fixed["mean_width_php"],
                                  reference["mean_width_php"], atol=1e-8)):
            raise ValueError(f"Fixed intervals do not reproduce replay scores at {level}")
    report = {
        "experiment": "prequential_fixed_expanding_recent_residual_calibration",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "replay_report_sha256": _sha256(replay_dir / "report.json"),
        "replay_observed_sha256": _sha256(path),
        "script_sha256": _sha256(Path(__file__)),
        "recent_origin_window": RECENT_ORIGINS,
        "expanding_origin_window": "all_prior_observed_targets",
        "nominal_levels": list(LEVELS),
        "forecast_leads": 14,
        "historical_test_reused_for_development": True,
        "saved_active_forecast_parity_passed": replay["saved_active_forecast_parity_passed"],
        "holdout_labels_used": False,
        "production_promotion_permitted": False,
        "availability_caveat": (
            "Only report-date availability is known, not immutable source-ingestion time. "
            "Weekly-origin 14-day targets overlap, so residuals are dependent."
        ),
        "summary": summary,
    }
    output_dir.mkdir(parents=True)
    scored.to_csv(output_dir / "paired_intervals.csv", index=False)
    (output_dir / "report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.replay_dir, args.output_dir)
    print(json.dumps({level: {
        "fixed": values["fixed"], "recent": values["recent"],
        "expanding": values["expanding"]}
        for level, values in report["summary"].items()}, indent=2))


if __name__ == "__main__":
    main()
