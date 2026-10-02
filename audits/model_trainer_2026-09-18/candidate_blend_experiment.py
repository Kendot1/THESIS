"""Validation-only blend check between the active and experimental LSTM runs."""
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2] / "model_trainer" / "artifacts_v2" / "runs"
ACTIVE = ROOT / "20260924T170337Z_14907530"
CANDIDATE = ROOT / "20260925T072109Z_9be2c0f6"
KEYS = ["series", "origin", "date", "horizon", "actual", "anchor"]


def load(split):
    active = pd.read_csv(ACTIVE / f"{split}_forecasts.csv")
    candidate = pd.read_csv(CANDIDATE / f"{split}_forecasts.csv")
    merged = active.merge(candidate[KEYS + ["lstm", "ensemble"]], on=KEYS,
                          validate="one_to_one", suffixes=("_active", "_candidate"))
    if len(merged) != len(active):
        raise ValueError(f"Mismatched {split} rows")
    return merged


def metrics(actual, predicted):
    error = np.asarray(predicted) - np.asarray(actual)
    return np.array([
        np.mean(np.abs(error)),
        np.sqrt(np.mean(np.square(error))),
        100 * np.mean(np.abs(error) / np.maximum(np.abs(actual), 1e-8)),
    ])


def choose_weights(validation, source):
    weights = {}
    for horizon, rows in validation.groupby("horizon"):
        base = metrics(rows.actual, rows.ensemble_active)
        best = (float("inf"), 0.0)
        for weight in np.linspace(0, .5, 101):
            pred = ((1 - weight) * rows.ensemble_active +
                    weight * rows[source])
            score = np.mean(metrics(rows.actual, pred) / base)
            # Mild shrinkage avoids selecting noisy nonzero weights for tiny gains.
            score += .002 * weight
            if score < best[0]:
                best = (score, float(weight))
        weights[int(horizon)] = best[1]
    return weights


def predict(frame, source, weights):
    weight = frame.horizon.map(weights).fillna(0).to_numpy()
    return ((1 - weight) * frame.ensemble_active.to_numpy() +
            weight * frame[source].to_numpy())


def main():
    validation, test = load("validation"), load("test")
    print("baseline", metrics(test.actual, test.ensemble_active).tolist())
    for source in ["lstm_candidate", "ensemble_candidate"]:
        weights = choose_weights(validation, source)
        val_pred = predict(validation, source, weights)
        test_pred = predict(test, source, weights)
        print(source)
        print("weights", weights)
        print("validation", metrics(validation.actual, val_pred).tolist())
        print("test", metrics(test.actual, test_pred).tolist())


if __name__ == "__main__":
    main()
