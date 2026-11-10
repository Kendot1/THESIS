"""One-step LightGBM; multi-step inference is explicitly recursive in ForecastEngine."""
from pathlib import Path
import json
import lightgbm as lgb
import numpy as np
from config.settings import get_settings
from features.builder import (FEATURE_COLUMNS_V3, FEATURE_COLUMNS_V4,
                              FEATURE_COLUMNS_V5, FEATURE_COLUMNS_V6, FEATURE_COLUMNS_V7,
                              FEATURE_COLUMNS_V8, FEATURE_COLUMNS_V9, FEATURE_COLUMNS_V10,
                              FEATURE_COLUMNS_V11, FEATURE_COLUMNS_V12,
                              FEATURE_COLUMNS_V13,
                              FEATURE_VERSION,
                              LEGACY_FEATURE_COLUMNS)
from utils.metrics import compute_all_metrics

RESIDUAL_FEATURE_SCHEMA = "recursive_lstm_path_v1"
RESIDUAL_FEATURE_COLUMNS = [
    "lstm_base_relative_change",
    "forecast_lead_fraction",
]


def _within5_squared_hinge_grad_hess(prediction, target, anchor,
                                      sample_weight=None):
    """Gradient/Hessian for squared PHP error outside the +/-5 hit band."""
    prediction = np.asarray(prediction, dtype=float).reshape(-1)
    target = np.asarray(target, dtype=float).reshape(-1)
    anchor = np.asarray(anchor, dtype=float).reshape(-1)
    if (prediction.shape != target.shape or anchor.shape != target.shape
            or not np.isfinite(prediction).all()
            or not np.isfinite(target).all()
            or not np.isfinite(anchor).all() or (anchor <= 0).any()):
        raise ValueError("Within-5 objective inputs must be finite and row-aligned")
    error_php = anchor * (prediction - target)
    outside_margin = np.maximum(np.abs(error_php) - 5.0, 0.0)
    gradient = 2.0 * outside_margin * np.sign(error_php) * anchor
    hessian = np.where(outside_margin > 0.0, 2.0 * anchor ** 2, 1e-6)
    if sample_weight is not None:
        weights = np.asarray(sample_weight, dtype=float).reshape(-1)
        if (weights.shape != target.shape or not np.isfinite(weights).all()
                or (weights <= 0).any()):
            raise ValueError("Within-5 objective weights must be positive and aligned")
        gradient *= weights
        hessian *= weights
    return gradient, np.maximum(hessian, 1e-6)


def _within5_softplus_grad_hess(prediction, target, anchor,
                                sample_weight=None, temperature_php=2.0):
    """Smooth PHP-5 miss loss with a fixed PHP-scale transition temperature."""
    prediction = np.asarray(prediction, dtype=float).reshape(-1)
    target = np.asarray(target, dtype=float).reshape(-1)
    anchor = np.asarray(anchor, dtype=float).reshape(-1)
    if (prediction.shape != target.shape or anchor.shape != target.shape
            or not np.isfinite(prediction).all()
            or not np.isfinite(target).all()
            or not np.isfinite(anchor).all() or (anchor <= 0).any()
            or not np.isfinite(temperature_php) or temperature_php <= 0):
        raise ValueError("Within-5 softplus inputs must be finite and row-aligned")
    error_php = anchor * (prediction - target)
    margin = (np.abs(error_php) - 5.0) / float(temperature_php)
    probability = 1.0 / (1.0 + np.exp(-np.clip(margin, -40.0, 40.0)))
    gradient = probability * np.sign(error_php) * anchor
    hessian = (probability * (1.0 - probability)
               / float(temperature_php) * anchor ** 2)
    if sample_weight is not None:
        weights = np.asarray(sample_weight, dtype=float).reshape(-1)
        if (weights.shape != target.shape or not np.isfinite(weights).all()
                or (weights <= 0).any()):
            raise ValueError("Within-5 softplus weights must be positive and aligned")
        gradient *= weights
        hessian *= weights
    return gradient, np.maximum(hessian, 1e-6)


class LightGBMModel:
    def __init__(self, artifact_dir=None, feature_version=None, target_mode=None):
        cfg = get_settings()
        self.path = Path(artifact_dir or cfg.artifacts_dir)
        self._model = None
        self._feature_version = int(feature_version or FEATURE_VERSION)
        supported = {2: LEGACY_FEATURE_COLUMNS, 3: FEATURE_COLUMNS_V3,
                     4: FEATURE_COLUMNS_V4, 5: FEATURE_COLUMNS_V5,
                     6: FEATURE_COLUMNS_V6, 7: FEATURE_COLUMNS_V7,
                     8: FEATURE_COLUMNS_V8, 9: FEATURE_COLUMNS_V9,
                     10: FEATURE_COLUMNS_V10, 11: FEATURE_COLUMNS_V11,
                     12: FEATURE_COLUMNS_V12, 13: FEATURE_COLUMNS_V13}
        if self._feature_version not in supported:
            raise ValueError('Unsupported LightGBM feature version')
        self._base_feature_names = list(supported[self._feature_version])
        self.target_mode = str(target_mode or cfg.lgbm_target_mode).lower()
        self.residual_feature_schema = (
            RESIDUAL_FEATURE_SCHEMA if self.target_mode in {
                "residual_absolute", "residual_relative"} else None)
        self._feature_names = list(self._base_feature_names)
        if self.residual_feature_schema == RESIDUAL_FEATURE_SCHEMA:
            self._feature_names += RESIDUAL_FEATURE_COLUMNS
        self.training_configuration = None
        if self.target_mode not in {
                "absolute", "relative", "log_relative",
                "residual_absolute", "residual_relative"}:
            raise ValueError(
                "Unsupported LightGBM target mode; expected absolute, relative, "
                "log_relative, residual_absolute, or residual_relative")

    @property
    def is_residual_model(self):
        return self.target_mode in {"residual_absolute", "residual_relative"}

    def _training_target(self, X, y, base_prediction=None):
        values = np.asarray(y, dtype=float)
        if not np.isfinite(values).all():
            raise ValueError("LightGBM targets must be finite")
        if self.is_residual_model:
            if base_prediction is None:
                raise ValueError("Residual LightGBM training requires LSTM base predictions")
            base = np.asarray(base_prediction, dtype=float).reshape(-1)
            if base.shape != values.shape or not np.isfinite(base).all():
                raise ValueError("Residual LightGBM base predictions are not aligned")
            values = values - base
        if self.target_mode in {"absolute", "residual_absolute"}:
            return values
        anchor = X["price_lag_1d"].to_numpy(dtype=float)
        if not np.isfinite(anchor).all() or (anchor <= 0).any():
            raise ValueError("Relative LightGBM targets require positive finite price_lag_1d")
        if self.target_mode == "residual_relative":
            return values / anchor
        if self.target_mode == "log_relative":
            if (values <= 0).any():
                raise ValueError("Log-relative LightGBM targets require positive finite prices")
            return np.log(values / anchor)
        return values / anchor - 1.0

    def train(self, X_train, y_train, X_val, y_val, incremental=False,
              train_sample_weight=None, sample_weight_description=None,
              base_train_prediction=None, base_val_prediction=None):
        if incremental:
            raise ValueError('Warm starts are disabled: use a fresh chronological experiment')
        if list(X_train.columns) != self._feature_names or list(X_val.columns) != self._feature_names:
            raise ValueError('Feature schema mismatch')
        if not len(X_train) or not len(X_val):
            raise ValueError('Observed training and validation data required')
        settings = get_settings()
        params = dict(settings.lgbm_params)
        rounds = params.pop('n_estimators')
        patience = params.pop('early_stopping_rounds')
        params['seed'] = settings.random_seed
        cats = [c for c in self._feature_names if c.endswith('_encoded')]
        train_target = self._training_target(
            X_train, y_train, base_prediction=base_train_prediction)
        validation_target = self._training_target(
            X_val, y_val, base_prediction=base_val_prediction)
        base_train_weight = None
        if train_sample_weight is not None:
            base_train_weight = np.asarray(train_sample_weight, dtype=float)
            if (base_train_weight.shape != (len(X_train),)
                    or not np.isfinite(base_train_weight).all()
                    or (base_train_weight <= 0).any()):
                raise ValueError("Training sample weights must be positive finite values aligned to X_train")

        def combine_train_weights(objective_weight=None):
            if base_train_weight is None:
                return objective_weight
            if objective_weight is None:
                return base_train_weight
            return base_train_weight * np.asarray(objective_weight, dtype=float)

        objective = params.get('objective')
        training = None
        validation = None
        custom_metric = None
        mape_delta = None
        mape_metric_used = (objective in {'mape_pseudo_huber', 'mape_weighted_l1'}
                            or params.get('metric') == 'mape_pct')
        actual_price_metric = params.get('metric')
        actual_price_metric_used = (
            isinstance(actual_price_metric, str)
            and actual_price_metric in {'mae_php', 'rmse_php'})
        within5_metric_used = params.get('metric') == 'within5_miss_pct'

        def price_scale(features, target, prediction):
            if self.target_mode in {'relative', 'log_relative',
                                    'residual_relative'}:
                anchor = features['price_lag_1d'].to_numpy(dtype=float)
                if self.target_mode == 'residual_relative':
                    base = (base_val_prediction if features is X_val
                            else base_train_prediction)
                    base = np.asarray(base, dtype=float)
                    actual = base + anchor * target
                    predicted = base + anchor * prediction
                elif self.target_mode == 'relative':
                    actual = anchor * (1.0 + target)
                    predicted = anchor * (1.0 + prediction)
                else:
                    actual = anchor * np.exp(np.clip(target, -100.0, 100.0))
                    predicted = anchor * np.exp(np.clip(prediction, -100.0, 100.0))
            elif self.target_mode == 'residual_absolute':
                base = (base_val_prediction if features is X_val
                        else base_train_prediction)
                base = np.asarray(base, dtype=float)
                actual = base + target
                predicted = base + prediction
            else:
                actual = target
                predicted = prediction
            return actual, np.maximum(0.01, predicted)

        def actual_price_mape(prediction, dataset):
            if dataset is validation:
                features, target = X_val, validation_target
            else:
                features, target = X_train, train_target
            actual, predicted = price_scale(features, target, prediction)
            percentage_error = np.abs(predicted - actual) / actual
            return 'mape_pct', float(np.mean(percentage_error) * 100.0), False

        def actual_price_mae(prediction, dataset):
            if dataset is validation:
                features, target = X_val, validation_target
            else:
                features, target = X_train, train_target
            actual, predicted = price_scale(features, target, prediction)
            return 'mae_php', float(np.mean(np.abs(predicted - actual))), False

        def actual_price_rmse(prediction, dataset):
            if dataset is validation:
                features, target = X_val, validation_target
            else:
                features, target = X_train, train_target
            actual, predicted = price_scale(features, target, prediction)
            error = predicted - actual
            return 'rmse_php', float(np.sqrt(np.mean(error * error))), False

        def actual_price_within5_miss(prediction, dataset):
            if dataset is validation:
                features, target = X_val, validation_target
            else:
                features, target = X_train, train_target
            actual, predicted = price_scale(features, target, prediction)
            miss_rate = np.mean(np.abs(predicted - actual) > 5.0) * 100.0
            return 'within5_miss_pct', float(miss_rate), False

        def inverse_actual_mape_weight(features, target, base_prediction=None):
            actual, _ = price_scale(features, target, target)
            if self.target_mode in {'relative', 'residual_relative'}:
                numerator = features['price_lag_1d'].to_numpy(dtype=float)
            else:
                numerator = np.ones(len(features), dtype=float)
            return numerator / np.maximum(actual, 1e-9)

        if objective in {'within5_squared_hinge', 'within5_softplus'}:
            if self.target_mode not in {'relative', 'residual_relative'}:
                raise ValueError('Within-5 loss requires relative LightGBM targets')
            training = lgb.Dataset(
                X_train, label=train_target, weight=base_train_weight,
                categorical_feature=cats)
            validation = lgb.Dataset(
                X_val, label=validation_target, reference=training,
                categorical_feature=cats)
            params['metric'] = 'None'

            def objective_function(prediction, dataset):
                if dataset is validation:
                    features, target = X_val, validation_target
                else:
                    features, target = X_train, train_target
                anchor = features['price_lag_1d'].to_numpy(dtype=float)
                if objective == 'within5_squared_hinge':
                    return _within5_squared_hinge_grad_hess(
                        prediction, target, anchor, dataset.get_weight())
                return _within5_softplus_grad_hess(
                    prediction, target, anchor, dataset.get_weight(),
                    temperature_php=2.0)

            params['objective'] = objective_function
            custom_metric = actual_price_within5_miss
        elif objective == 'mape_weighted_l1':
            if self.target_mode not in {'relative', 'residual_relative'}:
                raise ValueError('Inverse-actual weighted L1 requires relative LightGBM targets')
            objective_weight = inverse_actual_mape_weight(
                X_train, train_target, base_train_prediction)
            train_weight = combine_train_weights(objective_weight)
            validation_weight = inverse_actual_mape_weight(
                X_val, validation_target, base_val_prediction)
            training = lgb.Dataset(
                X_train, label=train_target, weight=train_weight,
                categorical_feature=cats)
            validation = lgb.Dataset(
                X_val, label=validation_target, weight=validation_weight,
                reference=training, categorical_feature=cats)
            params['objective'] = 'regression_l1'
            params['metric'] = 'None'
            custom_metric = actual_price_mape
        elif objective == 'mape_pseudo_huber':
            if self.target_mode not in {'relative', 'residual_relative'}:
                raise ValueError('MAPE pseudo-Huber requires relative LightGBM targets')
            mape_delta = float(settings.lgbm_mape_delta)
            if not np.isfinite(mape_delta) or mape_delta <= 0:
                raise ValueError('FOODCAST_LGBM_MAPE_DELTA must be finite and positive')
            objective_weight = inverse_actual_mape_weight(
                X_train, train_target, base_train_prediction)
            train_weight = combine_train_weights(objective_weight)
            validation_weight = inverse_actual_mape_weight(
                X_val, validation_target, base_val_prediction)
            training = lgb.Dataset(
                X_train, label=train_target, weight=train_weight,
                categorical_feature=cats)
            validation = lgb.Dataset(
                X_val, label=validation_target, weight=validation_weight,
                reference=training, categorical_feature=cats)
            params['metric'] = 'None'

            def objective_function(prediction, dataset):
                target = dataset.get_label()
                sample_weight = dataset.get_weight()
                if sample_weight is None:
                    sample_weight = np.ones_like(target)
                residual = prediction - target
                denominator = np.sqrt(residual * residual + mape_delta * mape_delta)
                gradient = sample_weight * residual / denominator
                hessian = (sample_weight * mape_delta * mape_delta
                           / denominator ** 3)
                return gradient, np.maximum(hessian, 1e-12)

            params['objective'] = objective_function
            custom_metric = actual_price_mape
        elif params.get('metric') == 'mape_pct':
            if self.target_mode in {'relative', 'log_relative', 'residual_relative'} and (
                    not np.isfinite(X_train['price_lag_1d'].to_numpy(dtype=float)).all()
                    or not np.isfinite(X_val['price_lag_1d'].to_numpy(dtype=float)).all()):
                raise ValueError('MAPE early stopping requires finite relative-target anchors')
            params['metric'] = 'None'
            training = lgb.Dataset(
                X_train, label=train_target, weight=base_train_weight,
                categorical_feature=cats)
            validation = lgb.Dataset(
                X_val, label=validation_target, reference=training,
                categorical_feature=cats)
            custom_metric = actual_price_mape
        elif actual_price_metric_used:
            training = lgb.Dataset(
                X_train, label=train_target, weight=base_train_weight,
                categorical_feature=cats)
            validation = lgb.Dataset(
                X_val, label=validation_target, reference=training,
                categorical_feature=cats)
            params['metric'] = 'None'
            custom_metric = (actual_price_mae if actual_price_metric == 'mae_php'
                             else actual_price_rmse)
        elif params.get('metric') == 'within5_miss_pct':
            training = lgb.Dataset(
                X_train, label=train_target, weight=base_train_weight,
                categorical_feature=cats)
            validation = lgb.Dataset(
                X_val, label=validation_target, reference=training,
                categorical_feature=cats)
            params['metric'] = 'None'
            custom_metric = actual_price_within5_miss
        else:
            training = lgb.Dataset(
                X_train, label=train_target, weight=base_train_weight,
                categorical_feature=cats)
            validation = lgb.Dataset(
                X_val, label=validation_target, reference=training,
                categorical_feature=cats)

        self._model = lgb.train(
            params, training, num_boost_round=rounds,
            valid_sets=[training, validation], valid_names=['train', 'validation'],
            feval=custom_metric,
            callbacks=[lgb.early_stopping(patience, first_metric_only=True),
                       lgb.log_evaluation(100)])
        recorded_params = dict(params)
        if objective in {'within5_squared_hinge', 'within5_softplus'}:
            recorded_params['objective'] = objective
            recorded_params['metric'] = 'within5_miss_pct'
        elif objective == 'mape_weighted_l1':
            recorded_params['objective'] = objective
            recorded_params['metric'] = 'mape_pct'
        elif objective == 'mape_pseudo_huber':
            recorded_params['objective'] = objective
            recorded_params['metric'] = 'mape_pct'
        elif mape_metric_used:
            recorded_params['metric'] = 'mape_pct'
        elif actual_price_metric_used:
            recorded_params['metric'] = actual_price_metric
        elif within5_metric_used:
            recorded_params['metric'] = 'within5_miss_pct'
        self.training_configuration = {
            "parameters": recorded_params,
            "requested_boost_rounds": int(rounds),
            "early_stopping_rounds": int(patience),
            "best_iteration": int(self._model.best_iteration),
        }
        if sample_weight_description is not None:
            self.training_configuration["sample_weighting"] = sample_weight_description
        if objective == 'within5_squared_hinge':
            self.training_configuration.update({
                'objective': 'squared hinge on absolute price errors outside PHP 5',
                'selection_metric': 'validation absolute error miss rate above PHP 5',
            })
        elif objective == 'within5_softplus':
            self.training_configuration.update({
                'objective': 'softplus of absolute PHP error margin beyond PHP 5',
                'softplus_temperature_php': 2.0,
                'selection_metric': 'validation absolute error miss rate above PHP 5',
            })
        elif objective == 'mape_weighted_l1':
            self.training_configuration.update({
                'objective': 'inverse-actual-weighted L1 on relative targets',
                'selection_metric': 'validation actual-price MAPE percent',
            })
        elif mape_delta is not None:
            self.training_configuration.update({
                'objective': 'inverse-actual-weighted pseudo-Huber on relative targets',
                'mape_smoothing_delta': mape_delta,
                'selection_metric': 'validation MAPE percent',
            })
        elif mape_metric_used:
            self.training_configuration['selection_metric'] = 'validation MAPE percent'
        elif actual_price_metric_used:
            description = 'MAE' if actual_price_metric == 'mae_php' else 'RMSE'
            self.training_configuration['selection_metric'] = (
                f'validation actual-price {description} in PHP')
        elif within5_metric_used:
            self.training_configuration['selection_metric'] = (
                'validation actual-price absolute error miss rate above PHP 5 percent')
        self.save()
        return compute_all_metrics(
            y_val, self.predict(X_val, base_prediction=base_val_prediction))

    def refit_fixed_rounds(self, X, y, *, num_boost_round,
                           base_prediction=None, sample_weight=None):
        """Refit the selected configuration on all eligible rows at fixed rounds."""
        if list(X.columns) != self._feature_names or not len(X):
            raise ValueError("Final LightGBM refit requires aligned nonempty features")
        if int(num_boost_round) <= 0:
            raise ValueError("Final LightGBM refit rounds must be positive")
        target = self._training_target(X, y, base_prediction=base_prediction)
        params = dict(get_settings().lgbm_params)
        params.pop('n_estimators', None)
        params.pop('early_stopping_rounds', None)
        params['seed'] = get_settings().random_seed
        objective_name = params.get('objective')
        weights = None
        if sample_weight is not None:
            weights = np.asarray(sample_weight, dtype=float)
            if (weights.shape != (len(X),) or not np.isfinite(weights).all()
                    or (weights <= 0).any()):
                raise ValueError("Final refit weights must be positive and row-aligned")

        def combine_weights(objective_weights=None):
            if objective_weights is None:
                return weights
            objective_weights = np.asarray(objective_weights, dtype=float)
            return (objective_weights if weights is None
                    else objective_weights * weights)

        if objective_name in {'within5_squared_hinge', 'within5_softplus'}:
            if self.target_mode not in {'relative', 'residual_relative'}:
                raise ValueError('Within-5 loss requires relative LightGBM targets')
            anchor = X['price_lag_1d'].to_numpy(dtype=float)
            if not np.isfinite(anchor).all() or (anchor <= 0).any():
                raise ValueError('Within-5 refit requires positive finite anchors')

            def objective_function(prediction, dataset):
                if objective_name == 'within5_squared_hinge':
                    return _within5_squared_hinge_grad_hess(
                        prediction, dataset.get_label(), anchor,
                        dataset.get_weight())
                return _within5_softplus_grad_hess(
                    prediction, dataset.get_label(), anchor,
                    dataset.get_weight(), temperature_php=2.0)

            params['objective'] = objective_function
            params['metric'] = 'None'
        elif objective_name == 'mape_weighted_l1':
            if self.target_mode not in {'relative', 'residual_relative'}:
                raise ValueError('Inverse-actual weighted L1 requires relative targets')
            anchor = X['price_lag_1d'].to_numpy(dtype=float)
            if (not np.isfinite(anchor).all() or (anchor <= 0).any()
                    or not np.isfinite(target).all()):
                raise ValueError('MAPE refit requires finite positive anchors and targets')
            actual = (anchor * (1.0 + target) if self.target_mode == 'relative'
                      else np.asarray(base_prediction, dtype=float) + anchor * target)
            weights = combine_weights(1.0 / np.maximum(actual, 1e-9))
            params['objective'] = 'regression_l1'
            params['metric'] = 'None'
        elif objective_name == 'mape_pseudo_huber':
            if self.target_mode not in {'relative', 'residual_relative'}:
                raise ValueError('MAPE pseudo-Huber requires relative targets')
            anchor = X['price_lag_1d'].to_numpy(dtype=float)
            if not np.isfinite(anchor).all() or (anchor <= 0).any():
                raise ValueError('MAPE refit requires finite positive anchors')
            if self.target_mode == 'relative':
                actual = anchor * (1.0 + target)
            else:
                if base_prediction is None:
                    raise ValueError('Residual MAPE refit requires base predictions')
                actual = np.asarray(base_prediction, dtype=float) + anchor * target
            objective_weights = 1.0 / np.maximum(actual, 1e-9)
            refit_weights = combine_weights(objective_weights)
            delta = float(get_settings().lgbm_mape_delta)
            if not np.isfinite(delta) or delta <= 0:
                raise ValueError('MAPE pseudo-Huber delta must be positive and finite')

            def objective_function(prediction, dataset):
                residual = prediction - dataset.get_label()
                denominator = np.sqrt(residual * residual + delta * delta)
                dataset_weights = dataset.get_weight()
                if dataset_weights is None:
                    dataset_weights = refit_weights
                gradient = dataset_weights * residual / denominator
                hessian = (dataset_weights * delta * delta
                           / denominator ** 3)
                return gradient, np.maximum(hessian, 1e-12)

            params['objective'] = objective_function
            params['metric'] = 'None'
        elif not isinstance(objective_name, str):
            raise ValueError(
                "Fixed-round refit requires a supported LightGBM objective")
        elif (isinstance(params.get('metric'), str)
              and params.get('metric') in {
                  'mape_pct', 'mae_php', 'rmse_php', 'within5_miss_pct'}):
            # These are Python evaluation functions in the selection fit. The
            # final fixed-round fit has no validation set to evaluate.
            params['metric'] = 'None'
        cats = [column for column in self._feature_names if column.endswith('_encoded')]
        dataset = lgb.Dataset(
            X, label=target, weight=weights, categorical_feature=cats)
        self._model = lgb.train(
            params, dataset, num_boost_round=int(num_boost_round))
        if self.training_configuration is None:
            self.training_configuration = {}
        self.training_configuration['final_refit'] = {
            'training_rows': int(len(X)),
            'boost_rounds': int(num_boost_round),
            'uses_all_supplied_rows': True,
            'target_mode': self.target_mode,
            'objective': objective_name,
        }
        self.training_configuration['best_iteration'] = int(num_boost_round)
        self.save()
        return self

    def predict(self, X, base_prediction=None):
        if self._model is None:
            self.load()
        values = X[self._feature_names]
        if not np.isfinite(values.to_numpy(dtype=float)).all():
            raise ValueError('Nonfinite LightGBM features')
        predicted = self._model.predict(values, num_threads=4)
        if self.target_mode in {"residual_absolute", "residual_relative"}:
            if base_prediction is None:
                raise ValueError("Residual LightGBM prediction requires an LSTM base path")
            base = np.asarray(base_prediction, dtype=float).reshape(-1)
            if base.shape != (len(values),) or not np.isfinite(base).all():
                raise ValueError("Residual LightGBM base path is not aligned")
            if self.target_mode == "residual_relative":
                predicted = base + values["price_lag_1d"].to_numpy(dtype=float) * predicted
            else:
                predicted = base + predicted
        elif self.target_mode == "relative":
            predicted = values["price_lag_1d"].to_numpy(dtype=float) * (1.0 + predicted)
        elif self.target_mode == "log_relative":
            predicted = values["price_lag_1d"].to_numpy(dtype=float) * np.exp(
                np.clip(predicted, -100.0, 100.0))
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
        if self.residual_feature_schema is not None:
            meta['residual_feature_schema'] = self.residual_feature_schema
        if self.training_configuration is not None:
            meta['training_configuration'] = self.training_configuration
        (self.path/'lightgbm_meta.json').write_text(
            json.dumps(meta, indent=2), encoding='utf-8')

    def load(self):
        meta = json.loads((self.path/'lightgbm_meta.json').read_text(encoding='utf-8'))
        supported = {2: LEGACY_FEATURE_COLUMNS, 3: FEATURE_COLUMNS_V3,
                     4: FEATURE_COLUMNS_V4, 5: FEATURE_COLUMNS_V5,
                     6: FEATURE_COLUMNS_V6, 7: FEATURE_COLUMNS_V7,
                     8: FEATURE_COLUMNS_V8, 9: FEATURE_COLUMNS_V9,
                     10: FEATURE_COLUMNS_V10, 11: FEATURE_COLUMNS_V11,
                     12: FEATURE_COLUMNS_V12, 13: FEATURE_COLUMNS_V13}
        version = meta.get('feature_version')
        if version not in supported:
            raise ValueError('Incompatible LightGBM bundle; retrain with the current schema')
        target_mode = meta.get('target_mode', 'absolute')
        base_features = list(supported[version])
        stored_features = meta.get('features')
        residual_schema = meta.get('residual_feature_schema')
        is_residual = target_mode in {'residual_absolute', 'residual_relative'}
        legacy_residual = is_residual and stored_features == base_features
        current_residual = (
            is_residual
            and residual_schema == RESIDUAL_FEATURE_SCHEMA
            and stored_features == base_features + RESIDUAL_FEATURE_COLUMNS)
        if not (stored_features == base_features or legacy_residual or current_residual):
            raise ValueError('Incompatible LightGBM bundle; retrain with the current schema')
        self._base_feature_names = base_features
        self._feature_names = list(stored_features)
        self._feature_version = version
        self.target_mode = target_mode
        self.residual_feature_schema = (
            RESIDUAL_FEATURE_SCHEMA if current_residual else None)
        self.training_configuration = meta.get('training_configuration')
        if self.target_mode not in {
                'absolute', 'relative', 'log_relative',
                'residual_absolute', 'residual_relative'}:
            raise ValueError('Incompatible LightGBM target mode')
        self._model = lgb.Booster(model_str=(self.path/'lightgbm_model.txt').read_text(encoding='utf-8'))
        if self._model.feature_name() != self._feature_names:
            raise ValueError('Stored LightGBM feature order mismatch')
