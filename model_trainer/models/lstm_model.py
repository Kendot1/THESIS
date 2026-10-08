"""Direct multi-horizon LSTM with causal sequences and masked targets."""
import json
import os
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# PyTorch can request a per-user Inductor cache while creating an optimizer.
# On Windows runtimes without a USERNAME environment variable, getpass falls
# back to importing the Unix-only ``pwd`` module. Give Torch a stable temp path
# before importing it so local Windows training does not fail during setup.
if os.name == "nt" and not os.environ.get("TORCHINDUCTOR_CACHE_DIR"):
    os.environ["TORCHINDUCTOR_CACHE_DIR"] = str(
        Path(tempfile.gettempdir()) / "foodcast_torchinductor"
    )

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

from config.settings import get_settings
from data.preprocessor import SERIES_KEY
from utils.metrics import compute_mae, compute_rmse
from utils.logger import get_logger

log = get_logger(__name__)


LSTM_FEATURE_COLS = [
    "price_lag_1d", "price_lag_2d", "price_lag_3d", "price_lag_7d",
    "price_lag_8d", "price_lag_14d", "price_lag_30d",
    "price_rolling_mean_3d", "price_rolling_mean_7d",
    "price_rolling_mean_14d", "price_rolling_mean_30d",
    "price_rolling_std_7d", "price_rolling_std_14d", "price_rolling_std_30d",
    "price_volatility_14d", "price_pct_change_1d", "price_pct_change_7d",
    "price_deviation_from_mean", "price_rsi_14d", "price_macd",
    "price_macd_signal", "price_acceleration_1d", "price_bollinger_position_14d",
    "month_sin", "month_cos", "doy_sin", "doy_cos",
    "is_wet_season", "is_christmas_season",
    "is_payday_window", "is_holiday_proximity",
]
SCALED_PRICE_FEATURES = {
    "price_lag_1d", "price_lag_2d", "price_lag_3d", "price_lag_7d",
    "price_lag_8d", "price_lag_14d", "price_lag_30d", "price_rolling_mean_3d",
    "price_rolling_mean_7d", "price_rolling_mean_14d", "price_rolling_mean_30d",
    "price_rolling_std_7d", "price_rolling_std_14d", "price_rolling_std_30d",
    "price_macd", "price_macd_signal",
}
LEGACY_LSTM_FEATURE_COLS = [
    "price_lag_1d", "price_lag_7d", "price_lag_30d",
    "price_rolling_mean_7d", "price_rolling_mean_30d",
    "price_pct_change_1d", "price_pct_change_7d", "price_rsi_14d",
    "price_macd", "price_macd_signal", "price_rolling_std_7d",
    "price_rolling_std_30d", "month_sin", "month_cos", "dow_sin", "dow_cos",
]


def series_key(values) -> str:
    if not isinstance(values, tuple):
        values = (values,)
    return "||".join(str(v) for v in values)


class PriceSequenceDataset(Dataset):
    def __init__(self, x, y):
        self.x = torch.as_tensor(x, dtype=torch.float32)
        self.y = torch.as_tensor(y, dtype=torch.float32)

    def __len__(self):
        return len(self.y)

    def __getitem__(self, index):
        return self.x[index], self.y[index]


class _LSTMNetwork(nn.Module):
    def __init__(self, input_size, hidden_size=128, num_layers=2, dropout=.2, horizon=30):
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers=num_layers,
                            batch_first=True, dropout=dropout if num_layers > 1 else 0)
        self.attention = nn.Sequential(nn.Linear(hidden_size, hidden_size // 2),
                                       nn.Tanh(), nn.Linear(hidden_size // 2, 1))
        self.head = nn.Sequential(nn.LayerNorm(hidden_size * 2),
                                  nn.Linear(hidden_size * 2, 64), nn.GELU(),
                                  nn.Dropout(dropout), nn.Linear(64, horizon))
        for name, value in self.lstm.named_parameters():
            if "weight_ih" in name:
                nn.init.xavier_uniform_(value)
            elif "weight_hh" in name:
                nn.init.orthogonal_(value)
            elif "bias" in name:
                nn.init.zeros_(value)
                value.data[value.numel() // 4:value.numel() // 2] = 1

    def forward(self, x):
        states, _ = self.lstm(x)
        weights = torch.softmax(self.attention(states), dim=1)
        context = (states * weights).sum(dim=1)
        return self.head(torch.cat([context, states[:, -1]], dim=1))


class LSTMModel:
    def __init__(self, artifact_dir=None):
        cfg = get_settings()
        self.path = Path(artifact_dir or cfg.artifacts_dir)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.seq_len = cfg.sequence_length
        self.horizon = cfg.monthly_horizon
        self.hidden = cfg.lstm_hidden_size
        self.layers = cfg.lstm_num_layers
        self.dropout = cfg.lstm_dropout
        self.lr = cfg.lstm_learning_rate
        self.epochs = cfg.lstm_epochs
        self.batch_size = cfg.lstm_batch_size
        self.patience = cfg.lstm_patience
        self.feature_cols = list(LSTM_FEATURE_COLS)
        self.scaled_features = list(SCALED_PRICE_FEATURES)
        self.model: Optional[_LSTMNetwork] = None

    def fit_scalers(self, train: pd.DataFrame):
        if not (train.is_observed & train.observed_price.notna()).any():
            raise ValueError("No observed training prices available for LSTM scaling")
        return self

    def _scale(self, values, mean):
        values = values.copy()
        price_idx = [self.feature_cols.index(c) for c in self.scaled_features
                     if c in self.feature_cols]
        values[:, price_idx] /= mean
        return values

    def build_sequences(self, featured: pd.DataFrame, target_start=None, target_end=None,
                        stride=1):
        """Build samples whose first target is the final feature-row date."""
        x, y, anchors, keys, dates = [], [], [], [], []
        start = pd.Timestamp(target_start) if target_start is not None else None
        end = pd.Timestamp(target_end) if target_end is not None else None
        for key, group in featured.groupby(SERIES_KEY, sort=True):
            group = group.sort_values("report_date").reset_index(drop=True)
            skey = series_key(key)
            features = group[self.feature_cols].to_numpy(dtype=float)
            targets = group.observed_price.to_numpy(dtype=float)
            for i in range(self.seq_len - 1, len(group), stride):
                date = group.report_date.iloc[i]
                if (start is not None and date < start) or (end is not None and date > end):
                    continue
                if i == 0:
                    continue
                window = features[i - self.seq_len + 1:i + 1]
                anchor = group.price_index.iloc[i - 1]
                if not np.isfinite(window).all() or not np.isfinite(anchor) or anchor <= 0:
                    continue
                future = np.full(self.horizon, np.nan)
                available = min(self.horizon, len(group) - i)
                future[:available] = targets[i:i + available]
                future_dates = group.report_date.iloc[i:i + available].to_numpy()
                if start is not None:
                    future[:available][future_dates < np.datetime64(start)] = np.nan
                if end is not None:
                    future[:available][future_dates > np.datetime64(end)] = np.nan
                relative = (future - anchor) / anchor
                if not np.isfinite(relative).any():
                    continue
                x.append(self._scale(window, anchor))
                y.append(relative)
                anchors.append(float(anchor))
                keys.append(skey)
                dates.append(date)
        shape = (0, self.seq_len, len(self.feature_cols))
        return (np.asarray(x, dtype=np.float32) if x else np.empty(shape, dtype=np.float32),
                np.asarray(y, dtype=np.float32) if y else np.empty((0, self.horizon), dtype=np.float32),
                np.asarray(anchors, dtype=float), keys, np.asarray(dates, dtype="datetime64[ns]"))

    def build_live_sequence(self, featured_series: pd.DataFrame):
        """Create the current sequence ending on the unlabeled first forecast day."""
        group = featured_series.sort_values("report_date").reset_index(drop=True)
        if len(group) < self.seq_len:
            raise ValueError("Insufficient causal feature history")
        window = group[self.feature_cols].tail(self.seq_len).to_numpy(dtype=float)
        anchor = float(group.iloc[-1].price_lag_1d)
        if not np.isfinite(window).all() or not np.isfinite(anchor) or anchor <= 0:
            raise ValueError("Incomplete causal features for live LSTM forecast")
        return self._scale(window, anchor)[None].astype(np.float32), anchor

    @staticmethod
    def _masked_loss(pred, target, delta=0.05):
        """Huber loss on finite targets — robust to outlier price moves."""
        mask = torch.isfinite(target)
        if not mask.any():
            return None
        return nn.functional.huber_loss(pred[mask], target[mask], reduction='mean', delta=delta)

    def train(self, x_train, y_train, x_val, y_val):
        if not len(x_train) or not len(x_val):
            raise ValueError("Training and validation sequences are required")
        cfg = get_settings()
        torch.manual_seed(cfg.random_seed)
        np.random.seed(cfg.random_seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(cfg.random_seed)
        self.model = _LSTMNetwork(len(self.feature_cols), self.hidden, self.layers,
                                  self.dropout, self.horizon).to(self.device)
        optimizer = torch.optim.AdamW(self.model.parameters(), lr=self.lr, weight_decay=1e-5)
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, mode="min", factor=.5, patience=2, min_lr=1e-5)
        generator = torch.Generator().manual_seed(cfg.random_seed)
        train_loader = DataLoader(PriceSequenceDataset(x_train, y_train),
                                  batch_size=self.batch_size, shuffle=True,
                                  drop_last=False, generator=generator)
        val_loader = DataLoader(PriceSequenceDataset(x_val, y_val),
                                batch_size=self.batch_size, shuffle=False)
        best, patience, history = float("inf"), 0, []
        self.path.mkdir(parents=True, exist_ok=True)
        for epoch in range(1, self.epochs + 1):
            self.model.train()
            train_num = train_den = 0
            for xb, yb in train_loader:
                xb, yb = xb.to(self.device), yb.to(self.device)
                loss = self._masked_loss(self.model(xb), yb)
                if loss is None:
                    continue
                optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(self.model.parameters(), 1)
                optimizer.step()
                count = int(torch.isfinite(yb).sum())
                train_num += float(loss.detach()) * count
                train_den += count
            self.model.eval()
            val_num = val_den = 0
            with torch.no_grad():
                for xb, yb in val_loader:
                    xb, yb = xb.to(self.device), yb.to(self.device)
                    loss = self._masked_loss(self.model(xb), yb)
                    if loss is not None:
                        count = int(torch.isfinite(yb).sum())
                        val_num += float(loss) * count
                        val_den += count
            if not train_den or not val_den:
                raise ValueError("No finite LSTM targets in a training partition")
            train_loss, val_loss = train_num / train_den, val_num / val_den
            history.append({"epoch": epoch, "train_loss": train_loss,
                            "val_loss": val_loss, "lr": optimizer.param_groups[0]["lr"]})
            log.info("LSTM epoch %d/%d: train Huber=%.6f, validation Huber=%.6f",
                     epoch, self.epochs, train_loss, val_loss)
            if val_loss < best - 1e-7:
                best, patience = val_loss, 0
                self.save()
            else:
                patience += 1
            scheduler.step(val_loss)
            if patience >= self.patience:
                break
        self.load()
        (self.path / "lstm_history.json").write_text(json.dumps(history, indent=2), encoding="utf-8")
        val_pred = self.predict_paths(x_val)
        mask = np.isfinite(y_val[:, 0])
        actual, predicted = y_val[mask, 0], val_pred[mask, 0]
        return {"relative_mae": compute_mae(actual, predicted),
                "relative_rmse": compute_rmse(actual, predicted),
                "n": int(mask.sum())}

    def predict_paths(self, sequences, anchors=None):
        if self.model is None:
            self.load()
        self.model.eval()
        with torch.no_grad():
            relative = self.model(torch.as_tensor(sequences, dtype=torch.float32,
                                                  device=self.device)).cpu().numpy()
        if anchors is None:
            return relative
        anchors = np.asarray(anchors, dtype=float).reshape(-1, 1)
        return np.maximum(.01, anchors * (1 + relative))

    def save(self):
        if self.model is None:
            raise ValueError("No LSTM network to save")
        self.path.mkdir(parents=True, exist_ok=True)
        torch.save(self.model.state_dict(), self.path / "lstm_model.pt")
        meta = {"schema_version": 3, "features": self.feature_cols,
                "sequence_length": self.seq_len, "horizon": self.horizon,
                "hidden": self.hidden, "layers": self.layers, "dropout": self.dropout,
                "scaled_features": self.scaled_features,
                "scaling": "currency_features_divided_by_each_sample_anchor"}
        (self.path / "lstm_meta.json").write_text(json.dumps(meta), encoding="utf-8")

    def load(self):
        meta = json.loads((self.path / "lstm_meta.json").read_text(encoding="utf-8"))
        version = meta.get("schema_version")
        features = meta.get("features")
        if (version == 2 and features == LEGACY_LSTM_FEATURE_COLS):
            self.feature_cols = list(features)
            # Preserve the original input scaling for immutable v2 bundles.
            self.scaled_features = [c for c in features
                                    if c.startswith("price_") and "pct_change" not in c]
        elif (version == 3 and isinstance(features, list)
              and set(features).issubset(LSTM_FEATURE_COLS)):
            self.feature_cols = list(features)
            self.scaled_features = list(meta.get("scaled_features", []))
            if set(self.scaled_features) - set(self.feature_cols):
                raise ValueError("Incompatible LSTM scaling features")
        else:
            raise ValueError("Incompatible LSTM bundle")
        expected_scaling = ("price_features_divided_by_each_sample_anchor" if version == 2
                            else "currency_features_divided_by_each_sample_anchor")
        if meta.get("scaling") != expected_scaling:
            raise ValueError("Incompatible LSTM scaling contract")
        if (meta["sequence_length"], meta["horizon"]) != (self.seq_len, self.horizon):
            raise ValueError("Incompatible LSTM sequence or horizon")
        self.hidden, self.layers, self.dropout = meta["hidden"], meta["layers"], meta["dropout"]
        self.model = _LSTMNetwork(len(self.feature_cols), self.hidden, self.layers,
                                  self.dropout, self.horizon).to(self.device)
        state = torch.load(self.path / "lstm_model.pt", map_location=self.device, weights_only=True)
        self.model.load_state_dict(state)
        self.model.eval()
