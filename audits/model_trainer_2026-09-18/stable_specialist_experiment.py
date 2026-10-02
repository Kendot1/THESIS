"""Two-way chronological validation for stable product-level specialists."""
import json
from pathlib import Path

import numpy as np
import pandas as pd


RUN = (Path(__file__).resolve().parents[2] / "model_trainer" / "artifacts_v2" /
       "runs" / "20260924T170337Z_14907530")
ALTERNATIVES = ["lstm", "persistence", "moving_average7"]
GROUPS = ["product", "horizon_bin"]


def enrich(frame):
    result = frame.copy()
    parts = result.series.astype(str).str.split("||", regex=False)
    result["product"] = parts.str[:2].str.join("||")
    result["horizon_bin"] = pd.cut(
        result.horizon, [0, 3, 7, 14, 21, 30], labels=False).astype(int)
    return result


def metrics(rows, prediction):
    actual = rows.actual.to_numpy(float)
    error = np.asarray(prediction, dtype=float) - actual
    return np.array([
        np.mean(np.abs(error)),
        np.sqrt(np.mean(np.square(error))),
        100 * np.mean(np.abs(error) / np.maximum(np.abs(actual), 1e-8)),
    ])


def choose(rows):
    base = metrics(rows, rows.ensemble)
    best = (1.0, None, 0.0)
    for name in ALTERNATIVES:
        for weight in np.linspace(.05, .5, 10):
            predicted = (1-weight)*rows.ensemble + weight*rows[name]
            score = float(np.mean(metrics(rows, predicted)/base))
            if score < best[0]:
                best = (score, name, float(weight))
    return best


def improves_all(rows, name, weight, minimum=.0025):
    base = metrics(rows, rows.ensemble)
    predicted = (1-weight)*rows.ensemble + weight*rows[name]
    ratio = metrics(rows, predicted)/base
    return bool((ratio < 1).all() and ratio.mean() <= 1-minimum), ratio


def main():
    validation = enrich(pd.read_csv(RUN / "validation_forecasts.csv"))
    test = enrich(pd.read_csv(RUN / "test_forecasts.csv"))
    origins = np.sort(pd.to_datetime(validation.origin).unique())
    cutoff = origins[len(origins)//2-1]
    early = validation[pd.to_datetime(validation.origin) <= cutoff]
    late = validation[pd.to_datetime(validation.origin) > cutoff]
    early_groups = early.groupby(GROUPS, observed=True)
    late_groups = late.groupby(GROUPS, observed=True)
    state = {}
    diagnostics = {}
    shared = sorted(set(early_groups.groups) & set(late_groups.groups))
    for key in shared:
        left, right = early_groups.get_group(key), late_groups.get_group(key)
        if len(left) < 20 or len(right) < 20:
            continue
        left_choice, right_choice = choose(left), choose(right)
        if left_choice[1] is None or left_choice[1] != right_choice[1]:
            continue
        name = left_choice[1]
        left_on_right, right_ratio = improves_all(right, name, left_choice[2])
        right_on_left, left_ratio = improves_all(left, name, right_choice[2])
        if not (left_on_right and right_on_left):
            continue
        weight = min(left_choice[2], right_choice[2])
        state[key] = (name, weight)
        diagnostics["||".join(map(str, key))] = {
            "model": name, "weight": weight,
            "early_ratio": left_ratio.tolist(), "late_ratio": right_ratio.tolist(),
        }

    def predict(frame):
        result = frame.ensemble.to_numpy(float).copy()
        alternatives = {name: frame[name].to_numpy(float) for name in ALTERNATIVES}
        for key, indices in frame.groupby(GROUPS, observed=True).indices.items():
            choice = state.get(key if isinstance(key, tuple) else (key,))
            if choice is None:
                continue
            name, weight = choice
            result[indices] = ((1-weight)*result[indices]
                               + weight*alternatives[name][indices])
        return result

    validation_prediction = predict(validation)
    test_prediction = predict(test)
    result = {
        "validation_origins": len(origins), "cutoff": str(cutoff),
        "accepted_specialists": len(state),
        "validation_baseline": metrics(validation, validation.ensemble).tolist(),
        "validation_specialists": metrics(validation, validation_prediction).tolist(),
        "test_baseline": metrics(test, test.ensemble).tolist(),
        "test_specialists": metrics(test, test_prediction).tolist(),
        "specialists": diagnostics,
    }
    Path(__file__).with_name("stable_specialist_result.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
