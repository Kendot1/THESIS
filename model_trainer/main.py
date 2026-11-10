"""FOODCAST model training and forecast CLI."""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))


def _read_data(path, through_date=None):
    if through_date is not None:
        from data.fetcher import iso_report_date
        through_date = iso_report_date(through_date)
    path = Path(path)
    if path.suffix.lower() == ".csv":
        frame = pd.read_csv(path)
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = data.get("rows", data.get("data", data))
        frame = pd.DataFrame(data)
    if through_date is not None:
        dates = pd.to_datetime(frame.report_date, errors="raise").dt.normalize()
        frame = frame.loc[dates <= pd.Timestamp(through_date)].copy()
    return frame


def cmd_train(args):
    from pipeline.trainer import TrainingPipeline
    from data.fetcher import DataFetcher
    source_as_of = bool(getattr(args, "report_date_as_of", False))
    residual_role = getattr(args, "lgbm_role", "direct") != "direct"
    if residual_role:
        if args.resume or args.recalibrate or args.mode != "full":
            raise ValueError("Residual architecture selection requires a new full candidate")
        if source_as_of:
            raise ValueError("Residual training requires a separate source-as-of OOF plan")
        if not args.no_activate:
            raise ValueError("Experimental residual training requires --no-activate")
    if args.through and (args.resume or args.recalibrate):
        raise ValueError("--through is for new training runs; resume/recalibrate must retain their original data scope")
    if source_as_of:
        if args.resume or args.recalibrate:
            raise ValueError("--report-date-as-of applies only to a new full training run")
        if args.mode != "full":
            raise ValueError("--report-date-as-of requires --mode full")
        if not args.data and not args.through:
            raise ValueError("--report-date-as-of requires an explicit --data snapshot or --through bound")
    raw = None
    if args.data:
        raw = _read_data(args.data, args.through)
    elif args.through:
        raw = DataFetcher().fetch_all(through_date=args.through)
    pipeline = TrainingPipeline(lgbm_role=getattr(args, "lgbm_role", "direct"))
    if source_as_of:
        metrics = pipeline.run_full_training(
            raw, activate=not args.no_activate, source_as_of=True)
    elif args.recalibrate:
        metrics = pipeline.recalibrate_candidate(
            args.recalibrate, activate=not args.no_activate)
    elif args.resume:
        if raw is None:
            raise ValueError("--resume requires --data for reproducible recovery")
        metrics = pipeline.resume_candidate(args.resume, raw, activate=not args.no_activate)
    elif args.mode == "full":
        metrics = pipeline.run_full_training(raw, activate=not args.no_activate)
    elif args.mode == "incremental":
        metrics = pipeline.run_incremental_training(raw_df=raw, activate=not args.no_activate)
    else:
        if raw is not None:
            metrics = pipeline.run_full_training(raw, activate=not args.no_activate)
        else:
            metrics = pipeline.run_daily()
    result_json = json.dumps(metrics, indent=2)
    if getattr(args, "result_json", None):
        output = Path(args.result_json)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(result_json + "\n", encoding="utf-8")
    print(result_json)


def cmd_evaluate(_args):
    from models.model_store import ModelStore
    from utils.metrics import compute_all_metrics
    store = ModelStore()
    path = store.active_path()
    metadata = json.loads((path / "metadata.json").read_text(encoding="utf-8"))
    forecasts = pd.read_csv(path / "test_forecasts.csv")
    test_metrics = {
        name: compute_all_metrics(forecasts.actual.to_numpy(), forecasts[name].to_numpy(),
                                  forecasts.anchor.to_numpy())
        for name in ['ensemble', 'lstm', 'lgbm', 'persistence', 'seasonal7', 'moving_average7']}
    improvements = {
        name: 100 * (test_metrics["persistence"][name]-test_metrics["ensemble"][name])
        / test_metrics["persistence"][name]
        for name in ["mae", "rmse", "mape"]
    }
    by_horizon = {}
    for horizon in [1, 7, 14, 21, 30]:
        rows = forecasts[forecasts.horizon == horizon]
        if rows.empty:
            continue
        by_horizon[str(horizon)] = {
            model: compute_all_metrics(rows.actual.to_numpy(), rows[model].to_numpy())
            for model in ["ensemble", "persistence"]
        }
    print(json.dumps({"run_id": path.name, "split": metadata["split"],
                      "test_metrics": test_metrics,
                      "improvement_over_persistence_percent": improvements,
                      "key_horizons": by_horizon,
                      "evaluation_scope": metadata["metrics"]["evaluation_scope"]},
                     indent=2))


def cmd_baseline_report(args):
    from evaluation.baseline_report import build_report, write_report
    from models.model_store import ModelStore

    store = ModelStore()
    bundle = store.active_path() if args.run_id is None else store.runs / args.run_id
    if not bundle.is_dir():
        raise FileNotFoundError(f"Model bundle is missing: {bundle}")
    report = build_report(bundle)
    paths = write_report(report, args.output_dir)
    print(json.dumps({"run_id": bundle.name, "paths": paths,
                      "summary": report["models"]["ensemble"]}, indent=2))


def cmd_predict(args):
    from pipeline.prediction_writer import PredictionWriter
    print(json.dumps(PredictionWriter().run(args.horizon, origin_date=getattr(args, "origin", None)), indent=2))


def cmd_export_quality(args):
    """Export measured capability for the exact active model, without database access."""
    from models.model_store import ModelStore
    from pipeline.prediction_writer import PredictionWriter
    path = ModelStore().active_path()
    forecasts = pd.read_csv(path/'validation_forecasts.csv', usecols=['series'])
    identities = {tuple(series.split('||')): series for series in forecasts.series.unique()}
    metrics = PredictionWriter._quality_metrics(path.name, identities)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({'modelRunId': path.name, 'metrics': metrics}, indent=2), encoding='utf-8')
    print(f'Exported measured model capability to {output}')


def cmd_check(_args):
    from pipeline.prediction_writer import PredictionWriter
    writer = PredictionWriter()
    writer.check_schema()
    print('Forecast publication schema and product identity are ready.')


def cmd_preview(args):
    """Generate local forecasts without resolving product IDs or publishing."""
    from data.fetcher import DataFetcher
    from data.preprocessor import DataPreprocessor, SERIES_KEY
    from features.builder import FeatureBuilder
    from models.registry import ModelRegistry
    from pipeline.prediction_writer import PUBLISHED_FORECAST_STEPS, PredictionWriter

    raw = (_read_data(args.data, args.through) if args.data else
           DataFetcher().fetch_all(through_date=args.through))
    from pipeline.rolling_periods import manila_today
    issue_origin = pd.Timestamp(manila_today())
    clean = DataPreprocessor().validate(raw)
    clean = clean.loc[pd.to_datetime(clean.report_date) <= issue_origin].copy()
    clean = PredictionWriter._extend_inputs_to_origin(clean, issue_origin, 7)
    registry = ModelRegistry.get().load_all()
    query = (args.product or "").casefold()
    results, failures = [], []
    selected = []
    for key, series in clean.groupby(SERIES_KEY, sort=True):
        identity = "||".join(map(str, key))
        if query and query not in identity.casefold():
            continue
        selected.append((key, series))
        if len(selected) >= args.limit:
            break
    market_daily = FeatureBuilder.category_return_history(clean)
    market_daily["category_return"] = market_daily.category_return.fillna(0.0)
    market_groups = {str(category): group for category, group
                     in market_daily.groupby("product_category", sort=False)}
    prepared, metadata = [], []
    for key, series in selected:
        try:
            category = str(key[0])
            origin = issue_origin
            market = market_groups.get(category)
            market_history = ([] if market is None else market.loc[
                pd.to_datetime(market.report_date) <= origin,
                "category_return"].to_numpy(dtype=float).tolist())
            prepared.append(registry.engine._prepare(series, None, market_history))
            metadata.append((key, series))
        except (ValueError, FileNotFoundError) as exc:
            failures.append({"series": "||".join(map(str, key)), "error": str(exc)})
    try:
        forecasts = registry.engine.forecast_many(prepared, 30)
    except (ValueError, FileNotFoundError) as exc:
        forecasts = []
        failures.extend({"series": "||".join(map(str, key)), "error": str(exc)} for key, _ in metadata)
    for (key, series), forecast in zip(metadata, forecasts):
        try:
            rows = PredictionWriter._production_rows(None, forecast.dates, forecast.point,
                                                     issue_origin, series, {}, allow_confidence=False)
            results.append({
                "series": dict(zip(SERIES_KEY, key)),
                "forecast_origin": issue_origin.date().isoformat(),
                "latest_observation": str(pd.Timestamp(series.loc[series.is_observed, 'report_date'].max()).date()),
                "anchor": round(float(forecast.anchor), 2),
                "forecast_horizon": args.horizon,
                "forecast_source": "daily_model_path" if args.horizon == "daily" else "complete_daily_path_mean",
                "forecast": [r for r in rows if r['forecast_horizon'] == args.horizon],
            })
        except (ValueError, FileNotFoundError) as exc:
            failures.append({"series": "||".join(map(str, key)), "error": str(exc)})
    if not results:
        detail = f" matching {args.product!r}" if args.product else ""
        raise ValueError(f"No forecastable product series found{detail}; failures={failures[:1]}")
    print(json.dumps({"model_run_id": registry.run_id,
                      "published": False, "series": results,
                      "failures": failures}, indent=2))


def cmd_schedule(args):
    from pipeline.scheduler import PipelineScheduler
    PipelineScheduler(run_time=args.time).start()


def main():
    from data.fetcher import iso_report_date
    parser = argparse.ArgumentParser(prog="foodcast-trainer")
    commands = parser.add_subparsers(dest="command", required=True)
    train = commands.add_parser("train")
    train.add_argument("--mode", choices=["full", "incremental", "daily"], default="full")
    train.add_argument("--data", help="Offline JSON or CSV snapshot")
    train.add_argument("--lgbm-role",
                       choices=["direct", "residual_absolute", "residual_relative"],
                       default="direct",
                       help="Direct tree forecast or correction of the LSTM base (candidate only)")
    train.add_argument("--through", type=iso_report_date,
                       help="Inclusive report-date cutoff (YYYY-MM-DD), applied before preprocessing")
    train.add_argument("--report-date-as-of", action="store_true",
                       help="Rebuild training inputs using report dates through each Manila origin (new full runs only)")
    train.add_argument("--no-activate", action="store_true",
                       help="Keep the completed bundle as a candidate")
    train.add_argument("--result-json",
                       help="Write the candidate result JSON to this path")
    train.add_argument("--resume", help="Resume calibration for a fitted candidate run ID")
    train.add_argument("--recalibrate", help="Recalibrate a completed run from saved forecasts")
    train.set_defaults(func=cmd_train)
    evaluate = commands.add_parser("evaluate")
    evaluate.set_defaults(func=cmd_evaluate)
    baseline_report = commands.add_parser(
        "baseline-report", help="Write a read-only per-model, per-lead and per-series report")
    baseline_report.add_argument("--output-dir", required=True)
    baseline_report.add_argument("--run-id", help="Saved bundle ID; defaults to the active bundle")
    baseline_report.set_defaults(func=cmd_baseline_report)
    export_quality = commands.add_parser('export-quality')
    export_quality.add_argument('--output', required=True)
    export_quality.set_defaults(func=cmd_export_quality)
    check = commands.add_parser('check')
    check.set_defaults(func=cmd_check)
    predict = commands.add_parser("predict")
    predict.add_argument("--horizon", choices=["daily", "weekly", "monthly"],
                         default="monthly")
    predict.add_argument("--origin", type=iso_report_date,
                         help="Forecast origin date (defaults to latest available report date)")
    predict.set_defaults(func=cmd_predict)
    preview = commands.add_parser("preview")
    preview.add_argument("--horizon", choices=["daily", "weekly", "monthly"],
                         default="weekly")
    preview.add_argument("--product", help="Case-insensitive product or series filter")
    preview.add_argument("--limit", type=int, default=5,
                         help="Maximum matching product series to display")
    preview.add_argument("--data", help="Optional offline JSON or CSV snapshot")
    preview.add_argument("--through", type=iso_report_date,
                         help="Inclusive report-date cutoff (YYYY-MM-DD)")
    preview.set_defaults(func=cmd_preview)
    schedule = commands.add_parser("schedule")
    schedule.add_argument("--time", default="02:00")
    schedule.set_defaults(func=cmd_schedule)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
