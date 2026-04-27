"""
Drift detection for data distribution and model performance.
Uses Population Stability Index (PSI) and performance monitoring.
"""

import numpy as np
import pandas as pd
import json
from pathlib import Path
from typing import Optional

from config.settings import get_settings
from utils.logger import get_logger

log = get_logger(__name__)


class DriftDetector:
    """
    Detect data drift and model performance degradation.

    Two mechanisms:
      1. PSI (Population Stability Index) on price distributions
      2. Performance drop tracking (MAPE increase over baseline)
    """

    def __init__(self):
        cfg = get_settings()
        self._psi_threshold = cfg.psi_threshold
        self._perf_threshold = cfg.performance_drop_threshold
        self._ref_path = cfg.artifacts_dir / "reference_distribution.json"

    # ──────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────
    def check_drift(self, current_df: pd.DataFrame) -> bool:
        """
        Compare current data distribution against the reference.
        Returns True if significant drift is detected (full retrain recommended).
        """
        reference = self._load_reference()
        if reference is None:
            log.info("No reference distribution found -- skipping drift check.")
            return False

        # Compute PSI for overall price distribution
        current_prices = current_df["price_index"].dropna().values
        ref_prices = np.array(reference.get("price_distribution", []))

        if len(ref_prices) == 0 or len(current_prices) == 0:
            return False

        psi = self._compute_psi(ref_prices, current_prices)
        log.info(f"PSI = {psi:.4f} (threshold = {self._psi_threshold})")

        if psi > self._psi_threshold:
            log.warning(f"Data drift detected! PSI={psi:.4f} exceeds threshold.")
            return True

        # Check per-category PSI
        for category in current_df["product_category"].unique():
            cat_prices = current_df.loc[
                current_df["product_category"] == category, "price_index"
            ].values
            ref_cat_prices = np.array(
                reference.get("category_distributions", {}).get(category, [])
            )

            if len(ref_cat_prices) == 0 or len(cat_prices) == 0:
                continue

            cat_psi = self._compute_psi(ref_cat_prices, cat_prices)
            if cat_psi > self._psi_threshold * 1.5:
                log.warning(
                    f"Category drift in '{category}': PSI={cat_psi:.4f}"
                )
                return True

        log.info("No significant drift detected.")
        return False

    def check_performance_drift(
        self, current_mape: float, baseline_mape: float
    ) -> bool:
        """
        Check if model performance has degraded beyond threshold.
        Returns True if retrain is recommended.
        """
        if baseline_mape == 0:
            return False

        degradation = (current_mape - baseline_mape) / baseline_mape

        if degradation > self._perf_threshold:
            log.warning(
                f"Performance drift: MAPE increased by {degradation:.1%} "
                f"({baseline_mape:.2f}% → {current_mape:.2f}%)"
            )
            return True

        return False

    # ──────────────────────────────────────────────
    # Reference management
    # ──────────────────────────────────────────────
    def save_reference(self, df: pd.DataFrame):
        """Save current data distribution as the reference baseline."""
        reference = {
            "price_distribution": df["price_index"].dropna().tolist(),
            "n_samples": len(df),
            "category_distributions": {},
        }

        for category in df["product_category"].unique():
            cat_prices = df.loc[
                df["product_category"] == category, "price_index"
            ].dropna().tolist()
            reference["category_distributions"][category] = cat_prices

        with open(self._ref_path, "w") as f:
            json.dump(reference, f)
        log.info(f"Saved reference distribution ({len(df)} samples).")

    def _load_reference(self) -> Optional[dict]:
        if self._ref_path.exists():
            with open(self._ref_path) as f:
                return json.load(f)
        return None

    # ──────────────────────────────────────────────
    # PSI computation
    # ──────────────────────────────────────────────
    @staticmethod
    def _compute_psi(
        reference: np.ndarray,
        current: np.ndarray,
        n_bins: int = 10,
    ) -> float:
        """
        Compute the Population Stability Index.

        PSI < 0.1  → No significant change
        PSI 0.1–0.2 → Moderate change
        PSI > 0.2  → Significant change (retrain recommended)
        """
        # Create bins from reference distribution
        breakpoints = np.percentile(reference, np.linspace(0, 100, n_bins + 1))
        breakpoints = np.unique(breakpoints)

        if len(breakpoints) < 2:
            return 0.0

        # Compute bin proportions
        ref_counts = np.histogram(reference, bins=breakpoints)[0].astype(float)
        cur_counts = np.histogram(current, bins=breakpoints)[0].astype(float)

        # Add small epsilon to avoid log(0) and division by zero
        eps = 1e-6
        ref_pct = (ref_counts + eps) / (ref_counts.sum() + eps * len(ref_counts))
        cur_pct = (cur_counts + eps) / (cur_counts.sum() + eps * len(cur_counts))

        psi = np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct))
        return float(psi)
