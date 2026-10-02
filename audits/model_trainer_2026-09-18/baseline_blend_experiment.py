"""Chronological validation experiment for robust baseline blending."""
import json
from pathlib import Path

import numpy as np
import pandas as pd


RUN = (Path(__file__).resolve().parents[2] / "model_trainer" / "artifacts_v2" /
       "runs" / "20260924T170337Z_14907530")
ALTERNATIVES = ["persistence", "seasonal7", "moving_average7"]


def enrich(frame):
    result = frame.copy()
    parts = result.series.astype(str).str.split("||", regex=False)
    result["category"] = parts.str[0]
    result["product"] = parts.str[:2].str.join("||")
    result["horizon_bin"] = pd.cut(
        result.horizon, [0, 3, 7, 14, 21, 30], labels=False).astype(int)
    return result


def metrics(actual, predicted):
    actual = np.asarray(actual, dtype=float)
    error = np.asarray(predicted, dtype=float) - actual
    return np.array([
        np.mean(np.abs(error)),
        np.sqrt(np.mean(np.square(error))),
        100 * np.mean(np.abs(error) / np.maximum(np.abs(actual), 1e-8)),
    ])


def fit(frame, groups, max_weight, min_gain, penalty):
    state = {}
    weights = np.linspace(.05, max_weight, int(round(max_weight / .05)))
    for key, rows in frame.groupby(groups, observed=True):
        if len(rows) < 20:
            continue
        if not isinstance(key, tuple):
            key = (key,)
        base = metrics(rows.actual, rows.ensemble)
        best = (1.0, None, 0.0)
        for name in ALTERNATIVES:
            for weight in weights:
                predicted = (1 - weight) * rows.ensemble + weight * rows[name]
                score = float(np.mean(metrics(rows.actual, predicted) / base)
                              + penalty * weight * weight)
                if score < best[0]:
                    best = (score, name, float(weight))
        if best[1] is not None and best[0] <= 1 - min_gain:
            state[key] = (best[1], best[2])
    return state


def predict(frame, groups, state):
    result = frame.ensemble.to_numpy(float).copy()
    alternatives = {name: frame[name].to_numpy(float) for name in ALTERNATIVES}
    for key, indices in frame.groupby(groups, observed=True).indices.items():
        if not isinstance(key, tuple):
            key = (key,)
        choice = state.get(key)
        if choice is None:
            continue
        name, weight = choice
        result[indices] = ((1 - weight) * result[indices]
                           + weight * alternatives[name][indices])
    return result


def score(frame, predicted):
    return float(np.mean(metrics(frame.actual, predicted) /
                         metrics(frame.actual, frame.ensemble)))


def main():
    validation = enrich(pd.read_csv(RUN / "validation_forecasts.csv"))
    test = enrich(pd.read_csv(RUN / "test_forecasts.csv"))
    origins = np.sort(pd.to_datetime(validation.origin).unique())
    cutoff = origins[max(1, int(len(origins) * .6)) - 1]
    fit_rows = validation[pd.to_datetime(validation.origin) <= cutoff].reset_index(drop=True)
    tune_rows = validation[pd.to_datetime(validation.origin) > cutoff].reset_index(drop=True)
    choices = []
    groupings = [
        ["horizon"], ["category", "horizon_bin"],
        ["category", "horizon"], ["product", "horizon_bin"],
    ]
    for groups in groupings:
        for max_weight in [.25, .5, 1.0]:
            for min_gain in [0, .0025, .005, .01, .02]:
                for penalty in [0, .01, .05]:
                    state = fit(fit_rows, groups, max_weight, min_gain, penalty)
                    predicted = predict(tune_rows, groups, state)
                    choices.append((score(tune_rows, predicted), groups, max_weight,
                                    min_gain, penalty, len(state)))
    best = min(choices, key=lambda row: row[0])
    _, groups, max_weight, min_gain, penalty, _ = best
    state = fit(validation, groups, max_weight, min_gain, penalty)
    val_pred = predict(validation.reset_index(drop=True), groups, state)
    test_pred = predict(test.reset_index(drop=True), groups, state)
    result = {
        "validation_origins": len(origins),
        "cutoff": str(cutoff),
        "selected": [best[0], best[1], *best[2:]],
        "final_groups": len(state),
        "validation_baseline": metrics(validation.actual, validation.ensemble).tolist(),
        "validation_blend": metrics(validation.actual, val_pred).tolist(),
        "test_baseline": metrics(test.actual, test.ensemble).tolist(),
        "test_blend": metrics(test.actual, test_pred).tolist(),
        "state": {"||".join(map(str, key)): value for key, value in state.items()},
    }
    output = Path(__file__).with_name("baseline_blend_result.json")
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
