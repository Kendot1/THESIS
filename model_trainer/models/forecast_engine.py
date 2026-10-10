"""The single forecast path used by calibration, test evaluation, and serving."""
from copy import deepcopy
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
        """Batch independent origins and extend long forecasts in model-sized chunks."""
        prepared = []
        for case in cases:
            if isinstance(case, dict):
                prepared.append(case)
            else:
                history, featured_history = case
                prepared.append(self._prepare(history, featured_history))
        if not prepared:
            return []
        if horizon <= 0:
            raise ValueError("Forecast horizon must be positive")
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
            initial_sequence = np.asarray(item['sequence'][0], dtype=float).copy()
            scaled_indices = [self.lstm.feature_cols.index(column)
                              for column in self.lstm.scaled_features
                              if column in self.lstm.feature_cols]
            initial_sequence[:, scaled_indices] *= float(item['anchor'])
            item['lstm_feature_history'] = initial_sequence.tolist()
        chunk_size = max(1, int(getattr(self.lstm, "horizon", horizon)))
        if self.ensemble is not None and self.ensemble.weights is not None:
            chunk_size = min(chunk_size, len(self.ensemble.weights))
        if chunk_size <= 0:
            raise ValueError("The trained models have no usable forecast steps")

        accumulated_lstm = [[] for _ in prepared]
        accumulated_lgbm = [[] for _ in prepared]
        accumulated_point = [[] for _ in prepared]
        for chunk_start in range(0, horizon, chunk_size):
            chunk_length = min(chunk_size, horizon - chunk_start)
            chunk_anchors = []
            chunk_references = []
            sequences = []
            for item in prepared:
                if chunk_start == 0:
                    sequences.append(item["sequence"])
                    chunk_anchors.append(float(item["anchor"]))
                    chunk_references.append(float(item["moving_average7"]))
                    continue

                anchor = float(item["state"].prices[-1])
                next_date = item["origin"] + pd.Timedelta(days=chunk_start + 1)
                next_row = item["state"].row(next_date, item['market_state'])
                next_features = next_row[self.lstm.feature_cols].to_numpy(dtype=float)[0]
                prior = np.asarray(item['lstm_feature_history'], dtype=float)
                history_count = max(0, self.lstm.seq_len - 1)
                prior = prior[-history_count:] if history_count else prior[:0]
                sequence = np.concatenate([prior, next_features[None, :]], axis=0)
                if len(sequence) != self.lstm.seq_len:
                    raise ValueError("Insufficient causal feature history for recursive forecast")
                sequences.append(self.lstm._scale(sequence, anchor)[None].astype(np.float32))
                chunk_anchors.append(anchor)
                chunk_references.append(float(np.mean(item["state"].prices[-7:])))

            anchors = np.asarray(chunk_anchors, dtype=float)
            lstm_chunk = self.lstm.predict_paths(np.concatenate(sequences), anchors)[:, :chunk_length]
            replay_states = [deepcopy(item['state']) for item in prepared]
            replay_market_states = {
                key: list(values) for key, values in market_states.items()
            }
            feature_histories = [list(item['lstm_feature_history']) for item in prepared]
            lgbm_chunk = np.empty((len(prepared), chunk_length), dtype=float)
            for offset in range(chunk_length):
                step = chunk_start + offset + 1
                rows = pd.concat([
                    item["state"].row(item["origin"] + pd.Timedelta(days=step),
                                      item['market_state'])
                    for item in prepared
                ], ignore_index=True)
                if not np.isfinite(rows[FEATURE_COLUMNS].to_numpy(dtype=float)).all():
                    raise ValueError(f"Incomplete LightGBM features at horizon {step}")
                predictions = self.lgbm.predict(rows[FEATURE_COLUMNS])
                lgbm_chunk[:, offset] = predictions
                category_returns = {}
                for item, prediction in zip(prepared, predictions):
                    previous = item['state'].prices[-1]
                    if np.isfinite(previous) and previous > 0:
                        category_returns.setdefault(item['market_key'], []).append(
                            float(prediction / previous - 1.0))
                    item["state"].append(prediction)
                for key, values in category_returns.items():
                    market_states[key].append(float(np.median(values)))

            point_chunk = []
            for index, item in enumerate(prepared):
                lstm_path, lgbm_path = lstm_chunk[index], lgbm_chunk[index]
                point = (self.ensemble.predict(
                    lstm_path, lgbm_path, chunk_anchors[index], item["category"],
                    chunk_references[index], item["product"])
                         if self.ensemble is not None else (lstm_path + lgbm_path) / 2)
                point_chunk.append(point)
                accumulated_lstm[index].extend(lstm_path.tolist())
                accumulated_lgbm[index].extend(lgbm_path.tolist())
                accumulated_point[index].extend(point.tolist())

            # Advance causal feature states with emitted ensemble prices so the
            # next model-sized chunk starts from the forecast users see.
            for offset in range(chunk_length):
                step = chunk_start + offset + 1
                for index, item in enumerate(prepared):
                    row = replay_states[index].row(
                        item['origin'] + pd.Timedelta(days=step),
                        replay_market_states[item['market_key']])
                    if step > 1:
                        feature_histories[index].append(
                            row[self.lstm.feature_cols].to_numpy(dtype=float)[0].tolist())

                category_returns = {}
                for index, item in enumerate(prepared):
                    prediction = point_chunk[index][offset]
                    previous = replay_states[index].prices[-1]
                    if np.isfinite(previous) and previous > 0:
                        category_returns.setdefault(item['market_key'], []).append(
                            float(prediction / previous - 1.0))
                    replay_states[index].append(prediction)
                for key, values in category_returns.items():
                    replay_market_states[key].append(float(np.median(values)))

            market_states = replay_market_states
            for index, item in enumerate(prepared):
                item['state'] = replay_states[index]
                item['market_state'] = replay_market_states[item['market_key']]
                item['lstm_feature_history'] = feature_histories[index]

        results = []
        for index, item in enumerate(prepared):
            lstm_path = np.asarray(accumulated_lstm[index], dtype=float)
            lgbm_path = np.asarray(accumulated_lgbm[index], dtype=float)
            point = np.asarray(accumulated_point[index], dtype=float)
            dates = pd.date_range(item["origin"] + pd.Timedelta(days=1),
                                  periods=horizon).to_numpy()
            results.append(ForecastPath(dates, item["anchor"], lstm_path, lgbm_path,
                                        point))
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
