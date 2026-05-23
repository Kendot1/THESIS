"""
FOODCAST Model Trainer -- CLI Entry Point.

Runs as a pure ML pipeline (no web server needed).
Continuous training is automated via GitHub Actions.

Usage:
  python main.py train --mode full
  python main.py train --mode incremental
  python main.py train --mode daily
  python main.py predict --horizon monthly
  python main.py schedule
  python main.py evaluate
"""

import sys
import argparse

# Add project root to path
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))

from utils.logger import get_logger

log = get_logger("main")


def cmd_train(args):
    """Run training pipeline."""
    from pipeline.trainer import TrainingPipeline

    pipeline = TrainingPipeline()

    if args.mode == "full":
        metrics = pipeline.run_full_training()
    elif args.mode == "incremental":
        metrics = pipeline.run_incremental_training()
    elif args.mode == "daily":
        metrics = pipeline.run_daily()
    else:
        log.error(f"Unknown mode: {args.mode}")
        sys.exit(1)

    log.info(f"Training complete. Metrics: {metrics}")





def cmd_schedule(args):
    """Start the daily training scheduler."""
    from pipeline.scheduler import PipelineScheduler

    scheduler = PipelineScheduler(run_time=args.time)
    log.info(f"Starting scheduler -- daily training at {args.time} UTC")
    scheduler.start()


def cmd_evaluate(args):
    """Evaluate current model on test data."""
    from data.fetcher import DataFetcher
    from data.preprocessor import DataPreprocessor
    from features.temporal import TemporalFeatures
    from features.lag_features import LagFeatures
    from features.categorical import CategoricalEncoder
    from models.lightgbm_model import LightGBMModel
    from pipeline.evaluator import ModelEvaluator

    log.info("Running model evaluation ...")

    fetcher = DataFetcher()
    preprocessor = DataPreprocessor()

    df = fetcher.fetch_all()
    df = preprocessor.validate(df)

    temporal = TemporalFeatures()
    lags = LagFeatures()
    encoder = CategoricalEncoder()

    df = temporal.transform(df)
    df = lags.transform(df)
    df = encoder.transform(df)
    df = df.dropna()

    from models.lstm_model import LSTMModel
    from models.ensemble import EnsembleModel
    import pandas as pd

    train_df, test_df = preprocessor.time_split(df, test_size=0.15)

    if test_df.empty:
        log.error("No test data available.")
        return

    feature_cols = [
        c for c in test_df.columns
        if c not in [
            "id", "report_date", "source_pdf", "created_at",
            "product_name", "product_category", "product_variant",
            "origin", "unit", "price_index",
        ]
        and test_df[c].dtype in ["int64", "float64", "int32", "float32"]
    ]

    lgbm = LightGBMModel()
    lgbm.load()
    
    lstm = LSTMModel()
    lstm.load()
    
    ensemble = EnsembleModel()
    ensemble.load()

    # Build sequences for LSTM inference
    seq_len = lstm._seq_len
    train_tail = train_df.groupby(["product_category", "product_name", "product_variant", "origin"]).tail(seq_len - 1)
    test_full_df = pd.concat([train_tail, test_df]).sort_values(["product_category", "product_name", "product_variant", "origin", "report_date"]).reset_index(drop=True)

    X_test_seq, _, test_indices, test_products, test_anchors = lstm.build_sequences_inference(test_full_df)

    if len(X_test_seq) == 0:
        log.error("Failed to build sequences for evaluation.")
        return

    # Get predictions
    lstm_preds = lstm.predict(X_test_seq, products=test_products, current_prices=test_anchors)
    X_test_lgbm = test_full_df.iloc[test_indices][feature_cols].copy()
    lgbm_preds = lgbm.predict(X_test_lgbm)

    # Blend
    stats = ensemble.get_residual_stats()
    lstm_w = stats.get("lstm_weight", 0.5) if stats else 0.5
    lgbm_w = stats.get("lgbm_weight", 0.5) if stats else 0.5
    hybrid_preds = (lstm_preds * lstm_w) + (lgbm_preds * lgbm_w)

    eval_df = test_full_df.iloc[test_indices].copy()
    eval_df["predicted_price"] = hybrid_preds

    evaluator = ModelEvaluator()
    report = evaluator.generate_report(eval_df)

    log.info("=== EVALUATION REPORT (HYBRID ENSEMBLE) ===")
    log.info(f"Overall: {report['overall']}")
    log.info(f"Products evaluated: {report['n_products']}")
    log.info(f"Total samples: {report['n_total_samples']}")

    # Generate and save plots locally
    try:
        from utils.plotter import generate_evaluation_plots
        import os
        
        plot_dir = os.path.join(os.path.dirname(__file__), "plots")
        generate_evaluation_plots(eval_df, report, output_dir=plot_dir)
    except ImportError as e:
        log.warning(f"Could not generate plots. Ensure matplotlib is installed: {e}")





def cmd_predict(args):
    """Batch-generate predictions for all products and write to Supabase."""
    from pipeline.prediction_writer import PredictionWriter

    writer = PredictionWriter()
    stats = writer.run(horizon=args.horizon)
    log.info(f"Prediction batch complete. Stats: {stats}")


def main():
    parser = argparse.ArgumentParser(
        prog="foodcast-trainer",
        description="FOODCAST -- AI Food Price Forecasting Model Trainer",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # train
    train_parser = subparsers.add_parser("train", help="Train the forecasting models")
    train_parser.add_argument(
        "--mode",
        choices=["full", "incremental", "daily"],
        default="incremental",
        help="Training mode (default: incremental)",
    )
    train_parser.set_defaults(func=cmd_train)



    # schedule
    sched_parser = subparsers.add_parser("schedule", help="Start the daily scheduler")
    sched_parser.add_argument(
        "--time", default="02:00", help="Daily training time in HH:MM UTC (default: 02:00)"
    )
    sched_parser.set_defaults(func=cmd_schedule)

    # evaluate
    eval_parser = subparsers.add_parser("evaluate", help="Evaluate current model")
    eval_parser.set_defaults(func=cmd_evaluate)



    # predict (batch → Supabase)
    predict_parser = subparsers.add_parser(
        "predict", help="Batch-generate predictions for all products and write to Supabase"
    )
    predict_parser.add_argument(
        "--horizon",
        choices=["daily", "weekly", "monthly"],
        default="monthly",
        help="Forecast horizon (default: monthly)",
    )
    predict_parser.set_defaults(func=cmd_predict)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()

