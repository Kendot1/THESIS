"""Validation-trained stacked return model using only live-available inputs."""
import argparse
import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2] / "model_trainer" / "artifacts_v2" / "runs"


def design(frame):
    anchor = frame.anchor.to_numpy(float)
    safe = np.maximum(anchor, 1e-8)
    values = pd.DataFrame({
        "lstm_return": (frame.lstm.to_numpy(float)-anchor)/safe,
        "lgbm_return": (frame.lgbm.to_numpy(float)-anchor)/safe,
        "ensemble_return": (frame.ensemble.to_numpy(float)-anchor)/safe,
        "ma7_return": (frame.moving_average7.to_numpy(float)-anchor)/safe,
        "model_disagreement": (frame.lgbm.to_numpy(float)-frame.lstm.to_numpy(float))/safe,
        "horizon": frame.horizon.to_numpy(float)/30,
        "horizon2": np.square(frame.horizon.to_numpy(float)/30),
    })
    categories = frame.series.astype(str).str.split("||", regex=False).str[0]
    for category in ["Corn", "Fish", "Fruits", "Livestock", "Oils", "Poultry", "Rice", "Sugar", "Vegetables"]:
        values[f"category_{category}"] = (categories == category).astype(int).to_numpy()
    return values


def target(frame):
    return ((frame.actual-frame.anchor)/frame.anchor).to_numpy(float)


def metrics(frame, prediction):
    actual = frame.actual.to_numpy(float)
    error = np.asarray(prediction)-actual
    return np.array([
        np.mean(np.abs(error)),
        np.sqrt(np.mean(np.square(error))),
        100*np.mean(np.abs(error)/np.maximum(np.abs(actual), 1e-8)),
    ])


def fit(train, params):
    return lgb.LGBMRegressor(
        objective="huber", random_state=42, deterministic=True,
        force_col_wise=True, verbosity=-1, n_jobs=4, **params,
    ).fit(design(train), target(train))


def predict(frame, model, blend):
    stacked = frame.anchor.to_numpy(float)*(1+model.predict(design(frame)))
    return np.maximum(.01, (1-blend)*frame.ensemble.to_numpy(float)+blend*stacked)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id")
    args = parser.parse_args()
    run = ROOT / args.run_id
    validation = pd.read_csv(run / "validation_forecasts.csv")
    test = pd.read_csv(run / "test_forecasts.csv")
    origins = np.sort(pd.to_datetime(validation.origin).unique())
    cutoff = origins[max(1, int(len(origins)*.6))-1]
    fit_rows = validation[pd.to_datetime(validation.origin) <= cutoff]
    tune_rows = validation[pd.to_datetime(validation.origin) > cutoff]
    configurations = [
        {"n_estimators": 100, "learning_rate": .03, "num_leaves": 7,
         "min_child_samples": 200, "reg_lambda": 5},
        {"n_estimators": 200, "learning_rate": .02, "num_leaves": 7,
         "min_child_samples": 200, "reg_lambda": 10},
        {"n_estimators": 150, "learning_rate": .03, "num_leaves": 15,
         "min_child_samples": 300, "reg_lambda": 10},
        {"n_estimators": 250, "learning_rate": .015, "num_leaves": 15,
         "min_child_samples": 500, "reg_lambda": 20},
    ]
    baseline = metrics(tune_rows, tune_rows.ensemble)
    choices = []
    for index, params in enumerate(configurations):
        model = fit(fit_rows, params)
        for blend in np.linspace(.05, .75, 15):
            candidate = metrics(tune_rows, predict(tune_rows, model, blend))
            ratios = candidate/baseline
            score = float(ratios.mean()+.25*np.maximum(ratios-1, 0).sum())
            choices.append((score, index, float(blend), ratios.tolist()))
    best = min(choices)
    _, index, blend, tune_ratios = best
    final_model = fit(validation, configurations[index])
    validation_prediction = predict(validation, final_model, blend)
    test_prediction = predict(test, final_model, blend)
    result = {
        "cutoff": str(cutoff), "fit_origins": int(pd.to_datetime(fit_rows.origin).nunique()),
        "tune_origins": int(pd.to_datetime(tune_rows.origin).nunique()),
        "parameters": configurations[index], "blend": blend,
        "tune_ratios": tune_ratios,
        "validation_baseline": metrics(validation, validation.ensemble).tolist(),
        "validation_stacked": metrics(validation, validation_prediction).tolist(),
        "test_baseline": metrics(test, test.ensemble).tolist(),
        "test_stacked": metrics(test, test_prediction).tolist(),
    }
    output = Path(__file__).with_name(f"stacked_return_{args.run_id}.json")
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
