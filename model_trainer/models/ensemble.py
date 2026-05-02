"""
Two-Stage Blended Hybrid Ensemble with Adaptive Weights.

Architecture:
  Stage 1: LSTM produces base price forecast (temporal patterns)
  Stage 2: LightGBM produces base price forecast (tabular patterns)
  Final:   predicted_price = (lstm_weight * lstm_base) + (lgbm_weight * lgbm_base)

The blending factor is dynamically optimized on the validation set using
fine-grained grid search across RMSE, MAE, and Directional Accuracy to find the best
combined performance.
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
    Two-stage blended hybrid: LSTM base + LightGBM base
    with fine-grained adaptive weight optimization.
    """

    def __init__(self):
        cfg = get_settings()
        self._meta_path = cfg.artifacts_dir / "ensemble_meta_model.pkl"
        self._residual_stats: Optional[Dict] = None
        self._stats_path = cfg.artifacts_dir / "ensemble_residual_stats.pkl"

    # ──────────────────────────────────────────────
    # Training
    # ──────────────────────────────────────────────
    def train_blended_ensemble(
        self,
        lstm_preds: np.ndarray,
        lgbm_preds: np.ndarray,
        y_true: np.ndarray,
    ) -> Dict[str, float]:
        """
        Evaluate the blended hybrid ensemble on validation data and find
        the optimal weighting between LSTM and LightGBM.
        """
        lstm_only_metrics = compute_all_metrics(y_true, lstm_preds)
        lgbm_only_metrics = compute_all_metrics(y_true, lgbm_preds)

        # Fine-grained grid search for the best mix between 0.0 and 1.0
        best_lgbm_weight = 0.5
        best_rmse = min(lstm_only_metrics["rmse"], lgbm_only_metrics["rmse"])
        best_dir_acc = max(lstm_only_metrics["directional_accuracy"], lgbm_only_metrics["directional_accuracy"])
        
        for w_int in range(0, 21):
            lgbm_w = w_int / 20.0
            lstm_w = 1.0 - lgbm_w
            hybrid = (lstm_preds * lstm_w) + (lgbm_preds * lgbm_w)
            metrics = compute_all_metrics(y_true, hybrid)
            
            # Optimize for Directional Accuracy first, use RMSE as tie-breaker/safeguard
            if metrics["directional_accuracy"] > best_dir_acc:
                best_dir_acc = metrics["directional_accuracy"]
                best_rmse = metrics["rmse"]
                best_lgbm_weight = lgbm_w
            elif metrics["directional_accuracy"] == best_dir_acc and metrics["rmse"] < best_rmse:
                best_rmse = metrics["rmse"]
                best_lgbm_weight = lgbm_w

        best_lstm_weight = 1.0 - best_lgbm_weight
        hybrid_preds = (lstm_preds * best_lstm_weight) + (lgbm_preds * best_lgbm_weight)
        hybrid_metrics = compute_all_metrics(y_true, hybrid_preds)

        self._residual_stats = {
            "lgbm_weight": best_lgbm_weight,
            "lstm_weight": best_lstm_weight,
            "lstm_rmse": lstm_only_metrics["rmse"],
            "lstm_mae": lstm_only_metrics["mae"],
            "lstm_mape": lstm_only_metrics["mape"],
            "hybrid_rmse": hybrid_metrics["rmse"],
            "hybrid_mae": hybrid_metrics["mae"],
            "hybrid_mape": hybrid_metrics["mape"],
            "hybrid_dir_acc": hybrid_metrics["directional_accuracy"],
            "improvement_pct": float(
                (lstm_only_metrics["rmse"] - hybrid_metrics["rmse"])
                / lstm_only_metrics["rmse"] * 100
            ) if lstm_only_metrics["rmse"] > 0 else 0.0,
        }

        log.info(
            f"Blended hybrid trained (LGBM_Weight={best_lgbm_weight:.2f}, LSTM_Weight={best_lstm_weight:.2f}) --\n"
            f"  LSTM-only:   RMSE={lstm_only_metrics['rmse']:.4f}  "
            f"DirAcc={lstm_only_metrics['directional_accuracy']:.2f}%\n"
            f"  LGBM-only:   RMSE={lgbm_only_metrics['rmse']:.4f}  "
            f"DirAcc={lgbm_only_metrics['directional_accuracy']:.2f}%\n"
            f"  Hybrid:      RMSE={hybrid_metrics['rmse']:.4f}  "
            f"DirAcc={hybrid_metrics['directional_accuracy']:.2f}%\n"
            f"  Improvement vs LSTM: {self._residual_stats['improvement_pct']:.1f}%"
        )

        self._save_stats()
        return hybrid_metrics

    # ──────────────────────────────────────────────
    # Prediction
    # ──────────────────────────────────────────────
    def predict(
        self,
        lstm_base: np.ndarray,
        lgbm_base: np.ndarray,
    ) -> np.ndarray:
        if self._residual_stats is None:
            self.load()
        lgbm_w = self._residual_stats.get("lgbm_weight", 0.5) if self._residual_stats else 0.5
        lstm_w = self._residual_stats.get("lstm_weight", 0.5) if self._residual_stats else 0.5
        return (lstm_base * lstm_w) + (lgbm_base * lgbm_w)

    def predict_with_intervals(
        self,
        lstm_point: np.ndarray,
        lstm_lower: np.ndarray,
        lstm_upper: np.ndarray,
        lgbm_residual: np.ndarray,
        lgbm_residual_lower: np.ndarray,
        lgbm_residual_upper: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        if self._residual_stats is None:
            self.load()
        shrinkage = self._residual_stats.get("shrinkage", 0.5) if self._residual_stats else 0.5
        
        point = lstm_point + (shrinkage * lgbm_residual)
        lower = lstm_lower + (shrinkage * lgbm_residual_lower)
        upper = lstm_upper + (shrinkage * lgbm_residual_upper)
        return point, lower, upper

    # ──────────────────────────────────────────────
    # Explainability helpers
    # ──────────────────────────────────────────────
    def get_model_contributions(self) -> Dict[str, float]:
        if self._residual_stats is not None:
            lgbm_w = self._residual_stats.get("lgbm_weight", 0.5)
            lstm_w = self._residual_stats.get("lstm_weight", 0.5)
            return {
                "lstm_contribution": lstm_w,
                "lgbm_residual_contribution": lgbm_w, # Kept key name to avoid breaking frontend
            }
        return {
            "lstm_contribution": 0.5,
            "lgbm_residual_contribution": 0.5,
        }

    def get_residual_stats(self) -> Optional[Dict]:
        if self._residual_stats is None:
            self.load()
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
