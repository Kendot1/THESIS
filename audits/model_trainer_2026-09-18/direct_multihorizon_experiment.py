"""Causal direct multi-horizon LightGBM experiment.

This model predicts the relative price change for horizons 1..30 from features
available at the forecast origin. It never recursively consumes its own output.
"""
import json
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "model_trainer"))

from data.preprocessor import DataPreprocessor, SERIES_KEY  # noqa: E402


SNAPSHOT = ROOT / "audits" / "model_trainer_2026-09-18" / "food_prices_snapshot.json"
BASE_RUN = ROOT / "model_trainer" / "artifacts_v2" / "runs" / "20260924T170337Z_14907530"
LAGS = [1, 2, 3, 7, 14, 30]
WINDOWS = [3, 7, 14, 30]


def load_raw():
    payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("rows", payload.get("data", payload))
    return pd.DataFrame(payload)


def metrics(actual, predicted):
    actual, predicted = np.asarray(actual), np.asarray(predicted)
    error = predicted-actual
    return {
        "mae": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "mape": float(np.mean(np.abs(error/actual))*100),
    }


def normalized_score(actual, predicted, persistence):
    result = metrics(actual, predicted)
    baseline = metrics(actual, persistence)
    return sum(result[name]/baseline[name] for name in ["mae", "rmse", "mape"])


class DirectDataset:
    def __init__(self, clean, train):
        self.groups = {}
        self.codes = {}
        for column in SERIES_KEY:
            values = sorted(train[column].astype(str).unique())
            self.codes[column] = {value: i for i, value in enumerate(values)}
        for key, group in clean.groupby(SERIES_KEY, sort=False):
            group = group.sort_values("report_date").reset_index(drop=True)
            identity = "||".join(map(str, key))
            self.groups[identity] = {
                "frame": group,
                "dates": group.report_date.to_numpy(dtype="datetime64[ns]"),
                "prices": group.price_index.to_numpy(float),
                "observed": group.observed_price.to_numpy(float),
                "codes": np.array([
                    self.codes[column].get(str(value), -1)
                    for column, value in zip(SERIES_KEY, key)
                ], dtype=float),
            }

    @staticmethod
    def _cyclical(date):
        date = pd.Timestamp(date)
        return [
            np.sin(2*np.pi*date.dayofweek/7), np.cos(2*np.pi*date.dayofweek/7),
            np.sin(2*np.pi*date.month/12), np.cos(2*np.pi*date.month/12),
            np.sin(2*np.pi*date.dayofyear/365.25),
            np.cos(2*np.pi*date.dayofyear/365.25),
        ]

    def feature(self, item, index, horizon):
        prices = item["prices"]
        if index < 30 or index+horizon >= len(prices):
            return None
        anchor = prices[index]
        history = prices[index-30:index+1]
        if not np.isfinite(anchor) or anchor <= 0 or not np.isfinite(history).all():
            return None
        values = list(item["codes"])
        values.extend(prices[index-lag]/anchor for lag in LAGS)
        for window in WINDOWS:
            recent = prices[index-window+1:index+1]
            values.extend([
                recent.mean()/anchor, recent.std()/anchor,
                np.median(recent)/anchor, recent.min()/anchor, recent.max()/anchor,
            ])
        for lag in [1, 7, 14, 30]:
            values.append(anchor/prices[index-lag]-1)
        for window in [7, 14, 30]:
            recent = prices[index-window+1:index+1]/anchor
            values.append(float(np.polyfit(np.arange(window), recent, 1)[0]))
        origin = item["dates"][index]
        target = item["dates"][index+horizon]
        values.extend(self._cyclical(origin))
        values.extend(self._cyclical(target))
        values.extend([horizon/30, np.sqrt(horizon/30), np.log1p(horizon)])
        return np.asarray(values, dtype=np.float32)

    def training(self, start, end, stride=7):
        x, y = [], []
        start, end = np.datetime64(start), np.datetime64(end)
        for item in self.groups.values():
            dates = item["dates"]
            for index in range(30, len(dates)-30, stride):
                if dates[index] < start or dates[index]+np.timedelta64(30, "D") > end:
                    continue
                anchor = item["prices"][index]
                if not np.isfinite(anchor) or anchor <= 0:
                    continue
                for horizon in range(1, 31):
                    target = item["observed"][index+horizon]
                    if not np.isfinite(target):
                        continue
                    feature = self.feature(item, index, horizon)
                    if feature is not None:
                        x.append(feature)
                        y.append((target-anchor)/anchor)
        return np.asarray(x, np.float32), np.asarray(y, np.float32)

    def forecast_frame(self, frame):
        x, keep = [], []
        for row_index, row in frame.iterrows():
            item = self.groups.get(row.series)
            if item is None:
                continue
            target_origin = np.datetime64(pd.Timestamp(row.origin))
            matches = np.flatnonzero(item["dates"] == target_origin)
            if not len(matches):
                continue
            feature = self.feature(item, int(matches[-1]), int(row.horizon))
            if feature is not None:
                x.append(feature)
                keep.append(row_index)
        return np.asarray(x, np.float32), np.asarray(keep, int)


raw = load_raw()
clean = DataPreprocessor().validate(raw)
train, validation_panel, test_panel = DataPreprocessor.split_three(clean)
dataset = DirectDataset(clean, train)
x_train, y_train = dataset.training(train.report_date.min(), train.report_date.max())
validation = pd.read_csv(BASE_RUN / "validation_forecasts.csv")
test = pd.read_csv(BASE_RUN / "test_forecasts.csv")
x_validation, validation_keep = dataset.forecast_frame(validation)
x_test, test_keep = dataset.forecast_frame(test)
validation = validation.iloc[validation_keep].reset_index(drop=True)
test = test.iloc[test_keep].reset_index(drop=True)

candidates = np.linspace(0, 1, 101)
experiments = []
for objective in ["regression_l1", "regression_l2", "huber"]:
    model = lgb.LGBMRegressor(
        objective=objective, alpha=.9, n_estimators=1500, learning_rate=.02,
        num_leaves=63, min_child_samples=100, max_depth=-1,
        subsample=.8, subsample_freq=5, colsample_bytree=.8,
        reg_alpha=.1, reg_lambda=.5, random_state=42, deterministic=True,
        force_col_wise=True, n_jobs=4, verbosity=-1,
    )
    model.fit(
        x_train, y_train,
        eval_set=[(x_validation, (validation.actual-validation.anchor)/validation.anchor)],
        callbacks=[lgb.early_stopping(100, first_metric_only=True, verbose=False)],
    )
    validation_direct = np.maximum(
        .01, validation.anchor.to_numpy()*(1+model.predict(x_validation)))
    test_direct = np.maximum(.01, test.anchor.to_numpy()*(1+model.predict(x_test)))
    scores = []
    for candidate_weight in candidates:
        prediction = ((1-candidate_weight)*validation.ensemble.to_numpy()
                      + candidate_weight*validation_direct)
        scores.append(normalized_score(
            validation.actual, prediction, validation.persistence))
    weight = float(candidates[np.argmin(scores)])
    test_blend = (1-weight)*test.ensemble.to_numpy()+weight*test_direct
    experiments.append({
        "objective": objective,
        "best_iteration": int(model.best_iteration_),
        "validation_direct": metrics(validation.actual, validation_direct),
        "test_direct": metrics(test.actual, test_direct),
        "validation_selected_direct_weight": weight,
        "test_blend": metrics(test.actual, test_blend),
    })

print(json.dumps({
    "training_samples": int(len(x_train)),
    "feature_count": int(x_train.shape[1]),
    "validation_rows": int(len(validation)),
    "test_rows": int(len(test)),
    "experiments": experiments,
    "current_ensemble": metrics(test.actual, test.ensemble),
}, indent=2))
