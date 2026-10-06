"""Leakage-safe training, calibration, and frozen holdout evaluation."""
import hashlib
import json
import shutil
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from config.settings import get_settings
from data.fetcher import DataFetcher
from data.preprocessor import DataPreprocessor, SERIES_KEY
from features.builder import FEATURE_COLUMNS, FeatureBuilder, usable_targets
from models.ensemble import INTERVAL_LEVELS, EnsembleModel
from models.forecast_engine import ForecastEngine
from models.lightgbm_model import LightGBMModel
from models.lstm_model import LSTMModel
from models.model_store import ModelStore
from utils.logger import get_logger
from utils.metrics import compute_all_metrics

log = get_logger(__name__)


def _jsonable(value):
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


class TrainingPipeline:
    def __init__(self, artifact_root=None):
        self.cfg = get_settings()
        self.fetcher = DataFetcher()
        self.preprocessor = DataPreprocessor()
        self.store = ModelStore(artifact_root)

    def run_full_training(self, raw_df=None, activate=True):
        raw = self.fetcher.fetch_all() if raw_df is None else raw_df
        if raw.empty:
            raise ValueError("No training data")
        return self._train(raw, activate=activate)

    def run_incremental_training(self, since_date=None, raw_df=None, activate=True):
        log.info("Incremental warm starts are disabled; running a fresh causal retrain.")
        return self.run_full_training(raw_df=raw_df, activate=activate)

    def run_daily(self):
        return self.run_full_training()

    def resume_candidate(self, run_id, raw, activate=False):
        """Resume calibration/evaluation when complete fitted models already exist."""
        run_dir = self.store.runs / run_id
        if not run_dir.is_dir():
            raise FileNotFoundError(run_id)
        clean = self.preprocessor.validate(raw)
        train, validation, test = self.preprocessor.split_three(
            clean, self.cfg.validation_size, self.cfg.test_size)
        split = {"train": self._partition_bounds(train),
                 "validation": self._partition_bounds(validation),
                 "test": self._partition_bounds(test)}
        builder = FeatureBuilder(run_dir).load()
        featured = builder.transform(clean)
        lgbm = LightGBMModel(run_dir)
        lgbm.load()
        lstm = LSTMModel(run_dir)
        lstm.load()
        val_mask = (featured.report_date.between(
            validation.report_date.min(), validation.report_date.max()) & usable_targets(featured))
        lgbm_metrics = compute_all_metrics(
            featured.loc[val_mask, "observed_price"].to_numpy(),
            lgbm.predict(featured.loc[val_mask, FEATURE_COLUMNS]))
        history = json.loads((run_dir / "lstm_history.json").read_text(encoding="utf-8"))
        relative_lstm_metrics = {
            "best_masked_relative_mae": min(row["val_loss"] for row in history),
            "best_epoch": min(history, key=lambda row: row["val_loss"])["epoch"],
            "resumed": True,
        }
        return self._finish_candidate(
            raw, clean, featured, train, validation, test, split, run_dir,
            builder, lgbm, lstm, lgbm_metrics, relative_lstm_metrics, activate,
            base_model_scope='unknown_for_resumed_base_models')

    def recalibrate_candidate(self, run_id, activate=False):
        """Create a recalibrated child bundle while preserving its immutable parent."""
        parent_dir = self.store.runs / run_id
        metadata = json.loads((parent_dir / "metadata.json").read_text(encoding="utf-8"))
        parent_test = dict(metadata["metrics"]["test"]["ensemble"])
        run_dir = self.store.begin_run()
        for name in ["categorical_mappings.json", "lightgbm_model.txt",
                     "lightgbm_meta.json", "lstm_model.pt", "lstm_meta.json",
                     "lstm_history.json"]:
            shutil.copy2(parent_dir / name, run_dir / name)
        validation = pd.read_csv(parent_dir / "validation_forecasts.csv")
        test = pd.read_csv(parent_dir / "test_forecasts.csv")
        tuning, calibration = self._split_forecasts(validation)
        ensemble = EnsembleModel(run_dir).fit(
            tuning, self.cfg.monthly_horizon, calibration_frame=calibration)
        ensemble.calibration['base_model_scope'] = 'parent_validation_used_for_early_stopping'
        ensemble.save()
        for frame in [validation, test]:
            frame["ensemble"] = ensemble.predict_rows(
                frame.lstm.to_numpy(), frame.lgbm.to_numpy(), frame.horizon.to_numpy(),
                frame.anchor.to_numpy(), frame.series.to_numpy(),
                frame.moving_average7.to_numpy())
        metrics = metadata["metrics"]
        names = ["ensemble", "lstm", "lgbm", "persistence", "seasonal7", "moving_average7"]
        metrics["validation"] = {name: self._metrics(validation, name) for name in names}
        metrics["test"] = {name: self._metrics(test, name) for name in names}
        interval_metrics = self._interval_metrics(ensemble, test)
        metrics["test_interval_metrics"] = interval_metrics
        metrics["interval_calibration"] = ensemble.calibration
        metrics["test_interval_coverage"] = interval_metrics["0.8"]["observed_coverage"]
        beats_persistence = self._beats_persistence(metrics["test"])
        beats_parent = self._improves_all_by(
            metrics["test"]["ensemble"], parent_test, .05)
        # A parent may be older/weaker than the currently active model. Saved
        # forecasts permit comparison only when their evaluation windows match.
        champion = None
        beats_champion = True
        try:
            active_path = self.store.active_path()
        except FileNotFoundError:
            active_path = None
        if active_path is not None:
            active = json.loads((active_path / 'metadata.json').read_text(encoding='utf-8'))
            comparable = (active.get('data_fingerprint') == metadata.get('data_fingerprint')
                          and active.get('split') == metadata.get('split'))
            beats_champion = comparable and self._improves_all_by(
                metrics['test']['ensemble'], active['metrics']['test']['ensemble'], .05)
            champion = {'run_id': active_path.name, 'same_evaluation_window': comparable}
        development_passed = beats_persistence and beats_parent and beats_champion
        # Saved retrospective forecasts have been used for repeated development.
        # They cannot establish an independent final holdout for this child model.
        passed = False
        metrics["promotion_gate"] = {
            "passed": bool(passed),
            "development_comparison_passed": bool(development_passed),
            "independent_final_holdout_verified": False,
            "blocked_reason": "Recalibration has no independent frozen final-holdout evidence",
            "target_met_on_development_rows": all(
                0 <= metrics["test"]["ensemble"][name] <= 5
                for name in ("mae", "rmse", "mape")),
            "beats_persistence": bool(beats_persistence),
            "beats_parent": bool(beats_parent),
            "beats_active_champion": bool(beats_champion),
            "active_champion": champion,
            "rule": (
                "Retrospective comparisons are diagnostic. Activation requires "
                "independent frozen final-holdout MAE <= 5, RMSE <= 5, MAPE <= 5%, "
                "validated selection provenance and declared product coverage."
            ),
        }
        metrics["calibration_parent_run_id"] = run_id
        metrics["recalibrated_at"] = datetime.now(timezone.utc).isoformat()
        validation.to_csv(run_dir / "validation_forecasts.csv", index=False)
        test.to_csv(run_dir / "test_forecasts.csv", index=False)
        self.store.finalize(run_dir, _jsonable(metrics), metadata["split"],
                            metadata["data_fingerprint"], activate=bool(activate and passed))
        metrics["run_id"] = run_dir.name
        metrics["activated"] = bool(activate and passed)
        return _jsonable(metrics)

    @staticmethod
    def _partition_bounds(frame):
        return {"start": pd.Timestamp(frame.report_date.min()).isoformat(),
                "end": pd.Timestamp(frame.report_date.max()).isoformat(),
                "rows": int(len(frame)),
                "observed_rows": int(frame.is_observed.sum())}

    @staticmethod
    def _fingerprint(raw):
        columns = [c for c in SERIES_KEY + ["report_date", "price_index", "source_pdf"]
                   if c in raw.columns]
        stable = raw[columns].astype(str).sort_values(columns).reset_index(drop=True)
        values = pd.util.hash_pandas_object(stable, index=False).to_numpy().tobytes()
        return hashlib.sha256(values).hexdigest()

    def _backtest(self, clean, featured, partition, engine):
        start = pd.Timestamp(partition.report_date.min())
        end = pd.Timestamp(partition.report_date.max())
        first_origin = start - pd.Timedelta(days=1)
        last_origin = end - pd.Timedelta(days=self.cfg.monthly_horizon)
        if last_origin < first_origin:
            raise ValueError("Evaluation partition is shorter than the forecast horizon")
        origins = pd.date_range(first_origin, last_origin, freq=f"{self.cfg.evaluation_stride}D")
        rows, cases, contexts = [], [], []
        feature_groups = {key: group for key, group in featured.groupby(SERIES_KEY, sort=False)}
        market_daily = FeatureBuilder.category_return_history(clean)
        market_daily['category_return'] = market_daily.category_return.fillna(0.0)
        market_histories = {}
        for category, group in market_daily.groupby('product_category', sort=False):
            dates = pd.to_datetime(group.report_date)
            for origin in origins:
                market_histories[(str(category), pd.Timestamp(origin))] = (
                    group.loc[dates <= origin, 'category_return'].to_numpy(dtype=float).tolist())
        for key, full_series in clean.groupby(SERIES_KEY, sort=True):
            full_series = full_series.sort_values("report_date")
            actual = full_series.set_index("report_date").observed_price
            for origin in origins:
                history = full_series[full_series.report_date <= origin]
                try:
                    category = str(full_series.product_category.iloc[-1])
                    market_history = market_histories.get((category, pd.Timestamp(origin)), [])
                    prepared = engine._prepare(history, feature_groups[key], market_history)
                except ValueError:
                    continue
                cases.append(prepared)
                last_seven = history.price_index[np.isfinite(history.price_index)].tail(7).to_numpy()
                contexts.append((key, origin, actual, last_seven))
        paths = engine.forecast_many(cases, self.cfg.monthly_horizon)
        for path, context in zip(paths, contexts):
            key, origin, actual, last_seven = context
            if pd.Timestamp(path.dates[0]) != origin + pd.Timedelta(days=1):
                continue
            if not len(last_seven):
                continue
            persistence = path.anchor
            moving_average = float(last_seven.mean())
            seasonal = np.resize(last_seven[-min(7, len(last_seven)):],
                                 self.cfg.monthly_horizon)
            for h, date in enumerate(pd.to_datetime(path.dates), start=1):
                truth = actual.get(date, np.nan)
                if not np.isfinite(truth):
                    continue
                rows.append({
                    "series": "||".join(map(str, key)), "origin": origin,
                    "date": date, "horizon": h, "actual": float(truth),
                    "anchor": path.anchor, "lstm": path.lstm[h - 1],
                    "lgbm": path.lgbm[h - 1], "persistence": persistence,
                    "seasonal7": seasonal[h - 1], "moving_average7": moving_average,
                })
        result = pd.DataFrame(rows)
        if result.empty:
            raise ValueError("No observed labels were available for sampled backtesting")
        return result

    @staticmethod
    def _metrics(frame, prediction):
        return compute_all_metrics(frame.actual.to_numpy(),
                                   frame[prediction].to_numpy(),
                                   frame.anchor.to_numpy())

    @staticmethod
    def _split_forecasts(frame, cutoff=None):
        origins = np.sort(pd.to_datetime(frame.origin).unique())
        if len(origins) < 3:
            raise ValueError('At least three validation origins are required for separate calibration')
        cutoff = pd.Timestamp(origins[int(len(origins)*2/3)] if cutoff is None else cutoff)
        tuning = frame[pd.to_datetime(frame.date) <= cutoff].copy()
        calibration = frame[pd.to_datetime(frame.origin) >= cutoff].copy()
        if tuning.empty or calibration.empty:
            raise ValueError('No disjoint tuning and calibration forecasts')
        return tuning, calibration

    def _tuning_partition(self, validation):
        origins = pd.date_range(validation.report_date.min()-pd.Timedelta(days=1),
                                validation.report_date.max()-pd.Timedelta(days=self.cfg.monthly_horizon),
                                freq=f'{self.cfg.evaluation_stride}D')
        if len(origins) < 3:
            raise ValueError('Validation needs three full forecast origins for separate calibration')
        return validation[validation.report_date <= origins[int(len(origins)*2/3)]]

    @staticmethod
    def _interval_metrics(ensemble, frame):
        report = {}
        for level in INTERVAL_LEVELS:
            lower, upper = ensemble.intervals_rows(
                frame.ensemble.to_numpy(), frame.anchor.to_numpy(),
                frame.horizon.to_numpy(), confidence=level, series=frame.series.to_numpy())
            actual = frame.actual.to_numpy(float)
            covered = (actual >= lower) & (actual <= upper)
            score = (upper-lower + 2/(1-level)*np.maximum(lower-actual, 0)
                     + 2/(1-level)*np.maximum(actual-upper, 0))
            report[str(level)] = {
                "nominal_coverage": level,
                "observed_coverage": float(np.mean(
                    (frame.actual >= lower) & (frame.actual <= upper))),
                "average_width": float(np.mean(upper - lower)),
                "interval_score": float(np.mean(score)),
                "sample_count": len(frame),
                "by_category": {
                    category: {"observed_coverage": float(covered[mask].mean()),
                               "sample_count": int(mask.sum())}
                    for category in sorted(frame.series.str.split('||', regex=False).str[0].unique())
                    for mask in [(frame.series.str.split('||', regex=False).str[0] == category).to_numpy()]
                },
            }
        return report

    def _active_champion_metrics(self, clean, test, fingerprint, split):
        """Evaluate the active model on the candidate's test window when needed."""
        try:
            active_dir = self.store.active_path()
        except FileNotFoundError:
            return None
        metadata = json.loads((active_dir / "metadata.json").read_text(encoding="utf-8"))
        if (metadata.get("data_fingerprint") == fingerprint
                and metadata.get("split") == _jsonable(split)):
            return {
                "run_id": active_dir.name,
                "ensemble": metadata["metrics"]["test"]["ensemble"],
                "evaluation": "reused_identical_frozen_test",
            }

        try:
            builder = FeatureBuilder(active_dir).load()
            featured = builder.transform(clean)
            lgbm = LightGBMModel(active_dir)
            lgbm.load()
            lstm = LSTMModel(active_dir)
            lstm.load()
            ensemble = EnsembleModel(active_dir)
            ensemble.load()
            engine = ForecastEngine(lgbm, lstm, ensemble, builder)
            forecasts = self._backtest(clean, featured, test, engine)
            forecasts["ensemble"] = ensemble.predict_rows(
                forecasts.lstm.to_numpy(), forecasts.lgbm.to_numpy(),
                forecasts.horizon.to_numpy(), forecasts.anchor.to_numpy(),
                forecasts.series.to_numpy(), forecasts.moving_average7.to_numpy())
        except (ValueError, FileNotFoundError) as exc:
            raise RuntimeError("Cannot evaluate the active champion; promotion is blocked") from exc
        return {
            "run_id": active_dir.name,
            "ensemble": self._metrics(forecasts, "ensemble"),
            "evaluation": "backtested_on_candidate_frozen_test",
        }

    def _train(self, raw, activate=True):
        run_dir = self.store.begin_run()
        log.info("Training candidate bundle %s", run_dir.name)
        clean = self.preprocessor.validate(raw)
        train, validation, test = self.preprocessor.split_three(
            clean, self.cfg.validation_size, self.cfg.test_size)
        tuning_partition = self._tuning_partition(validation)
        split = {"train": self._partition_bounds(train),
                 "validation": self._partition_bounds(validation),
                 "test": self._partition_bounds(test)}

        builder = FeatureBuilder(run_dir).fit(train)
        featured = builder.transform(clean)
        train_mask = featured.report_date.between(train.report_date.min(), train.report_date.max())
        val_mask = featured.report_date.between(tuning_partition.report_date.min(), tuning_partition.report_date.max())
        train_rows = train_mask & usable_targets(featured)
        val_rows = val_mask & usable_targets(featured)
        if not train_rows.any() or not val_rows.any():
            raise ValueError("No finite observed LightGBM targets after causal feature construction")

        lgbm = LightGBMModel(run_dir)
        lgbm_metrics = lgbm.train(
            featured.loc[train_rows, FEATURE_COLUMNS],
            featured.loc[train_rows, "observed_price"],
            featured.loc[val_rows, FEATURE_COLUMNS],
            featured.loc[val_rows, "observed_price"])

        lstm = LSTMModel(run_dir).fit_scalers(train)
        train_start, train_end = train.report_date.min(), train.report_date.max()
        val_start, val_end = tuning_partition.report_date.min(), tuning_partition.report_date.max()
        x_train, y_train, _, _, _ = lstm.build_sequences(
            featured, target_start=train_start, target_end=train_end,
            stride=self.cfg.training_sequence_stride)
        x_val, y_val, _, _, _ = lstm.build_sequences(
            featured, target_start=val_start, target_end=val_end)
        relative_lstm_metrics = lstm.train(x_train, y_train, x_val, y_val)

        return self._finish_candidate(
            raw, clean, featured, train, validation, test, split, run_dir,
            builder, lgbm, lstm, lgbm_metrics, relative_lstm_metrics, activate)

    def _finish_candidate(self, raw, clean, featured, train, validation, test,
                          split, run_dir, builder, lgbm, lstm, lgbm_metrics,
                          relative_lstm_metrics, activate,
                          base_model_scope='calibration_excluded_from_early_stopping'):
        raw_engine = ForecastEngine(lgbm, lstm, None, builder)
        validation_forecasts = self._backtest(clean, featured, validation, raw_engine)
        tuning, calibration = self._split_forecasts(
            validation_forecasts, cutoff=self._tuning_partition(validation).report_date.max())
        ensemble = EnsembleModel(run_dir).fit(
            tuning, self.cfg.monthly_horizon, calibration_frame=calibration)
        ensemble.calibration['base_model_scope'] = base_model_scope
        ensemble.save()
        validation_forecasts["ensemble"] = ensemble.predict_rows(
            validation_forecasts.lstm.to_numpy(), validation_forecasts.lgbm.to_numpy(),
            validation_forecasts.horizon.to_numpy(), validation_forecasts.anchor.to_numpy(),
            validation_forecasts.series.to_numpy(),
            validation_forecasts.moving_average7.to_numpy())

        frozen_engine = ForecastEngine(lgbm, lstm, ensemble, builder)
        test_forecasts = self._backtest(clean, featured, test, frozen_engine)
        test_forecasts["ensemble"] = ensemble.predict_rows(
            test_forecasts.lstm.to_numpy(), test_forecasts.lgbm.to_numpy(),
            test_forecasts.horizon.to_numpy(), test_forecasts.anchor.to_numpy(),
            test_forecasts.series.to_numpy(), test_forecasts.moving_average7.to_numpy())
        interval_metrics = self._interval_metrics(ensemble, test_forecasts)
        observed = clean.loc[clean.is_observed, "report_date"]
        source_data = {
            "processed_from": (
                pd.Timestamp(observed.min()).date().isoformat() if not observed.empty else None
            ),
            "processed_through": (
                pd.Timestamp(observed.max()).date().isoformat() if not observed.empty else None
            ),
            "observed_rows": int(clean.is_observed.sum()),
            "series_count": int(clean.groupby(SERIES_KEY).ngroups),
        }

        metrics = {
            "lightgbm_one_step_validation": lgbm_metrics,
            "lstm_relative_validation": relative_lstm_metrics,
            "validation": {
                name: self._metrics(validation_forecasts, name)
                for name in ["ensemble", "lstm", "lgbm", "persistence",
                             "seasonal7", "moving_average7"]
            },
            "test": {
                name: self._metrics(test_forecasts, name)
                for name in ["ensemble", "lstm", "lgbm", "persistence",
                             "seasonal7", "moving_average7"]
            },
            "test_interval_coverage": interval_metrics["0.8"]["observed_coverage"],
            "test_interval_metrics": interval_metrics,
            "interval_calibration": ensemble.calibration,
            "source_data": source_data,
            "validation_samples": int(len(validation_forecasts)),
            "test_samples": int(len(test_forecasts)),
            "evaluation_stride_days": self.cfg.evaluation_stride,
            "evaluation_scope": (
                "retrospective source-dated backtest; the database has no immutable "
                "historical ingestion vintages for point-in-time reconstruction"
            ),
            "trained_at": datetime.now(timezone.utc).isoformat(),
        }
        fingerprint = self._fingerprint(raw)
        champion = self._active_champion_metrics(clean, test, fingerprint, split)
        beats_baseline, beats_champion, development_passed = self._promotion_decision(
            metrics["test"], champion["ensemble"] if champion else None)
        # This function creates and inspects an internal chronological split.
        # Re-running it cannot turn that reused development data into a final
        # holdout. Stage the bundle until independent final evidence is reviewed.
        passed = False
        metrics["promotion_gate"] = {
            "passed": bool(passed),
            "development_comparison_passed": bool(development_passed),
            "independent_final_holdout_verified": False,
            "blocked_reason": "Training has no independent frozen final-holdout evidence",
            "target_met_on_development_rows": all(
                0 <= metrics["test"]["ensemble"][name] <= 5
                for name in ("mae", "rmse", "mape")),
            "beats_persistence": bool(beats_baseline),
            "beats_active_champion": bool(beats_champion),
            "active_champion": champion,
            "rule": (
                "Retrospective comparisons are diagnostic. Activation requires "
                "independent frozen final-holdout MAE <= 5, RMSE <= 5, MAPE <= 5%, "
                "validated selection provenance and declared product coverage."
            ),
        }
        validation_forecasts.to_csv(run_dir / "validation_forecasts.csv", index=False)
        test_forecasts.to_csv(run_dir / "test_forecasts.csv", index=False)
        run_id = self.store.finalize(
            run_dir, _jsonable(metrics), split, fingerprint,
            activate=bool(activate and passed))
        metrics["run_id"] = run_id
        metrics["activated"] = bool(activate and passed)
        log.info("Candidate %s complete; activated=%s", run_id, metrics["activated"])
        return _jsonable(metrics)

    @staticmethod
    def _beats_persistence(test_metrics):
        return TrainingPipeline._improves_all(
            test_metrics["ensemble"], test_metrics["persistence"])

    @staticmethod
    def _promotion_decision(test_metrics, champion_metrics=None):
        """Development comparison only; this does not authorize activation."""
        beats_persistence = TrainingPipeline._beats_persistence(test_metrics)
        beats_champion = (champion_metrics is None or TrainingPipeline._improves_all_by(
            test_metrics["ensemble"], champion_metrics, .05))
        return beats_persistence, beats_champion, beats_persistence and beats_champion

    @staticmethod
    def _improves_all(candidate, reference):
        return all(candidate[name] < reference[name] for name in ["mae", "rmse", "mape"])

    @staticmethod
    def _improves_all_by(candidate, reference, fraction):
        return all(candidate[name] <= reference[name] * (1 - fraction)
                   for name in ["mae", "rmse", "mape"])
