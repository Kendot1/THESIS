"""Leakage-safe training, calibration, and frozen holdout evaluation."""
import hashlib
import json
import shutil
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from config.settings import get_settings
from data.fetcher import DataFetcher
from data.preprocessor import DataPreprocessor, SERIES_KEY, source_date
from features.builder import CausalFeatureState, FEATURE_COLUMNS, FeatureBuilder, usable_targets
from models.ensemble import EnsembleModel
from models.forecast_engine import ForecastEngine
from models.lightgbm_model import LightGBMModel
from models.lstm_model import LSTMModel
from models.model_store import ModelStore
from utils.logger import get_logger
from utils.metrics import compute_all_metrics

log = get_logger(__name__)
EVALUATION_ORIGIN_POLICY = "fixed_stride_plus_partition_terminal_v1"
WITHIN_10_TARGET_PERCENT = 90.0
PRICE_ERROR_TARGET_PHP = 5.0


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

    def run_full_training(self, raw_df=None, activate=True, *, source_as_of=False,
                          fit_source_cutoff=None, source_availability_cutoffs=None):
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
        raw = self.fetcher.fetch_all() if raw_df is None else raw_df
        if raw.empty:
            raise ValueError("No training data")
        return self._train(
            raw, activate=activate,
            source_as_of=source_as_of,
            fit_source_cutoff=fit_source_cutoff,
            source_availability_cutoffs=source_availability_cutoffs)

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
        if "within_10_accuracy_pct" not in parent_test:
            saved_test = parent_dir / "test_forecasts.csv"
            if saved_test.exists():
                parent_test = self._metrics(pd.read_csv(saved_test), "ensemble")
        run_dir = self.store.begin_run()
        for name in ["categorical_mappings.json", "lightgbm_model.txt",
                     "lightgbm_meta.json", "lstm_model.pt", "lstm_meta.json",
                     "lstm_history.json"]:
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
        beats_champion = True
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
            beats_champion = comparable and self._improves_all_by(
                metrics['test']['ensemble'], active['metrics']['test']['ensemble'], .05)
            if comparable and not beats_champion:
                stored_metrics = active.get("metrics", {}).get("test", {}).get("ensemble", {})
                saved_test = active_path / "test_forecasts.csv"
                if ("within_10_accuracy_pct" not in stored_metrics and saved_test.exists()
                        and len(pd.read_csv(saved_test)) == stored_metrics.get("n")):
                    active_test = self._metrics(pd.read_csv(saved_test), "ensemble")
                    beats_champion = self._improves_all_by(
                        metrics["test"]["ensemble"], active_test, .05)
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
            "target_met_on_development_rows": self._targets_met(
                metrics["test"]["ensemble"]),
            "beats_persistence": bool(beats_persistence),
            "beats_parent": bool(beats_parent),
            "beats_active_champion": bool(beats_champion),
            "active_champion": champion,
            "rule": (
                "Retrospective comparisons are diagnostic. Activation requires "
                "independent frozen final-holdout Within-10 >= 90%, MAE/RMSE <= PHP 5, "
                "MAPE <= 5%, "
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
                            model_configuration=model_configuration)
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
            for _, series in input_view.groupby(SERIES_KEY, sort=True):
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

            for key, full_series in input_view.groupby(SERIES_KEY, sort=True):
                history = full_series[full_series.report_date <= origin].sort_values("report_date")
                usable_history = history.loc[np.isfinite(history.price_index)]
                if usable_history.empty or pd.Timestamp(
                        usable_history.report_date.iloc[-1]) != pd.Timestamp(origin):
                    continue
                market_history = market_histories.get(str(full_series.product_category.iloc[-1]), [])
                try:
                    prepared = engine._prepare(history, feature_groups.get(key), market_history)
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

            target_rows = []
            for _, series in input_view.groupby(SERIES_KEY, sort=True):
                series = series.sort_values("report_date")
                available = series.loc[np.isfinite(series.price_index)]
                if (available.empty
                        or pd.Timestamp(available.report_date.iloc[-1]) != origin):
                    continue
                category = str(series.product_category.iloc[-1])
                state = CausalFeatureState(series, builder.encoder)
                target_row = state.row(
                    target_date, market_histories.get(category, []))
                target_row["forecast_anchor"] = float(available.price_index.iloc[-1])
                target_rows.append(target_row[
                    SERIES_KEY + ["report_date", "forecast_anchor"] + FEATURE_COLUMNS])
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
                 & np.isfinite(featured[FEATURE_COLUMNS]).all(axis=1)).sum()),
            "observed_labels_without_source_anchor_or_features": int(
                (featured.is_observed & ~(
                    featured.forecast_anchor.notna()
                    & np.isfinite(featured[FEATURE_COLUMNS]).all(axis=1))).sum()),
            "origin_cutoffs_from_utc": min(cutoff_times).isoformat() if cutoff_times else None,
            "origin_cutoffs_through_utc": max(cutoff_times).isoformat() if cutoff_times else None,
        }
        return featured, audit

    def _backtest(self, clean, featured, partition, engine, return_paths=False,
                  source_availability_cutoffs=None):
        if source_availability_cutoffs is not None:
            return self._backtest_as_of_sources(
                clean, partition, engine, source_availability_cutoffs,
                return_paths=return_paths)
        start = pd.Timestamp(partition.report_date.min())
        end = pd.Timestamp(partition.report_date.max())
        origins = self._evaluation_origins(
            start, end, self.cfg.monthly_horizon, self.cfg.evaluation_stride)
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
                row = {
                    "series": "||".join(map(str, key)), "origin": origin,
                    "date": date, "horizon": h,
                    "actual": float(truth) if np.isfinite(truth) else np.nan,
                    "anchor": path.anchor, "lstm": path.lstm[h - 1],
                    "lgbm": path.lgbm[h - 1], "persistence": persistence,
                    "seasonal7": seasonal[h - 1], "moving_average7": moving_average,
                }
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
        within_10 = metrics.get("within_10_accuracy_pct")
        return (
            within_10 is not None
            and within_10 >= WITHIN_10_TARGET_PERCENT
            and all(metrics.get(name) is not None
                    and 0 <= metrics[name] <= PRICE_ERROR_TARGET_PHP
                    for name in ("mae", "rmse", "mape"))
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
            if "within_10_accuracy_pct" in stored_metrics:
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
               source_availability_cutoffs=None):
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
        split = {"train": self._partition_bounds(train),
                 "validation": self._partition_bounds(validation),
                 "test": self._partition_bounds(test)}

        builder = FeatureBuilder(run_dir).fit(train)
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
        train_rows = train_mask & usable_targets(featured)
        if strict_sources:
            train_rows &= featured["_fit_label_available"]
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
        train_featured = featured
        anchor_column = None
        if strict_sources:
            train_featured = featured.copy()
            train_featured.loc[~train_featured["_fit_label_available"],
                              "observed_price"] = np.nan
            anchor_column = "forecast_anchor"
        x_train, y_train, _, _, _ = lstm.build_sequences(
            train_featured, target_start=train_start, target_end=train_end,
            stride=self.cfg.training_sequence_stride, anchor_column=anchor_column)
        x_val, y_val, _, _, _ = lstm.build_sequences(
            featured, target_start=val_start, target_end=val_end,
            anchor_column=anchor_column)
        relative_lstm_metrics = lstm.train(x_train, y_train, x_val, y_val)

        return self._finish_candidate(
            raw, clean, featured, train, validation, test, split, run_dir,
            builder, lgbm, lstm, lgbm_metrics, relative_lstm_metrics, activate,
            fit_source_cutoff=fit_source_cutoff,
            source_availability_cutoffs=source_availability_cutoffs,
            training_feature_audit=feature_audit,
            label_filtering_applied=bool(strict_sources))

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
                "feature_columns": list(FEATURE_COLUMNS),
            },
            "lightgbm": lgbm_config,
            "lstm": lstm_config,
            "ensemble": {
                "artifact": "ensemble.json",
                "objective": ensemble.get("objective"),
                "calibration": ensemble.get("calibration"),
            },
        }

    def _finish_candidate(self, raw, clean, featured, train, validation, test,
                          split, run_dir, builder, lgbm, lstm, lgbm_metrics,
                          relative_lstm_metrics, activate,
                          base_model_scope='calibration_excluded_from_early_stopping',
                          fit_source_cutoff=None, source_availability_cutoffs=None,
                          training_feature_audit=None, label_filtering_applied=False):
        raw_engine = ForecastEngine(lgbm, lstm, None, builder)
        validation_forecasts, validation_paths = self._backtest(
            clean, featured, validation, raw_engine, return_paths=True,
            source_availability_cutoffs=source_availability_cutoffs)
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
            "beats_active_champion": bool(beats_champion),
            "active_champion": champion,
            "rule": (
                "Retrospective comparisons are diagnostic. Activation requires "
                "independent frozen final-holdout Within-10 >= 90%, MAE/RMSE <= PHP 5, "
                "MAPE <= 5%, "
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
        run_id = self.store.finalize(
            run_dir, _jsonable(metrics), split, fingerprint,
            activate=bool(activate and passed),
            model_configuration=model_configuration)
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
        within_10 = candidate.get("within_10_accuracy_pct")
        reference_within_10 = reference.get("within_10_accuracy_pct")
        return (
            within_10 is not None and reference_within_10 is not None
            and within_10 > reference_within_10
            and all(candidate.get(name) is not None and reference.get(name) is not None
                    and candidate[name] < reference[name]
                    for name in ("mae", "rmse", "mape"))
        )

    @staticmethod
    def _improves_all_by(candidate, reference, fraction):
        within_10 = candidate.get("within_10_accuracy_pct")
        reference_within_10 = reference.get("within_10_accuracy_pct")
        return (
            within_10 is not None and reference_within_10 is not None
            and within_10 > reference_within_10
            and within_10 >= reference_within_10 * (1 + fraction)
            and all(candidate.get(name) is not None and reference.get(name) is not None
                    and candidate[name] <= reference[name] * (1 - fraction)
                    for name in ("mae", "rmse", "mape"))
        )
