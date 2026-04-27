"""
LightGBM wrapper with incremental training support.
Handles training, prediction, feature importance, and model persistence.
"""

import lightgbm as lgb
import numpy as np
import pandas as pd
from pathlib import Path
from typing import List, Optional, Dict, Tuple

from config.settings import get_settings
from utils.logger import get_logger
from utils.metrics import compute_all_metrics

log = get_logger(__name__)


class LightGBMModel:
    """
    LightGBM regressor for food price forecasting.

    Key capabilities:
      • Full training from scratch
      • Incremental training (init_model) -- avoids full retrain
      • Feature importance extraction for explainability
      • Quantile regression for confidence intervals
    """

    def __init__(self):
        cfg = get_settings()
        self._params = dict(cfg.lgbm_params)
        self._n_estimators = self._params.pop("n_estimators", 500)
        self._early_stopping = self._params.pop("early_stopping_rounds", 50)
        self._model: Optional[lgb.Booster] = None
        self._feature_names: List[str] = []
        self._model_path = cfg.artifacts_dir / "lightgbm_model.txt"

        # Quantile models for confidence intervals
        self._model_lower: Optional[lgb.Booster] = None
        self._model_upper: Optional[lgb.Booster] = None

        # Residual correction model (Stage 2 of hybrid)
        self._residual_model: Optional[lgb.Booster] = None
        self._residual_model_lower: Optional[lgb.Booster] = None
        self._residual_model_upper: Optional[lgb.Booster] = None
        self._residual_feature_names: List[str] = []
        self._residual_model_path = cfg.artifacts_dir / "lightgbm_residual_model.txt"

    # ──────────────────────────────────────────────
    # Training
    # ──────────────────────────────────────────────
    def train(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: Optional[pd.DataFrame] = None,
        y_val: Optional[pd.Series] = None,
        incremental: bool = False,
    ) -> Dict[str, float]:
        """
        Train the LightGBM model.

        Args:
            incremental: If True, continue training from the existing model
                         (warm start). Requires a previously saved model.
        """
        self._feature_names = list(X_train.columns)

        train_set = lgb.Dataset(X_train, label=y_train)
        valid_sets = [train_set]
        valid_names = ["train"]

        if X_val is not None and y_val is not None:
            val_set = lgb.Dataset(X_val, label=y_val, reference=train_set)
            valid_sets.append(val_set)
            valid_names.append("val")

        # Incremental: load existing model as init_model
        init_model = None
        if incremental and self._model is not None:
            init_model = self._model
            log.info("Incremental training -- warm-starting from existing model.")
        elif incremental and self._model_path.exists():
            init_model = lgb.Booster(model_file=str(self._model_path))
            log.info("Incremental training -- loaded model from disk.")

        callbacks = [
            lgb.log_evaluation(period=50),
        ]
        if X_val is not None:
            callbacks.append(lgb.early_stopping(self._early_stopping))

        self._model = lgb.train(
            self._params,
            train_set,
            num_boost_round=self._n_estimators,
            valid_sets=valid_sets,
            valid_names=valid_names,
            init_model=init_model,
            callbacks=callbacks,
        )

        # Evaluate
        metrics = {}
        if X_val is not None and y_val is not None:
            preds = self._model.predict(X_val)
            metrics = compute_all_metrics(y_val.values, preds)
            log.info(f"LightGBM validation -- RMSE: {metrics['rmse']:.4f}  "
                     f"MAE: {metrics['mae']:.4f}  MAPE: {metrics['mape']:.2f}%")

        # Save
        self.save()

        # Train quantile models for confidence intervals
        self._train_quantile_models(X_train, y_train, X_val, y_val, init_model)

        return metrics

    def train_residual(
        self,
        X_train: pd.DataFrame,
        y_residual_train: np.ndarray,
        X_val: Optional[pd.DataFrame] = None,
        y_residual_val: Optional[np.ndarray] = None,
    ) -> Dict[str, float]:
        """
        Train LightGBM to predict LSTM residuals (actual - lstm_pred).

        This is Stage 2 of the hybrid architecture. The target is NOT the
        price itself, but the error the LSTM makes. LightGBM learns to
        correct systematic LSTM biases using tabular features.

        Args:
            X_train:          Tabular features (lags, rolling, temporal + lstm_prediction)
            y_residual_train: Residuals (actual_price - lstm_predicted_price)
            X_val:            Validation features
            y_residual_val:   Validation residuals
        """
        self._residual_feature_names = list(X_train.columns)

        train_set = lgb.Dataset(X_train, label=y_residual_train)
        valid_sets = [train_set]

        if X_val is not None and y_residual_val is not None:
            val_set = lgb.Dataset(X_val, label=y_residual_val, reference=train_set)
            valid_sets.append(val_set)

        callbacks = [lgb.log_evaluation(period=50)]
        if X_val is not None:
            callbacks.append(lgb.early_stopping(self._early_stopping))

        self._residual_model = lgb.train(
            self._params,
            train_set,
            num_boost_round=self._n_estimators,
            valid_sets=valid_sets,
            callbacks=callbacks,
        )

        # Evaluate
        metrics = {}
        if X_val is not None and y_residual_val is not None:
            preds = self._residual_model.predict(X_val)
            # For residuals, MAPE is not meaningful — use RMSE/MAE
            from sklearn.metrics import mean_squared_error, mean_absolute_error
            rmse = float(np.sqrt(mean_squared_error(y_residual_val, preds)))
            mae = float(mean_absolute_error(y_residual_val, preds))
            metrics = {"rmse": rmse, "mae": mae}
            log.info(
                f"LightGBM residual model -- RMSE: {rmse:.4f}  MAE: {mae:.4f}"
            )

        # Save residual model
        self._residual_model.save_model(str(self._residual_model_path))
        log.info(f"Saved LightGBM residual model -> {self._residual_model_path}")

        # Train quantile models for residual confidence
        self._train_residual_quantile_models(X_train, y_residual_train, X_val, y_residual_val)

        return metrics

    def _train_quantile_models(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: Optional[pd.DataFrame],
        y_val: Optional[pd.Series],
        init_model=None,
    ):
        """Train lower (10th percentile) and upper (90th percentile) quantile models."""
        for quantile, attr_name in [(0.1, "_model_lower"), (0.9, "_model_upper")]:
            params = dict(self._params)
            params["objective"] = "quantile"
            params["alpha"] = quantile
            params.pop("metric", None)
            params["metric"] = "quantile"

            train_set = lgb.Dataset(X_train, label=y_train)
            valid_sets = [train_set]
            if X_val is not None and y_val is not None:
                valid_sets.append(lgb.Dataset(X_val, label=y_val, reference=train_set))

            callbacks = [lgb.log_evaluation(period=0)]
            if X_val is not None:
                callbacks.append(lgb.early_stopping(self._early_stopping))

            model = lgb.train(
                params,
                train_set,
                num_boost_round=self._n_estimators,
                valid_sets=valid_sets,
                callbacks=callbacks,
            )
            setattr(self, attr_name, model)

        log.info("Trained quantile models for confidence intervals.")

    def _train_residual_quantile_models(
        self,
        X_train: pd.DataFrame,
        y_train: np.ndarray,
        X_val: Optional[pd.DataFrame],
        y_val: Optional[np.ndarray],
    ):
        """Train quantile models for residual confidence bounds."""
        for quantile, attr_name in [(0.1, "_residual_model_lower"), (0.9, "_residual_model_upper")]:
            params = dict(self._params)
            params["objective"] = "quantile"
            params["alpha"] = quantile
            params.pop("metric", None)
            params["metric"] = "quantile"

            train_set = lgb.Dataset(X_train, label=y_train)
            valid_sets = [train_set]
            if X_val is not None and y_val is not None:
                valid_sets.append(lgb.Dataset(X_val, label=y_val, reference=train_set))

            callbacks = [lgb.log_evaluation(period=0)]
            if X_val is not None:
                callbacks.append(lgb.early_stopping(self._early_stopping))

            model = lgb.train(
                params,
                train_set,
                num_boost_round=self._n_estimators,
                valid_sets=valid_sets,
                callbacks=callbacks,
            )
            setattr(self, attr_name, model)

        log.info("Trained residual quantile models for confidence intervals.")

    # ──────────────────────────────────────────────
    # Prediction
    # ──────────────────────────────────────────────
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Point predictions."""
        if self._model is None:
            self.load()
        return self._model.predict(X[self._feature_names])

    def predict_residual(self, X: pd.DataFrame) -> np.ndarray:
        """Predict residual correction (for hybrid ensemble)."""
        if self._residual_model is None:
            self.load_residual()
        return self._residual_model.predict(X[self._residual_feature_names])

    def predict_residual_with_intervals(
        self, X: pd.DataFrame
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Returns (residual_point, residual_lower, residual_upper)."""
        point = self.predict_residual(X)
        X_feat = X[self._residual_feature_names]

        if self._residual_model_lower is not None and self._residual_model_upper is not None:
            lower = self._residual_model_lower.predict(X_feat)
            upper = self._residual_model_upper.predict(X_feat)
        else:
            # Fallback: ±residual magnitude
            lower = point - np.abs(point) * 0.5
            upper = point + np.abs(point) * 0.5

        return point, lower, upper

    def predict_with_intervals(
        self, X: pd.DataFrame
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Returns (point_predictions, lower_bound, upper_bound).
        Uses quantile regression for the 80% confidence interval.
        """
        point = self.predict(X)
        X_feat = X[self._feature_names]

        if self._model_lower is not None and self._model_upper is not None:
            lower = self._model_lower.predict(X_feat)
            upper = self._model_upper.predict(X_feat)
        else:
            # Fallback: ±10% of point prediction
            lower = point * 0.9
            upper = point * 1.1

        return point, lower, upper

    # ──────────────────────────────────────────────
    # Explainability
    # ──────────────────────────────────────────────
    def feature_importance(self, importance_type: str = "gain") -> Dict[str, float]:
        """
        Return feature importances as {feature_name: importance_score}.
        importance_type: 'gain' (default) or 'split'.
        """
        if self._model is None:
            self.load()

        raw = self._model.feature_importance(importance_type=importance_type)
        names = self._model.feature_name()
        total = raw.sum() if raw.sum() > 0 else 1
        return {
            name: float(score / total)
            for name, score in sorted(
                zip(names, raw), key=lambda x: x[1], reverse=True
            )
        }

    def residual_feature_importance(self, importance_type: str = "gain") -> Dict[str, float]:
        """Return feature importances for the residual correction model."""
        if self._residual_model is None:
            self.load_residual()

        raw = self._residual_model.feature_importance(importance_type=importance_type)
        names = self._residual_model.feature_name()
        total = raw.sum() if raw.sum() > 0 else 1
        return {
            name: float(score / total)
            for name, score in sorted(
                zip(names, raw), key=lambda x: x[1], reverse=True
            )
        }

    def top_features(self, n: int = 10) -> List[Tuple[str, float]]:
        """Return top-N most important features."""
        imp = self.feature_importance()
        return list(imp.items())[:n]

    # ──────────────────────────────────────────────
    # Persistence
    # ──────────────────────────────────────────────
    def save(self):
        if self._model is not None:
            self._model.save_model(str(self._model_path))
            log.info(f"Saved LightGBM model -> {self._model_path}")

    def load(self):
        if self._model_path.exists():
            self._model = lgb.Booster(model_file=str(self._model_path))
            self._feature_names = self._model.feature_name()
            log.info(f"Loaded LightGBM model <- {self._model_path}")
        else:
            raise FileNotFoundError(f"No model found at {self._model_path}")

    def load_residual(self):
        if self._residual_model_path.exists():
            self._residual_model = lgb.Booster(model_file=str(self._residual_model_path))
            self._residual_feature_names = self._residual_model.feature_name()
            log.info(f"Loaded LightGBM residual model <- {self._residual_model_path}")
        else:
            raise FileNotFoundError(f"No residual model found at {self._residual_model_path}")

