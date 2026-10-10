"""One-step LightGBM; multi-step inference is explicitly recursive in ForecastEngine."""
from pathlib import Path
import json
import lightgbm as lgb
import numpy as np
from config.settings import get_settings
from features.builder import (FEATURE_COLUMNS, FEATURE_COLUMNS_V3, FEATURE_VERSION,
                              LEGACY_FEATURE_COLUMNS)
from utils.metrics import compute_all_metrics


class LightGBMModel:
    def __init__(self, artifact_dir=None):
        cfg = get_settings()
        self.path = Path(artifact_dir or cfg.artifacts_dir)
        self._model = None
        self._feature_names = list(FEATURE_COLUMNS)
        self._feature_version = FEATURE_VERSION
        self.target_mode = cfg.lgbm_target_mode
        self.training_configuration = None
        if self.target_mode not in {"absolute", "relative"}:
            raise ValueError("FOODCAST_LGBM_TARGET_MODE must be 'absolute' or 'relative'")

    def _training_target(self, X, y):
        values = np.asarray(y, dtype=float)
        if self.target_mode == "absolute":
            return values
        anchor = X["price_lag_1d"].to_numpy(dtype=float)
        if not np.isfinite(anchor).all() or (anchor <= 0).any():
            raise ValueError("Relative LightGBM targets require positive finite price_lag_1d")
        return values / anchor - 1.0

    def train(self, X_train, y_train, X_val, y_val, incremental=False):
        if incremental:
            raise ValueError('Warm starts are disabled: use a fresh chronological experiment')
        if list(X_train.columns) != self._feature_names or list(X_val.columns) != self._feature_names:
            raise ValueError('Feature schema mismatch')
        if not len(X_train) or not len(X_val):
            raise ValueError('Observed training and validation data required')
        params = dict(get_settings().lgbm_params)
        rounds = params.pop('n_estimators')
        patience = params.pop('early_stopping_rounds')
        params['seed'] = get_settings().random_seed
        cats = [c for c in self._feature_names if c.endswith('_encoded')]
        train = lgb.Dataset(
            X_train, label=self._training_target(X_train, y_train),
            categorical_feature=cats)
        val = lgb.Dataset(
            X_val, label=self._training_target(X_val, y_val), reference=train,
            categorical_feature=cats)
        self._model = lgb.train(params, train, num_boost_round=rounds, valid_sets=[train,val],
            valid_names=['train','validation'], callbacks=[lgb.early_stopping(patience,first_metric_only=True),
                                                         lgb.log_evaluation(100)])
        self.training_configuration = {
            "parameters": dict(params),
            "requested_boost_rounds": int(rounds),
            "early_stopping_rounds": int(patience),
            "best_iteration": int(self._model.best_iteration),
        }
        self.save()
        return compute_all_metrics(y_val, self.predict(X_val))

    def predict(self, X):
        if self._model is None:
            self.load()
        values = X[self._feature_names]
        if not np.isfinite(values.to_numpy(dtype=float)).all():
            raise ValueError('Nonfinite LightGBM features')
        predicted = self._model.predict(values, num_threads=4)
        if self.target_mode == "relative":
            predicted = values["price_lag_1d"].to_numpy(dtype=float) * (1.0 + predicted)
        return np.maximum(0.01, predicted)

    def feature_importance(self, importance_type='gain'):
        scores = self._model.feature_importance(importance_type)
        total = max(float(scores.sum()),1)
        return dict(sorted(zip(self._feature_names,(scores/total).tolist()),key=lambda x:-x[1]))

    def save(self):
        self.path.mkdir(parents=True,exist_ok=True)
        # Explicit bytes avoid platform newline translation of tree offsets.
        (self.path/'lightgbm_model.txt').write_bytes(self._model.model_to_string().encode('utf-8'))
        meta = {'feature_version': self._feature_version,
                'features': self._feature_names,
                'target_mode': self.target_mode}
        if self.training_configuration is not None:
            meta['training_configuration'] = self.training_configuration
        (self.path/'lightgbm_meta.json').write_text(
            json.dumps(meta, indent=2), encoding='utf-8')

    def load(self):
        meta = json.loads((self.path/'lightgbm_meta.json').read_text(encoding='utf-8'))
        supported = {2: LEGACY_FEATURE_COLUMNS, 3: FEATURE_COLUMNS_V3,
                     FEATURE_VERSION: FEATURE_COLUMNS}
        version = meta.get('feature_version')
        if version not in supported or meta.get('features') != supported[version]:
            raise ValueError('Incompatible LightGBM bundle; retrain with the current schema')
        self._feature_names = list(meta['features'])
        self._feature_version = version
        self.target_mode = meta.get('target_mode', 'absolute')
        self.training_configuration = meta.get('training_configuration')
        if self.target_mode not in {'absolute', 'relative'}:
            raise ValueError('Incompatible LightGBM target mode')
        self._model = lgb.Booster(model_str=(self.path/'lightgbm_model.txt').read_text(encoding='utf-8'))
        if self._model.feature_name() != self._feature_names:
            raise ValueError('Stored LightGBM feature order mismatch')
