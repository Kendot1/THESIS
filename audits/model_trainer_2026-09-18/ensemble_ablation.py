"""Measure existing ensemble calibration layers without refitting on test."""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "model_trainer"))
from models.ensemble import EnsembleModel  # noqa: E402


def metrics(rows, prediction):
    actual = rows.actual.to_numpy(float)
    error = np.asarray(prediction)-actual
    direction = np.sign(np.asarray(prediction)-rows.anchor.to_numpy(float))
    actual_direction = np.sign(actual-rows.anchor.to_numpy(float))
    moving = actual_direction != 0
    return {
        "mae": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(np.square(error)))),
        "mape": float(100*np.mean(np.abs(error)/np.maximum(np.abs(actual), 1e-8))),
        "direction": float(100*np.mean(direction[moving] == actual_direction[moving])),
    }


def apply(model, frame):
    return model.predict_rows(
        frame.lstm.to_numpy(float), frame.lgbm.to_numpy(float),
        frame.horizon.to_numpy(int), frame.anchor.to_numpy(float),
        frame.series.to_numpy(str), frame.moving_average7.to_numpy(float))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id")
    args = parser.parse_args()
    run = ROOT / "model_trainer" / "artifacts_v2" / "runs" / args.run_id
    model = EnsembleModel(run)
    model.load()
    result = {}
    for split in ["validation", "test"]:
        frame = pd.read_csv(run / f"{split}_forecasts.csv")
        result[split] = {"published": metrics(frame, frame.ensemble)}
        specialists = model.specialist_blends
        model.specialist_blends = {}
        result[split]["without_specialists"] = metrics(frame, apply(model, frame))
        category = model.category_trust_weights
        model.category_trust_weights = {}
        result[split]["without_specialists_or_category"] = metrics(frame, apply(model, frame))
        anomaly = (model.anomaly_threshold, model.anomaly_strength, model.anomaly_decay)
        model.anomaly_threshold, model.anomaly_strength, model.anomaly_decay = 1e9, 0, 1
        result[split]["global_horizon_only"] = metrics(frame, apply(model, frame))
        model.anomaly_threshold, model.anomaly_strength, model.anomaly_decay = anomaly
        model.category_trust_weights = category
        model.specialist_blends = specialists
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
