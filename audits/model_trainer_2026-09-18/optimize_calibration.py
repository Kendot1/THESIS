"""Nested-validation experiment for ensemble calibration regularization."""
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "model_trainer" / "artifacts_v2" / "runs" / "20260924T121849Z_8610c9f3"
CANDIDATES = np.linspace(0, 1, 101)


def category(frame):
    return frame.series.astype(str).str.split("||", regex=False).str[0]


def metrics(actual, predicted):
    error = np.asarray(predicted) - np.asarray(actual)
    return np.array([
        np.mean(np.abs(error)),
        np.sqrt(np.mean(error**2)),
        np.mean(np.abs(error / np.asarray(actual))) * 100,
    ])


def normalized_score(frame, predicted):
    return float(np.sum(metrics(frame.actual, predicted) /
                        np.maximum(metrics(frame.actual, frame.persistence), 1e-12)))


def fit(frame, penalty=0.0):
    actual = frame.actual.to_numpy(float)
    lstm = frame.lstm.to_numpy(float)
    lgbm = frame.lgbm.to_numpy(float)
    errors = [np.mean(np.abs(actual - ((1-w)*lstm + w*lgbm))) for w in CANDIDATES]
    model_weight = float(CANDIDATES[np.argmin(errors)])
    horizon_trust = np.ones(30)
    for horizon in range(1, 31):
        rows = frame[frame.horizon == horizon]
        if len(rows) < 2:
            continue
        base = (1-model_weight)*rows.lstm.to_numpy(float) + model_weight*rows.lgbm.to_numpy(float)
        scores = [normalized_score(rows, rows.anchor + trust*(base-rows.anchor))
                  for trust in CANDIDATES]
        horizon_trust[horizon-1] = CANDIDATES[np.argmin(scores)]

    categories = category(frame)
    category_trust = {}
    for name in sorted(categories.unique()):
        weights = np.ones(30)
        for horizon in range(1, 31):
            rows = frame[(categories == name) & (frame.horizon == horizon)]
            if len(rows) < 10:
                continue
            base = ((1-model_weight)*rows.lstm.to_numpy(float)
                    + model_weight*rows.lgbm.to_numpy(float))
            horizon_prediction = (rows.anchor.to_numpy(float)
                                  + horizon_trust[horizon-1]
                                  * (base-rows.anchor.to_numpy(float)))
            scores = [
                normalized_score(
                    rows,
                    rows.anchor.to_numpy(float)
                    + trust*(horizon_prediction-rows.anchor.to_numpy(float)),
                ) + penalty*(trust-1.0)**2
                for trust in CANDIDATES[::5]
            ]
            weights[horizon-1] = CANDIDATES[::5][np.argmin(scores)]
        category_trust[name] = weights
    return model_weight, horizon_trust, category_trust


def predict(frame, fitted):
    model_weight, horizon_trust, category_trust = fitted
    horizons = frame.horizon.to_numpy(int)-1
    anchor = frame.anchor.to_numpy(float)
    base = ((1-model_weight)*frame.lstm.to_numpy(float)
            + model_weight*frame.lgbm.to_numpy(float))
    horizon_prediction = anchor + horizon_trust[horizons]*(base-anchor)
    group_trust = np.ones(len(frame))
    for i, (name, horizon) in enumerate(zip(category(frame), horizons)):
        group_trust[i] = category_trust.get(name, np.ones(30))[horizon]
    return anchor + group_trust*(horizon_prediction-anchor)


validation = pd.read_csv(RUN / "validation_forecasts.csv")
test = pd.read_csv(RUN / "test_forecasts.csv")
origins = np.sort(validation.origin.unique())
cutoff = origins[int(len(origins)*2/3)]
inner_train = validation[validation.origin < cutoff]
inner_tune = validation[validation.origin >= cutoff]

penalties = [0.0, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0]
results = []
for penalty in penalties:
    fitted = fit(inner_train, penalty)
    results.append((penalty, normalized_score(inner_tune, predict(inner_tune, fitted))))

selected = min(results, key=lambda row: row[1])[0]
inner_fitted = fit(inner_train, selected)
inner_prediction = predict(inner_tune, inner_fitted)
anomaly_results = []
for threshold in [0.15, 0.2, 0.25, 0.3, 0.5, 0.75, 1.0]:
    anomaly = np.abs(np.log(inner_tune.anchor / inner_tune.moving_average7)) > threshold
    for strength in [0.25, 0.5, 0.75, 1.0]:
        for decay in [1.0, 3.0, 7.0, 14.0]:
            horizon_strength = strength*(1-np.exp(-inner_tune.horizon.to_numpy(float)/decay))
            adjusted = inner_prediction.copy()
            adjusted[anomaly] += horizon_strength[anomaly] * (
                inner_tune.moving_average7.to_numpy(float)[anomaly]-adjusted[anomaly])
            anomaly_results.append(
                ((threshold, strength, decay), normalized_score(inner_tune, adjusted)))
anomaly_parameters = min(anomaly_results, key=lambda row: row[1])[0]
final = fit(validation, selected)
test_prediction = predict(test, final)
validation_prediction = predict(validation, final)
full_anomaly_results = []
for threshold in [0.15, 0.2, 0.25, 0.3, 0.5, 0.75, 1.0]:
    validation_anomaly = (
        np.abs(np.log(validation.anchor / validation.moving_average7)) > threshold)
    for strength in [0.25, 0.5, 0.75, 1.0]:
        for decay in [1.0, 3.0, 7.0, 14.0]:
            horizon_strength = strength*(1-np.exp(-validation.horizon.to_numpy(float)/decay))
            adjusted = validation_prediction.copy()
            adjusted[validation_anomaly] += horizon_strength[validation_anomaly] * (
                validation.moving_average7.to_numpy(float)[validation_anomaly]
                - adjusted[validation_anomaly])
            full_anomaly_results.append(
                ((threshold, strength, decay), normalized_score(validation, adjusted)))
full_anomaly_parameters = min(full_anomaly_results, key=lambda row: row[1])[0]
threshold, strength, decay = anomaly_parameters
anomaly = np.abs(np.log(test.anchor / test.moving_average7)) > threshold
horizon_strength = strength*(1-np.exp(-test.horizon.to_numpy(float)/decay))
adjusted_test_prediction = test_prediction.copy()
adjusted_test_prediction[anomaly] += horizon_strength[anomaly] * (
    test.moving_average7.to_numpy(float)[anomaly]-adjusted_test_prediction[anomaly])
full_threshold, full_strength, full_decay = full_anomaly_parameters
full_anomaly = np.abs(np.log(test.anchor / test.moving_average7)) > full_threshold
full_horizon_strength = full_strength*(
    1-np.exp(-test.horizon.to_numpy(float)/full_decay))
full_adjusted_test_prediction = test_prediction.copy()
full_adjusted_test_prediction[full_anomaly] += full_horizon_strength[full_anomaly] * (
    test.moving_average7.to_numpy(float)[full_anomaly]
    - full_adjusted_test_prediction[full_anomaly])
print({
    "inner_cutoff": cutoff,
    "inner_scores": results,
    "selected_penalty": selected,
    "test_metrics": dict(zip(["mae", "rmse", "mape"], metrics(test.actual, test_prediction))),
    "anomaly_parameters": anomaly_parameters,
    "anomaly_inner_score": min(anomaly_results, key=lambda row: row[1])[1],
    "anomaly_test_rows": int(anomaly.sum()),
    "adjusted_test_metrics": dict(zip(
        ["mae", "rmse", "mape"], metrics(test.actual, adjusted_test_prediction))),
    "full_validation_anomaly_parameters": full_anomaly_parameters,
    "full_validation_anomaly_score": min(full_anomaly_results, key=lambda row: row[1])[1],
    "full_validation_adjusted_test_metrics": dict(zip(
        ["mae", "rmse", "mape"], metrics(test.actual, full_adjusted_test_prediction))),
    "persistence_metrics": dict(zip(["mae", "rmse", "mape"], metrics(test.actual, test.persistence))),
})
