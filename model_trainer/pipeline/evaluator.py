"""
Model evaluation and per-product / per-category metric tracking.
"""

import pandas as pd
import numpy as np
from typing import Dict, List

from utils.logger import get_logger
from utils.metrics import compute_all_metrics

log = get_logger(__name__)


class ModelEvaluator:
    """
    Evaluate model predictions with breakdowns by:
      • Overall
      • Per product
      • Per category
      • Per forecast horizon
    """

    def evaluate_overall(
        self, y_true: np.ndarray, y_pred: np.ndarray
    ) -> Dict[str, float]:
        """Compute aggregate metrics."""
        return compute_all_metrics(y_true, y_pred)

    def evaluate_per_product(
        self,
        df: pd.DataFrame,
        pred_col: str = "predicted_price",
        actual_col: str = "price_index",
    ) -> pd.DataFrame:
        """
        Compute RMSE / MAE / MAPE per product_name.
        Returns a DataFrame with one row per product.
        """
        results = []

        for product, group in df.groupby("product_name"):
            if len(group) < 2:
                continue
            y_true = group[actual_col].values
            y_pred = group[pred_col].values
            metrics = compute_all_metrics(y_true, y_pred)
            metrics["product_name"] = product
            metrics["n_samples"] = len(group)
            results.append(metrics)

        result_df = pd.DataFrame(results)
        if not result_df.empty:
            result_df = result_df.sort_values("mape", ascending=True)
        return result_df

    def evaluate_per_category(
        self,
        df: pd.DataFrame,
        pred_col: str = "predicted_price",
        actual_col: str = "price_index",
    ) -> pd.DataFrame:
        """Compute metrics per product_category."""
        results = []

        for category, group in df.groupby("product_category"):
            if len(group) < 2:
                continue
            y_true = group[actual_col].values
            y_pred = group[pred_col].values
            metrics = compute_all_metrics(y_true, y_pred)
            metrics["product_category"] = category
            metrics["n_samples"] = len(group)
            results.append(metrics)

        return pd.DataFrame(results).sort_values("mape", ascending=True)

    def evaluate_per_horizon(
        self,
        predictions: Dict[str, Dict],
    ) -> pd.DataFrame:
        """
        Evaluate across forecast horizons (daily / weekly / monthly).
        Expects:
          predictions = {
              "daily": {"y_true": [...], "y_pred": [...]},
              "weekly": {...},
              "monthly": {...},
          }
        """
        results = []
        for horizon, data in predictions.items():
            y_true = np.array(data["y_true"])
            y_pred = np.array(data["y_pred"])
            if len(y_true) == 0:
                continue
            metrics = compute_all_metrics(y_true, y_pred)
            metrics["horizon"] = horizon
            metrics["n_samples"] = len(y_true)
            results.append(metrics)

        return pd.DataFrame(results)

    def generate_report(
        self,
        df: pd.DataFrame,
        pred_col: str = "predicted_price",
        actual_col: str = "price_index",
    ) -> Dict:
        """Generate a comprehensive evaluation report."""
        y_true = df[actual_col].values
        y_pred = df[pred_col].values

        report = {
            "overall": self.evaluate_overall(y_true, y_pred),
            "per_product": self.evaluate_per_product(df, pred_col, actual_col).to_dict("records"),
            "per_category": self.evaluate_per_category(df, pred_col, actual_col).to_dict("records"),
            "n_total_samples": len(df),
            "n_products": df["product_name"].nunique(),
        }

        log.info(
            f"Evaluation report: Overall RMSE={report['overall']['rmse']:.4f}, "
            f"MAE={report['overall']['mae']:.4f}, MAPE={report['overall']['mape']:.2f}%"
        )
        return report
