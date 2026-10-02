"""Chronological validation experiment for persistent ensemble residual bias."""
from pathlib import Path

import numpy as np
import pandas as pd


RUN = (Path(__file__).resolve().parents[2] / "model_trainer" / "artifacts_v2" /
       "runs" / "20260924T170337Z_14907530")


def enrich(frame):
    result = frame.copy()
    pieces = result.series.astype(str).str.split("||", regex=False)
    result["category"] = pieces.str[0]
    result["product"] = pieces.str[:2].str.join("||")
    result["horizon_bin"] = pd.cut(
        result.horizon, [0, 3, 7, 14, 21, 30], labels=False).astype(int)
    return result


def metrics(frame, predicted):
    actual = frame.actual.to_numpy(float)
    error = np.asarray(predicted) - actual
    return np.array([
        np.mean(np.abs(error)),
        np.sqrt(np.mean(np.square(error))),
        100 * np.mean(np.abs(error) / np.maximum(np.abs(actual), 1e-8)),
    ])


def fit_bias(frame, groups, mode, shrink):
    work = frame.copy()
    residual = work.actual - work.ensemble
    work["bias"] = residual / work.anchor if mode == "relative" else residual
    global_bias = work.groupby("horizon_bin", observed=True).bias.mean()
    stats = work.groupby(groups, observed=True).bias.agg(["mean", "count"])
    bins = [index[-1] if groups[-1] == "horizon_bin"
            else int(np.digitize(index[-1], [3, 7, 14, 21], right=True))
            for index in stats.index]
    stats["fallback"] = [global_bias.loc[value] for value in bins]
    stats["value"] = ((stats["count"] * stats["mean"] + shrink * stats["fallback"])
                      / (stats["count"] + shrink))
    return stats.value, global_bias


def apply_bias(frame, state, groups, mode, alpha):
    values, fallback = state
    lookup = pd.MultiIndex.from_frame(frame[groups])
    bias = values.reindex(lookup).to_numpy(float, copy=True)
    missing = ~np.isfinite(bias)
    if missing.any():
        bias[missing] = frame.loc[missing, "horizon_bin"].map(fallback).to_numpy(float)
    scale = frame.anchor.to_numpy(float) if mode == "relative" else 1.0
    return np.maximum(.01, frame.ensemble.to_numpy(float) + alpha * bias * scale)


def score(frame, predicted):
    return float(np.mean(metrics(frame, predicted) / metrics(frame, frame.ensemble)))


def main():
    validation = enrich(pd.read_csv(RUN / "validation_forecasts.csv"))
    test = enrich(pd.read_csv(RUN / "test_forecasts.csv"))
    origins = np.sort(pd.to_datetime(validation.origin).unique())
    cutoff = origins[max(1, int(len(origins) * .6)) - 1]
    fit_rows = validation[pd.to_datetime(validation.origin) <= cutoff]
    tune_rows = validation[pd.to_datetime(validation.origin) > cutoff]
    choices = []
    for groups in [["category", "horizon_bin"],
                   ["product", "horizon_bin"],
                   ["category", "horizon"]]:
        for mode in ["relative", "absolute"]:
            for shrink in [5, 10, 25, 50, 100]:
                state = fit_bias(fit_rows, groups, mode, shrink)
                for alpha in [.25, .5, .75, 1.0]:
                    predicted = apply_bias(tune_rows, state, groups, mode, alpha)
                    choices.append((score(tune_rows, predicted), groups, mode, shrink, alpha))
    best = min(choices, key=lambda row: row[0])
    _, groups, mode, shrink, alpha = best
    state = fit_bias(validation, groups, mode, shrink)
    val_pred = apply_bias(validation, state, groups, mode, alpha)
    test_pred = apply_bias(test, state, groups, mode, alpha)
    print("validation_origins", len(origins), "cutoff", str(cutoff))
    print("selected", best)
    print("validation_baseline", metrics(validation, validation.ensemble).tolist())
    print("validation_corrected", metrics(validation, val_pred).tolist())
    print("test_baseline", metrics(test, test.ensemble).tolist())
    print("test_corrected", metrics(test, test_pred).tolist())


if __name__ == "__main__":
    main()
