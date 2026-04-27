"""
Central configuration for the FOODCAST model trainer.
All hyperparameters, paths, and environment variables are managed here.
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List
from dotenv import load_dotenv

load_dotenv(override=True)

# ──────────────────────────────────────────────
# Base paths
# ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
LOGS_DIR = PROJECT_ROOT / "logs"
ARTIFACTS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)


@dataclass
class Settings:
    """Immutable settings for the entire pipeline."""

    # ── Supabase ──
    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_key: str = os.getenv("SUPABASE_KEY", "")

    # ── OpenAI ──
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")

    # ── Groq ──
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")

    # ── Data ──
    food_prices_table: str = "food_prices"
    news_events_table: str = "stored_events"
    news_articles_table: str = "news_articles"
    predictions_table: str = "price_predictions"
    model_metrics_table: str = "model_metrics"

    # ── Feature Engineering ──
    lag_days: List[int] = field(default_factory=lambda: [1, 2, 3, 7, 14, 30])
    rolling_windows: List[int] = field(default_factory=lambda: [3, 7, 14, 30])
    sequence_length: int = 30  # LSTM look-back window (days)

    # ── Categories from the scraper schema ──
    product_categories: List[str] = field(default_factory=lambda: [
        "Rice", "Corn", "Poultry", "Livestock",
        "Vegetables", "Fruits", "Fish", "Oils", "Sugar"
    ])

    # ── LightGBM Hyperparameters ──
    lgbm_params: dict = field(default_factory=lambda: {
        "objective": "regression",
        "metric": ["rmse", "mae"],
        "boosting_type": "gbdt",
        "num_leaves": 127,
        "learning_rate": 0.005,          # Lower LR for better generalization
        "feature_fraction": 0.75,
        "bagging_fraction": 0.8,
        "bagging_freq": 5,
        "extra_trees": True,
        "min_child_samples": 10,         # Prevent overfitting on tiny leaf nodes
        "lambda_l1": 0.01,              # L1 regularization
        "lambda_l2": 0.1,               # L2 regularization
        "verbose": -1,
        "n_estimators": 2500,            # More estimators to compensate for lower LR
        "early_stopping_rounds": 150,    # More patience for lower LR
    })

    # ── LSTM Hyperparameters ──
    lstm_hidden_size: int = 128
    lstm_num_layers: int = 2
    lstm_dropout: float = 0.2
    lstm_learning_rate: float = 0.001
    lstm_epochs: int = 200
    lstm_batch_size: int = 32          # Larger batch for more stable gradients
    lstm_patience: int = 25            # Early stopping patience

    # ── Ensemble ──
    ensemble_method: str = "stacking"  # "weighted_average" | "stacking"
    lgbm_weight: float = 0.6
    lstm_weight: float = 0.4

    # ── Drift Detection ──
    psi_threshold: float = 0.2  # Population Stability Index threshold
    performance_drop_threshold: float = 0.15  # 15% MAPE increase triggers retrain

    # ── Forecast Horizons ──
    daily_horizon: int = 1
    weekly_horizon: int = 7
    monthly_horizon: int = 30

    # ── Model Versioning ──
    max_model_versions: int = 10

    # ── API ──
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # ── Paths ──
    artifacts_dir: Path = ARTIFACTS_DIR
    logs_dir: Path = LOGS_DIR


# Singleton
_settings = None

def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
