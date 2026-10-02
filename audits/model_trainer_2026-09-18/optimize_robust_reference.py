"""Compare causal trailing references for anomaly mean reversion."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "model_trainer"))

from data.preprocessor import DataPreprocessor, SERIES_KEY  # noqa: E402


RUN = ROOT / "model_trainer" / "artifacts_v2" / "runs" / "20260924T121849Z_8610c9f3"
SNAPSHOT = ROOT / "audits" / "model_trainer_2026-09-18" / "food_prices_snapshot.json"
CANDIDATES = np.linspace(0, 1, 101)


def category(frame):
    return frame.series.astype(str).str.split("||", regex=False).str[0]


def metrics(actual, predicted):
    error = np.asarray(predicted)-np.asarray(actual)
    return np.array([
        np.mean(np.abs(error)),
        np.sqrt(np.mean(error**2)),
        np.mean(np.abs(error/np.asarray(actual)))*100,
    ])


def normalized_score(frame, predicted):
    return float(np.sum(
        metrics(frame.actual, predicted)
        / np.maximum(metrics(frame.actual, frame.persistence), 1e-12)))


def fit(frame, penalty=0.0):
    actual = frame.actual.to_numpy(float)
    lstm = frame.lstm.to_numpy(float)
    lgbm = frame.lgbm.to_numpy(float)
    errors = [np.mean(np.abs(actual-((1-w)*lstm+w*lgbm))) for w in CANDIDATES]
    model_weight = float(CANDIDATES[np.argmin(errors)])
    horizon_trust = np.ones(30)
    for horizon in range(1, 31):
        rows = frame[frame.horizon == horizon]
        base = ((1-model_weight)*rows.lstm.to_numpy(float)
                + model_weight*rows.lgbm.to_numpy(float))
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
                    rows, rows.anchor.to_numpy(float)
                    + trust*(horizon_prediction-rows.anchor.to_numpy(float)))
                + penalty*(trust-1.0)**2
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
    horizon_prediction = anchor+horizon_trust[horizons]*(base-anchor)
    group_trust = np.ones(len(frame))
    for i, (name, horizon) in enumerate(zip(category(frame), horizons)):
        group_trust[i] = category_trust.get(name, np.ones(30))[horizon]
    return anchor+group_trust*(horizon_prediction-anchor)


def load_raw():
    payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("rows", payload.get("data", payload))
    return pd.DataFrame(payload)


def add_references(frame, clean):
    groups = {
        "||".join(map(str, key)): group.sort_values("report_date")
        for key, group in clean.groupby(SERIES_KEY, sort=False)
    }
    cache = {}
    for identity, origin in frame[["series", "origin"]].drop_duplicates().itertuples(index=False):
        history = groups[identity]
        values = history.loc[
            history.report_date <= pd.Timestamp(origin), "price_index"
        ].dropna().to_numpy(float)
        for window in [7, 14, 30]:
            recent = values[-window:]
            cache[(identity, origin, f"median{window}")] = float(np.median(recent))
    result = frame.copy()
    for window in [7, 14, 30]:
        result[f"median{window}"] = [
            cache[(identity, origin, f"median{window}")]
            for identity, origin in result[["series", "origin"]].itertuples(index=False)
        ]
    return result


def tune_reversion(frame, base, reference_column):
    anchor = frame.anchor.to_numpy(float)
    reference = frame[reference_column].to_numpy(float)
    horizons = frame.horizon.to_numpy(float)
    best = (normalized_score(frame, base), None)
    for threshold in [.1, .15, .2, .25, .3, .4, .5, .75, 1.0]:
        anomaly = np.abs(np.log(anchor/reference)) > threshold
        if not anomaly.any():
            continue
        for strength in [.25, .5, .75, 1.0]:
            for decay in [.5, 1.0, 2.0, 3.0, 7.0, 14.0]:
                horizon_strength = strength*(1-np.exp(-horizons/decay))
                adjusted = base.copy()
                adjusted[anomaly] += horizon_strength[anomaly]*(
                    reference[anomaly]-adjusted[anomaly])
                score = normalized_score(frame, adjusted)
                if score < best[0]:
                    best = (score, (threshold, strength, decay))
    return best


def apply_reversion(frame, base, reference_column, parameters):
    if parameters is None:
        return base
    threshold, strength, decay = parameters
    anchor = frame.anchor.to_numpy(float)
    reference = frame[reference_column].to_numpy(float)
    horizons = frame.horizon.to_numpy(float)
    anomaly = np.abs(np.log(anchor/reference)) > threshold
    horizon_strength = strength*(1-np.exp(-horizons/decay))
    adjusted = base.copy()
    adjusted[anomaly] += horizon_strength[anomaly]*(reference[anomaly]-adjusted[anomaly])
    return adjusted


clean = DataPreprocessor().validate(load_raw())
validation = add_references(pd.read_csv(RUN / "validation_forecasts.csv"), clean)
test = add_references(pd.read_csv(RUN / "test_forecasts.csv"), clean)
calibrator = fit(validation, penalty=0.0)
validation_base = predict(validation, calibrator)
test_base = predict(test, calibrator)

results = []
for reference in ["moving_average7", "median7", "median14", "median30"]:
    score, parameters = tune_reversion(validation, validation_base, reference)
    test_prediction = apply_reversion(test, test_base, reference, parameters)
    results.append({
        "reference": reference,
        "validation_score": score,
        "parameters": parameters,
        "test_metrics": dict(zip(["mae", "rmse", "mape"],
                                 metrics(test.actual, test_prediction))),
    })
print(results)
