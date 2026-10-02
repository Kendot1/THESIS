"""Validation-calibrated model blend and empirical relative-error bands."""
import json
from pathlib import Path
import numpy as np
from config.settings import get_settings

INTERVAL_LEVELS = (.8, .9, .95)


class EnsembleModel:
    def __init__(self, artifact_dir=None):
        self.path = Path(artifact_dir or get_settings().artifacts_dir)
        self.weights = None
        self.trust_weights = None
        self.category_trust_weights = {}
        self.anomaly_threshold = 1e9
        self.anomaly_strength = 0.0
        self.anomaly_decay = 1.0
        self.specialist_blends = {}
        self.widths = None
        self.interval_widths = {}
        self.category_interval_widths = {}
        self.fallback_interval_widths = {}
        self.calibration = {'scope': 'legacy_in_sample'}

    def fit(self, frame, horizon, calibration_frame=None):
        if len(frame) < 2:
            raise ValueError('At least two observed validation forecasts are required')
        self.category_trust_weights, self.specialist_blends = {}, {}
        self.anomaly_threshold, self.anomaly_strength, self.anomaly_decay = 1e9, 0.0, 1.0
        if calibration_frame is not None and {'date', 'origin'}.issubset(frame.columns):
            import pandas as pd
            if pd.to_datetime(frame.date).max() > pd.to_datetime(calibration_frame.origin).min():
                raise ValueError('Calibration must follow all ensemble tuning targets')
        actual, lstm, lgbm = (frame[c].to_numpy() for c in ['actual','lstm','lgbm'])
        candidates = np.linspace(0, 1, 101)
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
                scores.append(
                    np.mean(np.abs(error))/denominators[0]
                    + np.sqrt(np.mean(error**2))/denominators[1]
                    + np.mean(np.abs(error/a))/denominators[2]
                )
            trust = float(candidates[int(np.argmin(scores))])
            prediction = anchor + trust*(base-anchor)
            weights.append(global_weight)
            trust_weights.append(trust)
        self.weights = np.array(weights)
        self.trust_weights = np.array(trust_weights)
        self.category_trust_weights = self._fit_category_trust(frame, candidates)
        self._fit_anomaly_reversion(frame)
        final = self.predict_rows(
            frame.lstm.to_numpy(), frame.lgbm.to_numpy(),
            frame.horizon.to_numpy(), frame.anchor.to_numpy(),
            frame.series.to_numpy() if 'series' in frame else None,
            frame.moving_average7.to_numpy() if 'moving_average7' in frame else None)
        specialist_frame = frame.copy()
        specialist_frame['ensemble'] = final
        self.specialist_blends = self._fit_stable_specialists(specialist_frame)
        self.calibrate_intervals(frame if calibration_frame is None else calibration_frame,
                                 horizon, independent=calibration_frame is not None)
        self.save()
        return self

    @staticmethod
    def _error_quantile(errors, level):
        # Finite-sample rank correction. Time-series dependence means nominal
        # coverage is a target, not an exchangeability-based guarantee.
        errors = np.sort(np.asarray(errors, dtype=float))
        if not len(errors) or not np.isfinite(errors).all():
            raise ValueError('Calibration requires finite observed errors')
        rank = min(len(errors), int(np.ceil((len(errors)+1)*level)))
        return float(errors[rank-1])

    def calibrate_intervals(self, frame, horizon, independent=False):
        point = self.predict_rows(
            frame.lstm.to_numpy(), frame.lgbm.to_numpy(), frame.horizon.to_numpy(),
            frame.anchor.to_numpy(), frame.series.to_numpy() if 'series' in frame else None,
            frame.moving_average7.to_numpy() if 'moving_average7' in frame else None)
        anchors = frame.anchor.to_numpy(dtype=float)
        actual = frame.actual.to_numpy(dtype=float)
        if (anchors <= 0).any() or not np.isfinite(anchors).all():
            raise ValueError('Calibration requires positive finite anchors')
        relative_error = np.abs(actual-point)/anchors
        fallback_error = np.abs(actual-anchors)/anchors
        horizon_values = frame.horizon.to_numpy(dtype=int)
        self.interval_widths, self.category_interval_widths = {}, {}
        self.fallback_interval_widths = {}
        for level in INTERVAL_LEVELS:
            widths, fallback_widths = [], []
            for h in range(1, horizon+1):
                errors = relative_error[horizon_values == h]
                if not len(errors):
                    errors = relative_error
                widths.append(self._error_quantile(errors, level))
                fallback = fallback_error[horizon_values == h]
                fallback_widths.append(self._error_quantile(
                    fallback if len(fallback) else fallback_error, level))
            self.interval_widths[str(level)] = np.asarray(widths)
            self.fallback_interval_widths[str(level)] = np.asarray(fallback_widths)
        # Pool nearby horizons within each category to avoid unstable quantiles
        # for sparse product series, falling back to the global horizon band.
        if 'series' in frame:
            categories = frame.series.astype(str).str.split('||', regex=False).str[0]
            bins = self._horizon_bins(horizon_values)
            target_bins = self._horizon_bins(np.arange(1, horizon+1))
            for category in sorted(categories.unique()):
                calibrated = {key: value.copy() for key, value in self.interval_widths.items()}
                for horizon_bin in np.unique(target_bins):
                    mask = (categories.to_numpy() == category) & (bins == horizon_bin)
                    if mask.sum() < 100:
                        continue
                    for level in INTERVAL_LEVELS:
                        calibrated[str(level)][target_bins == horizon_bin] = self._error_quantile(
                            relative_error[mask], level)
                self.category_interval_widths[str(category)] = calibrated
        self.widths = self.interval_widths[str(INTERVAL_LEVELS[0])]
        self.calibration = {
            'scope': 'held_out_from_ensemble_fit' if independent else 'in_sample_diagnostic',
            'sample_count': len(frame), 'minimum_category_bin_samples': 100,
            'start': str(frame.date.min()) if 'date' in frame else None,
            'end': str(frame.date.max()) if 'date' in frame else None,
            'coverage_guarantee': False,
        }
        return self

    def _fit_category_trust(self, frame, candidates):
        if 'series' not in frame:
            return {}
        categories = frame.series.astype(str).str.split('||', regex=False).str[0]
        result = {}
        for category in sorted(categories.unique()):
            category_weights = []
            for h in range(1, len(self.weights)+1):
                mask = (categories == category) & (frame.horizon == h)
                rows = frame[mask]
                if len(rows) < 10:
                    category_weights.append(1.0)
                    continue
                a,l,g,anchor = (rows[c].to_numpy(dtype=float)
                                for c in ['actual','lstm','lgbm','anchor'])
                base = (1-self.weights[h-1])*l + self.weights[h-1]*g
                horizon_prediction = anchor + self.trust_weights[h-1]*(base-anchor)
                persistence_error = a-anchor
                denominators = np.maximum(np.array([
                    np.mean(np.abs(persistence_error)),
                    np.sqrt(np.mean(persistence_error**2)),
                    np.mean(np.abs(persistence_error/a)),
                ]), 1e-12)
                scores = []
                for trust in candidates[::5]:
                    prediction = anchor + trust*(horizon_prediction-anchor)
                    error = a-prediction
                    scores.append(
                        np.mean(np.abs(error))/denominators[0]
                        + np.sqrt(np.mean(error**2))/denominators[1]
                        + np.mean(np.abs(error/a))/denominators[2]
                    )
                category_weights.append(float(candidates[::5][int(np.argmin(scores))]))
            result[str(category)] = np.asarray(category_weights)
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

    def _fit_anomaly_reversion(self, frame):
        if 'moving_average7' not in frame:
            return
        base = self.predict_rows(
            frame.lstm.to_numpy(), frame.lgbm.to_numpy(),
            frame.horizon.to_numpy(), frame.anchor.to_numpy(),
            frame.series.to_numpy() if 'series' in frame else None)
        anchor = frame.anchor.to_numpy(dtype=float)
        reference = frame.moving_average7.to_numpy(dtype=float)
        horizons = frame.horizon.to_numpy(dtype=float)
        best = (self._normalized_score(frame, base), 1e9, 0.0, 1.0)
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
                    score = self._normalized_score(frame, prediction)
                    if score < best[0]:
                        best = (score, threshold, strength, decay)
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

    def _fit_stable_specialists(self, frame):
        required = {'origin','series','ensemble','lstm','anchor','moving_average7'}
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

        def choose(rows):
            baseline = self._error_triplet(rows, rows.ensemble)
            best = (1.0, None, 0.0)
            for name in alternatives:
                for weight in np.linspace(.05, .5, 10):
                    prediction = (1-weight)*rows.ensemble+weight*rows[name]
                    score = float(np.mean(self._error_triplet(rows, prediction)/baseline))
                    if score < best[0]:
                        best = (score, name, float(weight))
            return best

        def stable(rows, name, weight):
            baseline = self._error_triplet(rows, rows.ensemble)
            prediction = (1-weight)*rows.ensemble+weight*rows[name]
            ratios = self._error_triplet(rows, prediction)/baseline
            return bool((ratios < 1).all() and ratios.mean() <= .9975)

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
                           'lstm':'lstm'}[name]
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
                source = {'lstm':lstm[index], 'persistence':float(anchor)}.get(
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
        w = self.weights[indices]
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
                source = {'lstm':lstm[index], 'persistence':anchors[index]}.get(
                    choice['model'])
                if choice['model'] == 'moving_average7' and references is not None:
                    source = references[index]
                if source is not None:
                    weight = choice['weight']
                    horizon_prediction[index] = ((1-weight)*horizon_prediction[index]
                                                 + weight*source)
        return horizon_prediction

    def _widths_for(self, confidence):
        key = str(float(confidence))
        if key not in self.interval_widths:
            supported = ", ".join(sorted(self.interval_widths))
            raise ValueError(f'Unsupported confidence level {confidence}; choose {supported}')
        return self.interval_widths[key]

    def intervals(self, point, anchor, confidence=.8, category=None, fallback=False):
        series = None if category is None else np.repeat(str(category), len(point))
        return self.intervals_rows(point, np.full(len(point), anchor),
                                   np.arange(1, len(point)+1), confidence, series, fallback)

    def intervals_rows(self, point, anchor, horizons, confidence=.8, series=None, fallback=False):
        indices = np.asarray(horizons, dtype=int) - 1
        base = self._widths_for(confidence)
        point, anchor = np.asarray(point, dtype=float), np.asarray(anchor, dtype=float)
        if (point.ndim != 1 or point.shape != indices.shape or anchor.shape != point.shape
                or (indices < 0).any() or (indices >= len(base)).any()
                or not np.isfinite(point).all() or not np.isfinite(anchor).all()
                or (anchor <= 0).any() or (point <= 0).any()
                or not np.array_equal(np.asarray(horizons), indices+1)):
            raise ValueError('Invalid interval inputs')
        key = str(float(confidence))
        relative = (self.fallback_interval_widths.get(key, base) if fallback else base)[indices].copy()
        if series is not None and not fallback:
            if np.asarray(series).shape != point.shape:
                raise ValueError('Invalid interval series identities')
            for i, identity in enumerate(series):
                category = str(identity).split('||', 1)[0]
                widths = self.category_interval_widths.get(category, {}).get(key)
                if widths is not None:
                    relative[i] = widths[indices[i]]
        width = relative * anchor
        return np.maximum(.01, point-width), point+width

    def save(self):
        self.path.mkdir(parents=True,exist_ok=True)
        (self.path/'ensemble.json').write_text(json.dumps({
            'objective':'validation_equal_mae_rmse_mape_with_persistence_shrinkage',
            'interval':'heldout_category_horizon_relative_absolute_error',
            'calibration':self.calibration,
            'category_interval_widths':{
                category:{key:value.tolist() for key,value in levels.items()}
                for category,levels in self.category_interval_widths.items()},
            'fallback_interval_widths':{
                key:value.tolist() for key,value in self.fallback_interval_widths.items()},
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
            'interval_widths':{
                key:value.tolist() for key,value in self.interval_widths.items()},
            'widths':self.widths.tolist()}),encoding='utf-8')

    def load(self):
        data = json.loads((self.path/'ensemble.json').read_text(encoding='utf-8'))
        self.weights = np.asarray(data['weights'],dtype=float)
        self.trust_weights = np.asarray(
            data.get('trust_weights', np.ones(len(self.weights))), dtype=float)
        self.category_trust_weights = {
            key:np.asarray(value,dtype=float)
            for key,value in data.get('category_trust_weights', {}).items()
        }
        self.specialist_blends = data.get('specialist_blends', {})
        anomaly = data.get('anomaly_reversion', {})
        self.anomaly_threshold = float(anomaly.get('log_ratio_threshold', 1e9))
        self.anomaly_strength = float(anomaly.get('strength', 0.0))
        self.anomaly_decay = float(anomaly.get('decay', 1.0))
        self.widths = np.asarray(data['widths'],dtype=float)
        saved_widths = data.get('interval_widths')
        self.interval_widths = ({key:np.asarray(value,dtype=float)
                                 for key,value in saved_widths.items()}
                                if saved_widths else {'0.8':self.widths})
        self.interval_widths.setdefault('0.8', self.widths)
        self.calibration = data.get('calibration', {'scope':'legacy_in_sample'})
        self.category_interval_widths = {
            category:{key:np.asarray(value, dtype=float) for key,value in levels.items()}
            for category,levels in data.get('category_interval_widths', {}).items()}
        self.fallback_interval_widths = {
            key:np.asarray(value, dtype=float)
            for key,value in data.get('fallback_interval_widths', {}).items()}
        additional = list(self.fallback_interval_widths.values()) + [
            value for levels in self.category_interval_widths.values() for value in levels.values()]
        if any(len(value) != len(self.weights) or not np.isfinite(value).all()
               or (value < 0).any() for value in additional):
            raise ValueError('Invalid category or fallback interval widths')
        if not (len(self.trust_weights) == len(self.weights)
                and np.isfinite(self.weights).all()
                and np.isfinite(self.trust_weights).all()
                and np.isfinite(self.widths).all()
                and ((self.weights>=0)&(self.weights<=1)).all() and (self.widths>=0).all()):
            raise ValueError('Invalid ensemble state')
        if not ((self.trust_weights>=0)&(self.trust_weights<=1)).all():
            raise ValueError('Invalid ensemble trust weights')
        if any(len(value) != len(self.weights) or not np.isfinite(value).all()
               or (value < 0).any() for value in self.interval_widths.values()):
            raise ValueError('Invalid interval widths')
        if any(len(value) != len(self.weights)
               or not np.isfinite(value).all()
               or not ((value>=0)&(value<=1)).all()
               for value in self.category_trust_weights.values()):
            raise ValueError('Invalid category trust weights')
        if any(value.get('model') not in {'lstm','persistence','moving_average7'}
               or not 0 <= value.get('weight', -1) <= 1
               for value in self.specialist_blends.values()):
            raise ValueError('Invalid specialist blends')
        if (self.anomaly_threshold <= 0 or not 0 <= self.anomaly_strength <= 1
                or self.anomaly_decay <= 0):
            raise ValueError('Invalid anomaly reversion state')
