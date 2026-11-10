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
    def __init__(self, x, y, anchors=None, sample_weights=None,
                 period_masks=None):
        self.x = torch.as_tensor(x, dtype=torch.float32)
        self.y = torch.as_tensor(y, dtype=torch.float32)
        self.anchors = None
        self.sample_weights = None
        if anchors is not None:
            values = np.asarray(anchors, dtype=float).reshape(-1)
            if (values.shape != (len(self.y),) or not np.isfinite(values).all()
                    or (values <= 0).any()):
                raise ValueError("Sequence anchors must be positive and aligned to targets")
            self.anchors = torch.as_tensor(values, dtype=torch.float32)
        if sample_weights is not None:
            values = np.asarray(sample_weights, dtype=float).reshape(-1)
            if (values.shape != (len(self.y),) or not np.isfinite(values).all()
                    or (values <= 0).any()):
                raise ValueError("Sequence sample weights must be positive and aligned to targets")
            self.sample_weights = torch.as_tensor(values, dtype=torch.float32)
        self.period_masks = None
        if period_masks is not None:
            masks = np.asarray(period_masks, dtype=bool)
            if (masks.ndim != 3 or masks.shape[0] != len(self.y)
                    or masks.shape[2] != self.y.shape[1]):
                raise ValueError("Period masks must align with sequence samples and leads")
            self.period_masks = torch.as_tensor(masks, dtype=torch.bool)

    def __len__(self):
        return len(self.y)

    def __getitem__(self, index):
        values = [self.x[index], self.y[index]]
        if self.anchors is not None:
            values.append(self.anchors[index])
        if self.sample_weights is not None:
            values.append(self.sample_weights[index])
        if self.period_masks is not None:
            values.append(self.period_masks[index])
        return tuple(values)


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
        self.training_configuration = None
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
                        stride=1, anchor_column=None):
        """Build samples whose first target is the final feature-row date.

        ``anchor_column`` lets source-as-of training provide the price actually
        available at that sample's origin. The default preserves legacy callers.
        """
        if anchor_column is not None and anchor_column not in featured.columns:
            raise ValueError(f"Missing LSTM anchor column: {anchor_column}")
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
                anchor = (group[anchor_column].iloc[i] if anchor_column is not None
                          else group.price_index.iloc[i - 1])
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
    def build_published_period_masks(target_start_dates, horizon):
        """Mask forecast days into up to six ISO weeks and three calendar months.

        The first six slots are weekly groups and the last three are monthly
        groups, matching the publisher's period boundaries. Target dates are
        the first forecast dates returned by ``build_sequences``.
        """
        dates = pd.to_datetime(target_start_dates, errors="raise")
        if horizon <= 0:
            raise ValueError("Forecast horizon must be positive")
        masks = np.zeros((len(dates), 9, int(horizon)), dtype=bool)
        for row_index, start in enumerate(dates):
            week_slots, month_slots = {}, {}
            for lead in range(int(horizon)):
                target = pd.Timestamp(start) + pd.Timedelta(days=lead)
                iso = target.isocalendar()
                week_key = (int(iso.year), int(iso.week))
                month_key = (target.year, target.month)
                week_slots.setdefault(week_key, []).append(lead)
                month_slots.setdefault(month_key, []).append(lead)
            if len(week_slots) > 6 or len(month_slots) > 3:
                raise ValueError("Forecast horizon exceeds published period-mask capacity")
            for slot, leads in enumerate(week_slots.values()):
                masks[row_index, slot, leads] = True
            for slot, leads in enumerate(month_slots.values(), start=6):
                masks[row_index, slot, leads] = True
        return masks

    @staticmethod
    def _masked_loss(pred, target, delta=0.05):
        """Huber loss on finite targets — robust to outlier price moves."""
        mask = torch.isfinite(target)
        if not mask.any():
            return None
        return nn.functional.huber_loss(pred[mask], target[mask], reduction='mean', delta=delta)

    @staticmethod
    def _masked_weighted_loss(pred, target, sample_weights, delta=0.05):
        """Per-sequence weighted Huber loss over finite multi-horizon labels."""
        mask = torch.isfinite(target)
        if not mask.any():
            return None
        weights = sample_weights.reshape(-1, 1).expand_as(target)
        if not torch.isfinite(weights).all() or (weights <= 0).any():
            raise ValueError("Training sample weights must be finite and positive")
        safe_target = torch.where(mask, target, torch.zeros_like(target))
        losses = nn.functional.huber_loss(
            pred, safe_target, reduction='none', delta=delta)
        weighted_mask = weights * mask.to(weights.dtype)
        denominator = weighted_mask.sum()
        if denominator <= 0:
            return None
        return (losses * weighted_mask).sum() / denominator

    @staticmethod
    def _masked_php_huber(pred, target, anchors, delta_php):
        """Huber loss on absolute PHP errors for relative-price outputs."""
        mask = torch.isfinite(target)
        if not mask.any():
            return None
        absolute_error = (pred - target) * anchors.reshape(-1, 1)
        return nn.functional.huber_loss(
            absolute_error[mask], torch.zeros_like(absolute_error[mask]),
            reduction='mean', delta=delta_php)

    @staticmethod
    def _masked_php_tolerance_huber(pred, target, anchors, delta_php,
                                    tolerance_php=5.0):
        """Robust margin loss: zero for hits, Huber penalty beyond +/-PHP 5."""
        mask = torch.isfinite(target)
        if not mask.any():
            return None
        absolute_error = (pred - target) * anchors.reshape(-1, 1)
        miss_margin = torch.clamp(torch.abs(absolute_error) - tolerance_php, min=0.0)
        return nn.functional.huber_loss(
            miss_margin[mask], torch.zeros_like(miss_margin[mask]),
            reduction='mean', delta=delta_php)

    @staticmethod
    def _masked_relative_tolerance_huber(pred, target, delta=0.01,
                                         tolerance=0.05):
        """Penalize relative price error only outside the requested hit band.

        LSTM targets are relative changes from the origin anchor. Dividing the
        prediction error by ``1 + target`` expresses it relative to actual
        price, rather than relative to the forecast-origin anchor.
        """
        finite_target = torch.isfinite(target)
        actual_scale = 1.0 + target
        mask = (finite_target & torch.isfinite(actual_scale)
                & (actual_scale > 0))
        if not mask.any():
            return None
        if not torch.isfinite(pred[mask]).all():
            raise ValueError("Relative-tolerance predictions must be finite on observed targets")
        safe_target = torch.where(mask, target, torch.zeros_like(target))
        safe_prediction = torch.where(mask, pred, torch.zeros_like(pred))
        safe_scale = torch.where(mask, actual_scale, torch.ones_like(actual_scale))
        relative_error = (safe_prediction - safe_target) / safe_scale
        miss_margin = torch.clamp(torch.abs(relative_error) - tolerance, min=0.0)
        return nn.functional.huber_loss(
            miss_margin[mask], torch.zeros_like(miss_margin[mask]),
            reduction='mean', delta=delta)

    @staticmethod
    def _masked_published_period_huber(pred, target, period_masks, delta=0.05):
        """Huber loss on masked weekly/monthly averages of relative prices."""
        if period_masks.ndim != 3 or period_masks.shape[0] != len(target):
            raise ValueError("Published-period masks are not batch-aligned")
        observed = torch.isfinite(target)
        period_masks = period_masks.to(dtype=torch.bool)
        safe_target = torch.where(observed, target, torch.zeros_like(target))
        losses = []
        for start, stop in ((0, 6), (6, 9)):
            masks = period_masks[:, start:stop, :]
            predicted_count = masks.sum(dim=2)
            observed_masks = masks & observed[:, None, :]
            observed_count = observed_masks.sum(dim=2)
            valid = (predicted_count > 0) & (observed_count > 0)
            if not valid.any():
                continue
            predicted_mean = (
                (pred[:, None, :] * masks.to(pred.dtype)).sum(dim=2)
                / predicted_count.clamp_min(1).to(pred.dtype))
            actual_mean = (
                (safe_target[:, None, :] * observed_masks.to(target.dtype)).sum(dim=2)
                / observed_count.clamp_min(1).to(target.dtype))
            error = predicted_mean[valid] - actual_mean[valid]
            losses.append(nn.functional.huber_loss(
                error, torch.zeros_like(error), reduction="mean", delta=delta))
        return torch.stack(losses).mean() if losses else None

    def train(self, x_train, y_train, x_val, y_val, *, train_anchors=None,
              val_anchors=None, price_huber_delta=None,
              price_tolerance_huber_delta=None,
              relative_tolerance_huber_delta=None, train_sample_weights=None,
              sample_weight_description=None, train_period_masks=None,
              val_period_masks=None, period_aggregate_loss_weight=0.0):
        if not len(x_train) or not len(x_val):
            raise ValueError("Training and validation sequences are required")
        php_scaled_loss = price_huber_delta is not None
        tolerance_loss = price_tolerance_huber_delta is not None
        relative_tolerance_loss = relative_tolerance_huber_delta is not None
        if sum((php_scaled_loss, tolerance_loss, relative_tolerance_loss)) > 1:
            raise ValueError("Choose only one specialized LSTM loss")
        if train_sample_weights is not None and (
                php_scaled_loss or tolerance_loss or relative_tolerance_loss):
            raise ValueError(
                "Recency sample weights currently support only ordinary relative Huber training")
        train_weight_values = None
        if train_sample_weights is not None:
            train_weight_values = np.asarray(
                train_sample_weights, dtype=float).reshape(-1)
            if (train_weight_values.shape != (len(y_train),)
                    or not np.isfinite(train_weight_values).all()
                    or (train_weight_values <= 0).any()):
                raise ValueError("Training sample weights must be positive and sequence-aligned")
            mean_weight = float(np.mean(train_weight_values))
            if not np.isfinite(mean_weight) or mean_weight <= 0:
                raise ValueError("Training sample weights must have a positive mean")
            train_weight_values = train_weight_values / mean_weight
            if not sample_weight_description:
                raise ValueError("Weighted training requires a sample-weight description")
        if (not np.isfinite(period_aggregate_loss_weight)
                or not 0.0 <= period_aggregate_loss_weight <= 0.5):
            raise ValueError("Published-period loss weight must be between 0 and 0.5")
        period_loss_enabled = period_aggregate_loss_weight > 0
        if period_loss_enabled:
            if train_period_masks is None or val_period_masks is None:
                raise ValueError("Published-period loss requires train and validation masks")
            for masks, targets, label in (
                    (train_period_masks, y_train, "training"),
                    (val_period_masks, y_val, "validation")):
                masks = np.asarray(masks)
                if (masks.ndim != 3 or masks.shape[0] != len(targets)
                        or masks.shape[2] != targets.shape[1]
                        or masks.shape[1] != 9):
                    raise ValueError(f"{label} period masks have an incompatible shape")
        if tolerance_loss and (
                not np.isfinite(price_tolerance_huber_delta)
                or price_tolerance_huber_delta <= 0):
            raise ValueError("PHP tolerance-Huber delta must be positive and finite")
        if relative_tolerance_loss and (
                not np.isfinite(relative_tolerance_huber_delta)
                or relative_tolerance_huber_delta <= 0):
            raise ValueError("Relative tolerance-Huber delta must be positive and finite")
        anchor_scaled_loss = php_scaled_loss or tolerance_loss
        if php_scaled_loss:
            if (not np.isfinite(price_huber_delta) or price_huber_delta <= 0
                    or train_anchors is None or val_anchors is None):
                raise ValueError(
                    "PHP-scale Huber requires a positive delta and train/validation anchors")
            train_anchor_values = np.asarray(train_anchors, dtype=float).reshape(-1)
            val_anchor_values = np.asarray(val_anchors, dtype=float).reshape(-1)
        elif tolerance_loss:
            if train_anchors is None or val_anchors is None:
                raise ValueError(
                    "PHP tolerance-Huber requires train and validation anchors")
            train_anchor_values = np.asarray(train_anchors, dtype=float).reshape(-1)
            val_anchor_values = np.asarray(val_anchors, dtype=float).reshape(-1)
        else:
            train_anchor_values = val_anchor_values = None
        if anchor_scaled_loss:
            if (train_anchor_values.shape != (len(y_train),)
                    or val_anchor_values.shape != (len(y_val),)
                    or not np.isfinite(train_anchor_values).all()
                    or not np.isfinite(val_anchor_values).all()
                    or (train_anchor_values <= 0).any()
                    or (val_anchor_values <= 0).any()):
                raise ValueError("PHP-scale loss anchors must be positive and sequence-aligned")
        cfg = get_settings()
        self.training_configuration = {
            "optimizer": {"name": "AdamW", "learning_rate": float(self.lr),
                          "weight_decay": 1e-5},
            "scheduler": {"name": "ReduceLROnPlateau", "mode": "min",
                          "factor": 0.5, "patience": 2, "min_learning_rate": 1e-5},
            "loss": ({"name": "Huber", "delta_php": float(price_huber_delta),
                      "target_scale": "absolute_price_error"}
                     if php_scaled_loss else
                     {"name": "tolerance_huber", "tolerance_php": 5.0,
                      "delta_php": float(price_tolerance_huber_delta),
                      "target_scale": "absolute_price_error_outside_tolerance"}
                     if tolerance_loss else
                     {"name": "relative_tolerance_huber", "tolerance_relative": 0.05,
                      "delta_relative": float(relative_tolerance_huber_delta),
                      "target_scale": "relative_error_to_actual_outside_tolerance"}
                     if relative_tolerance_loss else
                     {"name": "daily_plus_published_period_huber", "delta": 0.05,
                      "published_period_loss_weight": float(period_aggregate_loss_weight)}
                     if period_loss_enabled else {"name": "Huber", "delta": 0.05}),
            "selection_metric": (
                "validation_within5_php_miss_rate" if tolerance_loss else
                "validation_actual_price_rmse_php" if php_scaled_loss else
                "validation_within5_percent_miss_rate" if relative_tolerance_loss else
                "validation_daily_and_published_period_huber"
                if period_loss_enabled else
                "validation_relative_huber_loss"),
            "gradient_clip_norm": 1.0,
            "max_epochs": int(self.epochs),
            "batch_size": int(self.batch_size),
            "early_stopping_patience": int(self.patience),
            "training_sequence_stride": int(cfg.training_sequence_stride),
            "random_seed": int(cfg.random_seed),
            "selected_epoch": None,
            "selected_validation_loss": None,
        }
        if train_weight_values is not None:
            self.training_configuration["sample_weighting"] = {
                "description": str(sample_weight_description),
                "normalization": "mean_weight_equals_1",
                "normalized_min": float(train_weight_values.min()),
                "normalized_max": float(train_weight_values.max()),
                "normalized_mean": float(train_weight_values.mean()),
            }
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
        train_loader = DataLoader(PriceSequenceDataset(
                                      x_train, y_train, train_anchor_values,
                                      train_weight_values, train_period_masks),
                                  batch_size=self.batch_size, shuffle=True,
                                  drop_last=False, generator=generator)
        val_loader = DataLoader(PriceSequenceDataset(
                                    x_val, y_val, val_anchor_values,
                                    period_masks=val_period_masks),
                                batch_size=self.batch_size, shuffle=False)
        best, patience, history = float("inf"), 0, []
        self.path.mkdir(parents=True, exist_ok=True)
        for epoch in range(1, self.epochs + 1):
            self.model.train()
            train_num = train_den = 0
            for batch in train_loader:
                xb, yb = batch[0].to(self.device), batch[1].to(self.device)
                anchor_batch = (batch[2].to(self.device)
                                if anchor_scaled_loss else None)
                sample_weight_batch = (
                    batch[3 if anchor_scaled_loss else 2].to(self.device)
                    if train_weight_values is not None else None)
                period_mask_batch = (
                    batch[-1].to(self.device)
                    if period_loss_enabled else None)
                prediction = self.model(xb)
                if php_scaled_loss:
                    loss = self._masked_php_huber(
                        prediction, yb, anchor_batch, float(price_huber_delta))
                elif tolerance_loss:
                    loss = self._masked_php_tolerance_huber(
                        prediction, yb, anchor_batch,
                        float(price_tolerance_huber_delta))
                elif relative_tolerance_loss:
                    loss = self._masked_relative_tolerance_huber(
                        prediction, yb, delta=float(relative_tolerance_huber_delta))
                elif sample_weight_batch is not None:
                    loss = self._masked_weighted_loss(
                        prediction, yb, sample_weight_batch)
                else:
                    loss = self._masked_loss(prediction, yb)
                if loss is not None and period_mask_batch is not None:
                    period_loss = self._masked_published_period_huber(
                        prediction, yb, period_mask_batch)
                    if period_loss is not None:
                        weight = float(period_aggregate_loss_weight)
                        loss = (1.0 - weight) * loss + weight * period_loss
                if loss is None:
                    continue
                optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(self.model.parameters(), 1)
                optimizer.step()
                mask = torch.isfinite(yb)
                if sample_weight_batch is None:
                    count = int(mask.sum())
                    train_num += float(loss.detach()) * count
                    train_den += count
                else:
                    effective_count = float((
                        sample_weight_batch.reshape(-1, 1)
                        * mask.to(sample_weight_batch.dtype)).sum())
                    train_num += float(loss.detach()) * effective_count
                    train_den += effective_count
            self.model.eval()
            val_num = val_den = 0
            with torch.no_grad():
                val_squared_error = 0.0
                val_within5_misses = 0
                val_relative_within5_misses = 0
                for batch in val_loader:
                    xb, yb = batch[0].to(self.device), batch[1].to(self.device)
                    anchor_batch = (batch[2].to(self.device) if len(batch) == 3 else None)
                    prediction = self.model(xb)
                    if php_scaled_loss:
                        loss = self._masked_php_huber(
                            prediction, yb, anchor_batch, float(price_huber_delta))
                    elif tolerance_loss:
                        loss = self._masked_php_tolerance_huber(
                            prediction, yb, anchor_batch,
                            float(price_tolerance_huber_delta))
                    elif relative_tolerance_loss:
                        loss = self._masked_relative_tolerance_huber(
                            prediction, yb,
                            delta=float(relative_tolerance_huber_delta))
                    else:
                        loss = self._masked_loss(prediction, yb)
                    if loss is not None and period_loss_enabled:
                        period_loss = self._masked_published_period_huber(
                            prediction, yb, batch[-1].to(self.device))
                        if period_loss is not None:
                            weight = float(period_aggregate_loss_weight)
                            loss = (1.0 - weight) * loss + weight * period_loss
                    if loss is not None:
                        count = int(torch.isfinite(yb).sum())
                        val_num += float(loss) * count
                        val_den += count
                        if anchor_scaled_loss:
                            error = (prediction - yb) * anchor_batch.reshape(-1, 1)
                            mask = torch.isfinite(yb)
                            if php_scaled_loss:
                                val_squared_error += float(torch.square(error[mask]).sum())
                            else:
                                val_within5_misses += int(
                                    torch.count_nonzero(torch.abs(error[mask]) > 5.0))
                        if relative_tolerance_loss:
                            actual_scale = 1.0 + yb
                            mask = (torch.isfinite(yb) & torch.isfinite(actual_scale)
                                    & (actual_scale > 0))
                            if not torch.isfinite(prediction[mask]).all():
                                raise ValueError(
                                    "LSTM validation predictions are nonfinite on observed targets")
                            safe_target = torch.where(mask, yb, torch.zeros_like(yb))
                            safe_prediction = torch.where(
                                mask, prediction, torch.zeros_like(prediction))
                            safe_scale = torch.where(
                                mask, actual_scale, torch.ones_like(actual_scale))
                            relative_error = (safe_prediction - safe_target) / safe_scale
                            val_relative_within5_misses += int(torch.count_nonzero(
                                torch.abs(relative_error[mask]) > 0.05))
            if not train_den or not val_den:
                raise ValueError("No finite LSTM targets in a training partition")
            train_loss, val_loss = train_num / train_den, val_num / val_den
            selection_score = (
                float(val_within5_misses / val_den) if tolerance_loss else
                float(np.sqrt(val_squared_error / val_den)) if php_scaled_loss else
                float(val_relative_within5_misses / val_den)
                if relative_tolerance_loss else
                val_loss)
            epoch_record = {"epoch": epoch, "train_loss": train_loss,
                            "val_loss": val_loss, "lr": optimizer.param_groups[0]["lr"]}
            if php_scaled_loss:
                epoch_record["validation_rmse_php"] = selection_score
                log.info(
                    "LSTM epoch %d/%d: train PHP-Huber=%.6f, validation PHP-RMSE=%.6f",
                    epoch, self.epochs, train_loss, selection_score)
            elif tolerance_loss:
                epoch_record["validation_within5_miss_rate"] = selection_score
                log.info(
                    "LSTM epoch %d/%d: train tolerance-Huber=%.6f, "
                    "validation Within-PHP-5 miss rate=%.6f",
                    epoch, self.epochs, train_loss, selection_score)
            elif relative_tolerance_loss:
                epoch_record["validation_within5_percent_miss_rate"] = selection_score
                log.info(
                    "LSTM epoch %d/%d: train relative-tolerance-Huber=%.6f, "
                    "validation within-5-percent miss rate=%.6f",
                    epoch, self.epochs, train_loss, selection_score)
            else:
                log.info("LSTM epoch %d/%d: train Huber=%.6f, validation Huber=%.6f",
                         epoch, self.epochs, train_loss, val_loss)
            history.append(epoch_record)
            if selection_score < best - 1e-7:
                best, patience = selection_score, 0
                self.training_configuration["selected_epoch"] = int(epoch)
                self.training_configuration["selected_validation_loss"] = float(val_loss)
                self.training_configuration["selected_validation_score"] = float(selection_score)
                self.save()
            else:
                patience += 1
            scheduler.step(selection_score)
            if patience >= self.patience:
                break
        self.load()
        (self.path / "lstm_history.json").write_text(json.dumps(history, indent=2), encoding="utf-8")
        val_pred = self.predict_paths(x_val)
        mask = np.isfinite(y_val[:, 0])
        actual, predicted = y_val[mask, 0], val_pred[mask, 0]
        result = {"relative_mae": compute_mae(actual, predicted),
                  "relative_rmse": compute_rmse(actual, predicted),
                  "n": int(mask.sum())}
        if val_anchor_values is not None:
            first_step_error = (predicted - actual) * val_anchor_values[mask]
            result["first_step_php_mae"] = float(np.mean(np.abs(first_step_error)))
            result["first_step_php_rmse"] = float(
                np.sqrt(np.mean(np.square(first_step_error))))
        return result

    def refit_fixed_epochs(self, x_train, y_train, *, epochs,
                           learning_rate_schedule=None, train_anchors=None,
                           price_huber_delta=None,
                           price_tolerance_huber_delta=None,
                           relative_tolerance_huber_delta=None,
                           train_sample_weights=None,
                           sample_weight_description=None,
                           train_period_masks=None,
                           period_aggregate_loss_weight=0.0):
        """Refit a selected LSTM configuration on all eligible rows.

        The epoch count and optional learning-rate schedule must come from an
        earlier chronological validation fit. This final pass has no validation
        loader, so no training label is reused for checkpoint selection.
        """
        x_train = np.asarray(x_train, dtype=np.float32)
        y_train = np.asarray(y_train, dtype=np.float32)
        epochs = int(epochs)
        if (epochs <= 0 or x_train.ndim != 3 or y_train.ndim != 2
                or len(x_train) != len(y_train) or not len(x_train)
                or x_train.shape[1] != self.seq_len
                or y_train.shape[1] != self.horizon
                or not np.isfinite(x_train).all()):
            raise ValueError("Final LSTM refit requires aligned finite sequences and positive epochs")
        php_scaled_loss = price_huber_delta is not None
        tolerance_loss = price_tolerance_huber_delta is not None
        relative_tolerance_loss = relative_tolerance_huber_delta is not None
        if sum((php_scaled_loss, tolerance_loss, relative_tolerance_loss)) > 1:
            raise ValueError("Choose only one specialized LSTM loss")
        anchor_scaled_loss = php_scaled_loss or tolerance_loss
        anchor_values = None
        if anchor_scaled_loss:
            if train_anchors is None:
                raise ValueError("PHP-scale final refit requires training anchors")
            anchor_values = np.asarray(train_anchors, dtype=float).reshape(-1)
            if (anchor_values.shape != (len(y_train),)
                    or not np.isfinite(anchor_values).all()
                    or (anchor_values <= 0).any()):
                raise ValueError("Final LSTM refit anchors must be positive and aligned")
        if php_scaled_loss and (
                not np.isfinite(price_huber_delta) or price_huber_delta <= 0):
            raise ValueError("PHP Huber delta must be positive and finite")
        if tolerance_loss and (
                not np.isfinite(price_tolerance_huber_delta)
                or price_tolerance_huber_delta <= 0):
            raise ValueError("PHP tolerance-Huber delta must be positive and finite")
        if relative_tolerance_loss and (
                not np.isfinite(relative_tolerance_huber_delta)
                or relative_tolerance_huber_delta <= 0):
            raise ValueError("Relative tolerance-Huber delta must be positive and finite")
        if train_sample_weights is not None and (
                anchor_scaled_loss or relative_tolerance_loss):
            raise ValueError(
                "Recency sample weights support ordinary relative Huber refitting only")
        weight_values = None
        if train_sample_weights is not None:
            weight_values = np.asarray(train_sample_weights, dtype=float).reshape(-1)
            if (weight_values.shape != (len(y_train),)
                    or not np.isfinite(weight_values).all()
                    or (weight_values <= 0).any()):
                raise ValueError("Final LSTM sample weights must be positive and aligned")
            mean_weight = float(weight_values.mean())
            if not np.isfinite(mean_weight) or mean_weight <= 0:
                raise ValueError("Final LSTM sample weights must have a positive mean")
            weight_values /= mean_weight
            if not sample_weight_description:
                raise ValueError("Weighted final refit requires a sample-weight description")
        if (not np.isfinite(period_aggregate_loss_weight)
                or not 0.0 <= period_aggregate_loss_weight <= 0.5):
            raise ValueError("Published-period loss weight must be between 0 and 0.5")
        period_loss_enabled = period_aggregate_loss_weight > 0
        if period_loss_enabled:
            masks = np.asarray(train_period_masks, dtype=bool)
            if (masks.ndim != 3 or masks.shape[0] != len(y_train)
                    or masks.shape[1] != 9 or masks.shape[2] != self.horizon):
                raise ValueError("Final refit period masks have an incompatible shape")
        else:
            masks = None
        if learning_rate_schedule is None:
            rates = [float(self.lr)] * epochs
            schedule_source = "configured_learning_rate"
        else:
            rates = [float(value) for value in learning_rate_schedule]
            if (len(rates) != epochs or not np.isfinite(rates).all()
                    or any(value <= 0 for value in rates)):
                raise ValueError("Final LSTM learning-rate schedule must match epochs")
            schedule_source = "replayed_chronological_selection_history"

        cfg = get_settings()
        torch.manual_seed(cfg.random_seed)
        np.random.seed(cfg.random_seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(cfg.random_seed)
        self.model = _LSTMNetwork(len(self.feature_cols), self.hidden, self.layers,
                                  self.dropout, self.horizon).to(self.device)
        optimizer = torch.optim.AdamW(
            self.model.parameters(), lr=rates[0], weight_decay=1e-5)
        generator = torch.Generator().manual_seed(cfg.random_seed)
        loader = DataLoader(
            PriceSequenceDataset(
                x_train, y_train, anchor_values, weight_values, masks),
            batch_size=self.batch_size, shuffle=True, drop_last=False,
            generator=generator)
        for epoch, learning_rate in enumerate(rates, start=1):
            for group in optimizer.param_groups:
                group["lr"] = learning_rate
            self.model.train()
            trained_targets = 0
            for batch in loader:
                xb, yb = batch[0].to(self.device), batch[1].to(self.device)
                anchor_batch = batch[2].to(self.device) if anchor_scaled_loss else None
                weight_batch = (batch[3 if anchor_scaled_loss else 2].to(self.device)
                                if weight_values is not None else None)
                period_batch = batch[-1].to(self.device) if period_loss_enabled else None
                prediction = self.model(xb)
                if php_scaled_loss:
                    loss = self._masked_php_huber(
                        prediction, yb, anchor_batch, float(price_huber_delta))
                elif tolerance_loss:
                    loss = self._masked_php_tolerance_huber(
                        prediction, yb, anchor_batch,
                        float(price_tolerance_huber_delta))
                elif relative_tolerance_loss:
                    loss = self._masked_relative_tolerance_huber(
                        prediction, yb,
                        delta=float(relative_tolerance_huber_delta))
                elif weight_batch is not None:
                    loss = self._masked_weighted_loss(prediction, yb, weight_batch)
                else:
                    loss = self._masked_loss(prediction, yb)
                if loss is not None and period_batch is not None:
                    period_loss = self._masked_published_period_huber(
                        prediction, yb, period_batch)
                    if period_loss is not None:
                        weight = float(period_aggregate_loss_weight)
                        loss = (1.0 - weight) * loss + weight * period_loss
                if loss is None:
                    continue
                optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                optimizer.step()
                trained_targets += int(torch.isfinite(yb).sum())
            if not trained_targets:
                raise ValueError("No finite LSTM targets in the final refit data")

        if self.training_configuration is None:
            self.training_configuration = {}
        self.training_configuration["final_refit"] = {
            "sequences": int(len(x_train)),
            "observed_targets": int(np.isfinite(y_train).sum()),
            "epochs": epochs,
            "uses_all_supplied_rows": True,
            "learning_rate_schedule": schedule_source,
            "validation_used_for_final_checkpoint_selection": False,
        }
        if weight_values is not None:
            self.training_configuration["final_refit"]["sample_weighting"] = str(
                sample_weight_description)
        self.save()
        return self.training_configuration["final_refit"]

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
        if self.training_configuration is not None:
            meta["training_configuration"] = self.training_configuration
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
              and (set(features).issubset(LSTM_FEATURE_COLS)
                   or features == LEGACY_LSTM_FEATURE_COLS)):
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
        self.training_configuration = meta.get("training_configuration")
        self.model = _LSTMNetwork(len(self.feature_cols), self.hidden, self.layers,
                                  self.dropout, self.horizon).to(self.device)
        state = torch.load(self.path / "lstm_model.pt", map_location=self.device, weights_only=True)
        self.model.load_state_dict(state)
        self.model.eval()
