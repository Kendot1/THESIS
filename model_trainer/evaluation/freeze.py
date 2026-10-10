"""Seal future incumbent forecasts from Supabase without fitting or publishing.

The issue date is the real Philippine calendar date. Historical cutoffs can
withhold already-reserved labels, but cannot backdate issuance. Missing inputs
use the configured causal fill limit; unforecastable series remain in scope.
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "model_trainer"))
PH_TIME = timezone(timedelta(hours=8))
BUNDLE = ("categorical_mappings.json", "lightgbm_model.txt", "lightgbm_meta.json",
          "lstm_model.pt", "lstm_meta.json", "ensemble.json")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)


def extend_inputs(clean, origin, max_fill_days):
    """Extend the existing daily panel, without creating observed prices."""
    import pandas as pd
    from data.preprocessor import SERIES_KEY

    groups = []
    for key, history in clean.groupby(SERIES_KEY, sort=True):
        history = history.set_index("report_date").sort_index()
        history = history.reindex(pd.date_range(history.index.min(), origin))
        for column, value in zip(SERIES_KEY, key):
            history[column] = value
        history["is_observed"] = history.is_observed.fillna(False).astype(bool)
        history["observed_price"] = history.observed_price.where(history.is_observed)
        history["price_index"] = history.observed_price.ffill(limit=max_fill_days)
        history.index.name = "report_date"
        groups.append(history.reset_index())
    return pd.concat(groups, ignore_index=True)


def freeze(output, through):
    import numpy as np
    import pandas as pd
    from config.settings import get_settings
    from data.fetcher import DataFetcher, iso_report_date
    from data.preprocessor import DataPreprocessor, SERIES_KEY
    from features.builder import FeatureBuilder
    from models.registry import ModelRegistry
    from models.model_store import ModelStore
    from evaluation.frozen_holdout import load_contract

    started = datetime.now(timezone.utc)
    issue_day = started.astimezone(PH_TIME).date()
    through = iso_report_date(through)
    if through > issue_day.isoformat():
        raise ValueError("Source cutoff cannot be after the real issue date")
    origin = pd.Timestamp(issue_day)
    start = issue_day + timedelta(days=1)
    deadline = datetime.combine(start, time.min, PH_TIME)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    # A failed attempt leaves its inputs/selection for diagnosis; never overwrite.
    store = ModelStore()
    run_dir = store.active_path()
    bundle_hashes = {name: digest(run_dir / name) for name in BUNDLE}
    source_hashes = {str(path.relative_to(ROOT)): digest(path)
                     for path in sorted((ROOT / "model_trainer").rglob("*.py"))
                     if all(part not in {".venv", "__pycache__", "tests"}
                            for part in path.relative_to(ROOT / "model_trainer").parts)}
    raw = DataFetcher().fetch_all(through_date=through)
    if pd.to_datetime(raw.report_date).max().date() > issue_day:
        raise ValueError("Source contains future dates")
    snapshot = output / "supabase_inputs.json"
    with snapshot.open("x", encoding="utf-8") as stream:
        stream.write(raw.to_json(orient="records", date_format="iso"))
    cfg = get_settings()
    clean = extend_inputs(DataPreprocessor().validate(raw), origin, cfg.max_fill_days)
    identities = ["||".join(map(str, key)) for key, _ in clean.groupby(SERIES_KEY, sort=True)]
    selection = {
        "selected_at": datetime.now(timezone.utc).isoformat(),
        "model_run_id": run_dir.name,
        "model_metadata_sha256": digest(run_dir / "metadata.json"),
        "model_bundle_sha256": bundle_hashes,
        "declared_series": identities,
        "decision": "Retain incumbent: development replacements do not consistently improve Within-10 and all three error metrics. No holdout outcome used for selection.",
        "input_cutoff": through, "forecast_origin": issue_day.isoformat(),
        "max_fill_days": cfg.max_fill_days,
        "missing_history_policy": "Retain unsupported series in the contract as skipped; no invented price, fallback model, or coverage removal.",
        "evidence": "audits/target5_20261002/GOAL_EVIDENCE_REVIEW.md",
        "evidence_sha256": digest(ROOT / "audits/target5_20261002/GOAL_EVIDENCE_REVIEW.md"),
        "source_code_sha256": source_hashes,
    }
    save_json(output / "selection.json", selection)
    registry = ModelRegistry.get().load_all()
    if registry.run_id != run_dir.name:
        raise ValueError("Active model changed during selection")
    market = FeatureBuilder.category_return_history(clean)
    market_groups = {str(category): group.category_return.fillna(0).to_numpy(float).tolist()
                     for category, group in market.groupby("product_category", sort=False)}
    cases, skipped, series_ids = [], [], []
    for key, history in clean.groupby(SERIES_KEY, sort=True):
        series = "||".join(map(str, key))
        try:
            case = registry.engine._prepare(history, None, market_groups.get(str(key[0]), []))
            if pd.Timestamp(case["origin"]) != origin:
                raise ValueError(f"No usable causal anchor at issue date; last usable date {case['origin'].date()}")
            cases.append(case)
            series_ids.append(series)
        except ValueError as exc:
            skipped.append({"series": series, "reason": str(exc)})
    if not cases:
        raise ValueError("No forecastable series at the real issue date")
    paths = registry.engine.forecast_many(cases, 30)
    if len(paths) != len(cases):
        raise ValueError("Forecast output count changed")
    rows = []
    for series, path in zip(series_ids, paths):
        if not all(len(values) == 30 for values in (path.dates, path.point)):
            raise ValueError("Incomplete forecast path")
        for step in range(30):
            rows.append({"series": series, "origin": issue_day.isoformat(),
                         "target_date": pd.Timestamp(path.dates[step]).date().isoformat(),
                         "horizon": step + 1, "anchor": float(path.anchor),
                         "prediction": float(path.point[step])})
    frame = pd.DataFrame(rows)
    if not np.isfinite(frame[["anchor", "prediction"]]).all().all():
        raise ValueError("Nonfinite predictions")
    if any(digest(run_dir / name) != value for name, value in bundle_hashes.items()):
        raise ValueError("Model weights changed during forecasting")
    if any(digest(ROOT / name) != value for name, value in source_hashes.items()):
        raise ValueError("Inference code changed during forecasting")
    forecasts = output / "forecasts.csv"
    frame.to_csv(forecasts, index=False, mode="x", float_format="%.17g")
    frozen_at = datetime.now(timezone.utc)
    if frozen_at >= deadline:
        raise ValueError("First target day has begun; this attempt cannot be sealed")
    contract = {
        "status": "frozen_predictions_waiting_for_complete_holdout_period",
        "holdout_type": "prospective", "forecasts_frozen_at_utc": frozen_at.isoformat(),
        "forecast_origin": issue_day.isoformat(), "holdout_start": start.isoformat(),
        "holdout_end": (issue_day + timedelta(days=30)).isoformat(), "horizon_days": 30,
        "model_run_id": run_dir.name, "model_bundle_sha256": bundle_hashes,
        "model_metadata_sha256": selection["model_metadata_sha256"],
        "selection_record_sha256": digest(output / "selection.json"),
        "source_code_sha256": source_hashes,
        "snapshot_file": snapshot.name, "snapshot_sha256": digest(snapshot),
        "source": "Supabase public.food_prices; bounded report_date query; fetched during this issuance",
        "snapshot_last_report_date": pd.to_datetime(raw.report_date).max().date().isoformat(),
        "input_cutoff": through, "max_fill_days": cfg.max_fill_days,
        "forecast_file": forecasts.name, "forecast_sha256": digest(forecasts),
        "forecast_rows": len(rows), "forecast_series": len(cases),
        "total_input_series": len(identities), "series_coverage": len(cases) / len(identities),
        "skipped_series_count": len(skipped), "skipped_series": skipped,
        "point_in_time_rule": "Only retrieved source rows through input_cutoff; issue-date padding is unobserved and forward-filled within the existing limit. No backward filling or target-period observations.",
        "selection_rule": "No tuning, selection, or retraining against these outcomes; score once after all 30 days close and actuals are reconciled.",
        "coverage_rule": "Unsupported input series remain in declared scope; partial scores do not establish complete-scope success.",
        "promotion_eligible": False,
        "promotion_note": "Forecast sealing is not final evidence or activation authorization; the incumbent lacks a qualifying new-candidate validation package.",
    }
    save_json(output / "contract.json", contract)
    _, _, integrity = load_contract(output / "contract.json")
    if not integrity["frozen_before_first_target_day"]:
        raise ValueError("Prospective timestamp verification failed")
    print(json.dumps(integrity, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="New evidence directory; never overwritten")
    parser.add_argument("--through", required=True, help="Inclusive Supabase report-date cutoff")
    args = parser.parse_args()
    freeze(args.output, args.through)
