"""
FOODCAST Model Trainer -- CLI Entry Point.

Usage:
  python main.py train --mode full
  python main.py train --mode incremental
  python main.py serve
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


def cmd_serve(args):
    """Start the FastAPI server."""
    import uvicorn
    from config.settings import get_settings

    cfg = get_settings()
    log.info(f"Starting API server on {cfg.api_host}:{cfg.api_port}")
    uvicorn.run(
        "api.main:app",
        host=cfg.api_host,
        port=cfg.api_port,
        reload=args.reload,
    )


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

    _, test_df = preprocessor.time_split(df, test_days=30)

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
    test_df = test_df.copy()
    test_df["predicted_price"] = lgbm.predict(test_df[feature_cols])

    evaluator = ModelEvaluator()
    report = evaluator.generate_report(test_df)

    log.info("=== EVALUATION REPORT ===")
    log.info(f"Overall: {report['overall']}")
    log.info(f"Products evaluated: {report['n_products']}")
    log.info(f"Total samples: {report['n_total_samples']}")





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

    # serve
    serve_parser = subparsers.add_parser("serve", help="Start the API server")
    serve_parser.add_argument(
        "--reload", action="store_true", help="Enable hot reload (development)"
    )
    serve_parser.set_defaults(func=cmd_serve)

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

