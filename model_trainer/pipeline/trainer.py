"""Leakage-safe training, calibration, and frozen holdout evaluation."""
import hashlib
import json
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from config.settings import get_settings
from data.fetcher import DataFetcher
from data.preprocessor import DataPreprocessor, SERIES_KEY, source_date
from data.snapshot import (
    MANIFEST_FILE as SOURCE_MANIFEST_FILE,
    SNAPSHOT_FILE as SOURCE_SNAPSHOT_FILE,
    capture_snapshot,
)
from features.builder import (CausalFeatureState, PEER_PRODUCT_KEY,
                              PRODUCT_VARIANT_KEY,
                              FeatureBuilder, usable_targets)
from models.ensemble import EnsembleModel
from models.forecast_engine import ForecastEngine
from models.lightgbm_model import (
    LightGBMModel, RESIDUAL_FEATURE_SCHEMA,
)
from models.lstm_model import LSTMModel
from models.model_store import ModelStore
from utils.logger import get_logger
from utils.metrics import compute_all_metrics

log = get_logger(__name__)
EVALUATION_ORIGIN_POLICY = "fixed_stride_plus_partition_terminal_v1"
MAPE_TARGET_PERCENT = 5.0
WITHIN_5_PHP_TARGET_PERCENT = 95.0
PRICE_ERROR_TARGET_PHP = 5.0
FROZEN_HOLDOUT_CONTRACT = (
    Path(__file__).resolve().parents[2]
    / "audits" / "target5_20261002" / "prospective_20261005" / "contract.json"
)


def pending_holdout_window(contract_path=FROZEN_HOLDOUT_CONTRACT):
    """Return the active frozen window while its one-time score is pending."""
    path = Path(contract_path)
    if not path.is_file() or path.with_name("score.json").is_file():
        return None
    contract = json.loads(path.read_text(encoding="utf-8"))
    if contract.get("status") != "frozen_predictions_waiting_for_complete_holdout_period":
        return None
    start = date.fromisoformat(contract["holdout_start"])
    end = date.fromisoformat(contract["holdout_end"])
    if end < start:
        raise ValueError("Frozen holdout end precedes its start")
    return start, end


def assert_no_pending_holdout_rows(frame, window):
    """Fail closed if candidate input data reaches a still-pending holdout."""
    if window is None:
        return
    if "report_date" not in frame:
        raise ValueError("Cannot verify training data against the pending frozen holdout")
    start, _ = window
    dates = pd.to_datetime(frame["report_date"], errors="coerce").dt.date
    if dates.ge(start).any():
        raise ValueError(
            f"Training input reaches the pending frozen holdout starting {start}; "
            "use a source snapshot ending before the holdout")


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
    def __init__(self, artifact_root=None, ensemble_objective='balanced',
                 feature_version=None, lgbm_role='direct'):
        if ensemble_objective not in {
                'balanced', 'balanced_lgbm', 'rmse_lgbm', 'within5'}:
            raise ValueError(
                'Ensemble objective must be balanced, balanced_lgbm, rmse_lgbm, or within5')
        self.cfg = get_settings()
        self.fetcher = DataFetcher()
        self.preprocessor = DataPreprocessor()
        self.store = ModelStore(artifact_root)
        self.ensemble_objective = ensemble_objective
        if lgbm_role not in {'direct', 'residual_absolute', 'residual_relative'}:
            raise ValueError(
                "LightGBM role must be direct, residual_absolute, or residual_relative")
        self.lgbm_role = lgbm_role
        self.lstm_price_huber_delta = None
        self.lstm_price_tolerance_huber_delta = None
        self.lstm_relative_tolerance_huber_delta = None
        self.feature_version = feature_version
        self._residual_training_provenance = None

    def run_full_training(self, raw_df=None, activate=True, *, source_as_of=False,
                          fit_source_cutoff=None, source_availability_cutoffs=None,
                          lgbm_sample_weight_half_life_days=None):
        explicit_cutoff_plan = (fit_source_cutoff is not None
                                or source_availability_cutoffs is not None)
        if source_as_of and explicit_cutoff_plan:
            raise ValueError(
                "Choose either the generated source-as-of cutoff plan or explicit cutoffs")
        strict_sources = (source_as_of or fit_source_cutoff is not None
                          or source_availability_cutoffs is not None)
        if strict_sources and (fit_source_cutoff is None
                               or source_availability_cutoffs is None) and not source_as_of:
            raise ValueError(
                "Point-in-time training requires both a fit source cutoff and "
                "per-origin source availability cutoffs")
        if strict_sources and raw_df is None:
            raise ValueError(
                "Point-in-time training requires an explicit bounded raw_df; "
                "it will not fetch unbounded production data")
        pending_window = pending_holdout_window()
        through_date = (
            (pending_window[0] - timedelta(days=1)).isoformat()
            if pending_window else None
        )
        if raw_df is None:
            raw = self.fetcher.fetch_all(through_date=through_date)
        else:
            raw = raw_df
            assert_no_pending_holdout_rows(raw, pending_window)
        if raw.empty:
            raise ValueError("No training data")
        return self._train(
            raw, activate=activate,
            source_as_of=source_as_of,
            fit_source_cutoff=fit_source_cutoff,
            source_availability_cutoffs=source_availability_cutoffs,
            lgbm_sample_weight_half_life_days=lgbm_sample_weight_half_life_days)

    def run_incremental_training(self, since_date=None, raw_df=None, activate=True):
        log.info("Incremental warm starts are disabled; running a fresh causal retrain.")
        return self.run_full_training(raw_df=raw_df, activate=activate)

    def run_daily(self):
        return self.run_full_training()

    def resume_candidate(self, run_id, raw, activate=False):
        """Resume calibration/evaluation when complete fitted models already exist."""
        assert_no_pending_holdout_rows(raw, pending_holdout_window())
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
            validation.report_date.min(), validation.report_date.max())
            & usable_targets(featured, builder.feature_columns))
        lgbm_metrics = compute_all_metrics(
            featured.loc[val_mask, "observed_price"].to_numpy(),
            lgbm.predict(featured.loc[val_mask, lgbm._feature_names]))
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
        if pending_holdout_window() is not None:
            raise ValueError(
                "Candidate recalibration is disabled while the final holdout score is pending")
        parent_dir = self.store.runs / run_id
        metadata = json.loads((parent_dir / "metadata.json").read_text(encoding="utf-8"))
        parent_test = dict(metadata["metrics"]["test"]["ensemble"])
        if "within_5_php_accuracy_pct" not in parent_test:
            saved_test = parent_dir / "test_forecasts.csv"
            if saved_test.exists():
                parent_test = self._metrics(pd.read_csv(saved_test), "ensemble")
        run_dir = self.store.begin_run()
        for name in ["categorical_mappings.json", "lightgbm_model.txt",
                     "lightgbm_meta.json", "lstm_model.pt", "lstm_meta.json",
                     "lstm_history.json"]:
            shutil.copy2(parent_dir / name, run_dir / name)
        snapshot_files = {SOURCE_SNAPSHOT_FILE, SOURCE_MANIFEST_FILE}
        archived = snapshot_files & set(metadata.get("sha256", {}))
        if archived and archived != snapshot_files:
            raise ValueError("Parent bundle has incomplete source snapshot provenance")
        for name in sorted(archived):
            if self.store._digest(parent_dir / name) != metadata["sha256"][name]:
                raise ValueError(f"Parent source snapshot is corrupt: {name}")
            shutil.copy2(parent_dir / name, run_dir / name)
        validation = pd.read_csv(parent_dir / "validation_forecasts.csv")
        test = pd.read_csv(parent_dir / "test_forecasts.csv")
        path_frames = {}
        for name in ("validation_paths.csv", "test_paths.csv"):
            path = parent_dir / name
            if path.exists():
                shutil.copy2(path, run_dir / name)
                path_frames[name] = pd.read_csv(path)
        tuning, calibration = self._split_forecasts(validation)
        ensemble = EnsembleModel(run_dir).fit(
            tuning, self.cfg.monthly_horizon, calibration_frame=calibration)
        ensemble.calibration['base_model_scope'] = 'parent_validation_used_for_early_stopping'
        ensemble.save()
        for frame in [validation, test, *path_frames.values()]:
            frame["ensemble"] = ensemble.predict_rows(
                frame.lstm.to_numpy(), frame.lgbm.to_numpy(), frame.horizon.to_numpy(),
                frame.anchor.to_numpy(), frame.series.to_numpy(),
                frame.moving_average7.to_numpy())
        metrics = metadata["metrics"]
        names = ["ensemble", "lstm", "lgbm", "persistence", "seasonal7", "moving_average7"]
        metrics["validation"] = {name: self._metrics(validation, name) for name in names}
        metrics["test"] = {name: self._metrics(test, name) for name in names}
        beats_persistence = self._beats_persistence(metrics["test"])
        beats_parent = self._improves_all_by(
            metrics["test"]["ensemble"], parent_test, .05)
        # A parent may be older/weaker than the currently active model. Saved
        # forecasts permit comparison only when their evaluation windows match.
        champion = None
        beats_champion = None
        try:
            active_path = self.store.active_path()
        except FileNotFoundError:
            active_path = None
        if active_path is not None:
            active = json.loads((active_path / 'metadata.json').read_text(encoding='utf-8'))
            comparable = (
                active.get('data_fingerprint') == metadata.get('data_fingerprint')
                and active.get('split') == metadata.get('split')
                and active.get('metrics', {}).get('evaluation_stride_days')
                == metadata.get('metrics', {}).get('evaluation_stride_days')
                and active.get('metrics', {}).get('evaluation_origin_policy')
                == metadata.get('metrics', {}).get('evaluation_origin_policy'))
            beats_champion = (
                self._improves_all_by(
                    metrics['test']['ensemble'], active['metrics']['test']['ensemble'], .05)
                if comparable else None)
            if comparable and beats_champion is False:
                stored_metrics = active.get("metrics", {}).get("test", {}).get("ensemble", {})
                saved_test = active_path / "test_forecasts.csv"
                if ("within_5_php_accuracy_pct" not in stored_metrics and saved_test.exists()
                        and len(pd.read_csv(saved_test)) == stored_metrics.get("n")):
                    active_test = self._metrics(pd.read_csv(saved_test), "ensemble")
                    beats_champion = self._improves_all_by(
                        metrics["test"]["ensemble"], active_test, .05)
            champion = {'run_id': active_path.name, 'same_evaluation_window': comparable}
        development_passed = bool(
            beats_persistence and beats_parent and beats_champion is True)
        # Saved retrospective forecasts have been used for repeated development.
        # They cannot establish an independent final holdout for this child model.
        passed = False
        metrics["promotion_gate"] = {
            "passed": bool(passed),
            "development_comparison_passed": bool(development_passed),
            "independent_final_holdout_verified": False,
            "blocked_reason": "Recalibration has no independent frozen final-holdout evidence",
            "target_met_on_development_rows": self._targets_met(
                metrics["test"]["ensemble"]),
            "beats_persistence": bool(beats_persistence),
            "beats_parent": bool(beats_parent),
            "beats_active_champion": beats_champion,
            "active_champion": champion,
            "rule": (
                "Retrospective comparisons are diagnostic. Activation requires "
                "independent frozen final-holdout pooled and per-horizon "
                "Within-5-PHP accuracy >= 95%, MAPE <= 5%, and MAE/RMSE <= PHP 5, "
                "validated selection provenance and declared product coverage."
            ),
        }
        metrics["calibration_parent_run_id"] = run_id
        metrics["recalibrated_at"] = datetime.now(timezone.utc).isoformat()
        validation.to_csv(run_dir / "validation_forecasts.csv", index=False)
        test.to_csv(run_dir / "test_forecasts.csv", index=False)
        for name, frame in path_frames.items():
            frame.to_csv(run_dir / name, index=False)
        self._attach_validation_quality(
            run_dir, validation, metrics, path_frames.get("validation_paths.csv"))
        model_configuration = metadata.get("model_configuration")
        if isinstance(model_configuration, dict):
            model_configuration = dict(model_configuration)
            ensemble_meta = json.loads((run_dir / "ensemble.json").read_text(encoding="utf-8"))
            model_configuration["ensemble"] = {
                "artifact": "ensemble.json",
                "objective": ensemble_meta.get("objective"),
                "calibration": ensemble_meta.get("calibration"),
            }
        self.store.finalize(run_dir, _jsonable(metrics), metadata["split"],
                            metadata["data_fingerprint"], activate=bool(activate and passed),
                            model_configuration=model_configuration,
                            preprocessing_contract=metadata.get("preprocessing_contract"))
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
    def _source_row_audit(raw):
        """Distinguish actual dated DA prices from the scraper's copied rows."""
        if raw is None or not isinstance(raw, pd.DataFrame):
            return {}
        audit = {"fetched_rows": int(len(raw))}
        if raw.empty or "report_date" not in raw:
            return audit
        report_dates = pd.to_datetime(raw.report_date, errors="coerce").dt.normalize()
        if "is_observed" in raw:
            observed = raw.is_observed.fillna(False).astype(bool)
            audit["fetched_rows_marked_observed"] = int(observed.sum())
            return audit
        if "source_pdf" not in raw:
            return audit
        source_dates = raw.source_pdf.map(source_date)
        parsed = source_dates.notna()
        matches = parsed & source_dates.eq(report_dates)
        audit.update({
            "rows_with_source_date_matching_report_date": int(matches.sum()),
            "rows_with_older_source_date_copied_forward": int(
                (parsed & source_dates.lt(report_dates)).sum()),
            "rows_with_source_date_after_report_date": int(
                (parsed & source_dates.gt(report_dates)).sum()),
            "rows_with_unparseable_source_date": int((~parsed).sum()),
        })
        return audit

    def _training_source_audit(self, train, available_through=None,
                               feature_audit=None, label_filtering_applied=False):
        """Audit use of report dates under the end-of-date availability assumption."""
        if available_through is None:
            boundary = pd.Timestamp(train.report_date.max()).normalize()
            if boundary.tzinfo is None:
                boundary = boundary.tz_localize("Asia/Manila")
            else:
                boundary = boundary.tz_convert("Asia/Manila")
            cutoff = boundary + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
            cutoff_basis = "end_of_last_training_report_date_in_Asia/Manila"
        else:
            cutoff = available_through
            cutoff_basis = "explicit_report_date_cutoff"
        _, audit = self.preprocessor.source_target_availability(train, cutoff)
        features_verified = bool(
            feature_audit
            and feature_audit.get("status") == "report_date_asof_reconstructed")
        audit.update({
            "fit_cutoff_basis": cutoff_basis,
            "report_date_cutoff_applied": bool(
                audit["labels_available_by_fit_cutoff"] > 0),
            "training_label_filtering_applied": bool(label_filtering_applied),
            "feature_availability_status": (
                "report_date_as_of_origins" if features_verified else "not_reconstructed"),
            "feature_availability_audit": feature_audit,
            "point_in_time_training_verified": False,
            "point_in_time_limitation": (
                "Publication time is not present; report_date is assumed available "
                "by end of day in Asia/Manila."),
        })
        return audit

    @staticmethod
    def _write_source_cutoff_manifest(run_dir, clean, fit_source_cutoff,
                                      source_availability_cutoffs):
        """Persist the exact cutoffs used by a strict source-as-of candidate."""
        fit_time = pd.Timestamp(fit_source_cutoff)
        if fit_time.tzinfo is None:
            raise ValueError("Fit source cutoff must include a timezone")
        origins = {}
        for target_date in pd.DatetimeIndex(
                pd.to_datetime(clean.report_date).unique()).sort_values():
            origin_key = (pd.Timestamp(target_date) - pd.Timedelta(days=1)).date().isoformat()
            if origin_key not in source_availability_cutoffs:
                raise ValueError(f"Missing source cutoff for origin {origin_key}")
            origin_time = pd.Timestamp(source_availability_cutoffs[origin_key])
            if origin_time.tzinfo is None:
                raise ValueError(f"Source cutoff for {origin_key} must include a timezone")
            origins[origin_key] = origin_time.tz_convert("UTC").isoformat(
                timespec="microseconds")
        manifest = {
            "schema_version": 1,
            "fit_source_cutoff_utc": fit_time.tz_convert("UTC").isoformat(
                timespec="microseconds"),
            "origin_source_cutoffs_utc": origins,
        }
        encoded = json.dumps(manifest, sort_keys=True, indent=2).encode("utf-8")
        (run_dir / "source_availability_cutoffs.json").write_bytes(encoded)
        return {
            "path": "source_availability_cutoffs.json",
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "origin_count": int(len(origins)),
        }

    @staticmethod
    def _fingerprint(raw):
        columns = [c for c in SERIES_KEY + ["report_date", "price_index", "source_pdf"]
                   if c in raw.columns]
        stable = raw[columns].astype(str).sort_values(columns).reset_index(drop=True)
        values = pd.util.hash_pandas_object(stable, index=False).to_numpy().tobytes()
        return hashlib.sha256(values).hexdigest()

    @staticmethod
    def _evaluation_origins(start, end, horizon_days, stride_days):
        first = pd.Timestamp(start) - pd.Timedelta(days=1)
        last = pd.Timestamp(end) - pd.Timedelta(days=horizon_days)
        if last < first:
            raise ValueError("Evaluation partition is shorter than the forecast horizon")
        origins = pd.date_range(first, last, freq=f"{stride_days}D")
        if origins[-1] != last:
            origins = origins.append(pd.DatetimeIndex([last]))
        return origins

    def _backtest_as_of_sources(self, clean, partition, engine, cutoffs,
                                return_paths=False):
        """Rebuild inference inputs per origin from report-date cutoffs.

        This constrains forecast-time inputs only. Callers must separately
        verify that the fitted model used training data available at fit time.
        """
        start = pd.Timestamp(partition.report_date.min())
        end = pd.Timestamp(partition.report_date.max())
        origins = self._evaluation_origins(
            start, end, self.cfg.monthly_horizon, self.cfg.evaluation_stride)
        truths = {
            key: group.sort_values("report_date").set_index("report_date").observed_price
            for key, group in clean.groupby(SERIES_KEY, sort=True)
        }
        cases, contexts, source_audits = [], [], {}

        for origin in origins:
            origin_key = pd.Timestamp(origin).date().isoformat()
            if origin_key not in cutoffs:
                raise ValueError(f"Missing source-availability cutoff for origin {origin_key}")
            input_view, source_audits[origin_key] = self.preprocessor.source_input_view(
                clean, cutoffs[origin_key])
            cutoff_date = pd.Timestamp(
                source_audits[origin_key]["report_date_cutoff_manila"]).date()
            if cutoff_date > pd.Timestamp(origin).date():
                raise ValueError(
                    f"Source-availability cutoff for {origin_key} falls after its forecast origin")
            input_view = input_view.loc[input_view.report_date <= origin].copy()
            feature_inputs = []
            for key, series in input_view.groupby(SERIES_KEY, sort=True):
                series = series.sort_values("report_date")
                feature_inputs.append(ForecastEngine._append_day(
                    series, pd.Timestamp(series.report_date.iloc[-1]) + pd.Timedelta(days=1)))
            if not feature_inputs:
                continue
            # Build one panel so category-return features use the same peer
            # products as the fitted feature contract, while every price in
            # the panel remains restricted to this origin's report-date cutoff.
            featured_as_of = engine.builder.transform(pd.concat(
                feature_inputs, ignore_index=True).sort_values(
                    SERIES_KEY + ["report_date"]).reset_index(drop=True))
            feature_groups = {
                key: group for key, group in featured_as_of.groupby(SERIES_KEY, sort=False)
            }
            market_daily = FeatureBuilder.category_return_history(input_view)
            market_daily["category_return"] = market_daily.category_return.fillna(0.0)
            market_histories = {}
            for category, group in market_daily.groupby("product_category", sort=False):
                dates = pd.to_datetime(group.report_date)
                market_histories[str(category)] = group.loc[
                    dates <= origin, "category_return"].to_numpy(dtype=float).tolist()
            product_daily = FeatureBuilder.product_return_history(input_view)
            product_daily["product_return"] = product_daily.product_return.fillna(0.0)
            product_histories = {}
            for product_key, group in product_daily.groupby(SERIES_KEY[:3], sort=False):
                dates = pd.to_datetime(group.report_date)
                product_histories[tuple(map(str, product_key))] = group.loc[
                    dates <= origin, "product_return"].to_numpy(dtype=float).tolist()

            for key, full_series in input_view.groupby(SERIES_KEY, sort=True):
                history = full_series[full_series.report_date <= origin].sort_values("report_date")
                usable_history = history.loc[np.isfinite(history.price_index)]
                if usable_history.empty or pd.Timestamp(
                        usable_history.report_date.iloc[-1]) != pd.Timestamp(origin):
                    continue
                market_history = market_histories.get(str(full_series.product_category.iloc[-1]), [])
                product_market_history = product_histories.get(tuple(map(str, key[:3])), [])
                try:
                    prepared = engine._prepare(
                        history, feature_groups.get(key), market_history,
                        product_market_history)
                except ValueError:
                    continue
                last_seven = history.price_index[
                    np.isfinite(history.price_index)].tail(7).to_numpy(dtype=float)
                if not len(last_seven):
                    continue
                cases.append(prepared)
                contexts.append((key, origin, truths.get(key), last_seven))

        paths = engine.forecast_many(cases, self.cfg.monthly_horizon)
        rows, path_rows = [], []
        for path, context in zip(paths, contexts):
            key, origin, actual, last_seven = context
            if pd.Timestamp(path.dates[0]) != origin + pd.Timedelta(days=1):
                continue
            persistence = path.anchor
            moving_average = float(last_seven.mean())
            seasonal = np.resize(last_seven[-min(7, len(last_seven)):],
                                 self.cfg.monthly_horizon)
            for horizon, target in enumerate(pd.to_datetime(path.dates), start=1):
                truth = actual.get(target, np.nan) if actual is not None else np.nan
                row = {
                    "series": "||".join(map(str, key)), "origin": origin,
                    "date": target, "horizon": horizon,
                    "actual": float(truth) if np.isfinite(truth) else np.nan,
                    "anchor": path.anchor, "lstm": path.lstm[horizon - 1],
                    "lgbm": path.lgbm[horizon - 1], "persistence": persistence,
                    "seasonal7": seasonal[horizon - 1],
                    "moving_average7": moving_average,
                }
                path_rows.append(row)
                if np.isfinite(truth):
                    rows.append(row)

        result = pd.DataFrame(rows)
        if result.empty:
            raise ValueError("No observed labels were available for report-date-as-of backtesting")
        result.attrs["report_date_availability_by_origin"] = source_audits
        if return_paths:
            paths_frame = pd.DataFrame(path_rows)
            if paths_frame.empty:
                raise ValueError("No full paths were generated for report-date-as-of backtesting")
            paths_frame.attrs["report_date_availability_by_origin"] = source_audits
            return result, paths_frame
        return result

    def _source_asof_training_features(self, clean, builder, cutoffs,
                                       through_date=None):
        """Build each target-date feature row from its report-date cutoff.

        Training sequences consume these rows chronologically. A separate anchor
        is retained for each target date. Only the target rows are evaluated; the
        fitted causal state avoids transforming every historical row again for
        every origin. Prices are assumed available by the end of report_date.
        """
        feature_frames = []
        input_audits = []
        dates = pd.DatetimeIndex(pd.to_datetime(clean.report_date).unique()).sort_values()
        if through_date is not None:
            dates = dates[dates <= pd.Timestamp(through_date)]
        for target_date in dates:
            origin = pd.Timestamp(target_date) - pd.Timedelta(days=1)
            origin_key = origin.date().isoformat()
            if origin_key not in cutoffs:
                raise ValueError(
                    f"Missing report-date cutoff for training origin {origin_key}")
            input_view, input_audit = self.preprocessor.source_input_view(
                clean, cutoffs[origin_key])
            cutoff_date = pd.Timestamp(input_audit["report_date_cutoff_manila"]).date()
            if cutoff_date != origin.date():
                raise ValueError(
                    f"Training report-date cutoff for {origin_key} must fall on that Manila origin date")
            input_audits.append(input_audit)
            input_view = input_view.loc[input_view.report_date <= origin].copy()

            # The target row uses only the seven category returns ending at its
            # origin. Include one earlier date so the first return in that
            # window has its prior price available.
            market_start = origin - pd.Timedelta(days=7)
            market_view = input_view.loc[input_view.report_date >= market_start]
            market_daily = FeatureBuilder.category_return_history(market_view)
            market_daily["category_return"] = market_daily.category_return.fillna(0.0)
            market_histories = {
                str(category): group.loc[
                    pd.to_datetime(group.report_date) <= origin,
                    "category_return"].to_numpy(dtype=float).tolist()
                for category, group in market_daily.groupby(
                    "product_category", sort=False)
            }
            product_market_daily = FeatureBuilder.product_return_history(input_view)
            product_market_daily["product_return"] = (
                product_market_daily.product_return.fillna(0.0))
            product_market_histories = {}
            for product_key, group in product_market_daily.groupby(SERIES_KEY[:3], sort=False):
                product_market_histories[tuple(map(str, product_key))] = group.loc[
                    pd.to_datetime(group.report_date) <= origin,
                    "product_return"].to_numpy(dtype=float).tolist()
            cross_variant_histories = {}
            if builder.feature_version in {12, 13}:
                cross_variant_daily = FeatureBuilder.cross_variant_peer_history(input_view)
                cross_variant_histories = {
                    tuple(map(str, product_key)): group.loc[
                        pd.to_datetime(group.report_date) <= origin,
                        ["_peer_return", "_peer_count"]].to_numpy(dtype=float).tolist()
                    for product_key, group in cross_variant_daily.groupby(
                        PRODUCT_VARIANT_KEY, sort=False)
                }
            category_peer_histories = {}
            if builder.feature_version in {10, 13}:
                category_peer_daily = FeatureBuilder.category_peer_return_history(input_view)
                category_peer_histories = {
                    tuple(map(str, product_key)): group.loc[
                        pd.to_datetime(group.report_date) <= origin,
                        ["_peer_mean", "_peer_count"]].to_numpy(dtype=float).tolist()
                    for product_key, group in category_peer_daily.groupby(
                        PEER_PRODUCT_KEY, sort=False)
                }

            target_rows = []
            for key, series in input_view.groupby(SERIES_KEY, sort=True):
                series = series.sort_values("report_date")
                available = series.loc[np.isfinite(series.price_index)]
                if (available.empty
                        or pd.Timestamp(available.report_date.iloc[-1]) != origin):
                    continue
                category = str(series.product_category.iloc[-1])
                state = CausalFeatureState(series, builder.encoder)
                target_row = state.row(
                    target_date, market_histories.get(category, []),
                    product_market_histories.get(tuple(map(str, key[:3])), []),
                    category_peer_market_history=category_peer_histories.get(
                        tuple(str(key[index]) for index in (0, 1, 2, 4)), []),
                    cross_variant_market_history=cross_variant_histories.get(
                        tuple(str(key[index]) for index in (0, 1, 4, 2)), []))
                target_row["forecast_anchor"] = float(available.price_index.iloc[-1])
                target_rows.append(target_row[
                    SERIES_KEY + ["report_date", "forecast_anchor"]
                    + builder.feature_columns])
            if target_rows:
                feature_frames.append(pd.concat(target_rows, ignore_index=True))

        if not feature_frames:
            raise ValueError("No report-date-as-of training feature rows could be reconstructed")
        source_features = pd.concat(feature_frames, ignore_index=True)
        if source_features.duplicated(SERIES_KEY + ["report_date"]).any():
            raise ValueError("Duplicate report-date-as-of training feature rows")
        featured = clean.merge(
            source_features, on=SERIES_KEY + ["report_date"], how="left",
            validate="one_to_one", sort=False)
        cutoff_times = [pd.Timestamp(audit["report_date_as_of_utc"])
                        for audit in input_audits]
        audit = {
            "status": "report_date_asof_reconstructed",
            "availability_policy": "report_date_assumed_available_by_end_of_day_Asia/Manila",
            "reconstruction": "causal_state_target_rows_only",
            "target_date_through": (
                pd.Timestamp(dates[-1]).date().isoformat() if len(dates) else None),
            "reconstructed_target_dates": int(len(input_audits)),
            "target_dates_with_feature_rows": int(source_features.report_date.nunique()),
            "target_feature_rows": int(len(source_features)),
            "observed_labels_with_source_anchor_and_features": int(
                (featured.is_observed & featured.forecast_anchor.notna()
                 & np.isfinite(featured[builder.feature_columns]).all(axis=1)).sum()),
            "observed_labels_without_source_anchor_or_features": int(
                (featured.is_observed & ~(
                    featured.forecast_anchor.notna()
                    & np.isfinite(featured[builder.feature_columns]).all(axis=1))).sum()),
            "origin_cutoffs_from_utc": min(cutoff_times).isoformat() if cutoff_times else None,
            "origin_cutoffs_through_utc": max(cutoff_times).isoformat() if cutoff_times else None,
        }
        return featured, audit

    def _backtest(self, clean, featured, partition, engine, return_paths=False,
                  source_availability_cutoffs=None, return_feature_rows=False,
                  stride_days=None, origin_dates=None):
        if source_availability_cutoffs is not None:
            if (return_feature_rows or stride_days is not None
                    or origin_dates is not None):
                raise ValueError(
                    "Feature-row collection, custom strides, and custom origins "
                    "require report-date replay")
            return self._backtest_as_of_sources(
                clean, partition, engine, source_availability_cutoffs,
                return_paths=return_paths)
        start = pd.Timestamp(partition.report_date.min())
        end = pd.Timestamp(partition.report_date.max())
        if origin_dates is None:
            origins = self._evaluation_origins(
                start, end, self.cfg.monthly_horizon,
                self.cfg.evaluation_stride if stride_days is None else stride_days)
        else:
            origins = pd.DatetimeIndex(
                pd.to_datetime(list(origin_dates), errors="raise")).normalize()
            if (origins.empty or not origins.is_unique
                    or not origins.is_monotonic_increasing):
                raise ValueError("Explicit forecast origins must be nonempty, unique, and sorted")
            if origins.min() < start - pd.Timedelta(days=1) or origins.max() > end:
                raise ValueError("Explicit forecast origins fall outside the evaluation window")
        rows, path_rows, cases, contexts = [], [], [], []
        feature_groups = {key: group for key, group in featured.groupby(SERIES_KEY, sort=False)}
        market_daily = FeatureBuilder.category_return_history(clean)
        market_daily['category_return'] = market_daily.category_return.fillna(0.0)
        market_histories = {}
        for category, group in market_daily.groupby('product_category', sort=False):
            dates = pd.to_datetime(group.report_date)
            for origin in origins:
                market_histories[(str(category), pd.Timestamp(origin))] = (
                    group.loc[dates <= origin, 'category_return'].to_numpy(dtype=float).tolist())
        product_daily = FeatureBuilder.product_return_history(clean)
        product_daily['product_return'] = product_daily.product_return.fillna(0.0)
        product_market_histories = {}
        for product_key, group in product_daily.groupby(SERIES_KEY[:3], sort=False):
            dates = pd.to_datetime(group.report_date)
            for origin in origins:
                product_market_histories[(tuple(map(str, product_key)), pd.Timestamp(origin))] = (
                    group.loc[dates <= origin, 'product_return'].to_numpy(dtype=float).tolist())
        for key, full_series in clean.groupby(SERIES_KEY, sort=True):
            full_series = full_series.sort_values("report_date")
            actual = full_series.set_index("report_date").observed_price
            for origin in origins:
                history = full_series[full_series.report_date <= origin]
                try:
                    category = str(full_series.product_category.iloc[-1])
                    market_history = market_histories.get((category, pd.Timestamp(origin)), [])
                    product_market_history = product_market_histories.get(
                        (tuple(map(str, key[:3])), pd.Timestamp(origin)), [])
                    prepared = engine._prepare(
                        history, feature_groups[key], market_history,
                        product_market_history)
                except ValueError:
                    continue
                cases.append(prepared)
                last_seven = history.price_index[np.isfinite(history.price_index)].tail(7).to_numpy()
                contexts.append((key, origin, actual, last_seven))
        paths = engine.forecast_many(
            cases, self.cfg.monthly_horizon,
            return_feature_rows=return_feature_rows)
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
                row = {
                    "series": "||".join(map(str, key)), "origin": origin,
                    "date": date, "horizon": h,
                    "actual": float(truth) if np.isfinite(truth) else np.nan,
                    "anchor": path.anchor, "lstm": path.lstm[h - 1],
                    "lgbm": path.lgbm[h - 1], "persistence": persistence,
                    "seasonal7": seasonal[h - 1], "moving_average7": moving_average,
                }
                if getattr(path, "point", None) is not None:
                    row["ensemble_path"] = path.point[h - 1]
                if return_feature_rows:
                    if path.feature_rows is None or len(path.feature_rows) != len(path.dates):
                        raise ValueError("Forecast engine did not return aligned feature rows")
                    row.update(path.feature_rows.iloc[h - 1].to_dict())
                path_rows.append(row)
                if np.isfinite(truth):
                    rows.append(row)
        result = pd.DataFrame(rows)
        if result.empty:
            raise ValueError("No observed labels were available for sampled backtesting")
        if return_paths:
            paths = pd.DataFrame(path_rows)
            if paths.empty:
                raise ValueError("No full forecast paths were generated for backtesting")
            return result, paths
        return result

    @staticmethod
    def _metrics(frame, prediction):
        return compute_all_metrics(frame.actual.to_numpy(),
                                   frame[prediction].to_numpy(),
                                   frame.anchor.to_numpy())

    @staticmethod
    def _targets_met(metrics):
        mape = metrics.get("mape")
        accuracy = metrics.get("within_5_php_accuracy_pct")
        return (
            mape is not None
            and 0 <= mape <= MAPE_TARGET_PERCENT
            and accuracy is not None
            and accuracy >= WITHIN_5_PHP_TARGET_PERCENT
            and all(metrics.get(name) is not None
                    and 0 <= metrics[name] <= PRICE_ERROR_TARGET_PHP
                    for name in ("mae", "rmse"))
        )

    def _attach_validation_quality(self, run_dir, validation, metrics,
                                   validation_paths=None):
        from evaluation.product_confidence import validation_confidence

        identities = sorted(validation.series.astype(str).unique())
        identity_map = {tuple(identity.split("||")): identity for identity in identities}
        metrics["product_confidence_by_identity"] = validation_confidence(
            run_dir, identity_map, forecast_paths=validation_paths)
        product_metrics = {}
        for identity, rows in validation.groupby("series", sort=True):
            result = self._metrics(rows, "ensemble")
            product_metrics[str(identity)] = {
                "mae": result["mae"], "rmse": result["rmse"], "mape": result["mape"],
                "sample_count": result["n"],
                "sample_origin_count": int(rows.origin.nunique()),
                "sample_basis": "observed_validation_targets_across_forecast_steps",
                "prediction_success": result["prediction_success"],
                "within_5_php_count": result["within_5_php_count"],
                "within_5_php_sample_count": result["within_5_php_sample_count"],
                "within_5_php_accuracy_pct": result["within_5_php_accuracy_pct"],
                "within_5_percent_count": result["within_5_percent_count"],
                "within_5_percent_sample_count": result["within_5_percent_sample_count"],
                "within_5_percent_accuracy_pct": result["within_5_percent_accuracy_pct"],
                "evaluation_source": "chronological_validation",
            }
        metrics["product_validation_metrics_by_identity"] = product_metrics

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
        origins = self._evaluation_origins(
            validation.report_date.min(), validation.report_date.max(),
            self.cfg.monthly_horizon, self.cfg.evaluation_stride)
        if len(origins) < 3:
            raise ValueError('Validation needs three full forecast origins for separate calibration')
        return validation[validation.report_date <= origins[int(len(origins)*2/3)]]

    @staticmethod
    def _source_asof_cutoff_plan(clean, train):
        """Use end-of-origin-day Manila cutoffs and fit at the train boundary."""
        one_day = pd.Timedelta(days=1)
        final_microsecond = pd.Timedelta(microseconds=1)

        def day_close(value):
            day = pd.Timestamp(value).normalize()
            if day.tzinfo is None:
                day = day.tz_localize("Asia/Manila")
            else:
                day = day.tz_convert("Asia/Manila").normalize()
            return day + one_day - final_microsecond

        cutoffs = {}
        dates = pd.DatetimeIndex(pd.to_datetime(clean.report_date).unique()).sort_values()
        for target_date in dates:
            origin = pd.Timestamp(target_date).normalize() - one_day
            cutoffs[origin.date().isoformat()] = day_close(origin).isoformat()
        fit_cutoff = day_close(train.report_date.max()).isoformat()
        return fit_cutoff, cutoffs

    @staticmethod
    def _validate_source_cutoff_timeline(clean, train, tuning_partition,
                                         fit_source_cutoff, cutoffs):
        """Fail fast unless every source vintage respects fit and forecast time."""
        fit_time = pd.Timestamp(fit_source_cutoff)
        if fit_time.tzinfo is None:
            raise ValueError("Fit source cutoff must include a timezone")
        fit_time_utc = fit_time.tz_convert("UTC")
        origin_times = {}
        for target_date in pd.DatetimeIndex(
                pd.to_datetime(clean.report_date).unique()).sort_values():
            origin = pd.Timestamp(target_date) - pd.Timedelta(days=1)
            origin_key = origin.date().isoformat()
            if origin_key not in cutoffs:
                raise ValueError(
                    f"Missing source-availability cutoff for training origin {origin_key}")
            origin_time = pd.Timestamp(cutoffs[origin_key])
            if origin_time.tzinfo is None:
                raise ValueError(
                    f"Source cutoff for {origin_key} must include a timezone")
            if origin_time.tz_convert("Asia/Manila").date() != origin.date():
                raise ValueError(
                    f"Source cutoff for {origin_key} must fall on that Manila origin date")
            origin_times[origin_key] = origin_time.tz_convert("UTC")

        for target_date in pd.DatetimeIndex(
                pd.to_datetime(train.report_date).unique()):
            origin_key = (pd.Timestamp(target_date) - pd.Timedelta(days=1)).date().isoformat()
            if origin_times[origin_key] > fit_time_utc:
                raise ValueError(
                    f"Training origin {origin_key} uses report dates after the model fit cutoff")

        first_validation_origin = (
            pd.Timestamp(tuning_partition.report_date.min()) - pd.Timedelta(days=1))
        first_key = first_validation_origin.date().isoformat()
        if first_key not in origin_times:
            raise ValueError(f"Missing validation source cutoff for {first_key}")
        if fit_time_utc > origin_times[first_key]:
            raise ValueError(
                "Model fit source cutoff is after the first validation forecast origin")

    def _active_champion_metrics(self, clean, test, fingerprint, split,
                                 source_availability_cutoffs=None):
        """Evaluate the active model on the candidate's test window when needed."""
        try:
            active_dir = self.store.active_path()
        except FileNotFoundError:
            return None
        metadata = json.loads((active_dir / "metadata.json").read_text(encoding="utf-8"))
        active_stride = metadata.get("metrics", {}).get("evaluation_stride_days")
        if (source_availability_cutoffs is None
                and metadata.get("data_fingerprint") == fingerprint
                and metadata.get("split") == _jsonable(split)
                and active_stride == self.cfg.evaluation_stride
                and metadata.get("metrics", {}).get("evaluation_origin_policy")
                == EVALUATION_ORIGIN_POLICY):
            stored_metrics = metadata.get("metrics", {}).get("test", {}).get("ensemble", {})
            if "within_5_php_accuracy_pct" in stored_metrics:
                return {
                    "run_id": active_dir.name,
                    "ensemble": stored_metrics,
                    "evaluation": "reused_identical_frozen_test",
                }
            saved_test = active_dir / "test_forecasts.csv"
            if (saved_test.exists()
                    and len(pd.read_csv(saved_test)) == stored_metrics.get("n")):
                forecasts = pd.read_csv(saved_test)
                if {"actual", "ensemble"}.issubset(forecasts.columns):
                    return {
                        "run_id": active_dir.name,
                        "ensemble": self._metrics(forecasts, "ensemble"),
                        "evaluation": "recomputed_from_identical_saved_test_rows",
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
            forecasts = self._backtest(
                clean, featured, test, engine,
                source_availability_cutoffs=source_availability_cutoffs)
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

    def _train(self, raw, activate=True, source_as_of=False, fit_source_cutoff=None,
               source_availability_cutoffs=None,
               lgbm_sample_weight_half_life_days=None):
        # Keep lightweight callers that construct a pipeline via ``__new__``
        # backward-compatible with the pre-role trainer contract.
        if not hasattr(self, 'lgbm_role'):
            self.lgbm_role = 'direct'
        assert_no_pending_holdout_rows(raw, pending_holdout_window())
        explicit_cutoff_plan = (fit_source_cutoff is not None
                                or source_availability_cutoffs is not None)
        if source_as_of and explicit_cutoff_plan:
            raise ValueError(
                "Choose either the generated source-as-of cutoff plan or explicit cutoffs")
        strict_sources = (source_as_of or fit_source_cutoff is not None
                          or source_availability_cutoffs is not None)
        if strict_sources and (fit_source_cutoff is None
                               or source_availability_cutoffs is None) and not source_as_of:
            raise ValueError(
                "Point-in-time training requires both fit and per-origin source cutoffs")
        self._training_availability_mode = (
            "source_as_of" if strict_sources else "report_date_causal")
        clean = self.preprocessor.validate(raw)
        train, validation, test = self.preprocessor.split_three(
            clean, self.cfg.validation_size, self.cfg.test_size)
        tuning_partition = self._tuning_partition(validation)
        if strict_sources:
            if source_as_of:
                fit_source_cutoff, source_availability_cutoffs = (
                    self._source_asof_cutoff_plan(clean, train))
                self._source_cutoff_policy = "end_of_origin_day_Asia/Manila_v1"
            else:
                self._source_cutoff_policy = "caller_supplied_instants"
            self._validate_source_cutoff_timeline(
                clean, train, tuning_partition, fit_source_cutoff,
                source_availability_cutoffs)
            fit_label_mask, _ = (
                self.preprocessor.source_target_availability(train, fit_source_cutoff))
            if not fit_label_mask.any():
                raise ValueError(
                    "Report-date training has no observed labels available by the fit cutoff")
        run_dir = self.store.begin_run()
        log.info("Training candidate bundle %s", run_dir.name)
        # Preserve the exact input vintage even when fitting or evaluation fails.
        capture_snapshot(run_dir, raw, self._fingerprint(raw), self._fingerprint)
        split = {"train": self._partition_bounds(train),
                 "validation": self._partition_bounds(validation),
                 "test": self._partition_bounds(test)}

        builder = FeatureBuilder(
            run_dir, feature_version=self.feature_version).fit(train)
        feature_columns = builder.feature_columns
        feature_audit = None
        if strict_sources:
            featured, feature_audit = self._source_asof_training_features(
                clean, builder, source_availability_cutoffs,
                through_date=tuning_partition.report_date.max())
            available_train_labels = train.loc[
                fit_label_mask, SERIES_KEY + ["report_date"]].copy()
            available_train_labels["_fit_label_available"] = True
            featured = featured.merge(
                available_train_labels, on=SERIES_KEY + ["report_date"],
                how="left", validate="one_to_one", sort=False)
            featured["_fit_label_available"] = featured[
                "_fit_label_available"].fillna(False).astype(bool)
        else:
            featured = builder.transform(clean)
        train_mask = featured.report_date.between(train.report_date.min(), train.report_date.max())
        val_mask = featured.report_date.between(tuning_partition.report_date.min(), tuning_partition.report_date.max())
        train_rows = train_mask & usable_targets(featured, feature_columns)
        if strict_sources:
            train_rows &= featured["_fit_label_available"]
        val_rows = val_mask & usable_targets(featured, feature_columns)
        if not train_rows.any() or not val_rows.any():
            raise ValueError("No finite observed LightGBM targets after causal feature construction")

        train_sample_weight = None
        sample_weight_description = None
        if lgbm_sample_weight_half_life_days is not None:
            half_life = float(lgbm_sample_weight_half_life_days)
            if not np.isfinite(half_life) or half_life <= 0:
                raise ValueError("LGBM sample-weight half-life must be positive and finite")
            train_dates = pd.to_datetime(featured.loc[train_rows, "report_date"])
            age_days = (pd.Timestamp(train.report_date.max()) - train_dates).dt.days
            train_sample_weight = np.exp(
                -np.log(2.0) * age_days.to_numpy(dtype=float) / half_life)
            mean_weight = float(train_sample_weight.mean())
            if not np.isfinite(mean_weight) or mean_weight <= 0:
                raise ValueError("Recency sample weights could not be normalized")
            train_sample_weight /= mean_weight
            sample_weight_description = {
                "method": "exponential_recency_decay",
                "half_life_days": half_life,
                "normalization": "mean training weight equals one",
                "validation_weights": "uniform",
            }

        lstm = LSTMModel(run_dir).fit_scalers(train)
        train_start, train_end = train.report_date.min(), train.report_date.max()
        val_start, val_end = tuning_partition.report_date.min(), tuning_partition.report_date.max()
        residual_partition = tuning_partition
        lstm_early_stopping_end = None
        if self.lgbm_role != 'direct':
            tuning_dates = pd.DatetimeIndex(
                pd.to_datetime(tuning_partition.report_date).unique()).sort_values()
            if len(tuning_dates) < 60:
                raise ValueError(
                    "Residual LightGBM requires at least 60 tuning dates to separate "
                    "LSTM early stopping from residual rollouts")
            lstm_stop_index = max(1, len(tuning_dates) // 3 - 1)
            val_end = tuning_dates[lstm_stop_index]
            lstm_early_stopping_end = pd.Timestamp(val_end)
            residual_partition = tuning_partition.loc[
                tuning_partition.report_date > val_end].copy()
            if residual_partition.empty:
                raise ValueError("No dates remain for out-of-sample residual rollouts")
        train_featured = featured
        anchor_column = None
        if strict_sources:
            train_featured = featured.copy()
            train_featured.loc[~train_featured["_fit_label_available"],
                              "observed_price"] = np.nan
            anchor_column = "forecast_anchor"
        x_train, y_train, train_anchors, _, _ = lstm.build_sequences(
            train_featured, target_start=train_start, target_end=train_end,
            stride=self.cfg.training_sequence_stride, anchor_column=anchor_column)
        x_val, y_val, val_anchors, _, _ = lstm.build_sequences(
            featured, target_start=val_start, target_end=val_end,
            anchor_column=anchor_column)
        price_huber_delta = getattr(self, 'lstm_price_huber_delta', None)
        tolerance_huber_delta = getattr(
            self, 'lstm_price_tolerance_huber_delta', None)
        relative_tolerance_huber_delta = getattr(
            self, 'lstm_relative_tolerance_huber_delta', None)
        if sum(value is not None for value in (
                price_huber_delta, tolerance_huber_delta,
                relative_tolerance_huber_delta)) > 1:
            raise ValueError("Choose only one specialized LSTM loss")
        if all(value is None for value in (
                price_huber_delta, tolerance_huber_delta,
                relative_tolerance_huber_delta)):
            relative_lstm_metrics = lstm.train(x_train, y_train, x_val, y_val)
        elif price_huber_delta is not None:
            relative_lstm_metrics = lstm.train(
                x_train, y_train, x_val, y_val,
                train_anchors=train_anchors, val_anchors=val_anchors,
                price_huber_delta=price_huber_delta)
        elif tolerance_huber_delta is not None:
            relative_lstm_metrics = lstm.train(
                x_train, y_train, x_val, y_val,
                train_anchors=train_anchors, val_anchors=val_anchors,
                price_tolerance_huber_delta=tolerance_huber_delta)
        else:
            relative_lstm_metrics = lstm.train(
                x_train, y_train, x_val, y_val,
                relative_tolerance_huber_delta=relative_tolerance_huber_delta)

        if self.lgbm_role == 'direct':
            lgbm = LightGBMModel(run_dir, feature_version=builder.feature_version)
            lgbm_metrics = lgbm.train(
                featured.loc[train_rows, feature_columns],
                featured.loc[train_rows, "observed_price"],
                featured.loc[val_rows, feature_columns],
                featured.loc[val_rows, "observed_price"],
                train_sample_weight=train_sample_weight,
                sample_weight_description=sample_weight_description)
        else:
            if strict_sources:
                raise ValueError(
                    "Residual LightGBM role requires an explicit source-as-of OOF plan")
            lgbm, lgbm_metrics = self._fit_residual_lightgbm(
                run_dir, clean, featured, builder, lstm, residual_partition,
                lstm_early_stopping_end)

        return self._finish_candidate(
            raw, clean, featured, train, validation, test, split, run_dir,
            builder, lgbm, lstm, lgbm_metrics, relative_lstm_metrics, activate,
            fit_source_cutoff=fit_source_cutoff,
            source_availability_cutoffs=source_availability_cutoffs,
            training_feature_audit=feature_audit,
            label_filtering_applied=bool(strict_sources),
            final_refit_data=clean if not strict_sources else None,
            final_refit_skip_reason=(
                "point_in_time_source_mode_requires_a_separate_final_cutoff_plan"
                if strict_sources else None))

    def _fit_residual_lightgbm(self, run_dir, clean, featured, builder, lstm,
                               validation_partition, lstm_early_stopping_end=None):
        """Fit residuals on recursive, out-of-sample LSTM forecast paths.

        The LSTM early-stopping labels end before this partition. A base-only
        recursive replay then generates both the LSTM predictions and the
        features LightGBM will receive at each forecast lead. Residual fitting
        and early stopping are chronological; training labels are purged at the
        first residual-validation origin.
        """
        if lstm_early_stopping_end is None:
            raise ValueError(
                "Residual LightGBM requires a disjoint LSTM early-stopping cutoff")

        class LSTMBaseOnly:
            _feature_names = list(builder.feature_columns)

            @staticmethod
            def predict(features, base_prediction=None):
                if base_prediction is None:
                    raise ValueError("Base-only rollout requires LSTM predictions")
                return np.asarray(base_prediction, dtype=float)

        base_engine = ForecastEngine(LSTMBaseOnly(), lstm, None, builder)
        _, residual_paths = self._backtest(
            clean, featured, validation_partition, base_engine,
            return_paths=True, return_feature_rows=True, stride_days=7)
        residual_rows = residual_paths.loc[
            np.isfinite(residual_paths.actual)
            & np.isfinite(residual_paths.lstm)
        ].copy()
        if residual_rows.empty:
            raise ValueError("Residual LightGBM has no observed recursive LSTM targets")
        residual_rows['origin'] = pd.to_datetime(residual_rows.origin)
        residual_rows['date'] = pd.to_datetime(residual_rows.date)
        if residual_rows.origin.min() < pd.Timestamp(lstm_early_stopping_end):
            raise ValueError("Residual rollout overlaps LSTM early-stopping dates")
        base_feature_columns = list(builder.feature_columns)
        usable = (np.isfinite(
            residual_rows[base_feature_columns].to_numpy(dtype=float)).all(axis=1)
                  & np.isfinite(residual_rows[['actual', 'lstm']].to_numpy(dtype=float)).all(axis=1))
        residual_rows = residual_rows.loc[usable].copy()
        lgbm = LightGBMModel(
            run_dir, feature_version=builder.feature_version,
            target_mode=self.lgbm_role)
        if lgbm.residual_feature_schema == RESIDUAL_FEATURE_SCHEMA:
            anchor = pd.to_numeric(
                residual_rows['price_lag_1d'], errors='coerce').to_numpy(float)
            if not np.isfinite(anchor).all() or (anchor <= 0).any():
                raise ValueError("Residual OOF features require positive finite anchors")
            residual_rows['lstm_base_relative_change'] = (
                residual_rows['lstm'].to_numpy(float) / anchor - 1.0)
            lead_denominator = max(1, int(self.cfg.monthly_horizon) - 1)
            residual_rows['forecast_lead_fraction'] = (
                (residual_rows['horizon'].to_numpy(float) - 1.0)
                / lead_denominator).clip(0.0, 1.0)
        feature_columns = list(lgbm._feature_names)
        feature_usable = np.isfinite(
            residual_rows[feature_columns].to_numpy(dtype=float)).all(axis=1)
        residual_rows = residual_rows.loc[feature_usable].copy()
        origins = pd.DatetimeIndex(residual_rows.origin.unique()).sort_values()
        if len(origins) < 4:
            raise ValueError(
                "Residual LightGBM requires four or more recursive validation origins")
        validation_origin = origins[len(origins) * 2 // 3]
        # A training target may be known at the first validation origin, but no
        # later target label can influence LightGBM early stopping.
        fit_rows = residual_rows.loc[
            (residual_rows.origin < validation_origin)
            & (residual_rows.date <= validation_origin)].copy()
        val_rows = residual_rows.loc[
            residual_rows.origin >= validation_origin].copy()
        if fit_rows.empty or val_rows.empty:
            raise ValueError("Residual LightGBM chronological fit/validation is empty")
        metrics = lgbm.train(
            fit_rows[feature_columns], fit_rows['actual'],
            val_rows[feature_columns], val_rows['actual'],
            base_train_prediction=fit_rows['lstm'],
            base_val_prediction=val_rows['lstm'])
        selected_iteration = int(lgbm.training_configuration['best_iteration'])
        lgbm.refit_fixed_rounds(
            residual_rows[feature_columns], residual_rows['actual'],
            base_prediction=residual_rows['lstm'],
            num_boost_round=selected_iteration)
        self._residual_training_provenance = {
            'role': self.lgbm_role,
            'base_prediction': 'recursive_lstm_only_rollout',
            'feature_state': 'causal_recursive_lstm_predictions_at_each_lead',
            'inference_feature_state': 'causal_recursive_lstm_predictions_at_each_lead',
            'residual_feature_schema': lgbm.residual_feature_schema,
            'uses_lstm_base_relative_change_feature': (
                'lstm_base_relative_change' in feature_columns),
            'uses_forecast_lead_feature': 'forecast_lead_fraction' in feature_columns,
            'lstm_early_stopping_end': pd.Timestamp(
                lstm_early_stopping_end).isoformat(),
            'origin_stride_days': 7,
            'rows': int(len(residual_rows)),
            'fit_rows': int(len(fit_rows)),
            'validation_rows': int(len(val_rows)),
            'final_fit_rows': int(len(residual_rows)),
            'selected_iteration': selected_iteration,
            'final_fit_target_start': pd.Timestamp(residual_rows.date.min()).isoformat(),
            'final_fit_target_end': pd.Timestamp(residual_rows.date.max()).isoformat(),
            'fit_origin_start': pd.Timestamp(fit_rows.origin.min()).isoformat(),
            'fit_origin_end': pd.Timestamp(fit_rows.origin.max()).isoformat(),
            'fit_target_end': pd.Timestamp(fit_rows.date.max()).isoformat(),
            'validation_origin_start': pd.Timestamp(val_rows.origin.min()).isoformat(),
            'validation_target_start': pd.Timestamp(val_rows.date.min()).isoformat(),
            'validation_horizons': sorted(
                residual_rows.horizon.astype(int).unique().tolist()),
            'first_validation_origin': pd.Timestamp(validation_origin).isoformat(),
        }
        return lgbm, metrics

    def _model_configuration(self, run_dir, lgbm, lstm):
        ensemble = json.loads((run_dir / "ensemble.json").read_text(encoding="utf-8"))
        lgbm_config = {
            "feature_version": int(lgbm._feature_version),
            "features": list(lgbm._feature_names),
            "target_mode": lgbm.target_mode,
            "training": lgbm.training_configuration,
        }
        lstm_config = {
            "features": list(lstm.feature_cols),
            "scaled_features": list(lstm.scaled_features),
            "sequence_length": int(lstm.seq_len),
            "horizon": int(lstm.horizon),
            "hidden_size": int(lstm.hidden),
            "layers": int(lstm.layers),
            "dropout": float(lstm.dropout),
            "training": lstm.training_configuration,
        }
        return {
            "schema_version": 1,
            "training_details_status": (
                "complete" if lgbm.training_configuration is not None
                and lstm.training_configuration is not None else "legacy_or_partial"),
            "pipeline": {
                "random_seed": int(self.cfg.random_seed),
                "validation_size": float(self.cfg.validation_size),
                "test_size": float(self.cfg.test_size),
                "max_fill_days": int(self.cfg.max_fill_days),
                "training_sequence_stride": int(self.cfg.training_sequence_stride),
                "evaluation_stride_days": int(self.cfg.evaluation_stride),
                "evaluation_origin_policy": EVALUATION_ORIGIN_POLICY,
                "training_availability_mode": getattr(
                    self, "_training_availability_mode", "report_date_causal"),
                "lightgbm_role": self.lgbm_role,
                "feature_columns": list(lgbm._feature_names),
            },
            "lightgbm": lgbm_config,
            "residual_training": self._residual_training_provenance,
            "lstm": lstm_config,
            "ensemble": {
                "artifact": "ensemble.json",
                "objective": ensemble.get("objective"),
            "weight_selection_objective": ensemble.get("weight_selection_objective", "balanced"),
                "calibration": ensemble.get("calibration"),
            },
        }

    def _refit_final_direct_models(self, clean, run_dir, builder, lgbm, lstm):
        """Refit selected direct models on all pre-origin observed history.

        The caller runs this only after chronological validation and diagnostic
        test forecasts have been saved. The test rows are therefore not used to
        select the ensemble or stop either model, but may be included in the
        final production fit when they precede the forecast origin.
        """
        if self.lgbm_role != 'direct':
            return builder, {
                "status": "skipped",
                "reason": "residual_model_requires_a_matched_oof_lstm_refit",
            }
        if clean is None or clean.empty:
            return builder, {"status": "skipped", "reason": "no_final_refit_data"}
        assert_no_pending_holdout_rows(clean, pending_holdout_window())
        config = lstm.training_configuration or {}
        selected_epoch = config.get("selected_epoch")
        if selected_epoch is None or int(selected_epoch) <= 0:
            raise ValueError(
                "Final LSTM refit requires an epoch selected by chronological validation")
        lgbm_config = lgbm.training_configuration or {}
        selected_rounds = lgbm_config.get("best_iteration")
        if selected_rounds is None or int(selected_rounds) <= 0:
            raise ValueError(
                "Final LightGBM refit requires rounds selected by chronological validation")

        # Refit categorical mappings only from data available at the forecast
        # origin, then rebuild causal features with those mappings.
        builder.fit(clean)
        featured = builder.transform(clean)
        feature_columns = list(builder.feature_columns)
        lgbm_rows = usable_targets(featured, feature_columns)
        if not lgbm_rows.any():
            raise ValueError("Final LightGBM refit has no eligible observed rows")
        lgbm_weights = None
        weight_config = lgbm_config.get("sample_weighting")
        if weight_config:
            half_life = float(weight_config.get("half_life_days", 0))
            if (weight_config.get("method") != "exponential_recency_decay"
                    or not np.isfinite(half_life) or half_life <= 0):
                raise ValueError("Unsupported LightGBM final-refit weighting policy")
            fit_dates = pd.to_datetime(featured.loc[lgbm_rows, "report_date"])
            age_days = (pd.Timestamp(clean.report_date.max()) - fit_dates).dt.days
            lgbm_weights = np.exp(-np.log(2.0) * age_days.to_numpy(float) / half_life)
            lgbm_weights /= lgbm_weights.mean()
        lgbm.refit_fixed_rounds(
            featured.loc[lgbm_rows, feature_columns],
            featured.loc[lgbm_rows, "observed_price"],
            num_boost_round=int(selected_rounds), sample_weight=lgbm_weights)

        start, end = clean.report_date.min(), clean.report_date.max()
        x_all, y_all, anchors, _, _ = lstm.build_sequences(
            featured, target_start=start, target_end=end,
            stride=self.cfg.training_sequence_stride)
        if not len(x_all):
            raise ValueError("Final LSTM refit has no eligible observed sequences")
        history_path = run_dir / "lstm_history.json"
        history = json.loads(history_path.read_text(encoding="utf-8"))
        selected_schedule = [
            float(row["lr"]) for row in history
            if int(row["epoch"]) <= int(selected_epoch)
        ]
        if len(selected_schedule) != int(selected_epoch):
            selected_schedule = [float(lstm.lr)] * int(selected_epoch)
        price_huber_delta = getattr(self, "lstm_price_huber_delta", None)
        tolerance_huber_delta = getattr(
            self, "lstm_price_tolerance_huber_delta", None)
        relative_tolerance_huber_delta = getattr(
            self, "lstm_relative_tolerance_huber_delta", None)
        if sum(value is not None for value in (
                price_huber_delta, tolerance_huber_delta,
                relative_tolerance_huber_delta)) > 1:
            raise ValueError("Choose only one specialized LSTM loss")
        lstm_refit = lstm.refit_fixed_epochs(
            x_all, y_all, epochs=int(selected_epoch),
            learning_rate_schedule=selected_schedule,
            train_anchors=(anchors if price_huber_delta is not None
                           or tolerance_huber_delta is not None else None),
            price_huber_delta=price_huber_delta,
            price_tolerance_huber_delta=tolerance_huber_delta,
            relative_tolerance_huber_delta=relative_tolerance_huber_delta)
        provenance = {
            "status": "completed",
            "strategy": "selected_configuration_refit_on_all_pre_origin_data",
            "training_start": pd.Timestamp(start).date().isoformat(),
            "training_end": pd.Timestamp(end).date().isoformat(),
            "observed_lightgbm_rows": int(lgbm_rows.sum()),
            "lstm_sequences": int(len(x_all)),
            "lstm_observed_targets": int(np.isfinite(y_all).sum()),
            "lstm_selected_epochs": int(selected_epoch),
            "lightgbm_selected_rounds": int(selected_rounds),
            "test_metrics_scope": "chronological_selection_fit_before_final_refit",
            "forecast_holdout_rows_included": False,
            "lstm_refit": lstm_refit,
        }
        return builder, provenance

    def _finish_candidate(self, raw, clean, featured, train, validation, test,
                          split, run_dir, builder, lgbm, lstm, lgbm_metrics,
                          relative_lstm_metrics, activate,
                          base_model_scope='calibration_excluded_from_early_stopping',
                          fit_source_cutoff=None, source_availability_cutoffs=None,
                          training_feature_audit=None, label_filtering_applied=False,
                          final_refit_data=None, final_refit_skip_reason=None):
        residual_role = bool(getattr(lgbm, 'is_residual_model', False))
        ensemble = EnsembleModel(run_dir) if residual_role else None
        if residual_role:
            ensemble.weights = np.ones(self.cfg.monthly_horizon, dtype=float)
            ensemble.trust_weights = np.ones(self.cfg.monthly_horizon, dtype=float)
            ensemble.category_trust_weights = {}
            ensemble.specialist_blends = {}
            ensemble.anomaly_threshold = 1e9
            ensemble.anomaly_strength = 0.0
            ensemble.anomaly_decay = 1.0
            ensemble.objective = self.ensemble_objective
            ensemble.calibration = {
                'scope': 'held_out_from_residual_fit',
                'base_model_scope': base_model_scope,
                'purpose': 'product_confidence_reliability',
            }
        raw_engine = ForecastEngine(lgbm, lstm, ensemble, builder)
        validation_forecasts, validation_paths = self._backtest(
            clean, featured, validation, raw_engine, return_paths=True,
            source_availability_cutoffs=source_availability_cutoffs)
        tuning, calibration = self._split_forecasts(
            validation_forecasts, cutoff=self._tuning_partition(validation).report_date.max())
        if residual_role:
            ensemble.calibration.update({
                'sample_count': int(len(calibration)),
                'start': str(pd.Timestamp(calibration.date.min())),
                'end': str(pd.Timestamp(calibration.date.max())),
            })
        else:
            ensemble = EnsembleModel(run_dir).fit(
                tuning, self.cfg.monthly_horizon, calibration_frame=calibration,
                objective=self.ensemble_objective)
            ensemble.calibration['base_model_scope'] = base_model_scope
        ensemble.save()
        validation_forecasts["ensemble"] = ensemble.predict_rows(
            validation_forecasts.lstm.to_numpy(), validation_forecasts.lgbm.to_numpy(),
            validation_forecasts.horizon.to_numpy(), validation_forecasts.anchor.to_numpy(),
            validation_forecasts.series.to_numpy(),
            validation_forecasts.moving_average7.to_numpy())
        validation_paths["ensemble"] = ensemble.predict_rows(
            validation_paths.lstm.to_numpy(), validation_paths.lgbm.to_numpy(),
            validation_paths.horizon.to_numpy(), validation_paths.anchor.to_numpy(),
            validation_paths.series.to_numpy(),
            validation_paths.moving_average7.to_numpy())

        frozen_engine = ForecastEngine(lgbm, lstm, ensemble, builder)
        test_forecasts, test_paths = self._backtest(
            clean, featured, test, frozen_engine, return_paths=True,
            source_availability_cutoffs=source_availability_cutoffs)
        test_forecasts["ensemble"] = ensemble.predict_rows(
            test_forecasts.lstm.to_numpy(), test_forecasts.lgbm.to_numpy(),
            test_forecasts.horizon.to_numpy(), test_forecasts.anchor.to_numpy(),
            test_forecasts.series.to_numpy(), test_forecasts.moving_average7.to_numpy())
        test_paths["ensemble"] = ensemble.predict_rows(
            test_paths.lstm.to_numpy(), test_paths.lgbm.to_numpy(),
            test_paths.horizon.to_numpy(), test_paths.anchor.to_numpy(),
            test_paths.series.to_numpy(), test_paths.moving_average7.to_numpy())
        final_refit = {"status": "skipped", "reason": final_refit_skip_reason}
        if final_refit_data is not None:
            builder, final_refit = self._refit_final_direct_models(
                final_refit_data, run_dir, builder, lgbm, lstm)
        if final_refit.get("status") == "completed":
            ensemble.calibration.update({
                "final_model_refit_scope": final_refit["strategy"],
                "calibration_base_model_scope": "pre_refit_chronological_selection_fit",
            })
            ensemble.save()
        observed = clean.loc[clean.is_observed, "report_date"]
        training_source_audit = self._training_source_audit(
            train, available_through=fit_source_cutoff,
            feature_audit=training_feature_audit,
            label_filtering_applied=label_filtering_applied)
        if source_availability_cutoffs is not None:
            training_source_audit["source_cutoff_manifest"] = (
                self._write_source_cutoff_manifest(
                    run_dir, clean, fit_source_cutoff, source_availability_cutoffs))
        source_data = {
            **self._source_row_audit(raw),
            "processed_from": (
                pd.Timestamp(observed.min()).date().isoformat() if not observed.empty else None
            ),
            "processed_through": (
                pd.Timestamp(observed.max()).date().isoformat() if not observed.empty else None
            ),
            "observed_rows": int(clean.is_observed.sum()),
            "series_count": int(clean.groupby(SERIES_KEY).ngroups),
            "training_report_date_availability": training_source_audit,
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
            "source_data": source_data,
            "validation_samples": int(len(validation_forecasts)),
            "test_samples": int(len(test_forecasts)),
            "validation_path_samples": int(len(validation_paths)),
            "test_path_samples": int(len(test_paths)),
            "final_model_refit": final_refit,
            "evaluation_stride_days": self.cfg.evaluation_stride,
            "evaluation_origin_policy": EVALUATION_ORIGIN_POLICY,
            "evaluation_scope": (
                "report-date-as-of training and evaluation with fit-time label filtering"
                if source_availability_cutoffs is not None else
                "report-date chronological backtest; report_date is assumed available "
                "by the end of that date in Asia/Manila"
            ),
            "point_in_time_training_verified": bool(
                training_source_audit["point_in_time_training_verified"]),
            "trained_at": datetime.now(timezone.utc).isoformat(),
        }
        fingerprint = self._fingerprint(raw)
        champion = self._active_champion_metrics(
            clean, test, fingerprint, split,
            source_availability_cutoffs=source_availability_cutoffs)
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
            "point_in_time_training_verified": bool(
                training_source_audit["point_in_time_training_verified"]),
            "blocked_reason": (
                "No independent frozen final-holdout evidence is available; report_date "
                "is a proxy for source publication time."
            ),
            "target_met_on_development_rows": self._targets_met(
                metrics["test"]["ensemble"]),
            "beats_persistence": bool(beats_baseline),
            "beats_active_champion": beats_champion,
            "active_champion": champion,
            "rule": (
                "Retrospective comparisons are diagnostic. Activation requires "
                "independent frozen final-holdout pooled and per-horizon "
                "Within-5-PHP accuracy >= 95%, MAPE <= 5%, and MAE/RMSE <= PHP 5, "
                "validated selection provenance and declared product coverage."
            ),
        }
        validation_forecasts.to_csv(run_dir / "validation_forecasts.csv", index=False)
        test_forecasts.to_csv(run_dir / "test_forecasts.csv", index=False)
        validation_paths.to_csv(run_dir / "validation_paths.csv", index=False)
        test_paths.to_csv(run_dir / "test_paths.csv", index=False)
        self._attach_validation_quality(
            run_dir, validation_forecasts, metrics, validation_paths)
        model_configuration = self._model_configuration(run_dir, lgbm, lstm)
        snapshot_manifest = capture_snapshot(
            run_dir, raw, fingerprint, self._fingerprint)
        model_configuration["pipeline"]["source_snapshot"] = {
            "file": SOURCE_SNAPSHOT_FILE,
            "manifest": SOURCE_MANIFEST_FILE,
            "sha256": snapshot_manifest["sha256"],
            "row_count": snapshot_manifest["row_count"],
            "report_date_min": snapshot_manifest["report_date_min"],
            "report_date_max": snapshot_manifest["report_date_max"],
            "scope": "raw_training_and_evaluation_input_before_preprocessing",
        }
        run_id = self.store.finalize(
            run_dir, _jsonable(metrics), split, fingerprint,
            activate=bool(activate and passed),
            model_configuration=model_configuration,
            preprocessing_contract=self.preprocessor.preprocessing_contract())
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
        beats_champion = (
            None if champion_metrics is None else
            TrainingPipeline._improves_all_by(
                test_metrics["ensemble"], champion_metrics, .05))
        development_passed = bool(beats_persistence and beats_champion is True)
        return beats_persistence, beats_champion, development_passed

    @staticmethod
    def _improves_all(candidate, reference):
        within_5_nonregression = (
            candidate.get("within_5_php_accuracy_pct") is not None
            and reference.get("within_5_php_accuracy_pct") is not None
            and candidate["within_5_php_accuracy_pct"]
                >= reference["within_5_php_accuracy_pct"])
        return within_5_nonregression and all(
            candidate.get(name) is not None and reference.get(name) is not None
            and candidate[name] < reference[name]
            for name in ("mae", "rmse", "mape"))

    @staticmethod
    def _improves_all_by(candidate, reference, fraction):
        within_5_nonregression = (
            candidate.get("within_5_php_accuracy_pct") is not None
            and reference.get("within_5_php_accuracy_pct") is not None
            and candidate["within_5_php_accuracy_pct"]
                >= reference["within_5_php_accuracy_pct"])
        return within_5_nonregression and all(
            candidate.get(name) is not None and reference.get(name) is not None
            and candidate[name] <= reference[name] * (1 - fraction)
            for name in ("mae", "rmse", "mape"))
