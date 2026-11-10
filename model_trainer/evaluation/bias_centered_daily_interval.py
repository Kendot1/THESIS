"""Research-only, causally bias-centered daily prediction intervals.

This is empirical interval calibration, not a finite-sample conformal claim:
the median center and radius are estimated on the same earlier residuals.
The historical evaluation period has already been reused and cannot promote
production confidence or point forecasts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from evaluation.dense_active_interval_replay import HOLDOUT_START, origin_schedule
from evaluation.interval_calibration import interval_metrics, minimum_conformal_sample_count


KEY = ["series", "origin", "date", "horizon"]
LEVELS = (0.80, 0.95)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def completed_history(rows: pd.DataFrame, origin: pd.Timestamp) -> pd.DataFrame:
    """Use only residuals from forecast paths fully elapsed before origin."""
    origin = pd.Timestamp(origin).normalize()
    past = rows.loc[
        (rows.origin < origin)
        & (rows.origin + pd.Timedelta(days=14) < origin)
        & (rows.date < origin)
    ].sort_values("origin")
    if past.duplicated("origin").any():
        raise ValueError("Duplicate forecast origins in one series/lead history")
    return past


def centered_calibration(history: pd.DataFrame, level: float) -> dict | None:
    minimum = minimum_conformal_sample_count(level)
    if len(history) < minimum or history.origin.nunique() < minimum:
        return None
    residuals = history.actual.to_numpy(dtype=float) - history.ensemble_path.to_numpy(dtype=float)
    if not np.isfinite(residuals).all():
        raise ValueError("Nonfinite calibration residual")
    center = float(np.median(residuals))
    rank = math.ceil((len(residuals) + 1) * level - 1e-12)
    if rank > len(residuals):
        return None
    radius = float(np.sort(np.abs(residuals - center))[rank - 1])
    return {
        "center_php": center,
        "radius_php": radius,
        "origin_count": int(history.origin.nunique()),
        "latest_target_date": str(history.date.max().date()),
    }


def bounds(point: float, calibration: dict) -> tuple[float, float]:
    lower = max(0.01, point + calibration["center_php"] - calibration["radius_php"])
    upper = max(lower, point + calibration["center_php"] + calibration["radius_php"])
    return float(lower), float(upper)


def _score(rows: pd.DataFrame, method: str, level: float) -> dict:
    scored = interval_metrics(rows.actual, rows[f"{method}_lower"],
                              rows[f"{method}_upper"], nominal_level=level)
    scored["upper_miss_count"] = int((rows.actual > rows[f"{method}_upper"]).sum())
    scored["lower_miss_count"] = int((rows.actual < rows[f"{method}_lower"]).sum())
    return scored


def compare(observed: pd.DataFrame, paired: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    required_observed = set(KEY) | {"actual", "ensemble_path"}
    required_paired = set(KEY) | {
        "actual", "point", "nominal_level", "fixed_lower", "fixed_upper",
        "expanding_lower", "expanding_upper",
    }
    if not required_observed.issubset(observed) or not required_paired.issubset(paired):
        raise ValueError("Input replay or paired intervals lack required columns")
    observed, paired = observed.copy(), paired.copy()
    for frame in (observed, paired):
        frame["origin"] = pd.to_datetime(frame.origin).dt.normalize()
        frame["date"] = pd.to_datetime(frame.date).dt.normalize()
    if (observed.empty or paired.empty or observed.duplicated(KEY).any()
            or paired.duplicated(KEY + ["nominal_level"]).any()
            or observed.date.max() >= HOLDOUT_START
            or paired.date.max() >= HOLDOUT_START
            or set(paired.nominal_level.unique()) - set(LEVELS)):
        raise ValueError("Empty, duplicate, unsupported-level, or holdout rows")
    if (not np.isfinite(observed[["actual", "ensemble_path"]].to_numpy(dtype=float)).all()
            or (observed.actual <= 0).any()):
        raise ValueError("Invalid observed price/point")
    for column in ("actual", "point", "fixed_lower", "fixed_upper",
                   "expanding_lower", "expanding_upper"):
        if not np.isfinite(paired[column].to_numpy(dtype=float)).all():
            raise ValueError(f"Nonfinite paired {column}")
    reference = paired.merge(
        observed[KEY + ["actual", "ensemble_path"]], on=KEY,
        how="left", validate="many_to_one", suffixes=("", "_observed"), indicator=True)
    if (not reference._merge.eq("both").all()
            or not np.allclose(reference.actual, reference.actual_observed, atol=1e-8)
            or not np.allclose(reference.point, reference.ensemble_path, atol=1e-8)):
        raise ValueError("Paired bounds do not align with observed replay targets")

    calibration_origins, evaluation_origins = origin_schedule()
    allowed = set(calibration_origins) | set(evaluation_origins)
    history = observed.loc[observed.origin.isin(allowed)].copy()
    if not paired.origin.isin(evaluation_origins).all():
        raise ValueError("Paired evaluation origin is outside the frozen schedule")
    generated = []
    for (series, lead), group in paired.groupby(["series", "horizon"], sort=True):
        source = history.loc[history.series.eq(series) & history.horizon.eq(lead)]
        for origin, vintage in group.groupby("origin", sort=True):
            past = completed_history(source, origin)
            for row in vintage.itertuples(index=False):
                calibration = centered_calibration(past, row.nominal_level)
                if calibration is None:
                    continue
                lower, upper = bounds(float(row.point), calibration)
                generated.append({
                    "series": series, "origin": origin, "date": row.date,
                    "horizon": int(lead), "actual": float(row.actual),
                    "point": float(row.point), "nominal_level": float(row.nominal_level),
                    "fixed_lower": float(row.fixed_lower), "fixed_upper": float(row.fixed_upper),
                    "expanding_lower": float(row.expanding_lower),
                    "expanding_upper": float(row.expanding_upper),
                    "centered_lower": lower, "centered_upper": upper,
                    "center_php": calibration["center_php"],
                    "radius_php": calibration["radius_php"],
                    "calibration_origins": calibration["origin_count"],
                    "latest_calibration_target_date": calibration["latest_target_date"],
                })
    if not generated:
        raise ValueError("No supported bias-centered interval rows")
    scored = pd.DataFrame(generated)
    if (pd.to_datetime(scored.latest_calibration_target_date) >= scored.origin).any():
        raise AssertionError("Future calibration residual reached evaluation")
    summary = {}
    for level, rows in scored.groupby("nominal_level", sort=True):
        methods = ("fixed", "expanding", "centered")
        summarize = lambda group: {method: _score(group, method, level) for method in methods}
        summary[f"{level:.2f}"] = {
            "sample_count": int(len(rows)),
            "series_count": int(rows.series.nunique()),
            "pooled": summarize(rows),
            "by_product": {series: summarize(group) for series, group in rows.groupby("series")},
            "by_lead": {str(int(lead)): summarize(group)
                        for lead, group in rows.groupby("horizon")},
            "by_quarter": {quarter: summarize(group) for quarter, group in rows.groupby(
                rows.date.dt.to_period("Q").astype(str))},
        }
    return summary, scored


def run(replay_dir: Path, prior_dir: Path, output_dir: Path) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite experiment: {output_dir}")
    replay_report_path = replay_dir / "report.json"
    replay_path = replay_dir / "replay_observed_targets.csv"
    prior_report = json.loads((prior_dir / "report.json").read_text(encoding="utf-8"))
    if (prior_report["replay_report_sha256"] != sha256(replay_report_path)
            or prior_report["replay_observed_sha256"] != sha256(replay_path)
            or prior_report["holdout_labels_used"] is not False):
        raise ValueError("Earlier interval comparison does not bind this replay")
    replay_report = json.loads(replay_report_path.read_text(encoding="utf-8"))
    if replay_report.get("saved_active_forecast_parity_passed") is not True:
        raise ValueError("Exact active-vintage replay parity was not verified")
    paired_path = prior_dir / "paired_intervals.csv"
    observed = pd.read_csv(replay_path, float_precision="round_trip")
    paired = pd.read_csv(paired_path, float_precision="round_trip")
    summary, rows = compare(observed, paired)
    report = {
        "experiment": "completed_origin_bias_centered_daily_intervals",
        "source_replay_report_sha256": sha256(replay_report_path),
        "source_replay_observed_sha256": sha256(replay_path),
        "source_paired_intervals_sha256": sha256(paired_path),
        "script_sha256": sha256(Path(__file__)),
        "method": "median signed residual plus/minus finite-rank absolute deviation",
        "formal_conformal_coverage_claim": False,
        "historical_test_reused": True,
        "holdout_labels_used": False,
        "production_promotion_permitted": False,
        "summary": summary,
    }
    output_dir.mkdir(parents=True)
    rows.to_csv(output_dir / "paired_centered_intervals.csv", index=False)
    (output_dir / "report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report


def main() -> None:
    repository = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay-dir", type=Path, default=repository /
                        "audits/foodcast_accuracy_20261017/dense_active_interval_replay_exact_vintage")
    parser.add_argument("--prior-dir", type=Path, default=repository /
                        "audits/foodcast_accuracy_20261017/prequential_interval_exact_vintage")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.replay_dir, args.prior_dir, args.output_dir)
    for level, values in result["summary"].items():
        print(level, values["sample_count"], values["pooled"])


if __name__ == "__main__":
    main()
