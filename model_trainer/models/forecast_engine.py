"""The single forecast path used by calibration, test evaluation, and serving."""
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from data.preprocessor import SERIES_KEY
from features.builder import FEATURE_COLUMNS, CausalFeatureState, FeatureBuilder
from models.ensemble import EnsembleModel
from models.lightgbm_model import LightGBMModel
from models.lstm_model import LSTMModel


@dataclass
class ForecastPath:
    dates: np.ndarray
    anchor: float
    lstm: np.ndarray
    lgbm: np.ndarray
    point: np.ndarray
    lower: np.ndarray
    upper: np.ndarray


class ForecastEngine:
    def __init__(self, lgbm: LightGBMModel, lstm: LSTMModel,
                 ensemble: Optional[EnsembleModel], builder: FeatureBuilder):
        self.lgbm = lgbm
        self.lstm = lstm
        self.ensemble = ensemble
        self.builder = builder

    @staticmethod
    def _append_day(frame, date, price=np.nan):
        row = {column: np.nan for column in frame.columns}
        for column in SERIES_KEY:
            row[column] = frame.iloc[-1][column]
        row.update({"report_date": pd.Timestamp(date), "price_index": price,
                    "observed_price": np.nan, "is_observed": False})
        return pd.concat([frame, pd.DataFrame([row])], ignore_index=True)

    def forecast(self, history: pd.DataFrame, horizon=30, featured_history=None):
        return self.forecast_many([(history, featured_history)], horizon)[0]

    def forecast_many(self, cases, horizon=30):
        """Batch independent origins while retaining recursive horizon updates."""
        prepared = []
        for case in cases:
            if isinstance(case, dict):
                prepared.append(case)
            else:
                history, featured_history = case
                prepared.append(self._prepare(history, featured_history))
        if not prepared:
            return []
        market_states = {}
        for item in prepared:
            key = (item['origin'], item['category'])
            if key not in market_states:
                initial = item.get('market_history')
                if initial is None:
                    prices = np.asarray(item['state'].prices, dtype=float)
                    initial = prices[1:] / prices[:-1] - 1.0 if len(prices) > 1 else []
                market_states[key] = list(initial)
            item['market_key'] = key
            item['market_state'] = market_states[key]
        sequences = np.concatenate([item["sequence"] for item in prepared])
        anchors = np.asarray([item["anchor"] for item in prepared])
        lstm_paths = self.lstm.predict_paths(sequences, anchors)[:, :horizon]
        lgbm_paths = np.empty((len(prepared), horizon), dtype=float)
        for step in range(1, horizon + 1):
            rows = pd.concat([
                item["state"].row(item["origin"] + pd.Timedelta(days=step),
                                   item['market_state'])
                for item in prepared
            ], ignore_index=True)
            if not np.isfinite(rows[FEATURE_COLUMNS].to_numpy(dtype=float)).all():
                raise ValueError(f"Incomplete LightGBM features at horizon {step}")
            predictions = self.lgbm.predict(rows[FEATURE_COLUMNS])
            lgbm_paths[:, step - 1] = predictions
            category_returns = {}
            for item, prediction in zip(prepared, predictions):
                previous = item['state'].prices[-1]
                if np.isfinite(previous) and previous > 0:
                    category_returns.setdefault(item['market_key'], []).append(
                        float(prediction / previous - 1.0))
                item["state"].append(prediction)
            for key, values in category_returns.items():
                market_states[key].append(float(np.median(values)))
        results = []
        for index, item in enumerate(prepared):
            lstm_path, lgbm_path = lstm_paths[index], lgbm_paths[index]
            point = (self.ensemble.predict(
                lstm_path, lgbm_path, item["anchor"], item["category"],
                item["moving_average7"], item["product"])
                     if self.ensemble is not None else (lstm_path + lgbm_path) / 2)
            if self.ensemble is not None:
                lower, upper = self.ensemble.intervals(
                    point, item["anchor"], category=item["category"])
            else:
                lower, upper = point.copy(), point.copy()
            dates = pd.date_range(item["origin"] + pd.Timedelta(days=1),
                                  periods=horizon).to_numpy()
            results.append(ForecastPath(dates, item["anchor"], lstm_path, lgbm_path,
                                        point, lower, upper))
        return results

    def _prepare(self, history, featured_history, market_history=None):
        history = history.sort_values("report_date").copy()
        finite = history.index[np.isfinite(history.price_index)]
        if len(finite) == 0:
            raise ValueError("Series has no usable causal price")
        history = history.loc[:finite[-1]].reset_index(drop=True)
        origin = pd.Timestamp(history.report_date.iloc[-1])
        anchor = float(history.price_index.iloc[-1])
        if featured_history is None:
            first = self._append_day(history, origin + pd.Timedelta(days=1))
            first_features = self.builder.transform(first)
        else:
            first_features = featured_history[
                featured_history.report_date <= origin + pd.Timedelta(days=1)]
            expected = origin + pd.Timedelta(days=1)
            if first_features.empty or pd.Timestamp(first_features.report_date.iloc[-1]) != expected:
                raise ValueError('Precomputed features do not include the first forecast date')
        sequence, live_anchor = self.lstm.build_live_sequence(first_features)
        if not np.isclose(anchor, live_anchor):
            raise ValueError("LSTM live anchor is not the forecast origin price")
        recent = history.price_index[np.isfinite(history.price_index)].tail(7).to_numpy(float)
        return {"origin": origin, "anchor": anchor,
                "category": str(history.product_category.iloc[-1]), "sequence": sequence,
                "market_history": None if market_history is None else list(market_history),
                "product": (f"{history.product_category.iloc[-1]}||"
                            f"{history.product_name.iloc[-1]}"),
                "moving_average7": float(recent.mean()),
                "state": CausalFeatureState(history, self.builder.encoder)}
