"""
Two-Stage Residual Hybrid Ensemble.

Architecture:
  Stage 1: LSTM produces base price forecast (temporal patterns)
  Stage 2: LightGBM corrects residual errors (structured tabular patterns)
  Final:   predicted_price = lstm_base + (shrinkage * lgbm_residual_correction)

The shrinkage factor is dynamically optimized on the validation set to strictly
ensure the ensemble NEVER performs worse than the LSTM base model.
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
    Two-stage residual hybrid: LSTM base + LightGBM residual correction with Shrinkage.
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
        Evaluate the residual hybrid ensemble on validation data and find optimal shrinkage.
        """
        lstm_only_metrics = compute_all_metrics(y_true, lstm_preds)
        
        # Grid search for optimal shrinkage to minimize MAPE
        best_shrinkage = 0.0
        best_mape = lstm_only_metrics["mape"]
        
        for shrinkage in [0.1, 0.25, 0.5, 0.75, 1.0]:
            hybrid = lstm_preds + (shrinkage * lgbm_residual_preds)
            mape = compute_all_metrics(y_true, hybrid)["mape"]
            if mape < best_mape:
                best_mape = mape
                best_shrinkage = shrinkage

        hybrid_preds = lstm_preds + (best_shrinkage * lgbm_residual_preds)
        hybrid_metrics = compute_all_metrics(y_true, hybrid_preds)

        actual_residuals = y_true - lstm_preds
        self._residual_stats = {
            "shrinkage": best_shrinkage,
            "mean": float(np.mean(actual_residuals)),
            "std": float(np.std(actual_residuals)),
            "lstm_rmse": lstm_only_metrics["rmse"],
            "hybrid_rmse": hybrid_metrics["rmse"],
            "improvement_pct": float(
                (lstm_only_metrics["rmse"] - hybrid_metrics["rmse"])
                / lstm_only_metrics["rmse"] * 100
            ) if lstm_only_metrics["rmse"] > 0 else 0.0,
        }

        log.info(
            f"Residual hybrid trained (Shrinkage={best_shrinkage}) --\n"
            f"  LSTM-only:   RMSE={lstm_only_metrics['rmse']:.4f}  MAPE={lstm_only_metrics['mape']:.2f}%\n"
            f"  Hybrid:      RMSE={hybrid_metrics['rmse']:.4f}  MAPE={hybrid_metrics['mape']:.2f}%\n"
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
        if self._residual_stats is None:
            self.load()
        shrinkage = self._residual_stats.get("shrinkage", 0.5) if self._residual_stats else 0.5
        return lstm_base + (shrinkage * lgbm_residual)

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
            shrinkage = self._residual_stats.get("shrinkage", 0.5)
            # If shrinkage is 0, LSTM does 100% of the work.
            return {
                "lstm_contribution": 1.0 - (shrinkage * 0.5),
                "lgbm_residual_contribution": (shrinkage * 0.5),
            }
        return {
            "lstm_contribution": 0.8,
            "lgbm_residual_contribution": 0.2,
        }

    def get_residual_stats(self) -> Optional[Dict]:
        if self._residual_stats is None:
            self.load()
        return self._residual_stats

    # ──────────────────────────────────────────────
    # Persistence
    # ──────────────────────────────────────────────
    def save(self):
        self._save_stats()

    def load(self):
        self._load_stats()

    def _save_stats(self):
        if self._residual_stats is not None:
            joblib.dump(self._residual_stats, str(self._stats_path))
            log.info(f"Saved residual stats -> {self._stats_path}")

    def _load_stats(self):
        if self._stats_path.exists():
            self._residual_stats = joblib.load(str(self._stats_path))
            log.info(f"Loaded residual stats <- {self._stats_path}")

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
