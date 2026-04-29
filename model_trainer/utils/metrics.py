"""
Evaluation metrics for regression forecasting.
"""

import numpy as np
from typing import Dict


def compute_rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Root Mean Squared Error."""
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def compute_mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Mean Absolute Error."""
    return float(np.mean(np.abs(y_true - y_pred)))


def compute_mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """
    Mean Absolute Percentage Error.
    Filters out zero actuals to avoid division by zero.
    """
    mask = y_true != 0
    if not np.any(mask):
        return 0.0
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)


def compute_r2(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """
    Coefficient of Determination (R²).
    R² = 1 means perfect prediction; R² = 0 means no better than predicting the mean.
    Negative R² means the model is worse than a constant mean prediction.
    """
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    if ss_tot == 0:
        return 1.0 if ss_res == 0 else 0.0
    return float(1.0 - (ss_res / ss_tot))


def compute_directional_accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """
    Directional Accuracy — percentage of times the predicted direction
    (up/down from previous value) matches the actual direction.
    This measures whether the model captures trends, not just magnitude.
    """
    if len(y_true) < 2:
        return 0.0
    actual_direction = np.sign(np.diff(y_true))
    pred_direction = np.sign(np.diff(y_pred))
    # Only count non-zero directions (ignore flat periods)
    mask = actual_direction != 0
    if not np.any(mask):
        return 100.0
    return float(np.mean(actual_direction[mask] == pred_direction[mask]) * 100)


def compute_all_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
) -> Dict[str, float]:
    """Compute all standard metrics at once."""
    y_true = np.asarray(y_true, dtype=np.float64)
    y_pred = np.asarray(y_pred, dtype=np.float64)

    return {
        "rmse": compute_rmse(y_true, y_pred),
        "mae": compute_mae(y_true, y_pred),
        "mape": compute_mape(y_true, y_pred),
        "r2": compute_r2(y_true, y_pred),
        "directional_accuracy": compute_directional_accuracy(y_true, y_pred),
    }
