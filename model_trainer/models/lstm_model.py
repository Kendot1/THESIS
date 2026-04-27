"""
LSTM model for time-series price forecasting using PyTorch.

Key improvements over baseline:
  • Multi-feature input: uses lag features, temporal features, and news sentiment
  • PER-PRODUCT StandardScaler normalization (avoids mixing scales across products)
  • Proper time-based sequence construction (no temporal leakage)
  • Temporal Attention mechanism to focus on important timesteps
  • SmoothL1 (Huber) loss for robustness to outliers
  • Gradient clipping, LR scheduling, early stopping
"""

import torch
import torch.nn as nn
import numpy as np
import pandas as pd
import joblib
from pathlib import Path
from typing import Optional, Dict, Tuple, List
from torch.utils.data import Dataset, DataLoader
from sklearn.preprocessing import StandardScaler

from config.settings import get_settings
from utils.logger import get_logger
from utils.metrics import compute_all_metrics

log = get_logger(__name__)

# Minimal feature set for LSTM — sequential features it excels at
LSTM_FEATURE_COLS = [
    # Short lags (sequential context the LSTM naturally uses)
    "price_lag_1d", "price_lag_7d",
    # Rolling averages (smooth trend signals)
    "price_rolling_mean_7d", "price_rolling_mean_30d",
    # Momentum (direction of change - available same day)
    "price_pct_change_1d",
    # Temporal (cyclical — helps with seasonality)
    "month_sin", "month_cos", "dow_sin", "dow_cos",
]

# News features strictly excluded to avoid target leakage with the reasoning layer.

# ──────────────────────────────────────────────
# Dataset
# ──────────────────────────────────────────────
class PriceSequenceDataset(Dataset):
    """
    Converts multi-feature sequences into PyTorch tensors.
    Each sample: (features[t-L:t, :], target_price[t])
    """

    def __init__(self, sequences: np.ndarray, targets: np.ndarray):
        self.sequences = torch.FloatTensor(sequences)
        self.targets = torch.FloatTensor(targets)

    def __len__(self):
        return len(self.targets)

    def __getitem__(self, idx):
        return self.sequences[idx], self.targets[idx]


# ──────────────────────────────────────────────
# Network with optional Attention
# ──────────────────────────────────────────────
class _LSTMNetwork(nn.Module):
    """
    Multi-layer LSTM with temporal attention and a fully-connected head.
    Input:  (batch, seq_len, n_features)
    Output: (batch, 1)
    """

    def __init__(
        self,
        input_size: int = 1,
        hidden_size: int = 128,
        num_layers: int = 2,
        dropout: float = 0.3,
        horizon: int = 30,
    ):
        super().__init__()
        self.hidden_size = hidden_size
        self.horizon = horizon

        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )

        # Temporal attention
        self.attention = nn.Sequential(
            nn.Linear(hidden_size, hidden_size // 2),
            nn.Tanh(),
            nn.Linear(hidden_size // 2, 1),
        )

        self.fc = nn.Sequential(
            nn.LayerNorm(hidden_size),
            nn.Linear(hidden_size, 64),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(64, 32),
            nn.GELU(),
            nn.Linear(32, horizon),  # Predict 30 future steps
        )

    def forward(self, x):
        # x: (batch, seq_len, features)
        lstm_out, _ = self.lstm(x)          # (batch, seq_len, hidden)

        # Temporal attention: learn which timesteps matter most
        attn_weights = self.attention(lstm_out)  # (batch, seq_len, 1)
        attn_weights = torch.softmax(attn_weights, dim=1)
        context = (lstm_out * attn_weights).sum(dim=1)  # (batch, hidden)

        return self.fc(context)


# ──────────────────────────────────────────────
# Model wrapper
# ──────────────────────────────────────────────
class LSTMModel:
    """
    High-level LSTM wrapper with multi-feature support.

    Handles:
      • Building multi-feature sequences from engineered DataFrames
      • Per-product StandardScaler normalization
      • Training with early stopping, LR scheduling, gradient clipping
      • Prediction with denormalization
      • MC Dropout uncertainty estimation
      • Auto-regressive multi-step forecasting
    """

    def __init__(self):
        cfg = get_settings()
        self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._seq_len = cfg.sequence_length
        self._horizon = 30  # Direct multi-step prediction window
        self._hidden = cfg.lstm_hidden_size
        self._layers = cfg.lstm_num_layers
        self._dropout = cfg.lstm_dropout
        self._lr = cfg.lstm_learning_rate
        self._epochs = cfg.lstm_epochs
        self._batch_size = cfg.lstm_batch_size
        self._patience = cfg.lstm_patience

        self._model: Optional[_LSTMNetwork] = None
        self._product_means: Dict[str, float] = {}
        self._feature_cols: List[str] = []
        self._n_features: int = 1

        self._model_path = cfg.artifacts_dir / "lstm_model.pt"
        self._product_means_path = cfg.artifacts_dir / "lstm_product_means.pkl"
        self._meta_path = cfg.artifacts_dir / "lstm_meta.npz"
        self._meta_path = cfg.artifacts_dir / "lstm_meta.npz"

    # ──────────────────────────────────────────────
    # Sequence building (multi-feature)
    # ──────────────────────────────────────────────
    def build_sequences(
        self, df: pd.DataFrame, target_col: str = "price_index"
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Convert the DataFrame into (sequences, targets) arrays.
        Uses static per-product mean scaling to preserve relative relationships.
        """
        # Ensure NO news/sentiment features are included
        available_features = [c for c in LSTM_FEATURE_COLS if c in df.columns]
        self._feature_cols = available_features
        self._n_features = len(self._feature_cols)

        log.info(f"LSTM using {self._n_features} input features: {self._feature_cols}")

        if self._n_features == 0:
            self._feature_cols = [target_col]
            self._n_features = 1

        df = df.sort_values(["product_name", "report_date"]).reset_index(drop=True)

        for col in self._feature_cols:
            if col in df.columns:
                df[col] = df.groupby("product_name")[col].transform(
                    lambda s: s.ffill().bfill().fillna(0)
                )

        all_seqs, all_targets = [], []
        self._product_means = {}

        price_cols_idx = [
            i for i, c in enumerate(self._feature_cols)
            if "price" in c and "pct" not in c
        ]

        for product, group in df.groupby("product_name"):
            if len(group) <= self._seq_len:
                continue

            features = group[self._feature_cols].values.astype(np.float64)
            targets = group[target_col].values.astype(np.float64)

            # Static mean scaling per product
            prod_mean = targets.mean()
            if prod_mean == 0 or np.isnan(prod_mean):
                prod_mean = 1.0
            
            self._product_means[product] = float(prod_mean)

            features_scaled = features.copy()
            # Divide ONLY price columns by the mean
            features_scaled[:, price_cols_idx] = features_scaled[:, price_cols_idx] / prod_mean
            
            targets_scaled = targets / prod_mean

            for i in range(self._seq_len - 1, len(features_scaled) - self._horizon + 1):
                seq = features_scaled[i - self._seq_len + 1 : i + 1]
                
                # To align with LightGBM (which predicts price[i] from features[i]),
                # our anchor must be the previous price (price[i-1]).
                current_price = targets[i - 1]
                if current_price == 0:
                    continue
                future_prices = targets[i : i + self._horizon]
                target_pct = (future_prices - current_price) / current_price
                
                all_seqs.append(seq)
                all_targets.append(target_pct)

        if not all_seqs:
            return np.array([]), np.array([])

        self._save_scalers()

        return np.array(all_seqs, dtype=np.float64), np.array(all_targets, dtype=np.float64)

    def build_sequences_inference(
        self, df: pd.DataFrame, target_col: str = "price_index"
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, List[str], np.ndarray]:
        """
        Build sequences using already-fitted scalers (for validation/test data).
        Returns: (sequences, targets, original_indices, products, anchors)
        """
        df = df.copy()
        for col in self._feature_cols:
            if col not in df.columns:
                df[col] = 0.0
            df[col] = df[col].fillna(0.0)

        all_seqs, all_targets, all_indices, all_products, all_anchors = [], [], [], [], []

        price_cols_idx = [
            i for i, c in enumerate(self._feature_cols)
            if "price" in c and "pct" not in c
        ]

        for product, group in df.groupby("product_name"):
            if len(group) <= self._seq_len or product not in self._product_means:
                continue

            prod_mean = self._product_means[product]

            features = group[self._feature_cols].values.astype(np.float64)
            targets = group[target_col].values.astype(np.float64)
            indices = group.index.values

            features_scaled = features.copy()
            features_scaled[:, price_cols_idx] = features_scaled[:, price_cols_idx] / prod_mean
            targets_scaled = targets / prod_mean

            for i in range(self._seq_len - 1, len(features_scaled) - self._horizon + 1):
                seq = features_scaled[i - self._seq_len + 1 : i + 1]
                
                # To align with LightGBM (which predicts price[i] from features[i]),
                # our anchor must be the previous price (price[i-1]).
                current_price = targets[i - 1]
                if current_price == 0:
                    continue
                future_prices = targets[i : i + self._horizon]
                target_pct = (future_prices - current_price) / current_price
                
                all_seqs.append(seq)
                all_targets.append(target_pct)
                all_indices.append(indices[i])
                all_products.append(product)
                all_anchors.append(current_price)
                

        if not all_seqs:
            return np.array([]), np.array([]), np.array([]), [], np.array([])

        return (
            np.array(all_seqs, dtype=np.float64),
            np.array(all_targets, dtype=np.float64),
            np.array(all_indices, dtype=np.int64),
            all_products,
            np.array(all_anchors, dtype=np.float64)
        )

    # ──────────────────────────────────────────────
    # Training
    # ──────────────────────────────────────────────
    def train(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: Optional[np.ndarray] = None,
        y_val: Optional[np.ndarray] = None,
        val_products: Optional[List[str]] = None,
        val_anchors: Optional[np.ndarray] = None,
        incremental: bool = False,
    ) -> Dict[str, float]:
        """Train the LSTM with early stopping, LR scheduling, and gradient clipping."""
        if len(X_train) == 0:
            log.warning("No training sequences — skipping LSTM training.")
            return {}

        input_size = X_train.shape[2]

        if incremental and self._model_path.exists():
            self._load_network(input_size)
            lr = self._lr * 0.1
            epochs = max(self._epochs // 3, 10)
            log.info(f"LSTM incremental fine-tuning (LR={lr}, epochs={epochs})")
        else:
            self._model = _LSTMNetwork(
                input_size=input_size,
                hidden_size=self._hidden,
                num_layers=self._layers,
                dropout=self._dropout,
                horizon=self._horizon,
            ).to(self._device)
            lr = self._lr
            epochs = self._epochs

        train_ds = PriceSequenceDataset(X_train, y_train)
        train_loader = DataLoader(
            train_ds, batch_size=self._batch_size, shuffle=True, drop_last=True
        )

        val_loader = None
        if X_val is not None and y_val is not None and len(X_val) > 0:
            # Note: y_val contains 30-dim targets
            val_ds = PriceSequenceDataset(X_val, y_val)
            val_loader = DataLoader(val_ds, batch_size=self._batch_size, shuffle=False)

        optimizer = torch.optim.AdamW(
            self._model.parameters(), lr=lr, weight_decay=1e-4
        )
        criterion = nn.SmoothL1Loss(reduction='none')  # per-element loss
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, mode='min', patience=8, factor=0.5, min_lr=1e-6
        )

        # Step-weighted loss: emphasize early steps (3x for step-1, 1x for step-30)
        step_weights = torch.linspace(3.0, 1.0, self._horizon).to(self._device)
        step_weights = step_weights / step_weights.mean()  # normalize to mean=1

        best_val_loss = float("inf")
        patience_counter = 0

        for epoch in range(1, epochs + 1):
            self._model.train()
            train_loss = 0.0
            for seqs, targets in train_loader:
                seqs, targets = seqs.to(self._device), targets.to(self._device)
                optimizer.zero_grad()
                preds = self._model(seqs)
                
                # Step-weighted loss: early steps matter more
                per_element_loss = criterion(preds, targets)  # (batch, 30)
                loss = (per_element_loss * step_weights).mean()

                loss.backward()
                torch.nn.utils.clip_grad_norm_(self._model.parameters(), max_norm=1.0)
                optimizer.step()
                train_loss += loss.item() * len(targets)
            train_loss /= len(train_ds)

            val_loss = None
            if val_loader is not None:
                self._model.eval()
                val_total = 0.0
                with torch.no_grad():
                    for seqs, targets in val_loader:
                        seqs, targets = seqs.to(self._device), targets.to(self._device)
                        preds = self._model(seqs)
                        per_element = criterion(preds, targets)
                        val_total += (per_element * step_weights).mean().item() * len(targets)
                val_loss = val_total / len(val_ds)
                scheduler.step(val_loss)

                if val_loss < best_val_loss:
                    best_val_loss = val_loss
                    patience_counter = 0
                    self.save()
                else:
                    patience_counter += 1

                if epoch % 10 == 0 or epoch == 1:
                    current_lr = optimizer.param_groups[0]['lr']
                    log.info(
                        f"Epoch {epoch:>3}/{epochs}  "
                        f"train={train_loss:.6f}  val={val_loss:.6f}  "
                        f"lr={current_lr:.2e}"
                    )

                if patience_counter >= self._patience:
                    log.info(f"Early stopping at epoch {epoch}")
                    break
            else:
                if epoch % 10 == 0 or epoch == 1:
                    log.info(f"Epoch {epoch:>3}/{epochs}  train={train_loss:.6f}")
                self.save()

        if val_loader is not None and self._model_path.exists():
            self._load_network(input_size)

        metrics = {}
        if X_val is not None and y_val is not None and val_products is not None and val_anchors is not None and len(X_val) > 0:
            # We compute metrics on the absolute 1-step ahead price
            preds_1step = self.predict(X_val, products=val_products, current_prices=val_anchors)
            # y_val is % change. Convert to absolute price.
            actuals_1step = val_anchors * (1 + y_val[:, 0])

            metrics = compute_all_metrics(actuals_1step, preds_1step)
            log.info(
                f"LSTM validation — RMSE: {metrics['rmse']:.4f}  "
                f"MAE: {metrics['mae']:.4f}  MAPE: {metrics['mape']:.2f}%"
            )

        self._save_meta()
        return metrics

    # ──────────────────────────────────────────────
    # Prediction
    # ──────────────────────────────────────────────
    def predict(self, sequences: np.ndarray, products: List[str] = None, current_prices: List[float] = None, **kwargs) -> np.ndarray:
        """Predict from scaled sequences. Returns denormalized 1-step prices for ensemble."""
        if self._model is None:
            self.load()
        # preds_norm is (batch, 30) of % changes
        preds_norm = self._predict_raw(sequences)
        # We only need the 1-step ahead prediction (index 0) for ensemble training
        step_1_pct = preds_norm[:, 0]
        
        if current_prices is not None:
            return np.array(current_prices) * (1 + step_1_pct)
        return step_1_pct

    def predict_with_uncertainty(
        self, sequences: np.ndarray, current_prices: List[float], n_samples: int = 50, **kwargs
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Predict future 30-day prices with MC dropout bounds.
        Returns: point, lower, upper arrays of shape (batch, 30).
        Prices are reconstructed from predicted % changes.
        """
        if self._model is None:
            self.load()

        x = torch.FloatTensor(sequences).to(self._device)
        
        # 1. Deterministic point prediction (no dropout, no noise)
        self._model.eval()
        with torch.no_grad():
            point_pct = self._model(x).cpu().numpy()

        # 2. Stochastic MC Dropout for confidence bounds
        self._model.train()  # Enable dropout
        all_preds = []

        with torch.no_grad():
            for _ in range(n_samples):
                # Add tiny noise to features for more robust MC bounds
                noise = torch.randn_like(x) * 0.01
                preds = self._model(x + noise).cpu().numpy()
                all_preds.append(preds)

        self._model.eval()
        
        # Shape: (n_samples, batch, 30)
        preds = np.array(all_preds)
        
        lower_pct = np.percentile(preds, 10, axis=0)
        upper_pct = np.percentile(preds, 90, axis=0)

        # Convert % changes to absolute prices
        point_prices = np.zeros_like(point_pct)
        lower_prices = np.zeros_like(lower_pct)
        upper_prices = np.zeros_like(upper_pct)

        for i in range(len(current_prices)):
            cp = current_prices[i]
            point_prices[i] = cp * (1 + point_pct[i])
            lower_prices[i] = cp * (1 + lower_pct[i])
            upper_prices[i] = cp * (1 + upper_pct[i])

        return point_prices, lower_prices, upper_prices

    def predict_future(
        self, last_sequence: np.ndarray, product: str, steps: int = 7, **kwargs
    ) -> np.ndarray:
        """Auto-regressive multi-step forecast."""
        if self._model is None:
            self.load()

        self._model.eval()
        seq = last_sequence.copy()
        predictions = []

        with torch.no_grad():
            for _ in range(steps):
                x = torch.FloatTensor(seq).unsqueeze(0).to(self._device)
                pred = self._model(x).cpu().numpy()[0]
                predictions.append(pred)
                seq = np.roll(seq, -1, axis=0)
                seq[-1, 0] = pred  

        preds = np.array(predictions)
        return self._inverse_transform_target(preds, [product] * steps)

    # ──────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────
    def _predict_raw(self, sequences: np.ndarray) -> np.ndarray:
        self._model.eval()
        x = torch.FloatTensor(sequences).to(self._device)
        with torch.no_grad():
            return self._model(x).cpu().numpy()

    def _inverse_transform_target(self, normalized: np.ndarray, products: List[str]) -> np.ndarray:
        """Convert mean-scaled predictions back to real price scale per product."""
        out = np.zeros_like(normalized)
        for i, prod in enumerate(products):
            if prod in self._product_means:
                out[i] = normalized[i] * self._product_means[prod]
            else:
                out[i] = normalized[i]
        return out

    def _load_network(self, input_size: int):
        self._model = _LSTMNetwork(
            input_size=input_size,
            hidden_size=self._hidden,
            num_layers=self._layers,
            dropout=self._dropout,
            horizon=self._horizon,
        ).to(self._device)
        self._model.load_state_dict(
            torch.load(str(self._model_path), map_location=self._device, weights_only=True)
        )

    # ──────────────────────────────────────────────
    # Persistence
    # ──────────────────────────────────────────────
    def save(self):
        if self._model is not None:
            torch.save(self._model.state_dict(), str(self._model_path))

    def load(self):
        self._load_scalers()
        self._load_meta()
        self._load_network(input_size=self._n_features)
        log.info(
            f"Loaded LSTM model ← {self._model_path} "
            f"({self._n_features} features)"
        )

    def _save_scalers(self):
        joblib.dump(self._product_means, str(self._product_means_path))

    def _load_scalers(self):
        if self._product_means_path.exists():
            self._product_means = joblib.load(str(self._product_means_path))

    def _save_meta(self):
        np.savez(
            str(self._meta_path),
            n_features=self._n_features,
            feature_cols=np.array(self._feature_cols, dtype=object),
        )

    def _load_meta(self):
        if self._meta_path.exists():
            data = np.load(str(self._meta_path), allow_pickle=True)
            self._n_features = int(data["n_features"])
            self._feature_cols = list(data["feature_cols"])
