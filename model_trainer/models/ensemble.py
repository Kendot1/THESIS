"""
Two-Stage Residual Hybrid Ensemble.

Architecture:
  Stage 1: LSTM produces base price forecast (temporal patterns)
  Stage 2: LightGBM corrects residual errors (structured tabular patterns)
  Final:   predicted_price = lstm_base + lgbm_residual_correction

This replaces the old Ridge stacking approach. Instead of treating both
models as equal peers and blending them, we use LSTM as the primary forecaster
and LightGBM as a learned error-correction layer.
"""

import numpy as np
import joblib
from typing import Dict, Tuple, Optional

from config.settings import get_settings
from utils.logger import get_logger
from utils.metrics import compute_all_metrics

log = get_logger(__name__)


class EnsembleModel:
    """
    Two-stage residual hybrid: LSTM base + LightGBM residual correction.

    Training flow:
      1. LSTM trained first on price sequences → produces base predictions
      2. Residuals computed: residual = actual - lstm_prediction
      3. LightGBM trained to predict these residuals from tabular features
      4. Final prediction = lstm_pred + lgbm_residual_pred

    This captures:
      • Temporal patterns via LSTM (sequences, trends, seasonality)
      • Structured residual patterns via LightGBM (feature interactions, non-linearities)
    """

    def __init__(self):
        cfg = get_settings()
        self._meta_path = cfg.artifacts_dir / "ensemble_meta_model.pkl"
        self._residual_stats: Optional[Dict] = None
        self._stats_path = cfg.artifacts_dir / "ensemble_residual_stats.pkl"

    # ──────────────────────────────────────────────
    # Training
    # ──────────────────────────────────────────────
    def train_residual_ensemble(
        self,
        lstm_preds: np.ndarray,
        lgbm_residual_preds: np.ndarray,
        y_true: np.ndarray,
    ) -> Dict[str, float]:
        """
        Evaluate the residual hybrid ensemble on validation data.

        Args:
            lstm_preds:          LSTM base predictions (absolute prices)
            lgbm_residual_preds: LightGBM predicted residuals
            y_true:              Actual prices

        Returns:
            Metrics dict comparing LSTM-only vs hybrid.
        """
        # Final hybrid prediction
        hybrid_preds = lstm_preds + lgbm_residual_preds

        # Compute metrics for both approaches
        lstm_only_metrics = compute_all_metrics(y_true, lstm_preds)
        hybrid_metrics = compute_all_metrics(y_true, hybrid_preds)

        # Compute actual residuals for stats
        actual_residuals = y_true - lstm_preds
        self._residual_stats = {
            "mean": float(np.mean(actual_residuals)),
            "std": float(np.std(actual_residuals)),
            "median": float(np.median(actual_residuals)),
            "mae": float(np.mean(np.abs(actual_residuals))),
            "lstm_rmse": lstm_only_metrics["rmse"],
            "hybrid_rmse": hybrid_metrics["rmse"],
            "improvement_pct": float(
                (lstm_only_metrics["rmse"] - hybrid_metrics["rmse"])
                / lstm_only_metrics["rmse"] * 100
            ) if lstm_only_metrics["rmse"] > 0 else 0.0,
        }

        log.info(
            f"Residual hybrid trained --\n"
            f"  LSTM-only:   RMSE={lstm_only_metrics['rmse']:.4f}  "
            f"MAE={lstm_only_metrics['mae']:.4f}  MAPE={lstm_only_metrics['mape']:.2f}%\n"
            f"  Hybrid:      RMSE={hybrid_metrics['rmse']:.4f}  "
            f"MAE={hybrid_metrics['mae']:.4f}  MAPE={hybrid_metrics['mape']:.2f}%\n"
            f"  Improvement: {self._residual_stats['improvement_pct']:.1f}%"
        )

        self._save_stats()
        return hybrid_metrics

    # ──────────────────────────────────────────────
    # Prediction
    # ──────────────────────────────────────────────
    def predict(
        self,
        lstm_base: np.ndarray,
        lgbm_residual: np.ndarray,
    ) -> np.ndarray:
        """
        Combine LSTM base prediction with LightGBM residual correction.
        final = lstm_base + lgbm_residual
        """
        return lstm_base + lgbm_residual

    def predict_with_intervals(
        self,
        lstm_point: np.ndarray,
        lstm_lower: np.ndarray,
        lstm_upper: np.ndarray,
        lgbm_residual: np.ndarray,
        lgbm_residual_lower: np.ndarray,
        lgbm_residual_upper: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Combine point predictions and confidence intervals.
        Residual correction is additive.
        """
        point = lstm_point + lgbm_residual
        lower = lstm_lower + lgbm_residual_lower
        upper = lstm_upper + lgbm_residual_upper
        return point, lower, upper

    # ──────────────────────────────────────────────
    # Explainability helpers
    # ──────────────────────────────────────────────
    def get_model_contributions(self) -> Dict[str, float]:
        """Return the relative contribution of each model stage."""
        if self._residual_stats is not None:
            lstm_rmse = self._residual_stats.get("lstm_rmse", 1.0)
            hybrid_rmse = self._residual_stats.get("hybrid_rmse", 1.0)
            correction = max(lstm_rmse - hybrid_rmse, 0)
            total = lstm_rmse
            return {
                "lstm_contribution": float((total - correction) / total) if total > 0 else 0.6,
                "lgbm_residual_contribution": float(correction / total) if total > 0 else 0.4,
            }
        return {
            "lstm_contribution": 0.6,
            "lgbm_residual_contribution": 0.4,
        }

    def get_residual_stats(self) -> Optional[Dict]:
        """Return statistics about the residual distribution."""
        if self._residual_stats is None:
            self._load_stats()
        return self._residual_stats

    # ──────────────────────────────────────────────
    # Persistence
    # ──────────────────────────────────────────────
    def save(self):
        """Public save method."""
        self._save_stats()

    def load(self):
        """Public load method."""
        self._load_stats()

    def _save_stats(self):
        if self._residual_stats is not None:
            joblib.dump(self._residual_stats, str(self._stats_path))
            log.info(f"Saved residual stats -> {self._stats_path}")

    def _load_stats(self):
        if self._stats_path.exists():
            self._residual_stats = joblib.load(str(self._stats_path))
            log.info(f"Loaded residual stats <- {self._stats_path}")
