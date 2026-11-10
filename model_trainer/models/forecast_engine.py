"""The single forecast path used by calibration, test evaluation, and serving."""
from copy import deepcopy
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from data.preprocessor import SERIES_KEY
from features.builder import CausalFeatureState, FeatureBuilder
from models.ensemble import EnsembleModel
from models.lightgbm_model import (
    LightGBMModel, RESIDUAL_FEATURE_SCHEMA,
)
from models.lstm_model import LSTMModel


@dataclass
class ForecastPath:
    dates: np.ndarray
    anchor: float
    lstm: np.ndarray
    lgbm: np.ndarray
    point: np.ndarray
    feature_rows: Optional[pd.DataFrame] = None


class ForecastEngine:
    def __init__(self, lgbm: LightGBMModel, lstm: LSTMModel,
                 ensemble: Optional[EnsembleModel], builder: FeatureBuilder,
                 recursive_market_updates=True):
        self.lgbm = lgbm
        self.lstm = lstm
        self.ensemble = ensemble
        self.builder = builder
        # Experimental replays can freeze category features at forecast-origin
        # values to measure the effect of predicted peer-return feedback.
        self.recursive_market_updates = bool(recursive_market_updates)

    @staticmethod
    def _append_day(frame, date, price=np.nan):
        row = {column: np.nan for column in frame.columns}
        for column in SERIES_KEY:
            row[column] = frame.iloc[-1][column]
        row.update({"report_date": pd.Timestamp(date), "price_index": price,
                    "observed_price": np.nan, "is_observed": False})
        return pd.concat([frame, pd.DataFrame([row])], ignore_index=True)

    @staticmethod
    def _peer_key(item):
        return (item['origin'], item['category'], tuple(item['peer_group_key']))

    @staticmethod
    def _cross_variant_key(item):
        return (item['origin'], tuple(item['cross_variant_group_key']),
                item['cross_variant_variant'])

    @classmethod
    def _initial_category_peer_histories(cls, prepared):
        """Build leave-one-product-out category returns from origin-known paths."""
        series_returns = {}
        origins = {item['origin'] for item in prepared}
        for item in prepared:
            prices = np.asarray(item['state'].prices, dtype=float)
            if len(prices) < 2:
                continue
            dates = pd.date_range(end=item['origin'], periods=len(prices), freq='D')
            returns = np.divide(prices[1:], prices[:-1], out=np.full(len(prices)-1, np.nan),
                                where=(prices[:-1] > 0)) - 1.0
            for day, value in zip(dates[1:], returns):
                if np.isfinite(value):
                    key = (item['origin'], item['category'],
                           tuple(item['peer_group_key']), day)
                    series_returns.setdefault(key, []).append(float(value))

        returns_by_day = {}
        for (origin, category, core, day), values in series_returns.items():
            returns_by_day.setdefault((origin, category, day), {})[core] = float(
                np.median(values))

        histories = {}
        for item in prepared:
            key = cls._peer_key(item)
            if key in histories:
                continue
            origin, category, core = key
            history = []
            for day in pd.date_range(origin - pd.Timedelta(days=29), origin, freq='D'):
                category_values = returns_by_day.get((origin, category, day), {})
                peers = [value for peer_core, value in category_values.items()
                         if peer_core != core]
                history.append((float(np.mean(peers)) if peers else 0.0, float(len(peers))))
            histories[key] = history
        return histories

    @classmethod
    def _advance_category_peer_histories(cls, prepared, predictions, states):
        returns_by_core = {}
        for item, prediction in zip(prepared, predictions):
            previous = (float(item['state'].prices[-2])
                        if len(item['state'].prices) > 1
                        else float(item['state'].prices[-1]))
            if not (np.isfinite(previous) and previous > 0 and
                    np.isfinite(prediction) and prediction > 0):
                continue
            key = (item['origin'], item['category'], tuple(item['peer_group_key']))
            returns_by_core.setdefault(key, []).append(float(prediction / previous - 1.0))
        rates = {key: float(np.median(values))
                 for key, values in returns_by_core.items()}
        seen = set()
        for item in prepared:
            own = cls._peer_key(item)
            if own in seen:
                continue
            seen.add(own)
            peers = [value for key, value in rates.items()
                     if key[0] == own[0] and key[1] == own[1] and key[2] != own[2]]
            states[own].append((float(np.mean(peers)) if peers else 0.0,
                                float(len(peers))))

    @classmethod
    def _initial_cross_variant_histories(cls, prepared):
        """Build seven origin-known daily peer returns for each variant."""
        returns_by_variant_day = {}
        for item in prepared:
            prices = np.asarray(item['state'].prices, dtype=float)
            if len(prices) < 2:
                continue
            dates = pd.date_range(end=item['origin'], periods=len(prices), freq='D')
            returns = np.divide(prices[1:], prices[:-1], out=np.full(len(prices)-1, np.nan),
                                where=(prices[:-1] > 0)) - 1.0
            variant_key = cls._cross_variant_key(item)
            for day, value in zip(dates[1:], returns):
                if np.isfinite(value):
                    returns_by_variant_day.setdefault(
                        (variant_key, day), []).append(float(value))
        by_family_day = {}
        for (variant_key, day), values in returns_by_variant_day.items():
            family_key = (variant_key[0], variant_key[1], day)
            by_family_day.setdefault(family_key, {})[variant_key[2]] = float(np.median(values))

        states = {}
        for item in prepared:
            own = cls._cross_variant_key(item)
            if own in states:
                continue
            history = []
            for day in pd.date_range(
                    item['origin'] - pd.Timedelta(days=6), item['origin'], freq='D'):
                peers = [value for variant, value in by_family_day.get(
                    (own[0], own[1], day), {}).items() if variant != own[2]]
                history.append((float(np.mean(peers)) if peers else 0.0,
                                float(len(peers))))
            states[own] = history
        return states

    @classmethod
    def _advance_cross_variant_histories(cls, prepared, predictions, states):
        returns_by_variant = {}
        for item, prediction in zip(prepared, predictions):
            previous = (float(item['state'].prices[-2])
                        if len(item['state'].prices) > 1
                        else float(item['state'].prices[-1]))
            if not (np.isfinite(previous) and previous > 0 and
                    np.isfinite(prediction) and prediction > 0):
                continue
            key = cls._cross_variant_key(item)
            returns_by_variant.setdefault(key, []).append(float(prediction / previous - 1.0))
        rates = {key: float(np.median(values))
                 for key, values in returns_by_variant.items()}
        seen = set()
        for item in prepared:
            own = cls._cross_variant_key(item)
            if own in seen:
                continue
            seen.add(own)
            peers = [value for key, value in rates.items()
                     if key[0] == own[0] and key[1] == own[1] and key[2] != own[2]]
            states[own].append((float(np.mean(peers)) if peers else 0.0,
                                float(len(peers))))

    def forecast(self, history: pd.DataFrame, horizon=30, featured_history=None):
        return self.forecast_many([(history, featured_history)], horizon)[0]

    def forecast_many(self, cases, horizon=30, return_feature_rows=False):
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
        # Residual training rollouts advance the feature state with LSTM-only
        # predictions. Keep that same state at inference so the LightGBM sees
        # the feature distribution it was trained on; the corrected points are
        # still emitted but are not fed back into later residual features.
        residual_base_state = bool(getattr(self.lgbm, "is_residual_model", False))
        lgbm_features = list(self.lgbm._feature_names)
        uses_product_peer_returns = (
            "product_return_lag_1d" in lgbm_features)
        uses_category_peer_returns = (
            "category_peer_return_lag_1d" in lgbm_features)
        uses_cross_variant_returns = (
            "cross_variant_return_lag_1d" in lgbm_features)
        market_states, product_market_states = {}, {}
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
            if uses_product_peer_returns:
                product_key = (item['origin'], tuple(item['product_group_key']))
                if product_key not in product_market_states:
                    initial_product = item.get('product_market_history')
                    if initial_product is None:
                        prices = np.asarray(item['state'].prices, dtype=float)
                        initial_product = prices[1:] / prices[:-1] - 1.0 if len(prices) > 1 else []
                    product_market_states[product_key] = list(initial_product)
                item['product_market_key'] = product_key
                item['product_market_state'] = product_market_states[product_key]
            else:
                item['product_market_key'] = None
                item['product_market_state'] = None
        if uses_category_peer_returns:
            category_peer_states = self._initial_category_peer_histories(prepared)
            for item in prepared:
                item['category_peer_key'] = self._peer_key(item)
                item['category_peer_market_state'] = category_peer_states[item['category_peer_key']]
        else:
            category_peer_states = {}
            for item in prepared:
                item['category_peer_key'] = None
                item['category_peer_market_state'] = None
        if uses_cross_variant_returns:
            cross_variant_states = self._initial_cross_variant_histories(prepared)
            for item in prepared:
                item['cross_variant_key'] = self._cross_variant_key(item)
                item['cross_variant_market_state'] = cross_variant_states[
                    item['cross_variant_key']]
        else:
            cross_variant_states = {}
            for item in prepared:
                item['cross_variant_key'] = None
                item['cross_variant_market_state'] = None
        for item in prepared:
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
        accumulated_features = ([[] for _ in prepared]
                                if return_feature_rows else None)
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
                next_row = item["state"].row(
                    next_date, item['market_state'], item['product_market_state'],
                    item['category_peer_market_state'],
                    item['cross_variant_market_state'])
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
            replay_product_market_states = ({
                key: list(values) for key, values in product_market_states.items()
            } if uses_product_peer_returns else {})
            replay_category_peer_states = ({
                key: list(values) for key, values in category_peer_states.items()
            } if uses_category_peer_returns else {})
            replay_cross_variant_states = ({
                key: list(values) for key, values in cross_variant_states.items()
            } if uses_cross_variant_returns else {})
            feature_histories = [list(item['lstm_feature_history']) for item in prepared]
            lgbm_chunk = np.empty((len(prepared), chunk_length), dtype=float)
            for offset in range(chunk_length):
                step = chunk_start + offset + 1
                rows = pd.concat([
                    item["state"].row(item["origin"] + pd.Timedelta(days=step),
                                      item['market_state'], item['product_market_state'],
                                      item['category_peer_market_state'],
                                      item['cross_variant_market_state'])
                    for item in prepared
                ], ignore_index=True)
                if (residual_base_state
                        and getattr(self.lgbm, "residual_feature_schema", None)
                        == RESIDUAL_FEATURE_SCHEMA):
                    lag = rows["price_lag_1d"].to_numpy(dtype=float)
                    if not np.isfinite(lag).all() or (lag <= 0).any():
                        raise ValueError(
                            "Residual features require positive finite prior prices")
                    rows["lstm_base_relative_change"] = (
                        lstm_chunk[:, offset] / lag - 1.0)
                    lead_denominator = max(1, int(self.lstm.horizon) - 1)
                    rows["forecast_lead_fraction"] = (
                        min(step - 1, lead_denominator) / lead_denominator)
                if not np.isfinite(rows[lgbm_features].to_numpy(dtype=float)).all():
                    raise ValueError(f"Incomplete LightGBM features at horizon {step}")
                if accumulated_features is not None:
                    for index in range(len(prepared)):
                        accumulated_features[index].append(
                            rows.loc[index, lgbm_features].to_dict())
                predictions = self.lgbm.predict(
                    rows[lgbm_features], base_prediction=lstm_chunk[:, offset])
                lgbm_chunk[:, offset] = predictions
                feature_state_predictions = (
                    lstm_chunk[:, offset] if residual_base_state else predictions)
                category_returns, product_returns = {}, {}
                for item, prediction in zip(prepared, feature_state_predictions):
                    previous = item['state'].prices[-1]
                    if np.isfinite(previous) and previous > 0:
                        rate = float(prediction / previous - 1.0)
                        category_returns.setdefault(item['market_key'], []).append(rate)
                        if uses_product_peer_returns:
                            product_returns.setdefault(item['product_market_key'], []).append(rate)
                    item["state"].append(prediction)
                if self.recursive_market_updates:
                    for key, values in category_returns.items():
                        market_states[key].append(float(np.median(values)))
                    if uses_product_peer_returns:
                        for key, values in product_returns.items():
                            product_market_states[key].append(float(np.median(values)))
                    if uses_category_peer_returns:
                        self._advance_category_peer_histories(
                            prepared, feature_state_predictions,
                            category_peer_states)
                    if uses_cross_variant_returns:
                        self._advance_cross_variant_histories(
                            prepared, feature_state_predictions,
                            cross_variant_states)

            point_chunk = []
            for index, item in enumerate(prepared):
                lstm_path, lgbm_path = lstm_chunk[index], lgbm_chunk[index]
                point = (self.ensemble.predict(
                    lstm_path, lgbm_path, chunk_anchors[index], item["category"],
                    chunk_references[index], item["product"])
                         if self.ensemble is not None else (
                             lgbm_path.copy() if residual_base_state
                             else (lstm_path + lgbm_path) / 2))
                point_chunk.append(point)
                accumulated_lstm[index].extend(lstm_path.tolist())
                accumulated_lgbm[index].extend(lgbm_path.tolist())
                accumulated_point[index].extend(point.tolist())

            # Direct models feed their published path back into future state.
            # Residual models retain the LSTM-only state used for OOF training.
            # Both state choices are causal and leave emitted points unchanged.
            replay_predictions = [
                lstm_chunk[index] if residual_base_state else point_chunk[index]
                for index in range(len(prepared))]
            for offset in range(chunk_length):
                step = chunk_start + offset + 1
                for index, item in enumerate(prepared):
                    row = replay_states[index].row(
                        item['origin'] + pd.Timedelta(days=step),
                        replay_market_states[item['market_key']],
                        (replay_product_market_states[item['product_market_key']]
                         if uses_product_peer_returns else None),
                        (replay_category_peer_states[item['category_peer_key']]
                         if uses_category_peer_returns else None),
                        (replay_cross_variant_states[item['cross_variant_key']]
                         if uses_cross_variant_returns else None))
                    if step > 1:
                        feature_histories[index].append(
                            row[self.lstm.feature_cols].to_numpy(dtype=float)[0].tolist())

                category_returns, product_returns = {}, {}
                for index, item in enumerate(prepared):
                    prediction = replay_predictions[index][offset]
                    previous = replay_states[index].prices[-1]
                    if np.isfinite(previous) and previous > 0:
                        rate = float(prediction / previous - 1.0)
                        category_returns.setdefault(item['market_key'], []).append(rate)
                        if uses_product_peer_returns:
                            product_returns.setdefault(item['product_market_key'], []).append(rate)
                    replay_states[index].append(prediction)
                if self.recursive_market_updates:
                    for key, values in category_returns.items():
                        replay_market_states[key].append(float(np.median(values)))
                    if uses_product_peer_returns:
                        for key, values in product_returns.items():
                            replay_product_market_states[key].append(float(np.median(values)))
                    if uses_category_peer_returns:
                        replay_items = []
                        for index, item in enumerate(prepared):
                            shadow = dict(item)
                            shadow['state'] = replay_states[index]
                            replay_items.append(shadow)
                        self._advance_category_peer_histories(
                            replay_items,
                            [replay_predictions[index][offset]
                             for index in range(len(prepared))],
                            replay_category_peer_states)
                    if uses_cross_variant_returns:
                        replay_items = []
                        for index, item in enumerate(prepared):
                            shadow = dict(item)
                            shadow['state'] = replay_states[index]
                            replay_items.append(shadow)
                        self._advance_cross_variant_histories(
                            replay_items,
                            [replay_predictions[index][offset]
                             for index in range(len(prepared))],
                            replay_cross_variant_states)

            market_states = replay_market_states
            if uses_product_peer_returns:
                product_market_states = replay_product_market_states
            if uses_category_peer_returns:
                category_peer_states = replay_category_peer_states
            if uses_cross_variant_returns:
                cross_variant_states = replay_cross_variant_states
            for index, item in enumerate(prepared):
                item['state'] = replay_states[index]
                item['market_state'] = replay_market_states[item['market_key']]
                item['product_market_state'] = (
                    replay_product_market_states[item['product_market_key']]
                    if uses_product_peer_returns else None)
                item['category_peer_market_state'] = (
                    replay_category_peer_states[item['category_peer_key']]
                    if uses_category_peer_returns else None)
                item['cross_variant_market_state'] = (
                    replay_cross_variant_states[item['cross_variant_key']]
                    if uses_cross_variant_returns else None)
                item['lstm_feature_history'] = feature_histories[index]

        results = []
        for index, item in enumerate(prepared):
            lstm_path = np.asarray(accumulated_lstm[index], dtype=float)
            lgbm_path = np.asarray(accumulated_lgbm[index], dtype=float)
            point = np.asarray(accumulated_point[index], dtype=float)
            dates = pd.date_range(item["origin"] + pd.Timedelta(days=1),
                                  periods=horizon).to_numpy()
            feature_rows = (pd.DataFrame(accumulated_features[index])
                            if accumulated_features is not None else None)
            results.append(ForecastPath(dates, item["anchor"], lstm_path, lgbm_path,
                                        point, feature_rows))
        return results

    def _prepare(self, history, featured_history, market_history=None,
                 product_market_history=None):
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
                "product_market_history": (
                    None if product_market_history is None else list(product_market_history)),
                "product_group_key": tuple(history.iloc[-1][SERIES_KEY[:3]]),
                "peer_group_key": tuple(str(history.iloc[-1][column])
                                        for column in (SERIES_KEY[0], SERIES_KEY[1],
                                                       SERIES_KEY[2], SERIES_KEY[4])),
                "cross_variant_group_key": tuple(
                    str(history.iloc[-1][column])
                    for column in (SERIES_KEY[0], SERIES_KEY[1], SERIES_KEY[4])),
                "cross_variant_variant": str(history.iloc[-1][SERIES_KEY[2]]),
                "product": (f"{history.product_category.iloc[-1]}||"
                            f"{history.product_name.iloc[-1]}"),
                "moving_average7": float(recent.mean()),
                "state": CausalFeatureState(history, self.builder.encoder)}
