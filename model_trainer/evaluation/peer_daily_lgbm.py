"""Vegetable-only direct LightGBM with origin-known peer momentum.

Research candidate only. Train on pre-validation labels, use early validation
origins for stopping, and select on later validation origins. Future labels
never determine the peer set; the peer panel is built from all origin histories.
No production activation or prospective holdout access.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from data.preprocessor import DataPreprocessor
from evaluation import horizon_specific as base
from utils.metrics import compute_all_metrics


EXTRA_FEATURES = ("peer_median_return3", "peer_count")
METHODS = ("candidate_shared", "vegetable_control", "hybrid", "persistence")
KEY = ["series", "forecast_origin", "target_start", "target_end", "lead"]
TRAIN_END = pd.Timestamp("2024-08-26")
VALIDATION_END = pd.Timestamp("2025-09-12")
HOLDOUT_START = pd.Timestamp("2026-10-06")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def peer_at_origin(history_index: dict, origin: pd.Timestamp,
                   spec: base.HorizonSpec) -> dict[str, tuple[float, int]]:
    """Compute leave-one-out peers without conditioning on future labels."""
    origin = pd.Timestamp(origin).normalize()
    eligible = {}
    vegetable_keys = []
    for key, (history, _) in history_index.items():
        if key[0] != "Vegetables":
            continue
        series = "||".join(map(str, key))
        vegetable_keys.append(series)
        features = base._history_features(history, origin, spec)
        if (features is not None
                and features["last_observed_age_days"] <= 1
                and np.isfinite(features["return_3"])):
            eligible[series] = float(features["return_3"])
    result = {}
    for series in vegetable_keys:
        other = np.asarray([value for key, value in eligible.items() if key != series],
                           dtype=float)
        result[series] = (float(np.median(other)) if len(other) >= 5 else np.nan,
                          int(len(other)))
    return result


def add_peer_features(frame: pd.DataFrame, history_index: dict,
                      spec: base.HorizonSpec) -> pd.DataFrame:
    if frame.empty:
        raise ValueError("Cannot augment an empty origin feature frame")
    result = frame.copy()
    result["forecast_origin"] = pd.to_datetime(result.forecast_origin).dt.normalize()
    values = {}
    for origin in sorted(result.forecast_origin.unique()):
        for series, pair in peer_at_origin(history_index, origin, spec).items():
            values[(series, origin)] = pair
    pairs = [values.get((row.series, row.forecast_origin), (np.nan, 0))
             for row in result.itertuples()]
    result["peer_median_return3"] = [pair[0] for pair in pairs]
    result["peer_count"] = [pair[1] for pair in pairs]
    return result


def _scores(frame: pd.DataFrame, prediction: str) -> dict:
    actual = frame.actual.to_numpy(dtype=float)
    predicted = frame[prediction].to_numpy(dtype=float)
    summary = compute_all_metrics(actual, predicted)
    if summary["n"] != len(frame) or summary["mape"] is None:
        raise ValueError("Evaluation must retain all positive observed targets")
    return {"n": int(summary["n"]), "mae_php": summary["mae"],
            "rmse_php": summary["rmse"], "mape_pct": summary["mape"],
            "within_5_php_pct": summary["within_5_php_accuracy_pct"],
            "bias_php": float(np.mean(predicted - actual))}


def _paired_report(frame: pd.DataFrame) -> dict:
    return {name: _scores(frame, name) for name in METHODS}


def _selection_report(frame: pd.DataFrame) -> dict:
    overall = _paired_report(frame)
    vegetable = _paired_report(frame.loc[frame.product_category.eq("Vegetables")])
    series = {key: _paired_report(block)
              for key, block in frame.groupby("series", sort=True)}
    lead = {str(int(key)): _paired_report(block)
            for key, block in frame.groupby("lead", sort=True)}
    macro = {}
    for name in METHODS:
        macro[name] = {metric: float(np.mean([row[name][metric] for row in series.values()]))
                       for metric in ("mae_php", "rmse_php", "mape_pct", "within_5_php_pct")}
    regressions = [
        key for key, row in series.items()
        if row["hybrid"]["mae_php"] > 1.10 * min(
            row[name]["mae_php"] for name in
            ("candidate_shared", "vegetable_control", "persistence"))
    ]
    passes = (all(
        block["hybrid"][metric] < block[reference][metric]
        for block in (overall, vegetable)
        for reference in ("candidate_shared", "vegetable_control", "persistence")
        for metric in ("mae_php", "rmse_php", "mape_pct"))
        and overall["hybrid"]["within_5_php_pct"] >= max(
            overall[name]["within_5_php_pct"] for name in
            ("candidate_shared", "vegetable_control", "persistence"))
        and not regressions)
    return {"overall": overall, "vegetables": vegetable,
            "equal_series_macro": macro, "by_series": series, "by_lead": lead,
            "series_mae_regressions_over_10pct_vs_better_reference": regressions,
            "validation_selected": bool(passes)}


def run(source_path: Path, baseline_dir: Path, output_dir: Path) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite candidate: {output_dir}")
    source_path, baseline_dir = Path(source_path), Path(baseline_dir)
    manifest_path = baseline_dir / "selection_manifest.json"
    baseline_path = baseline_dir / "daily" / "validation_predictions.csv"
    baseline_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (sha256(source_path) != baseline_manifest["source_snapshot_sha256"]
            or baseline_manifest["holdout_labels_used"] is not False
            or baseline_manifest["selected_strategy_by_horizon"]["daily"] != "shared"):
        raise ValueError("Baseline and raw snapshot do not match")
    raw = base.load_snapshot(source_path)
    if pd.to_datetime(raw.report_date, errors="coerce").max() >= HOLDOUT_START:
        raise ValueError("Source reaches sealed prospective holdout")
    clean = DataPreprocessor().validate(raw)
    spec = base.SPECS["daily"]
    history_index = base.prepare_history_index(clean, spec)
    baseline = pd.read_csv(baseline_path)
    if baseline.empty or baseline.duplicated(KEY).any():
        raise ValueError("Baseline validation keys are empty or duplicated")
    origins = [pd.Timestamp(value) for value in sorted(baseline.forecast_origin.unique())]
    if len(origins) != 13 or origins[-1] > VALIDATION_END:
        raise ValueError("Unexpected baseline validation schedule")
    tuning_origins, selection_origins = origins[:6], origins[6:]
    if pd.to_datetime(baseline.loc[
            baseline.forecast_origin.isin([str(x.date()) for x in tuning_origins]),
            "target_end"]).max() >= selection_origins[0]:
        raise ValueError("Tuning targets reach later selection origins")
    first = pd.Timestamp(clean.report_date.min()).normalize() + pd.Timedelta(days=30)
    train_origins = base.origin_schedule(spec, first, TRAIN_END, 7)
    train = base.build_examples(clean, spec, train_origins, TRAIN_END, history_index)
    train = train.loc[train.forecast_origin.lt(TRAIN_END)
                      & train.target_end.le(TRAIN_END)].reset_index(drop=True)
    validation = base.build_examples(clean, spec, origins, VALIDATION_END, history_index)
    validation = add_peer_features(validation, history_index, spec)
    train = add_peer_features(train, history_index, spec)
    for column in ("forecast_origin", "target_start", "target_end"):
        baseline[column] = pd.to_datetime(baseline[column]).dt.normalize()
    joined = validation.merge(
        baseline[KEY + ["actual", "anchor", "candidate_shared"]], on=KEY,
        validate="one_to_one", how="outer", indicator=True,
        suffixes=("", "_baseline"))
    if (len(joined) != len(baseline) or not joined._merge.eq("both").all()
            or not np.allclose(joined.actual, joined.actual_baseline, atol=1e-8)
            or not np.allclose(joined.anchor, joined.anchor_baseline, atol=1e-8)):
        raise ValueError("Candidate/baseline validation rows or labels differ")
    vegetable_train = train.loc[train.product_category.eq("Vegetables")]
    tuning = joined.loc[joined.product_category.eq("Vegetables")
                        & joined.forecast_origin.isin(tuning_origins)]
    selection = joined.loc[joined.forecast_origin.isin(selection_origins)].copy()
    if vegetable_train.empty or tuning.empty or selection.empty:
        raise ValueError("Missing vegetable training or validation support")
    control_columns = base.model_feature_columns(spec)
    columns = control_columns + list(EXTRA_FEATURES)
    x_train, categories = base._feature_frame(vegetable_train, columns)
    x_tuning, _ = base._feature_frame(tuning, columns, categories)
    def new_model():
        return lgb.LGBMRegressor(
            objective="regression_l1", n_estimators=800, learning_rate=0.03,
            num_leaves=31, min_child_samples=80, reg_lambda=5.0,
            feature_fraction=0.85, bagging_fraction=0.85, bagging_freq=1,
            random_state=42, n_jobs=4, verbosity=-1)

    model = new_model()
    model.fit(x_train, vegetable_train.target_relative,
              eval_set=[(x_tuning, tuning.target_relative)],
              categorical_feature=list(base.CATEGORICAL_COLUMNS),
              callbacks=[lgb.early_stopping(60, verbose=False)])
    x_train_control, control_categories = base._feature_frame(
        vegetable_train, control_columns)
    x_tuning_control, _ = base._feature_frame(
        tuning, control_columns, control_categories)
    control = new_model()
    control.fit(x_train_control, vegetable_train.target_relative,
                eval_set=[(x_tuning_control, tuning.target_relative)],
                categorical_feature=list(base.CATEGORICAL_COLUMNS),
                callbacks=[lgb.early_stopping(60, verbose=False)])
    selection["hybrid"] = selection.candidate_shared.to_numpy(dtype=float)
    selection["vegetable_control"] = selection.candidate_shared.to_numpy(dtype=float)
    vegetable = selection.loc[selection.product_category.eq("Vegetables")]
    x_vegetable, _ = base._feature_frame(vegetable, columns, categories)
    x_vegetable_control, _ = base._feature_frame(
        vegetable, control_columns, control_categories)
    selection.loc[vegetable.index, "hybrid"] = np.maximum(
        0.01, vegetable.anchor.to_numpy(dtype=float) * (1 + model.predict(x_vegetable)))
    selection.loc[vegetable.index, "vegetable_control"] = np.maximum(
        0.01, vegetable.anchor.to_numpy(dtype=float)
        * (1 + control.predict(x_vegetable_control)))
    result = _selection_report(selection)
    output_dir.mkdir(parents=True)
    model_path = output_dir / "vegetable_shared.txt"
    model.booster_.save_model(str(model_path))
    control_path = output_dir / "vegetable_control.txt"
    control.booster_.save_model(str(control_path))
    selection[KEY + ["product_category", "actual", "anchor", "candidate_shared",
                     "persistence", "vegetable_control", "hybrid", *EXTRA_FEATURES]].to_csv(
        output_dir / "selection_paired_predictions.csv", index=False)
    report = {
        "experiment": "vegetable_only_direct_lightgbm_with_origin_peer_momentum",
        "source_snapshot_sha256": sha256(source_path),
        "baseline_manifest_sha256": sha256(manifest_path),
        "baseline_validation_sha256": sha256(baseline_path),
        "script_sha256": sha256(Path(__file__)),
        "model_sha256": sha256(model_path),
        "vegetable_control_model_sha256": sha256(control_path),
        "model_feature_columns": columns,
        "control_feature_columns": control_columns,
        "fit_rows": int(len(vegetable_train)),
        "tuning_rows": int(len(tuning)),
        "selection_rows": int(len(selection)),
        "best_iteration": int(model.best_iteration_),
        "control_best_iteration": int(control.best_iteration_),
        "training_target_cutoff": str(TRAIN_END.date()),
        "tuning_origins": [str(value.date()) for value in tuning_origins],
        "selection_origins": [str(value.date()) for value in selection_origins],
        "peer_feature_policy": "leave-one-out other vegetables, age<=1d, >=5 peers",
        "selection": result,
        "historical_test_opened": False,
        "holdout_labels_used": False,
        "production_promotion_permitted": False,
        "limitation": (
            "Historical validation of a research model only. Other-category direct "
            "baseline used all 13 validation origins for early stopping. Immutable "
            "source-ingestion timestamps are absent. No calibrated intervals."),
    }
    (output_dir / "report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report


def main() -> None:
    repository = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=repository /
                        "audits/accuracy_goal_20261011/supabase_food_prices_through_20261005.json")
    parser.add_argument("--baseline-dir", type=Path, default=repository /
                        "audits/foodcast_accuracy_20261017/relative5_test_confirmation_v2")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.source, args.baseline_dir, args.output_dir)
    summary = report["selection"]
    print(json.dumps({"selected": summary["validation_selected"],
                      "overall": summary["overall"],
                      "vegetables": summary["vegetables"],
                      "regression_count": len(summary[
                          "series_mae_regressions_over_10pct_vs_better_reference"]),
                      "best_iteration": report["best_iteration"],
                      "control_best_iteration": report["control_best_iteration"]}, indent=2))


if __name__ == "__main__":
    main()
