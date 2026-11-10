"""Validation-calibrated point-forecast model blend."""
import json
from pathlib import Path
import numpy as np
from config.settings import get_settings

class EnsembleModel:
    def __init__(self, artifact_dir=None):
        self.path = Path(artifact_dir or get_settings().artifacts_dir)
        self.weights = None
        self.trust_weights = None
        self.category_weights = {}
        self.category_trust_weights = {}
        self.anomaly_threshold = 1e9
        self.anomaly_strength = 0.0
        self.anomaly_decay = 1.0
        self.specialist_blends = {}
        self.objective = 'balanced'
        self.calibration = {'scope': 'legacy_in_sample'}

    def fit(self, frame, horizon, calibration_frame=None, objective='balanced'):
        if len(frame) < 2:
            raise ValueError('At least two observed validation forecasts are required')
        if objective not in {'balanced', 'balanced_lgbm', 'rmse_lgbm', 'within5', 'volatility_regime'}:
            raise ValueError(
                'Ensemble objective must be balanced, balanced_lgbm, rmse_lgbm, within5, or volatility_regime')
        self.objective = objective
        self.category_weights, self.category_trust_weights, self.specialist_blends = {}, {}, {}
        self.anomaly_threshold, self.anomaly_strength, self.anomaly_decay = 1e9, 0.0, 1.0
        if calibration_frame is not None and {'date', 'origin'}.issubset(frame.columns):
            import pandas as pd
            if pd.to_datetime(frame.date).max() > pd.to_datetime(calibration_frame.origin).min():
                raise ValueError('Calibration must follow all ensemble tuning targets')
        actual, lstm, lgbm = (frame[c].to_numpy() for c in ['actual','lstm','lgbm'])
        candidates = np.linspace(0, 1, 201 if objective == 'within5' else 101)
        if objective == 'within5':
            global_key = [self._objective_key(
                frame, (1-w)*lstm+w*lgbm, objective) for w in candidates]
            selected = max(range(len(global_key)), key=global_key.__getitem__)
            global_weight = float(candidates[selected])
        elif objective == 'rmse_lgbm':
            errors = [np.sqrt(np.mean(np.square(
                actual-((1-w)*lstm+w*lgbm)))) for w in candidates]
            global_weight = float(candidates[int(np.argmin(errors))])
        else:
            errors = [np.mean(np.abs(actual-((1-w)*lstm+w*lgbm))) for w in candidates]
            global_weight = float(candidates[int(np.argmin(errors))])
        weights, trust_weights = [], []
        for h in range(1,horizon+1):
            rows = frame[frame.horizon == h]
            if len(rows) < 2:
                rows = frame
            a,l,g,anchor = (rows[c].to_numpy(dtype=float)
                            for c in ['actual','lstm','lgbm','anchor'])
            base = (1-global_weight)*l + global_weight*g
            persistence_error = a-anchor
            denominators = np.maximum(np.array([
                np.mean(np.abs(persistence_error)),
                np.sqrt(np.mean(persistence_error**2)),
                np.mean(np.abs(persistence_error/a)),
            ]), 1e-12)
            scores = []
            for trust in candidates:
                prediction = anchor + trust*(base-anchor)
                error = a-prediction
                if objective == 'within5':
                    scores.append(self._objective_key(rows, prediction, objective))
                elif objective == 'rmse_lgbm':
                    scores.append(-float(np.sqrt(np.mean(np.square(error)))))
                else:
                    scores.append(
                        np.mean(np.abs(error))/denominators[0]
                        + np.sqrt(np.mean(error**2))/denominators[1]
                        + np.mean(np.abs(error/a))/denominators[2]
                    )
            selected = (max(range(len(scores)), key=scores.__getitem__)
                        if objective in {'within5', 'rmse_lgbm'}
                        else int(np.argmin(scores)))
            trust = float(candidates[selected])
            weights.append(global_weight)
            trust_weights.append(trust)
        self.weights = np.array(weights)
        self.trust_weights = np.array(trust_weights)
        if objective == 'volatility_regime':
            self.category_weights = self._fit_category_weights(frame, candidates)
        self.category_trust_weights = self._fit_category_trust(
            frame, candidates, objective=objective)
        self._fit_anomaly_reversion(frame, objective=objective)
        final = self.predict_rows(
            frame.lstm.to_numpy(), frame.lgbm.to_numpy(),
            frame.horizon.to_numpy(), frame.anchor.to_numpy(),
            frame.series.to_numpy() if 'series' in frame else None,
            frame.moving_average7.to_numpy() if 'moving_average7' in frame else None)
        specialist_frame = frame.copy()
        specialist_frame['ensemble'] = final
        self.specialist_blends = self._fit_stable_specialists(
            specialist_frame, objective=objective)
        evidence = frame if calibration_frame is None else calibration_frame
        self.calibration = {
            'scope': 'held_out_from_ensemble_fit' if calibration_frame is not None else 'legacy_in_sample',
            'sample_count': len(evidence),
            'start': str(evidence.date.min()) if 'date' in evidence else None,
            'end': str(evidence.date.max()) if 'date' in evidence else None,
            'purpose': 'product_confidence_reliability',
        }
        self.save()
        return self

    def _fit_category_weights(self, frame, candidates):
        if 'series' not in frame:
            return {}
        categories = frame.series.astype(str).str.split('||', regex=False).str[0]
        result = {}
        for category in sorted(categories.unique()):
            rows = frame[categories == category]
            if len(rows) < 10:
                continue
            a, l, g, anchor = (rows[c].to_numpy(dtype=float)
                               for c in ['actual', 'lstm', 'lgbm', 'anchor'])
            persistence_error = a - anchor
            denominators = np.maximum(np.array([
                np.mean(np.abs(persistence_error)),
                np.sqrt(np.mean(persistence_error**2)),
                np.mean(np.abs(persistence_error / np.maximum(np.abs(a), 1e-8))),
            ]), 1e-12)
            scores = []
            for w in candidates:
                pred = (1.0 - w) * l + w * g
                err = a - pred
                scores.append(
                    np.mean(np.abs(err)) / denominators[0]
                    + np.sqrt(np.mean(err**2)) / denominators[1]
                    + np.mean(np.abs(err / np.maximum(np.abs(a), 1e-8))) / denominators[2]
                )
            result[str(category)] = float(candidates[int(np.argmin(scores))])
        return result

    def _fit_category_trust(self, frame, candidates, objective='balanced'):
        if 'series' not in frame:
            return {}
        categories = frame.series.astype(str).str.split('||', regex=False).str[0]
        result = {}
        for category in sorted(categories.unique()):
            category_weights = []
            w_cat_override = self.category_weights.get(str(category))
            for h in range(1, len(self.weights)+1):
                mask = (categories == category) & (frame.horizon == h)
                rows = frame[mask]
                if len(rows) < 10:
                    category_weights.append(1.0)
                    continue
                a,l,g,anchor = (rows[c].to_numpy(dtype=float)
                                for c in ['actual','lstm','lgbm','anchor'])
                w_eff = float(w_cat_override) if w_cat_override is not None else float(self.weights[h-1])
                base = (1-w_eff)*l + w_eff*g
                horizon_prediction = anchor + self.trust_weights[h-1]*(base-anchor)
                persistence_error = a-anchor
                denominators = np.maximum(np.array([
                    np.mean(np.abs(persistence_error)),
                    np.sqrt(np.mean(persistence_error**2)),
                    np.mean(np.abs(persistence_error/a)),
                ]), 1e-12)
                scores = []
                category_candidates = candidates[::5]
                for trust in category_candidates:
                    prediction = anchor + trust*(horizon_prediction-anchor)
                    error = a-prediction
                    if objective == 'within5':
                        scores.append(self._objective_key(rows, prediction, objective))
                    elif objective == 'rmse_lgbm':
                        scores.append(-float(np.sqrt(np.mean(np.square(error)))))
                    else:
                        scores.append(
                            np.mean(np.abs(error))/denominators[0]
                            + np.sqrt(np.mean(error**2))/denominators[1]
                            + np.mean(np.abs(error/a))/denominators[2]
                        )
                selected = (max(range(len(scores)), key=scores.__getitem__)
                            if objective in {'within5', 'rmse_lgbm'}
                            else int(np.argmin(scores)))
                category_weights.append(float(category_candidates[selected]))
            arr = np.asarray(category_weights, dtype=float)
            if objective == 'volatility_regime' and len(arr) >= 3:
                smoothed = arr.copy()
                smoothed[1:-1] = (arr[:-2] + 2.0 * arr[1:-1] + arr[2:]) / 4.0
                smoothed[0] = (2.0 * arr[0] + arr[1]) / 3.0
                smoothed[-1] = (arr[-2] + 2.0 * arr[-1]) / 3.0
                arr = np.clip(np.round(smoothed, 4), 0.0, 1.0)
            result[str(category)] = arr
        return result

    @staticmethod
    def _normalized_score(rows, prediction):
        actual = rows.actual.to_numpy(dtype=float)
        persistence = rows.anchor.to_numpy(dtype=float)
        error = actual-np.asarray(prediction)
        persistence_error = actual-persistence
        denominators = np.maximum(np.array([
            np.mean(np.abs(persistence_error)),
            np.sqrt(np.mean(persistence_error**2)),
            np.mean(np.abs(persistence_error/actual)),
        ]), 1e-12)
        return float(
            np.mean(np.abs(error))/denominators[0]
            + np.sqrt(np.mean(error**2))/denominators[1]
            + np.mean(np.abs(error/actual))/denominators[2]
        )

    @classmethod
    def _objective_key(cls, rows, prediction, objective):
        score = cls._normalized_score(rows, prediction)
        if objective == 'within5':
            actual = rows.actual.to_numpy(dtype=float)
            error = np.abs(np.asarray(prediction, dtype=float)-actual)
            return (float(np.mean(error <= 5.0)), -score)
        if objective == 'rmse_lgbm':
            actual = rows.actual.to_numpy(dtype=float)
            anchor = rows.anchor.to_numpy(dtype=float)
            error = np.asarray(prediction, dtype=float)-actual
            persistence_rmse = max(float(np.sqrt(np.mean(np.square(actual-anchor)))), 1e-12)
            return (-float(np.sqrt(np.mean(np.square(error))))/persistence_rmse,)
        return (-score,)

    def _fit_anomaly_reversion(self, frame, objective='balanced'):
        if 'moving_average7' not in frame:
            return
        base = self.predict_rows(
            frame.lstm.to_numpy(), frame.lgbm.to_numpy(),
            frame.horizon.to_numpy(), frame.anchor.to_numpy(),
            frame.series.to_numpy() if 'series' in frame else None)
        anchor = frame.anchor.to_numpy(dtype=float)
        reference = frame.moving_average7.to_numpy(dtype=float)
        horizons = frame.horizon.to_numpy(dtype=float)
        best_key = self._objective_key(frame, base, objective)
        best = (best_key, 1e9, 0.0, 1.0)
        for threshold in [.15,.2,.25,.3,.5,.75,1.0]:
            anomaly = np.abs(np.log(anchor/reference)) > threshold
            if not anomaly.any():
                continue
            for strength in [.25,.5,.75,1.0]:
                for decay in [1.0,3.0,7.0,14.0]:
                    horizon_strength = strength*(1-np.exp(-horizons/decay))
                    prediction = base.copy()
                    prediction[anomaly] += horizon_strength[anomaly]*(
                        reference[anomaly]-prediction[anomaly])
                    key = self._objective_key(frame, prediction, objective)
                    if key > best[0]:
                        best = (key, threshold, strength, decay)
        _, self.anomaly_threshold, self.anomaly_strength, self.anomaly_decay = best

    @staticmethod
    def _error_triplet(rows, prediction):
        actual = rows.actual.to_numpy(dtype=float)
        error = np.asarray(prediction, dtype=float)-actual
        return np.array([
            np.mean(np.abs(error)),
            np.sqrt(np.mean(np.square(error))),
            np.mean(np.abs(error)/np.maximum(np.abs(actual), 1e-8)),
        ])

    @staticmethod
    def _horizon_bins(horizons):
        return np.digitize(np.asarray(horizons, dtype=int), [3, 7, 14, 21], right=True)

    def _fit_stable_specialists(self, frame, objective='balanced'):
        required = {'origin','series','ensemble','lstm','lgbm','anchor','moving_average7'}
        if not required.issubset(frame.columns):
            return {}
        work = frame.copy()
        origins = np.sort(np.asarray(work.origin, dtype='datetime64[ns]'))
        origins = np.unique(origins)
        if len(origins) < 4:
            return {}
        work['product'] = work.series.astype(str).str.split(
            '||', regex=False).str[:2].str.join('||')
        work['horizon_bin'] = self._horizon_bins(work.horizon)
        cutoff = origins[len(origins)//2-1]
        early = work[np.asarray(work.origin, dtype='datetime64[ns]') <= cutoff]
        late = work[np.asarray(work.origin, dtype='datetime64[ns]') > cutoff]
        groups = ['product','horizon_bin']
        early_groups = early.groupby(groups, observed=True)
        late_groups = late.groupby(groups, observed=True)
        alternatives = ['lstm','anchor','moving_average7']
        if objective in {'within5', 'balanced_lgbm', 'rmse_lgbm', 'volatility_regime'}:
            alternatives.append('lgbm')

        def choose(rows):
            baseline = self._error_triplet(rows, rows.ensemble)
            if not np.isfinite(baseline).all() or (baseline <= 1e-12).any():
                # A zero baseline error cannot be strictly improved by any blend.
                return (1.0, None, 0.0)
            best_key = ((-1.0,) if objective == 'balanced'
                        else self._objective_key(rows, rows.ensemble, objective))
            best = (best_key, None, 0.0)
            for name in alternatives:
                for weight in np.linspace(.05, .5, 10):
                    prediction = (1-weight)*rows.ensemble+weight*rows[name]
                    ratios = self._error_triplet(rows, prediction)/baseline
                    if not np.isfinite(ratios).all():
                        continue
                    if objective in {'within5', 'rmse_lgbm'} and (ratios >= 1).any():
                        continue
                    if objective == 'within5':
                        key = self._objective_key(rows, prediction, objective)
                    elif objective == 'rmse_lgbm':
                        key = (-float(ratios[1]),)
                    else:
                        key = (-float(np.mean(ratios)),)
                    if key > best[0]:
                        best = (key, name, float(weight))
            return best

        def stable(rows, name, weight):
            baseline = self._error_triplet(rows, rows.ensemble)
            if not np.isfinite(baseline).all() or (baseline <= 1e-12).any():
                return False
            prediction = (1-weight)*rows.ensemble+weight*rows[name]
            ratios = self._error_triplet(rows, prediction)/baseline
            if objective == 'within5':
                baseline_w5 = self._objective_key(rows, rows.ensemble, objective)[0]
                prediction_w5 = self._objective_key(rows, prediction, objective)[0]
                return bool(np.isfinite(ratios).all() and (ratios < 1).all()
                            and ratios.mean() <= .9975
                            and prediction_w5 >= baseline_w5)
            return bool(np.isfinite(ratios).all() and (ratios < 1).all()
                        and ratios.mean() <= .9975)

        result = {}
        for key in sorted(set(early_groups.groups) & set(late_groups.groups)):
            left, right = early_groups.get_group(key), late_groups.get_group(key)
            if len(left) < 20 or len(right) < 20:
                continue
            left_choice, right_choice = choose(left), choose(right)
            if left_choice[1] is None or left_choice[1] != right_choice[1]:
                continue
            name = left_choice[1]
            if not (stable(right, name, left_choice[2])
                    and stable(left, name, right_choice[2])):
                continue
            public_name = {'anchor':'persistence','moving_average7':'moving_average7',
                           'lgbm':'lgbm','lstm':'lstm'}[name]
            result[f'{key[0]}##{int(key[1])}'] = {
                'model':public_name, 'weight':min(left_choice[2], right_choice[2])}
        return result

    def predict(self, lstm, lgbm, anchor, category=None, reference=None, product=None):
        if self.weights is None:
            raise ValueError('Ensemble has not been calibrated')
        lstm,lgbm = np.asarray(lstm),np.asarray(lgbm)
        if lstm.shape != lgbm.shape or lstm.ndim != 1 or len(lstm)>len(self.weights):
            raise ValueError('Invalid ensemble paths')
        w = self.weights[:len(lstm)]
        if category is not None and str(category) in self.category_weights:
            w = np.full(len(lstm), float(self.category_weights[str(category)]), dtype=float)
        trust = self.trust_weights[:len(lstm)]
        base = (1-w)*lstm+w*lgbm
        horizon_prediction = np.asarray(anchor) + trust*(base-np.asarray(anchor))
        category_trust = self.category_trust_weights.get(str(category))
        if category_trust is not None:
            horizon_prediction = (np.asarray(anchor)
                                  + category_trust[:len(lstm)]
                                  *(horizon_prediction-np.asarray(anchor)))
        if (reference is not None and np.isfinite(self.anomaly_threshold)
                and abs(np.log(float(anchor)/float(reference))) > self.anomaly_threshold):
            horizons = np.arange(1, len(lstm)+1, dtype=float)
            strength = self.anomaly_strength*(1-np.exp(-horizons/self.anomaly_decay))
            horizon_prediction += strength*(float(reference)-horizon_prediction)
        if product is not None and self.specialist_blends:
            bins = self._horizon_bins(np.arange(1, len(lstm)+1))
            for index, horizon_bin in enumerate(bins):
                choice = self.specialist_blends.get(f'{product}##{int(horizon_bin)}')
                if choice is None:
                    continue
                source = {'lstm':lstm[index], 'lgbm':lgbm[index],
                          'persistence':float(anchor)}.get(
                    choice['model'])
                if choice['model'] == 'moving_average7' and reference is not None:
                    source = float(reference)
                if source is not None:
                    weight = choice['weight']
                    horizon_prediction[index] = ((1-weight)*horizon_prediction[index]
                                                 + weight*source)
        return horizon_prediction

    def predict_rows(self, lstm, lgbm, horizons, anchors, series=None, references=None):
        lstm, lgbm = np.asarray(lstm), np.asarray(lgbm)
        indices = np.asarray(horizons, dtype=int) - 1
        anchors = np.asarray(anchors, dtype=float)
        if (lstm.shape != lgbm.shape or indices.shape != lstm.shape
                or anchors.shape != lstm.shape):
            raise ValueError('Invalid row-wise ensemble inputs')
        if (indices < 0).any() or (indices >= len(self.weights)).any():
            raise ValueError('Forecast horizon outside calibrated range')
        w = self.weights[indices].astype(float, copy=True)
        if series is not None and self.category_weights:
            series_arr = np.asarray(series).astype(str)
            if series_arr.shape != lstm.shape:
                raise ValueError('Invalid row-wise series identities')
            for index, identity in enumerate(series_arr):
                cat_w = self.category_weights.get(identity.split('||', 1)[0])
                if cat_w is not None:
                    w[index] = float(cat_w)
        trust = self.trust_weights[indices]
        base = (1-w)*lstm+w*lgbm
        horizon_prediction = anchors + trust*(base-anchors)
        if series is not None and self.category_trust_weights:
            series = np.asarray(series).astype(str)
            if series.shape != lstm.shape:
                raise ValueError('Invalid row-wise series identities')
            category_trust = np.ones(len(lstm), dtype=float)
            for index, identity in enumerate(series):
                weights = self.category_trust_weights.get(identity.split('||', 1)[0])
                if weights is not None:
                    category_trust[index] = weights[indices[index]]
            horizon_prediction = anchors + category_trust*(horizon_prediction-anchors)
        if references is not None and np.isfinite(self.anomaly_threshold):
            references = np.asarray(references, dtype=float)
            if references.shape != lstm.shape or (references <= 0).any():
                raise ValueError('Invalid anomaly references')
            anomaly = np.abs(np.log(anchors/references)) > self.anomaly_threshold
            strength = self.anomaly_strength*(
                1-np.exp(-(indices.astype(float)+1)/self.anomaly_decay))
            horizon_prediction[anomaly] += strength[anomaly]*(
                references[anomaly]-horizon_prediction[anomaly])
        if series is not None and self.specialist_blends:
            bins = self._horizon_bins(indices+1)
            for index, identity in enumerate(series):
                product = '||'.join(identity.split('||')[:2])
                choice = self.specialist_blends.get(f'{product}##{int(bins[index])}')
                if choice is None:
                    continue
                source = {'lstm':lstm[index], 'lgbm':lgbm[index],
                          'persistence':anchors[index]}.get(
                    choice['model'])
                if choice['model'] == 'moving_average7' and references is not None:
                    source = references[index]
                if source is not None:
                    weight = choice['weight']
                    horizon_prediction[index] = ((1-weight)*horizon_prediction[index]
                                                 + weight*source)
        return horizon_prediction

    def save(self):
        self.path.mkdir(parents=True,exist_ok=True)
        payload = {
            'objective':'validation_equal_mae_rmse_mape_with_persistence_shrinkage',
            'weight_selection_objective': self.objective,
            'calibration':self.calibration,
            'weights':self.weights.tolist(),
            'trust_weights':self.trust_weights.tolist(),
            'category_trust_weights':{
                key:value.tolist() for key,value in self.category_trust_weights.items()},
            'specialist_blends':self.specialist_blends,
            'anomaly_reversion':{
                'reference':'trailing_7_day_mean',
                'log_ratio_threshold':self.anomaly_threshold,
                'strength':self.anomaly_strength,
                'decay':self.anomaly_decay},
        }
        if self.category_weights:
            payload['category_weights'] = {
                key: float(value) for key, value in self.category_weights.items()
            }
        (self.path/'ensemble.json').write_text(json.dumps(payload),encoding='utf-8')

    def load(self):
        data = json.loads((self.path/'ensemble.json').read_text(encoding='utf-8'))
        self.objective = data.get('weight_selection_objective', 'balanced')
        self.weights = np.asarray(data['weights'],dtype=float)
        self.trust_weights = np.asarray(
            data.get('trust_weights', np.ones(len(self.weights))), dtype=float)
        self.category_weights = {
            key: float(value)
            for key, value in data.get('category_weights', {}).items()
        }
        self.category_trust_weights = {
            key:np.asarray(value,dtype=float)
            for key,value in data.get('category_trust_weights', {}).items()
        }
        self.specialist_blends = data.get('specialist_blends', {})
        anomaly = data.get('anomaly_reversion', {})
        self.anomaly_threshold = float(anomaly.get('log_ratio_threshold', 1e9))
        self.anomaly_strength = float(anomaly.get('strength', 0.0))
        self.anomaly_decay = float(anomaly.get('decay', 1.0))
        self.calibration = data.get('calibration', {'scope':'legacy_in_sample'})
        if not (len(self.trust_weights) == len(self.weights)
                and np.isfinite(self.weights).all()
                and np.isfinite(self.trust_weights).all()
                and ((self.weights>=0)&(self.weights<=1)).all()):
            raise ValueError('Invalid ensemble state')
        if not ((self.trust_weights>=0)&(self.trust_weights<=1)).all():
            raise ValueError('Invalid ensemble trust weights')
        if any(not np.isfinite(value) or not (0.0 <= value <= 1.0)
               for value in self.category_weights.values()):
            raise ValueError('Invalid category weights')
        if any(len(value) != len(self.weights)
               or not np.isfinite(value).all()
               or not ((value>=0)&(value<=1)).all()
               for value in self.category_trust_weights.values()):
            raise ValueError('Invalid category trust weights')
        if any(value.get('model') not in {'lstm','lgbm','persistence','moving_average7'}
               or not 0 <= value.get('weight', -1) <= 1
               for value in self.specialist_blends.values()):
            raise ValueError('Invalid specialist blends')
        if (self.anomaly_threshold <= 0 or not 0 <= self.anomaly_strength <= 1
                or self.anomaly_decay <= 0):
            raise ValueError('Invalid anomaly reversion state')
