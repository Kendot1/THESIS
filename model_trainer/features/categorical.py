"""
Categorical feature encoding for product_category, product_variant, origin.
Uses label encoding for LightGBM (which handles categoricals natively)
and stores the mappings for inference consistency.
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path
from typing import Dict, Optional

from config.settings import get_settings
from utils.logger import get_logger

log = get_logger(__name__)


class CategoricalEncoder:
    """
    Label-encode categorical columns.
    Saves / loads mapping files so inference uses the same encoding.
    """

    CATEGORICAL_COLUMNS = ["product_category", "product_name", "product_variant", "origin"]

    def __init__(self):
        cfg = get_settings()
        self._mappings: Dict[str, Dict[str, int]] = {}
        self._save_path = cfg.artifacts_dir / "categorical_mappings.json"

    # ──────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────
    def fit_transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Fit on training data and transform."""
        df = df.copy()
        for col in self.CATEGORICAL_COLUMNS:
            if col not in df.columns:
                continue
            df[col] = df[col].fillna("Unknown").astype(str)
            unique_vals = sorted(df[col].unique())
            mapping = {val: idx for idx, val in enumerate(unique_vals)}
            self._mappings[col] = mapping
            df[f"{col}_encoded"] = df[col].map(mapping).astype(int)

        self._save_mappings()
        log.info(
            f"Encoded {len(self._mappings)} categorical columns "
            f"({sum(len(m) for m in self._mappings.values())} unique values)."
        )
        return df

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Transform using previously fitted mappings (for inference)."""
        if not self._mappings:
            self._load_mappings()

        df = df.copy()
        for col, mapping in self._mappings.items():
            if col not in df.columns:
                continue
            df[col] = df[col].astype(str)
            # Unseen categories get a default value (max + 1)
            default = max(mapping.values()) + 1 if mapping else 0
            df[f"{col}_encoded"] = df[col].map(mapping).fillna(default).astype(int)

        return df

    def get_product_name_for_id(self, encoded_id: int) -> Optional[str]:
        """Reverse lookup: encoded ID → product name."""
        mapping = self._mappings.get("product_name", {})
        reverse = {v: k for k, v in mapping.items()}
        return reverse.get(encoded_id)

    def get_category_for_id(self, encoded_id: int) -> Optional[str]:
        """Reverse lookup: encoded ID → category."""
        mapping = self._mappings.get("product_category", {})
        reverse = {v: k for k, v in mapping.items()}
        return reverse.get(encoded_id)

    # ──────────────────────────────────────────────
    # Persistence
    # ──────────────────────────────────────────────
    def _save_mappings(self):
        with open(self._save_path, "w", encoding="utf-8") as f:
            json.dump(self._mappings, f, indent=2)
        log.info(f"Saved categorical mappings → {self._save_path}")

    def _load_mappings(self):
        if self._save_path.exists():
            with open(self._save_path, "r", encoding="utf-8") as f:
                self._mappings = json.load(f)
            log.info(f"Loaded categorical mappings from {self._save_path}")
        else:
            log.warning("No saved mappings found -- call fit_transform() first.")
