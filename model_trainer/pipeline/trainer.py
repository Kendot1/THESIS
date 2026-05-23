"""
Main training orchestrator — Two-Stage Residual Hybrid Architecture.

Pipeline:
  1. Fetch → Preprocess → Feature Engineering
  2. Train LightGBM on absolute prices (standalone baseline)
  3. Train LSTM (Stage 1: base temporal model)
  4. Compute LSTM residuals → Train LightGBM residual corrector (Stage 2)
  5. Evaluate hybrid ensemble with adaptive shrinkage
  6. Version & store
"""

import pandas as pd
import numpy as np
from datetime import datetime, timezone
from typing import Dict, Optional

from config.settings import get_settings
from data.fetcher import DataFetcher
from data.preprocessor import DataPreprocessor
from features.temporal import TemporalFeatures
from features.lag_features import LagFeatures
from features.categorical import CategoricalEncoder
from features.news_sentiment import NewsSentimentFeatures
from models.lightgbm_model import LightGBMModel
from models.lstm_model import LSTMModel
from models.ensemble import EnsembleModel
from models.model_store import ModelStore
from pipeline.evaluator import ModelEvaluator
from pipeline.drift_detector import DriftDetector
from utils.logger import get_logger

log = get_logger(__name__)


class TrainingPipeline:
    """
    Two-Stage Residual Hybrid training pipeline.

    Architecture:
      Stage 1: LSTM learns temporal patterns → produces base predictions
      Stage 2: LightGBM learns to correct LSTM residuals → error correction
      Final:   predicted_price = lstm_base + lgbm_residual_correction

    Modes:
      - full        -- Train from scratch on all available data
      - incremental -- Fetch only new data, fine-tune existing models
    """

    # Features used by LightGBM (excludes raw text / date columns)
    EXCLUDE_COLS = [
        "id", "report_date", "source_pdf", "created_at",
        "product_name", "product_category", "product_variant",
        "origin", "unit",
    ]

    def __init__(self):
        self._cfg = get_settings()
        self._fetcher = DataFetcher()
        self._preprocessor = DataPreprocessor()
        self._temporal = TemporalFeatures()
        self._lags = LagFeatures()
        self._encoder = CategoricalEncoder()
        self._sentiment = NewsSentimentFeatures()
        self._lgbm = LightGBMModel()
        self._lstm = LSTMModel()
        self._ensemble = EnsembleModel()
        self._store = ModelStore()
        self._evaluator = ModelEvaluator()
        self._drift = DriftDetector()

    # ──────────────────────────────────────────────
    # Public entry points
    # ──────────────────────────────────────────────
    def run_full_training(self) -> Dict[str, float]:
        """Complete training from scratch."""
        log.info("=== FULL TRAINING PIPELINE ===")

        # 1. Fetch all data
        raw_df = self._fetcher.fetch_all()
        if raw_df.empty:
            log.error("No data fetched -- aborting.")
            return {}

        return self._train(raw_df, incremental=False)

    def run_incremental_training(self, since_date: Optional[str] = None) -> Dict[str, float]:
        """
        Incremental training with new data only.
        Falls back to full training if no existing model is found.
        """
        log.info("=== INCREMENTAL TRAINING PIPELINE ===")

        # Determine the date to fetch from
        if since_date is None:
            latest = self._store.get_latest_metrics()
            if latest is None:
                log.info("No previous model found -- switching to full training.")
                return self.run_full_training()
            # Fetch all data (we need history for lag features)
            # but only retrain on recent data
            raw_df = self._fetcher.fetch_all()
        else:
            raw_df = self._fetcher.fetch_all()

        if raw_df.empty:
            log.error("No data fetched -- aborting.")
            return {}

        return self._train(raw_df, incremental=True)

    def run_daily(self) -> Dict[str, float]:
        """
        Daily pipeline run.
        Checks for drift first, then decides between incremental or full retrain.
        """
        log.info("=== DAILY PIPELINE RUN ===")

        # Fetch all data for drift check
        raw_df = self._fetcher.fetch_all()
        if raw_df.empty:
            log.warning("No data available -- skipping daily run.")
            return {}

        # Preprocess for drift check
        clean_df = self._preprocessor.validate(raw_df)

        # Check for drift
        needs_full_retrain = self._drift.check_drift(clean_df)

        if needs_full_retrain:
            log.warning("Drift detected -- performing FULL retrain.")
            return self._train(raw_df, incremental=False)
        else:
            log.info("No significant drift -- performing incremental update.")
            return self._train(raw_df, incremental=True)

    # ──────────────────────────────────────────────
    # Core training logic
    # ──────────────────────────────────────────────
    def _train(self, raw_df: pd.DataFrame, incremental: bool) -> Dict[str, float]:
        """
        Internal training method — Two-Stage Residual Hybrid.

        Stage 1: Train LightGBM on absolute prices (proven baseline)
        Stage 2: Train LSTM on temporal sequences (base temporal model)
        Stage 3: Compute LSTM residuals → Train LightGBM residual corrector
        Stage 4: Evaluate hybrid (LSTM base + LightGBM correction)
        """

        # ── Step 1: Preprocess ──
        log.info("Step 1/8 -- Preprocessing ...")
        clean_df = self._preprocessor.validate(raw_df)

        # ── Step 2: Feature engineering ──
        log.info("Step 2/8 -- Feature engineering ...")
        featured_df = self._build_features(clean_df, fit=not incremental)

        # ── Step 3: Prepare datasets ──
        log.info("Step 3/8 -- Splitting data ...")
        train_df, val_df = self._preprocessor.time_split(featured_df, test_size=0.15)

        # Drop rows with NaN from lag features (first rows of each product)
        train_df = train_df.dropna().reset_index(drop=True)
        val_df = val_df.dropna().reset_index(drop=True)

        if train_df.empty:
            log.error("Training set is empty after processing -- aborting.")
            return {}

        log.info(
            f"Data split -- train: {len(train_df):,} rows, "
            f"val: {len(val_df):,} rows ({len(val_df)/(len(train_df)+len(val_df))*100:.1f}%)"
        )

        feature_cols = self._get_feature_columns(train_df)

        # ── Step 4: Train LightGBM on absolute prices (baseline) ──
        log.info("Step 4/8 -- Training LightGBM (absolute prices) ...")
        X_train = train_df[feature_cols]
        y_train = train_df["price_index"]
        X_val = val_df[feature_cols] if not val_df.empty else None
        y_val = val_df["price_index"] if not val_df.empty else None

        lgbm_metrics = self._lgbm.train(
            X_train, y_train, X_val, y_val,
            incremental=incremental,
        )

        # ── Step 5: Train LSTM (Stage 1 — Base Temporal Model) ──
        log.info("Step 5/8 -- Training LSTM (Stage 1: base temporal model) ...")
        lstm_metrics = self._train_lstm(train_df, val_df, incremental)

        # ── Step 6: Evaluate hybrid ensemble ──
        log.info("Step 6/8 -- Evaluating blended hybrid ensemble ...")
        ensemble_metrics = {}
        if not val_df.empty and lstm_metrics:
            ensemble_metrics = self._evaluate_hybrid(train_df, val_df, feature_cols)

        # ── Step 7: Version & store ──
        log.info("Step 7/8 -- Saving model version ...")
        combined_metrics = {
            "lgbm": lgbm_metrics,
            "lstm": lstm_metrics,
            "ensemble": ensemble_metrics,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data_rows": len(clean_df),
            "mode": "incremental" if incremental else "full",
        }

        self._store.create_version(
            metrics=combined_metrics,
            notes=f"{'Incremental' if incremental else 'Full'} training on {len(clean_df)} rows",
        )

        # Store reference distribution for future drift detection
        self._drift.save_reference(clean_df)

        # ── Step 8: Generate visual dashboards ──
        log.info("Step 8/8 -- Generating visual training dashboards ...")
        try:
            self._generate_plots(train_df, val_df, feature_cols, combined_metrics)
        except Exception as e:
            log.error(f"Visual dashboard generation failed: {e}")

        # ── Summary ──
        self._log_training_summary(combined_metrics)

        log.info("=== TRAINING COMPLETE ===")
        return combined_metrics

    def _generate_plots(self, train_df: pd.DataFrame, val_df: pd.DataFrame, feature_cols: list, combined_metrics: dict = None):
        """Generate all 8 thesis-quality visual dashboards."""
        log.info("Generating training and evaluation visual dashboards ...")
        from utils.plotting import (
            plot_lstm_loss, plot_learning_rate, plot_feature_importance,
            plot_predictions_vs_actuals, plot_residual_distribution,
            plot_per_category_metrics, plot_model_comparison,
            plot_scatter_predicted_vs_actual,
        )

        artifacts = self._cfg.artifacts_dir
        history_path = artifacts / "lstm_history.json"

        # 1. LSTM Training vs Validation Loss Curve
        try:
            if history_path.exists():
                plot_lstm_loss(history_path, artifacts / "loss_curves.png")
                log.info(f"Generated plot 1/8: Loss Curves -> {artifacts / 'loss_curves.png'}")
        except Exception as e:
            log.error(f"Plot 1 (loss curves) failed: {e}")

        # 2. Learning Rate Schedule
        try:
            if history_path.exists():
                plot_learning_rate(history_path, artifacts / "lr_schedule.png")
                log.info(f"Generated plot 2/8: LR Schedule -> {artifacts / 'lr_schedule.png'}")
        except Exception as e:
            log.error(f"Plot 2 (LR schedule) failed: {e}")

        # 3. Feature Importance
        try:
            importance = self._lgbm.feature_importance()
            if importance:
                plot_feature_importance(importance, artifacts / "feature_importance.png", top_n=15)
                log.info(f"Generated plot 3/8: Feature Importance -> {artifacts / 'feature_importance.png'}")
        except Exception as e:
            log.error(f"Plot 3 (feature importance) failed: {e}")

        # 7. Model Comparison (does not need validation inference)
        try:
            if combined_metrics:
                plot_model_comparison(combined_metrics, artifacts / "model_comparison.png")
                log.info(f"Generated plot 7/8: Model Comparison -> {artifacts / 'model_comparison.png'}")
        except Exception as e:
            log.error(f"Plot 7 (model comparison) failed: {e}")

        # Plots 4, 5, 6, 8 require validation inference
        try:
            if not val_df.empty:
                seq_len = self._lstm._seq_len
                train_tail = train_df.groupby(["product_category", "product_name", "product_variant", "origin"]).tail(seq_len - 1)
                val_full_df = pd.concat([train_tail, val_df]).sort_values(["product_category", "product_name", "product_variant", "origin", "report_date"]).reset_index(drop=True)

                X_val_seq, y_val_seq, val_indices, val_products, val_anchors = \
                    self._lstm.build_sequences_inference(val_full_df)

                if len(X_val_seq) > 0:
                    # Get predictions from all models
                    lstm_preds = self._lstm.predict(X_val_seq, products=val_products, current_prices=val_anchors)
                    X_val_lgbm = val_full_df.iloc[val_indices][feature_cols].copy()
                    lgbm_preds = self._lgbm.predict(X_val_lgbm)

                    stats = self._ensemble.get_residual_stats()
                    lstm_w = stats.get("lstm_weight", 0.5) if stats else 0.5
                    lgbm_w = stats.get("lgbm_weight", 0.5) if stats else 0.5
                    hybrid_preds = (lstm_preds * lstm_w) + (lgbm_preds * lgbm_w)

                    _, lower_bound, upper_bound = self._lgbm.predict_with_intervals(X_val_lgbm)
                    hybrid_error = hybrid_preds - lgbm_preds
                    hybrid_lower = lower_bound + hybrid_error
                    hybrid_upper = upper_bound + hybrid_error

                    y_val_actual = val_full_df["price_index"].values[val_indices]

                    # 4. Predicted vs Actual Time Series (representative product)
                    try:
                        product_counts = {}
                        for p in val_products:
                            product_counts[p] = product_counts.get(p, 0) + 1

                        if product_counts:
                            rep_product = max(product_counts, key=product_counts.get)
                            rep_indices = [i for i, p in enumerate(val_products) if p == rep_product]

                            if len(rep_indices) > 1:
                                y_true_rep = y_val_actual[rep_indices]
                                hybrid_rep = hybrid_preds[rep_indices]
                                lstm_rep = lstm_preds[rep_indices]
                                lgbm_rep = lgbm_preds[rep_indices]
                                lower_rep = hybrid_lower[rep_indices]
                                upper_rep = hybrid_upper[rep_indices]

                                clean_prod_name = rep_product.split("||")[1] if "||" in rep_product else rep_product

                                plot_predictions_vs_actuals(
                                    y_true=y_true_rep, y_pred=hybrid_rep,
                                    product_name=clean_prod_name, save_path=artifacts / "evaluation_results.png",
                                    lstm_pred=lstm_rep, lgbm_pred=lgbm_rep,
                                    lower_bound=lower_rep, upper_bound=upper_rep
                                )
                                log.info(f"Generated plot 4/8: Predicted vs Actual ({clean_prod_name}) -> {artifacts / 'evaluation_results.png'}")
                    except Exception as e:
                        log.error(f"Plot 4 (predicted vs actual) failed: {e}")

                    # 5. Residual Distribution
                    try:
                        plot_residual_distribution(
                            y_val_actual, hybrid_preds,
                            save_path=artifacts / "residual_distribution.png",
                            model_name="Hybrid Ensemble"
                        )
                        log.info(f"Generated plot 5/8: Residual Distribution -> {artifacts / 'residual_distribution.png'}")
                    except Exception as e:
                        log.error(f"Plot 5 (residual distribution) failed: {e}")

                    # 6. Per-Category Metrics
                    try:
                        eval_df = val_full_df.iloc[val_indices].copy()
                        eval_df["predicted_price"] = hybrid_preds
                        from pipeline.evaluator import ModelEvaluator
                        evaluator = ModelEvaluator()
                        cat_metrics = evaluator.evaluate_per_category(eval_df).to_dict("records")
                        if cat_metrics:
                            plot_per_category_metrics(cat_metrics, artifacts / "per_category_metrics.png")
                            log.info(f"Generated plot 6/8: Per-Category Metrics -> {artifacts / 'per_category_metrics.png'}")
                    except Exception as e:
                        log.error(f"Plot 6 (per-category metrics) failed: {e}")

                    # 8. Scatter Plot (Predicted vs Actual)
                    try:
                        cat_labels = val_full_df["product_category"].values[val_indices]
                        plot_scatter_predicted_vs_actual(
                            y_val_actual, hybrid_preds,
                            save_path=artifacts / "scatter_predicted_vs_actual.png",
                            model_name="Hybrid Ensemble",
                            category_labels=np.array(cat_labels)
                        )
                        log.info(f"Generated plot 8/8: Scatter Plot -> {artifacts / 'scatter_predicted_vs_actual.png'}")
                    except Exception as e:
                        log.error(f"Plot 8 (scatter plot) failed: {e}")

        except Exception as e:
            log.error(f"Validation inference for plots failed: {e}")

    # ──────────────────────────────────────────────
    def _build_features(self, df: pd.DataFrame, fit: bool = True) -> pd.DataFrame:
        """Apply all feature engineering transformations."""
        df = self._temporal.transform(df)
        df = self._lags.transform(df)

        if fit:
            df = self._encoder.fit_transform(df)
        else:
            df = self._encoder.transform(df)

        # News sentiment is strictly excluded from forecasting to avoid leakage.
        # It is handled independently by the reasoning pipeline post-prediction.

        return df

    def _get_feature_columns(self, df: pd.DataFrame) -> list:
        """Get columns suitable for LightGBM training."""
        exclude = set(self.EXCLUDE_COLS + ["price_index"])
        features = [
            c for c in df.columns
            if c not in exclude
            and df[c].dtype in ["int64", "float64", "int32", "float32"]
            and "sentiment" not in c
            and "news" not in c
            and "supply_shock" not in c
        ]

        # Explicit validation safeguards as requested
        assert not any("sentiment" in f for f in features), "CRITICAL LEAKAGE: Sentiment found in features"
        assert not any("news" in f for f in features), "CRITICAL LEAKAGE: News found in features"
        
        log.info(f"LightGBM using {len(features)} historical data features. No reasoning features included.")
        return features

    def _train_lstm(self, train_df: pd.DataFrame, val_df: pd.DataFrame, incremental: bool) -> Dict:
        """Stage 1: Build multi-feature sequences and train LSTM."""
        try:
            X_train_seq, y_train_seq = self._lstm.build_sequences(train_df)
            if len(X_train_seq) == 0:
                log.warning("Not enough training data for LSTM sequences.")
                return {}

            # Build validation sequences using fitted scalers
            X_val_seq, y_val_seq, val_indices, val_products, val_anchors = np.array([]), np.array([]), [], [], np.array([])
            if not val_df.empty:
                # Need lag history from train_df to build sequences that predict into val_df
                seq_len = self._lstm._seq_len
                train_tail = train_df.groupby(["product_category", "product_name", "product_variant", "origin"]).tail(seq_len - 1)
                val_full_df = pd.concat([train_tail, val_df]).sort_values(["product_category", "product_name", "product_variant", "origin", "report_date"]).reset_index(drop=True)
                
                X_val_seq, y_val_seq, val_indices, val_products, val_anchors = self._lstm.build_sequences_inference(val_full_df)

            log.info(
                f"LSTM sequences -- train: {len(X_train_seq)}, val: {len(X_val_seq)}, "
                f"features: {X_train_seq.shape[2] if len(X_train_seq) > 0 else 0}"
            )

            return self._lstm.train(
                X_train_seq, y_train_seq,
                X_val_seq if len(X_val_seq) > 0 else None,
                y_val_seq if len(y_val_seq) > 0 else None,
                val_products=val_products if len(val_products) > 0 else None,
                val_anchors=val_anchors if len(val_anchors) > 0 else None,
                incremental=incremental,
            )
        except Exception as e:
            log.error(f"LSTM training failed: {e}")
            import traceback
            traceback.print_exc()
            return {}

    def _train_lgbm_residual(
        self,
        train_df: pd.DataFrame,
        val_df: pd.DataFrame,
        feature_cols: list,
        incremental: bool,
    ) -> Dict:
        """
        Stage 2: Train LightGBM on LSTM residuals.

        Flow:
          1. Get LSTM 1-step predictions on the training set
          2. Compute residuals: actual_price - lstm_prediction
          3. Add lstm_prediction as an extra feature
          4. Train LightGBM to predict the residuals
        """
        try:
            # Get LSTM predictions on training data using inference mode
            X_train_seq, y_train_seq, train_indices, train_products, train_anchors = \
                self._lstm.build_sequences_inference(train_df)

            if len(X_train_seq) == 0:
                log.warning("No LSTM sequences for residual training -- falling back to direct LightGBM.")
                return self._train_lgbm_direct(train_df, val_df, feature_cols, incremental)

            # Get LSTM 1-step predictions (absolute prices)
            lstm_train_preds = self._lstm.predict(
                X_train_seq, products=train_products, current_prices=train_anchors
            )

            # Get actual prices at the aligned indices
            y_train_actual = train_df["price_index"].values[train_indices]

            # Compute residuals: what LSTM got wrong
            train_residuals = y_train_actual - lstm_train_preds

            log.info(
                f"Residual stats (train) -- mean: {np.mean(train_residuals):.4f}, "
                f"std: {np.std(train_residuals):.4f}, "
                f"median: {np.median(train_residuals):.4f}"
            )

            # Build feature matrix for LightGBM (tabular features + lstm_prediction)
            X_train_lgbm = train_df.iloc[train_indices][feature_cols].copy()
            X_train_lgbm["lstm_prediction"] = lstm_train_preds

            # Repeat for validation
            X_val_lgbm = None
            val_residuals = None

            if not val_df.empty:
                seq_len = self._lstm._seq_len
                train_tail = train_df.groupby(["product_category", "product_name", "product_variant", "origin"]).tail(seq_len - 1)
                val_full_df = pd.concat([train_tail, val_df]).sort_values(["product_category", "product_name", "product_variant", "origin", "report_date"]).reset_index(drop=True)

                X_val_seq, y_val_seq, val_indices, val_products, val_anchors = \
                    self._lstm.build_sequences_inference(val_full_df)

                if len(X_val_seq) > 0:
                    lstm_val_preds = self._lstm.predict(
                        X_val_seq, products=val_products, current_prices=val_anchors
                    )
                    y_val_actual = val_full_df["price_index"].values[val_indices]
                    val_residuals = y_val_actual - lstm_val_preds

                    X_val_lgbm = val_full_df.iloc[val_indices][feature_cols].copy()
                    X_val_lgbm["lstm_prediction"] = lstm_val_preds

                    log.info(
                        f"Residual stats (val) -- mean: {np.mean(val_residuals):.4f}, "
                        f"std: {np.std(val_residuals):.4f}"
                    )

            # Train LightGBM on residuals
            residual_metrics = self._lgbm.train_residual(
                X_train_lgbm, train_residuals,
                X_val_lgbm, val_residuals,
            )

            return residual_metrics

        except Exception as e:
            log.error(f"Residual training failed: {e}")
            import traceback
            traceback.print_exc()
            # Fallback: train LightGBM directly on prices
            log.warning("Falling back to direct LightGBM price training.")
            return self._train_lgbm_direct(train_df, val_df, feature_cols, incremental)

    def _train_lgbm_direct(
        self,
        train_df: pd.DataFrame,
        val_df: pd.DataFrame,
        feature_cols: list,
        incremental: bool,
    ) -> Dict:
        """Fallback: train LightGBM directly on prices (non-hybrid mode)."""
        X_train = train_df[feature_cols]
        y_train = train_df["price_index"]
        X_val = val_df[feature_cols] if not val_df.empty else None
        y_val = val_df["price_index"] if not val_df.empty else None

        return self._lgbm.train(
            X_train, y_train, X_val, y_val,
            incremental=incremental,
        )

    def _evaluate_hybrid(self, train_df: pd.DataFrame, val_df: pd.DataFrame, feature_cols: list) -> Dict:
        """Evaluate the full hybrid ensemble on validation data."""
        try:
            # Get LSTM predictions on validation
            seq_len = self._lstm._seq_len
            train_tail = train_df.groupby(["product_category", "product_name", "product_variant", "origin"]).tail(seq_len - 1)
            val_full_df = pd.concat([train_tail, val_df]).sort_values(["product_category", "product_name", "product_variant", "origin", "report_date"]).reset_index(drop=True)

            X_val_seq, y_val_seq, val_indices, val_products, val_anchors = \
                self._lstm.build_sequences_inference(val_full_df)

            if len(X_val_seq) == 0:
                log.warning("No LSTM sequences for hybrid evaluation.")
                return {}

            lstm_preds = self._lstm.predict(
                X_val_seq, products=val_products, current_prices=val_anchors
            )

            # Get LightGBM Base predictions
            X_val_lgbm = val_full_df.iloc[val_indices][feature_cols].copy()
            lgbm_preds = self._lgbm.predict(X_val_lgbm)

            # Get actual prices
            y_val_actual = val_full_df["price_index"].values[val_indices]

            # Evaluate blended hybrid
            return self._ensemble.train_blended_ensemble(
                lstm_preds, lgbm_preds, y_val_actual
            )

        except Exception as e:
            log.error(f"Hybrid evaluation failed: {e}")
            import traceback
            traceback.print_exc()
            return {}

    def _log_training_summary(self, metrics: Dict):
        """Log a clean summary of all model performances."""
        log.info("=" * 60)
        log.info("TRAINING SUMMARY")
        log.info("=" * 60)

        if metrics.get("lgbm"):
            m = metrics["lgbm"]
            log.info(f"  LightGBM (standalone): RMSE={m.get('rmse', 'N/A'):.4f}  MAE={m.get('mae', 'N/A'):.4f}  MAPE={m.get('mape', 'N/A'):.2f}%")
        
        if metrics.get("lstm"):
            m = metrics["lstm"]
            log.info(f"  LSTM (base):           RMSE={m.get('rmse', 'N/A'):.4f}  MAE={m.get('mae', 'N/A'):.4f}  MAPE={m.get('mape', 'N/A'):.2f}%")
        
        if metrics.get("lgbm_residual"):
            m = metrics["lgbm_residual"]
            log.info(f"  LightGBM (residual):   RMSE={m.get('rmse', 'N/A'):.4f}  MAE={m.get('mae', 'N/A'):.4f}")

        if metrics.get("ensemble"):
            m = metrics["ensemble"]
            log.info(f"  HYBRID ENSEMBLE:       RMSE={m.get('rmse', 'N/A'):.4f}  MAE={m.get('mae', 'N/A'):.4f}  MAPE={m.get('mape', 'N/A'):.2f}%")
        
        log.info("=" * 60)
