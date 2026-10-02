"""
Central configuration for the FOODCAST model trainer.
All hyperparameters, paths, and environment variables are managed here.
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List
from dotenv import load_dotenv
import truststore

truststore.inject_into_ssl()

load_dotenv(override=False)

# ──────────────────────────────────────────────
# Base paths
# ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS_DIR = Path(os.getenv('FOODCAST_ARTIFACTS_DIR', str(PROJECT_ROOT / 'artifacts_v2')))
LOGS_DIR = Path(os.getenv('FOODCAST_LOGS_DIR', str(PROJECT_ROOT / 'logs')))


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

    # ── Cloudflare R2 ──
    cf_r2_account_id: str = os.getenv("CLOUDFLARE_R2_ACCOUNT_ID", "")
    cf_r2_access_key_id: str = os.getenv("CLOUDFLARE_R2_ACCESS_KEY_ID", "")
    cf_r2_secret_access_key: str = os.getenv("CLOUDFLARE_R2_SECRET_ACCESS_KEY", "")
    cf_r2_bucket_name: str = os.getenv("CLOUDFLARE_R2_BUCKET_NAME", "")
    cf_r2_public_url: str = os.getenv("CLOUDFLARE_R2_PUBLIC_URL", "")

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
    max_fill_days: int = 7
    random_seed: int = field(
        default_factory=lambda: int(os.getenv("FOODCAST_RANDOM_SEED", "42")))
    evaluation_stride: int = 30
    training_sequence_stride: int = field(
        default_factory=lambda: int(os.getenv("FOODCAST_TRAINING_SEQUENCE_STRIDE", "1")))
    lgbm_target_mode: str = field(
        default_factory=lambda: os.getenv("FOODCAST_LGBM_TARGET_MODE", "relative").lower())
    validation_size: float = 0.15
    test_size: float = 0.15

    # ── Categories from the scraper schema ──
    product_categories: List[str] = field(default_factory=lambda: [
        "Rice", "Corn", "Poultry", "Livestock",
        "Vegetables", "Fruits", "Fish", "Oils", "Sugar"
    ])

    # ── LightGBM Hyperparameters ──
    lgbm_params: dict = field(default_factory=lambda: {
        "objective": "regression",
        "seed": 42,
        "deterministic": True,
        "force_col_wise": True,
        "num_threads": 4,
        "metric": ["rmse", "mae"],
        "boosting_type": "gbdt",
        "num_leaves": 127,               # Increased for richer feature space
        "learning_rate": 0.005,          # Slower for more precise convergence
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 5,
        "extra_trees": True,
        "min_child_samples": 20,
        "min_data_in_bin": 5,            # Better handling of sparse categorical features
        "lambda_l1": 0.05,
        "lambda_l2": 0.2,
        "verbose": -1,
        "n_estimators": 3000,            # More rounds for the lower learning rate
        "early_stopping_rounds": 150,    # More patience for the lower learning rate
    })

    # ── LSTM Hyperparameters ──
    lstm_hidden_size: int = 128
    lstm_num_layers: int = 2
    lstm_dropout: float = 0.2            # Increased slightly to prevent overfitting with custom loss
    lstm_learning_rate: float = 0.001
    lstm_epochs: int = field(
        default_factory=lambda: int(os.getenv("FOODCAST_LSTM_EPOCHS", "80")))
    lstm_batch_size: int = 256
    lstm_patience: int = field(
        default_factory=lambda: int(os.getenv("FOODCAST_LSTM_PATIENCE", "12")))

    # ── Drift Detection ──
    psi_threshold: float = 0.2  # Population Stability Index threshold
    performance_drop_threshold: float = 0.15  # 15% MAPE increase triggers retrain

    # ── Forecast Horizons ──
    daily_horizon: int = 1
    weekly_horizon: int = 7
    monthly_horizon: int = 30

    # ── Model Versioning ──
    max_model_versions: int = 10

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
