import json
import csv
import tempfile
import unittest
import warnings
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd

from data.preprocessor import DataPreprocessor, SERIES_KEY
from features.builder import FEATURE_COLUMNS, LEGACY_FEATURE_COLUMNS, CausalFeatureState, FeatureBuilder, usable_targets
from models.ensemble import EnsembleModel
from models.forecast_engine import ForecastEngine
from models.lstm_model import LSTMModel
from models.lightgbm_model import LightGBMModel
from models.model_store import ModelStore, REQUIRED_FILES
from pipeline.trainer import TrainingPipeline
from pipeline.prediction_writer import PredictionWriter
from config.settings import get_settings
from utils.metrics import compute_directional_accuracy


def panel(days=100):
    dates = pd.date_range("2025-01-01", periods=days)
    return pd.DataFrame({
        "product_category": "Rice", "product_name": "Rice",
        "product_variant": "Standard", "origin": "NCR", "unit": "kg",
        "report_date": dates, "price_index": 50 + np.sin(np.arange(days) / 7),
        "observed_price": 50 + np.sin(np.arange(days) / 7), "is_observed": True,
    })


def local_builder(data):
    builder = FeatureBuilder()
    builder.encoder._save_mappings = lambda: None
    return builder.fit(data)


class CausalPipelineTests(unittest.TestCase):
    def test_backtest_can_rebuild_features_from_each_report_date_cutoff(self):
        dates = pd.date_range("2026-10-01", periods=4)
        clean = pd.DataFrame({
            "product_category": ["Rice"] * 4, "product_name": ["Rice"] * 4,
            "product_variant": ["Standard"] * 4, "origin": ["NCR"] * 4,
            "unit": ["kg"] * 4, "report_date": dates,
            "price_index": [10.0, 50.0, 80.0, 90.0],
            "observed_price": [10.0, 50.0, 80.0, 90.0],
            "is_observed": [True] * 4,
            "source_pdf": [f"day-{day}.pdf" for day in range(1, 5)],
        })
        partition = clean[clean.report_date.between(dates[1], dates[3])]
        pipeline = TrainingPipeline.__new__(TrainingPipeline)
        pipeline.cfg = SimpleNamespace(monthly_horizon=2, evaluation_stride=2)
        pipeline.preprocessor = DataPreprocessor()
        builder = local_builder(clean)

        class StubEngine:
            def __init__(self, builder):
                self.builder = builder
                self.anchors = []

            def _prepare(self, history, featured_history, market_history):
                self.assert_no_precomputed_features = featured_history is None
                anchor = float(history.price_index.iloc[-1])
                origin = pd.Timestamp(history.report_date.iloc[-1])
                self.anchors.append(anchor)
                return {"anchor": anchor, "origin": origin}

            def forecast_many(self, cases, horizon):
                return [SimpleNamespace(
                    dates=pd.date_range(case["origin"] + pd.Timedelta(days=1), periods=horizon),
                    anchor=case["anchor"], lstm=np.full(horizon, case["anchor"]),
                    lgbm=np.full(horizon, case["anchor"]),
                ) for case in cases]

        engine = StubEngine(builder)
        predictions, paths = pipeline._backtest(
            clean, None, partition, engine, return_paths=True,
            source_availability_cutoffs={
                "2026-10-01": "2026-10-01T23:59:59+08:00",
                "2026-10-02": "2026-10-02T23:59:59+08:00",
            })
        self.assertEqual(engine.anchors, [10.0, 50.0])
        self.assertEqual(len(predictions), 4)
        self.assertEqual(len(paths), 4)
        self.assertIn("report_date_availability_by_origin", paths.attrs)
        self.assertIn(50.0, predictions.actual.tolist())
        self.assertFalse(engine.assert_no_precomputed_features)

    def test_source_as_of_replay_uses_category_peer_returns(self):
        dates = pd.date_range("2026-10-01", periods=4)
        clean = pd.DataFrame([
            {
                "product_category": "Rice", "product_name": name,
                "product_variant": "Standard", "origin": "NCR", "unit": "kg",
                "report_date": date, "price_index": price,
                "observed_price": price, "is_observed": True,
                "source_pdf": f"{name}-{date:%Y%m%d}.pdf",
            }
            for name, prices in {"A": [10., 20., 22., 24.],
                                 "B": [10., 10., 10., 10.]}.items()
            for date, price in zip(dates, prices)
        ])
        clean = DataPreprocessor().validate(clean)
        partition = clean[clean.report_date.between(dates[1], dates[3])]
        pipeline = TrainingPipeline.__new__(TrainingPipeline)
        pipeline.cfg = SimpleNamespace(monthly_horizon=2, evaluation_stride=2)
        pipeline.preprocessor = DataPreprocessor()
        builder = local_builder(clean)

        class StubEngine:
            def __init__(self, builder):
                self.builder = builder
                self.category_lags = []

            def _prepare(self, history, featured_history, market_history):
                origin = pd.Timestamp(history.report_date.iloc[-1])
                first_forecast = featured_history.loc[
                    featured_history.report_date.eq(origin + pd.Timedelta(days=1))]
                self.category_lags.append(float(
                    first_forecast.category_return_lag_1d.iloc[-1]))
                return {"anchor": float(history.price_index.iloc[-1]), "origin": origin}

            def forecast_many(self, cases, horizon):
                return [SimpleNamespace(
                    dates=pd.date_range(case["origin"] + pd.Timedelta(days=1), periods=horizon),
                    anchor=case["anchor"], lstm=np.full(horizon, case["anchor"]),
                    lgbm=np.full(horizon, case["anchor"]),
                ) for case in cases]

        engine = StubEngine(builder)
        pipeline._backtest(
            clean, None, partition, engine,
            source_availability_cutoffs={
                "2026-10-01": "2026-10-01T23:59:59+08:00",
                "2026-10-02": "2026-10-02T23:59:59+08:00",
            })
        self.assertIn(0.5, engine.category_lags)

    def test_report_date_as_of_replay_rejects_cutoff_after_origin_day(self):
        raw = panel(days=4)
        dates = pd.date_range("2026-10-01", periods=4)
        raw["report_date"] = dates
        clean = DataPreprocessor().validate(raw)
        partition = clean[clean.report_date.between(dates[1], dates[3])]
        pipeline = TrainingPipeline.__new__(TrainingPipeline)
        pipeline.cfg = SimpleNamespace(monthly_horizon=2, evaluation_stride=2)
        pipeline.preprocessor = DataPreprocessor()

        with self.assertRaisesRegex(ValueError, "falls after its forecast origin"):
            pipeline._backtest(
                clean, None, partition, object(),
                source_availability_cutoffs={
                    "2026-10-01": "2026-10-02T00:00:00+08:00",
                })

    def test_training_report_date_audit_separates_available_and_late_labels(self):
        dates = pd.date_range("2026-10-01", periods=3)
        raw = panel(days=3)
        raw["report_date"] = dates
        clean = DataPreprocessor().validate(raw)
        pipeline = TrainingPipeline.__new__(TrainingPipeline)
        pipeline.preprocessor = DataPreprocessor()

        audit = pipeline._training_source_audit(
            clean, available_through="2026-10-02T23:59:59+08:00")

        self.assertEqual(audit["status"], "report_date_based")
        self.assertEqual(audit["observed_training_labels"], 3)
        self.assertEqual(audit["labels_available_by_fit_cutoff"], 2)
        self.assertEqual(audit["labels_after_fit_cutoff"], 1)
        self.assertEqual(audit["labels_without_report_date"], 0)
        self.assertEqual(audit["coverage"], 2 / 3)
        self.assertEqual(audit["feature_availability_status"], "not_reconstructed")
        self.assertFalse(audit["point_in_time_training_verified"])

    def test_report_date_asof_training_features_mask_future_dates_and_preserve_targets(self):
        dates = pd.date_range("2026-10-01", periods=4)
        raw = pd.DataFrame([
            {
                "product_category": "Rice", "product_name": name,
                "product_variant": "Standard", "origin": "NCR", "unit": "kg",
                "report_date": date, "price_index": price,
                "observed_price": price, "is_observed": True,
                "source_pdf": f"{name}-{date:%Y%m%d}.pdf",
            }
            for name, prices in {"A": [10., 50., 80., 90.],
                                 "B": [10., 10., 10., 10.]}.items()
            for date, price in zip(dates, prices)
        ])
        clean = DataPreprocessor().validate(raw)
        pipeline = TrainingPipeline.__new__(TrainingPipeline)
        pipeline.preprocessor = DataPreprocessor()
        builder = local_builder(clean)
        cutoffs = {
            (date - pd.Timedelta(days=1)).date().isoformat():
                f"{(date - pd.Timedelta(days=1)):%Y-%m-%d}T23:59:59+08:00"
            for date in dates
        }

        featured, audit = pipeline._source_asof_training_features(clean, builder, cutoffs)
        row = featured.loc[
            featured.product_name.eq("A") & featured.report_date.eq(dates[3])].iloc[0]

        self.assertEqual(row.price_lag_1d, 80.0)
        self.assertEqual(row.forecast_anchor, 80.0)
        self.assertEqual(row.observed_price, 90.0)
        self.assertTrue(row.is_observed)
        self.assertEqual(audit["status"], "report_date_asof_reconstructed")
        self.assertEqual(audit["reconstructed_target_dates"], len(dates))

    def test_source_asof_target_rows_match_batch_features_and_stop_at_requested_date(self):
        dates = pd.date_range("2026-07-01", periods=100)
        rows = []
        for name, base in (("A", 25.0), ("B", 60.0)):
            for index, date in enumerate(dates):
                rows.append({
                    "product_category": "Rice", "product_name": name,
                    "product_variant": "Standard", "origin": "NCR", "unit": "kg",
                    "report_date": date, "price_index": base + index * .1,
                    "observed_price": base + index * .1, "is_observed": True,
                    "source_pdf": f"{name}-{date:%Y%m%d}.pdf",
                })
        clean = DataPreprocessor().validate(pd.DataFrame(rows))
        builder = local_builder(clean)
        pipeline = TrainingPipeline.__new__(TrainingPipeline)
        pipeline.preprocessor = DataPreprocessor()
        cutoffs = {
            (date - pd.Timedelta(days=1)).date().isoformat():
                f"{date - pd.Timedelta(days=1):%Y-%m-%d}T23:59:59+08:00"
            for date in dates
        }
        through_date = dates[78]
        featured, audit = pipeline._source_asof_training_features(
            clean, builder, cutoffs, through_date=through_date)

        target_date = dates[75]
        origin = target_date - pd.Timedelta(days=1)
        input_view, _ = pipeline.preprocessor.source_input_view(
            clean, cutoffs[origin.date().isoformat()])
        input_view = input_view.loc[input_view.report_date <= origin].copy()
        feature_inputs = [ForecastEngine._append_day(
            group.sort_values("report_date"), target_date)
            for _, group in input_view.groupby(SERIES_KEY, sort=True)]
        batch = builder.transform(pd.concat(
            feature_inputs, ignore_index=True).sort_values(
                SERIES_KEY + ["report_date"]).reset_index(drop=True))

        for name in ("A", "B"):
            actual_row = featured.loc[
                featured.product_name.eq(name)
                & featured.report_date.eq(target_date)].iloc[0]
            batch_row = batch.loc[
                batch.product_name.eq(name) & batch.report_date.eq(target_date)].iloc[0]
            np.testing.assert_allclose(actual_row[FEATURE_COLUMNS].to_numpy(float),
                                       batch_row[FEATURE_COLUMNS].to_numpy(float),
                                       rtol=1e-10, atol=1e-10, equal_nan=True)
        self.assertEqual(audit["target_date_through"], through_date.date().isoformat())
        self.assertEqual(audit["reconstructed_target_dates"], 79)
        self.assertTrue(featured.loc[
            featured.report_date.gt(through_date), FEATURE_COLUMNS].isna().all().all())

    def test_source_cutoff_timeline_rejects_training_vintage_after_fit_cutoff(self):
        dates = pd.date_range("2025-01-01", periods=20)
        clean = pd.DataFrame({"report_date": dates})
        train = clean.iloc[:8]
        tuning_partition = clean.iloc[8:]
        cutoffs = {
            (date - pd.Timedelta(days=1)).date().isoformat():
                f"{date - pd.Timedelta(days=1):%Y-%m-%d}T23:59:00+08:00"
            for date in dates
        }

        with self.assertRaisesRegex(ValueError, "after the model fit cutoff"):
            TrainingPipeline._validate_source_cutoff_timeline(
                clean, train, tuning_partition,
                "2024-01-07T12:00:00+08:00", cutoffs)

    def test_source_asof_cutoff_plan_uses_manila_origin_and_fit_closes(self):
        clean = DataPreprocessor().validate(panel(days=600))
        train, _, _ = DataPreprocessor.split_three(clean)
        fit_cutoff, cutoffs = TrainingPipeline._source_asof_cutoff_plan(clean, train)
        train_close = (pd.Timestamp(train.report_date.max()).tz_localize("Asia/Manila")
                       + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1))
        first_target = pd.Timestamp(clean.report_date.min())
        first_origin = first_target - pd.Timedelta(days=1)
        first_close = (first_origin.tz_localize("Asia/Manila")
                       + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1))

        self.assertEqual(pd.Timestamp(fit_cutoff), train_close)
        self.assertEqual(pd.Timestamp(cutoffs[first_origin.date().isoformat()]), first_close)
        self.assertEqual(len(cutoffs), clean.report_date.nunique())

    def test_report_date_cutoff_uses_existing_observed_labels(self):
        pipeline = TrainingPipeline.__new__(TrainingPipeline)
        pipeline.cfg = get_settings()
        pipeline.preprocessor = DataPreprocessor()

        clean = pipeline.preprocessor.validate(panel(days=600))
        train, _, _ = pipeline.preprocessor.split_three(
            clean, pipeline.cfg.validation_size, pipeline.cfg.test_size)
        fit_cutoff, _ = TrainingPipeline._source_asof_cutoff_plan(clean, train)
        available, audit = pipeline.preprocessor.source_target_availability(
            train, fit_cutoff)
        self.assertTrue(available.any())
        self.assertEqual(audit["availability_assumption"],
                         "available_by_end_of_report_date_in_Asia/Manila")

    def test_report_date_training_filters_labels_and_threads_asof_anchors(self):
        dates = pd.date_range("2025-01-01", periods=600)
        raw = panel(days=len(dates))

        pipeline = TrainingPipeline.__new__(TrainingPipeline)
        pipeline.cfg = get_settings()
        pipeline.preprocessor = DataPreprocessor()
        clean = pipeline.preprocessor.validate(raw)
        train, validation, _ = pipeline.preprocessor.split_three(
            clean, pipeline.cfg.validation_size, pipeline.cfg.test_size)
        tuning_partition = pipeline._tuning_partition(validation)
        cutoffs = {
            (date - pd.Timedelta(days=1)).date().isoformat():
                f"{date - pd.Timedelta(days=1):%Y-%m-%d}T23:59:00+08:00"
            for date in dates
        }
        first_validation_origin = (
            pd.Timestamp(tuning_partition.report_date.min()) - pd.Timedelta(days=1))
        fit_cutoff = cutoffs[first_validation_origin.date().isoformat()]
        late_label_date = pd.Timestamp(train.report_date.max())

        builder = FeatureBuilder()
        builder.encoder._save_mappings = lambda: None
        source_featured = []

        def build_source_asof_features(frame, fitted_builder, origin_cutoffs,
                                       through_date=None):
            featured = fitted_builder.transform(frame)
            featured["forecast_anchor"] = featured.groupby(
                SERIES_KEY, sort=False).price_index.shift(1)
            source_featured.append(featured)
            return featured, {"status": "report_date_asof_reconstructed"}

        pipeline._source_asof_training_features = build_source_asof_features
        run_dir = Path("strict-training-unit-test")
        pipeline.store = SimpleNamespace(begin_run=lambda: run_dir)
        finish_args = {}

        def finish_candidate(*args, **kwargs):
            finish_args.update(kwargs)
            return "candidate-staged"

        pipeline._finish_candidate = finish_candidate
        lgbm_instances, lstm_instances = [], []

        class StubLightGBM:
            def __init__(self, artifact_dir):
                self.y_train = None
                lgbm_instances.append(self)

            def train(self, x_train, y_train, x_val, y_val):
                self.y_train = np.asarray(y_train)
                return {"stub": True}

        class StubLSTM:
            def __init__(self, artifact_dir):
                self.feature_cols = ["stub_feature"]
                self.calls = []
                lstm_instances.append(self)

            def fit_scalers(self, frame):
                return self

            def build_sequences(self, frame, target_start=None, target_end=None,
                                stride=1, anchor_column=None):
                self.calls.append((frame.copy(), anchor_column))
                return (np.zeros((1, 1, 1), dtype=np.float32),
                        np.zeros((1, 30), dtype=np.float32), np.ones(1),
                        ["series"], np.asarray([target_start], dtype="datetime64[ns]"))

            def train(self, x_train, y_train, x_val, y_val):
                return {"stub": True}

        with patch("pipeline.trainer.FeatureBuilder", return_value=builder), \
             patch("pipeline.trainer.LightGBMModel", StubLightGBM), \
             patch("pipeline.trainer.LSTMModel", StubLSTM):
            result = pipeline._train(
                raw, activate=False, fit_source_cutoff=fit_cutoff,
                source_availability_cutoffs=cutoffs)

        self.assertEqual(result, "candidate-staged")
        self.assertTrue(finish_args["label_filtering_applied"])
        self.assertEqual(finish_args["source_availability_cutoffs"], cutoffs)
        self.assertEqual(len(lgbm_instances), 1)
        featured = source_featured[0]
        late_label = featured.loc[
            featured.report_date.eq(late_label_date)].iloc[0]
        self.assertTrue(usable_targets(featured.loc[
            featured.report_date.eq(late_label_date)]).iloc[0])
        self.assertEqual(len(lgbm_instances[0].y_train),
                         int((featured.report_date.between(
                             train.report_date.min(), train.report_date.max())
                              & usable_targets(featured)).sum()))
        train_sequence_frame, train_anchor_column = lstm_instances[0].calls[0]
        self.assertEqual(train_anchor_column, "forecast_anchor")
        self.assertTrue(np.isfinite(train_sequence_frame.loc[
            train_sequence_frame.report_date.eq(late_label_date),
            "observed_price"].iloc[0]))
        self.assertTrue(np.isfinite(late_label.forecast_anchor))

    def test_lstm_sequences_accept_sample_origin_anchor(self):
        clean = panel(days=100)
        builder = local_builder(clean)
        featured = builder.transform(clean)
        featured["forecast_anchor"] = 42.0
        target_date = featured.report_date.iloc[60]
        model = LSTMModel()

        _, _, anchors, _, _ = model.build_sequences(
            featured, target_start=target_date, target_end=target_date,
            anchor_column="forecast_anchor")

        np.testing.assert_allclose(anchors, [42.0])

    def test_source_input_view_uses_report_date_and_preserves_actual_labels(self):
        clean = pd.DataFrame({
            "product_category": ["Rice"] * 3, "product_name": ["Rice"] * 3,
            "product_variant": ["Standard"] * 3, "origin": ["NCR"] * 3,
            "unit": ["kg"] * 3, "report_date": pd.date_range("2026-10-01", periods=3),
            "price_index": [10.0, 50.0, 90.0],
            "observed_price": [10.0, 50.0, 90.0],
            "is_observed": [True, True, True],
            "source_pdf": ["oct-1.pdf", "oct-2.pdf", "oct-3.pdf"],
        })
        view, audit = DataPreprocessor.source_input_view(
            clean, "2026-10-02T00:00:00+00:00")
        self.assertEqual(view.price_index.tolist(), [10.0, 50.0])
        self.assertEqual(view.observed_price.iloc[0], 10.0)
        self.assertEqual(view.observed_price.iloc[1], 50.0)
        self.assertEqual(audit["rows_after_report_date_cutoff"], 1)
        self.assertEqual(audit["observations_available_by_cutoff"], 2)
        self.assertEqual(audit["observed_rows_excluded"], 0)

    def test_source_input_view_respects_manila_report_date_boundary(self):
        clean = panel(days=2)
        clean["report_date"] = pd.date_range("2026-10-01", periods=2)
        clean["observed_price"] = [10.0, 50.0]
        clean["price_index"] = [10.0, 50.0]
        view, audit = DataPreprocessor.source_input_view(
            clean, "2026-10-01T15:59:59+00:00")
        self.assertEqual(view.report_date.dt.date.tolist(), [pd.Timestamp("2026-10-01").date()])
        self.assertEqual(view.price_index.tolist(), [10.0])
        self.assertEqual(audit["report_date_cutoff_manila"], "2026-10-01")

    def test_data_fingerprint_tracks_existing_source_name(self):
        raw = pd.DataFrame({
            "product_category": ["Rice"], "product_name": ["Rice"],
            "product_variant": ["Standard"], "origin": ["NCR"], "unit": ["kg"],
            "report_date": ["2026-10-10"], "price_index": [50.0],
            "source_pdf": ["https://example.test/Price-Monitoring-October-10-2026.pdf"],
        })
        changed_source = raw.copy()
        changed_source.loc[0, "source_pdf"] = "revised-source.pdf"
        self.assertNotEqual(TrainingPipeline._fingerprint(raw),
                            TrainingPipeline._fingerprint(changed_source))

    def test_published_quality_uses_precomputed_validation_metrics_only(self):
        identity = ("Rice", "Rice", "Standard", "NCR", "kg")
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "example-run"
            run_dir.mkdir()
            series = "||".join(identity)
            (run_dir / "metadata.json").write_text(json.dumps({
                "metrics": {
                    "validation": {"ensemble": {"n": 3, "mae": 20 / 3,
                        "rmse": np.sqrt(400 / 3), "mape": 20 / 3,
                        "prediction_success": 2 / 3}},
                    "product_validation_metrics_by_identity": {series: {
                        "mae": 20 / 3, "rmse": np.sqrt(400 / 3), "mape": 20 / 3,
                        "sample_count": 3,
                        "sample_basis": "observed_validation_targets_across_forecast_steps",
                        "prediction_success": 2 / 3,
                    }},
                },
            }), encoding="utf-8")
            with patch("pipeline.prediction_writer.ModelStore") as store:
                store.return_value.runs = Path(tmp)
                metrics = PredictionWriter._quality_metrics("example-run", {identity: "rice-id"})

        self.assertEqual(metrics["product_metrics"]["rice-id"]["sample_count"], 3)
        self.assertEqual(metrics["product_metrics"]["rice-id"]["sample_basis"],
                         "observed_validation_targets_across_forecast_steps")
        self.assertEqual(metrics["prediction_success"], 2 / 3)
        self.assertEqual(metrics["sample_count"], 3)
        self.assertEqual(metrics["mae"], 20 / 3)
        self.assertEqual(metrics["mape"], 20 / 3)
        self.assertNotIn("interval_coverage", metrics)

    def test_relative_lightgbm_target_normalizes_product_scale(self):
        model = LightGBMModel()
        model.target_mode = "relative"
        features = pd.DataFrame({"price_lag_1d": [50.0, 200.0]})
        target = model._training_target(features, np.array([55.0, 220.0]))
        np.testing.assert_allclose(target, np.array([.1, .1]))

    def test_calibration_is_disjoint_even_for_overlapping_origins(self):
        rows = []
        for origin in pd.date_range('2025-01-01', periods=6, freq='10D'):
            for h in range(1, 31):
                rows.append({'origin': origin, 'date': origin+pd.Timedelta(days=h)})
        tuning, calibration = TrainingPipeline._split_forecasts(pd.DataFrame(rows))
        self.assertLess(tuning.date.max(), calibration.date.min())
        self.assertLess(tuning.origin.max(), calibration.origin.min())

    def test_legacy_interval_artifacts_load_for_point_inference_but_are_not_saved(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "ensemble.json").write_text(json.dumps({
                "weights": [0.0, 0.0], "trust_weights": [1.0, 1.0],
                "category_trust_weights": {}, "specialist_blends": {},
                "anomaly_reversion": {"log_ratio_threshold": 1e9,
                    "strength": 0.0, "decay": 1.0},
                "widths": [0.1, 0.2], "interval_widths": {"0.8": [0.1, 0.2]},
            }), encoding="utf-8")
            loaded = EnsembleModel(Path(tmp))
            loaded.load()
            np.testing.assert_array_equal(loaded.predict_rows(
                np.array([100., 100.]), np.array([100., 100.]), np.array([1, 2]),
                np.array([100., 100.])), np.array([100., 100.]))
            self.assertFalse(hasattr(loaded, "intervals"))
            loaded.save()
            saved = json.loads(Path(tmp, "ensemble.json").read_text(encoding="utf-8"))
            self.assertNotIn("widths", saved)
            self.assertNotIn("interval_widths", saved)

    def test_calibration_labels_cannot_change_point_model(self):
        tuning = pd.DataFrame({'horizon': [1]*40, 'actual': np.linspace(95, 105, 40),
                               'anchor': [100.]*40, 'lstm': [102.]*40, 'lgbm': [101.]*40})
        calibration = tuning.copy()
        shifted = calibration.copy()
        shifted['actual'] += 50
        with tempfile.TemporaryDirectory() as tmp:
            original = EnsembleModel(Path(tmp)/'a').fit(tuning, 1, calibration)
            changed = EnsembleModel(Path(tmp)/'b').fit(tuning, 1, shifted)
            np.testing.assert_array_equal(original.weights, changed.weights)
            np.testing.assert_array_equal(original.trust_weights, changed.trust_weights)
            self.assertEqual(original.calibration["purpose"], "product_confidence_reliability")
            self.assertEqual(changed.calibration["scope"], "held_out_from_ensemble_fit")

    def test_point_success_uses_fixed_tolerance(self):
        from utils.metrics import compute_all_metrics
        metrics = compute_all_metrics([100., 100.], [105., 150.])
        self.assertEqual(metrics['prediction_success'], .5)
        self.assertEqual(metrics['success_tolerance'], .05)
        self.assertEqual(metrics['within_10_count'], 1)
        self.assertEqual(metrics['within_10_accuracy_pct'], 50.0)

    def test_within_10_accuracy_uses_inclusive_ten_percent_boundary(self):
        from utils.metrics import compute_all_metrics
        metrics = compute_all_metrics([100., 100.], [110., 110.01])
        self.assertEqual(metrics['within_10_count'], 1)
        self.assertEqual(metrics['within_10_accuracy_pct'], 50.0)

    def test_mape_rejects_zero_or_near_zero_actuals(self):
        from utils.metrics import compute_all_metrics
        with self.assertRaisesRegex(ValueError, "MAPE undefined"):
            compute_all_metrics([1e-9], [1e-9])

    def test_absolute_lightgbm_target_remains_backward_compatible(self):
        model = LightGBMModel()
        model.target_mode = "absolute"
        features = pd.DataFrame({"price_lag_1d": [50.0]})
        target = model._training_target(features, np.array([55.0]))
        np.testing.assert_array_equal(target, np.array([55.0]))

    def test_future_price_change_does_not_change_past_features(self):
        data = panel()
        with tempfile.TemporaryDirectory() as tmp:
            builder = FeatureBuilder(Path(tmp)).fit(data.iloc[:60])
            original = builder.transform(data)
            changed = data.copy()
            changed.loc[changed.report_date > "2025-03-15", "price_index"] *= 9
            altered = builder.transform(changed)
            mask = original.report_date <= "2025-03-15"
            np.testing.assert_allclose(
                original.loc[mask, FEATURE_COLUMNS].to_numpy(float),
                altered.loc[mask, FEATURE_COLUMNS].to_numpy(float),
                equal_nan=True,
            )

    def test_category_return_features_are_lagged_and_match_live_state(self):
        first = panel(80)
        second = panel(80)
        second["product_name"] = "Beans"
        second["price_index"] = 80 + np.arange(80) * .2 + np.sin(np.arange(80) / 4)
        second["observed_price"] = second["price_index"]
        data = pd.concat([first, second], ignore_index=True)
        with tempfile.TemporaryDirectory() as tmp:
            builder = FeatureBuilder(Path(tmp)).fit(data.iloc[:100])
            featured = builder.transform(data)
            target_date = pd.Timestamp("2025-02-15")
            market = FeatureBuilder.category_return_history(data)
            history = market.loc[
                (market.product_category == "Rice") & (market.report_date < target_date),
                "category_return"].fillna(0.).tolist()
            one_series = data[(data.product_name == "Rice") &
                              (data.report_date < target_date)]
            incremental = CausalFeatureState(one_series, builder.encoder).row(
                target_date, history).iloc[0]
            batch = featured[(featured.product_name == "Rice") &
                             (featured.report_date == target_date)].iloc[0]
            np.testing.assert_allclose(
                batch[["category_return_lag_1d", "category_return_mean_7d",
                       "category_return_std_7d"]].to_numpy(float),
                incremental[["category_return_lag_1d", "category_return_mean_7d",
                             "category_return_std_7d"]].to_numpy(float),
                rtol=1e-10, atol=1e-10)

    def test_preprocessor_keeps_truth_separate_from_causal_fill(self):
        raw = panel(10).iloc[[0, 4, 9]].copy()
        raw["is_observed"] = [True, False, True]
        raw.loc[raw.index[1], "price_index"] = 999
        clean = DataPreprocessor().validate(raw)
        copied = clean.loc[clean.report_date == raw.report_date.iloc[1]].iloc[0]
        self.assertFalse(copied.is_observed)
        self.assertTrue(np.isnan(copied.observed_price))
        self.assertNotEqual(copied.price_index, 999)
        self.assertEqual(len(clean), 10)

    def test_chronological_three_way_split_is_disjoint(self):
        train, validation, test = DataPreprocessor.split_three(panel())
        self.assertLess(train.report_date.max(), validation.report_date.min())
        self.assertLess(validation.report_date.max(), test.report_date.min())

    def test_lstm_masks_unobserved_targets(self):
        pred = __import__("torch").tensor([[1.0, 5.0]], requires_grad=True)
        target = __import__("torch").tensor([[3.0, float("nan")]])
        loss = LSTMModel._masked_loss(pred, target)
        self.assertAlmostEqual(float(loss.detach()), 0.05 * (2.0 - 0.025))
        loss.backward()
        self.assertEqual(float(pred.grad[0, 1]), 0.0)
        self.assertIsNone(LSTMModel._masked_loss(pred, target * float("nan")))

    def test_previous_lightgbm_feature_contract_preserves_predictions(self):
        import lightgbm as lgb
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            features = pd.DataFrame(
                np.random.default_rng(42).uniform(1, 2, (40, len(LEGACY_FEATURE_COLUMNS))),
                columns=LEGACY_FEATURE_COLUMNS)
            booster = lgb.train({'objective': 'regression', 'verbosity': -1, 'num_threads': 1,
                                 'min_data_in_leaf': 2},
                                lgb.Dataset(features, label=np.linspace(0, .1, 40)), num_boost_round=2)
            (path / 'lightgbm_model.txt').write_bytes(booster.model_to_string().encode('utf-8'))
            metadata = {'feature_version': 2, 'features': LEGACY_FEATURE_COLUMNS,
                        'target_mode': 'relative'}
            (path / 'lightgbm_meta.json').write_text(json.dumps(metadata), encoding='utf-8')
            loaded = LightGBMModel(path)
            loaded.load()
            expanded = features.reindex(columns=FEATURE_COLUMNS, fill_value=0.)
            expected = features.price_lag_1d.to_numpy() * (1 + booster.predict(features))
            np.testing.assert_allclose(loaded.predict(expanded), expected)
            metadata['features'] = list(reversed(LEGACY_FEATURE_COLUMNS))
            (path / 'lightgbm_meta.json').write_text(json.dumps(metadata), encoding='utf-8')
            with self.assertRaises(ValueError):
                LightGBMModel(path).load()

    def test_lstm_partition_boundary_masks_future_labels(self):
        data = panel()
        boundary = data.report_date.iloc[70]
        with tempfile.TemporaryDirectory() as tmp:
            builder = FeatureBuilder(Path(tmp)).fit(data.iloc[:60])
            featured = builder.transform(data)
            model = LSTMModel(Path(tmp)).fit_scalers(data.iloc[:71])
            _, targets, _, _, _ = model.build_sequences(
                featured, target_start=boundary, target_end=boundary)
            self.assertEqual(len(targets), 1)
            self.assertTrue(np.isfinite(targets[0, 0]))
            self.assertTrue(np.isnan(targets[0, 1:]).all())

    def test_incremental_next_row_matches_batch_features(self):
        data = panel()
        with tempfile.TemporaryDirectory() as tmp:
            builder = FeatureBuilder(Path(tmp)).fit(data.iloc[:60])
            next_date = data.report_date.max() + pd.Timedelta(days=1)
            placeholder = data.iloc[[-1]].copy()
            placeholder["report_date"] = next_date
            placeholder[["price_index", "observed_price"]] = np.nan
            placeholder["is_observed"] = False
            batch = builder.transform(pd.concat([data, placeholder], ignore_index=True)).iloc[-1]
            state = CausalFeatureState(data, builder.encoder)
            incremental = state.row(next_date).iloc[0]
            np.testing.assert_allclose(batch[FEATURE_COLUMNS].to_numpy(float),
                                       incremental[FEATURE_COLUMNS].to_numpy(float),
                                       rtol=1e-10, atol=1e-10, equal_nan=True)
            state.append(52.5)
            forecast_row = placeholder.copy()
            forecast_row["price_index"] = 52.5
            second = placeholder.copy()
            second["report_date"] = next_date + pd.Timedelta(days=1)
            expanded = pd.concat([data, forecast_row, second], ignore_index=True)
            batch_second = builder.transform(expanded).iloc[-1]
            incremental_second = state.row(second.report_date.iloc[0]).iloc[0]
            np.testing.assert_allclose(batch_second[FEATURE_COLUMNS].to_numpy(float),
                                       incremental_second[FEATURE_COLUMNS].to_numpy(float),
                                       rtol=1e-10, atol=1e-10, equal_nan=True)

    def test_ensemble_can_choose_endpoint(self):
        rows = []
        for horizon in range(1, 4):
            for actual in [10.0, 12.0]:
                rows.append({"horizon": horizon, "actual": actual, "anchor": 10.0,
                             "lstm": actual, "lgbm": actual + 5})
        with tempfile.TemporaryDirectory() as tmp:
            model = EnsembleModel(Path(tmp)).fit(pd.DataFrame(rows), 3)
            np.testing.assert_array_equal(model.weights, np.zeros(3))
            np.testing.assert_array_equal(model.trust_weights, np.ones(3))

    def test_ensemble_fit_saves_point_model_without_interval_parameters(self):
        rows = []
        for actual in np.linspace(5, 15, 40):
            rows.append({"horizon": 1, "actual": actual, "anchor": 10.0,
                         "lstm": 10.0, "lgbm": 10.0})
        with tempfile.TemporaryDirectory() as tmp:
            EnsembleModel(Path(tmp)).fit(pd.DataFrame(rows), 1)
            saved = json.loads(Path(tmp, "ensemble.json").read_text(encoding="utf-8"))
            self.assertNotIn("widths", saved)
            self.assertFalse(any("interval" in key for key in saved))

    def test_product_specialist_is_identical_for_path_and_row_prediction(self):
        model = EnsembleModel()
        model.weights = np.zeros(2)
        model.trust_weights = np.ones(2)
        model.specialist_blends = {
            "Fish||Tilapia##0": {"model": "moving_average7", "weight": .5}}
        path = model.predict(
            np.array([20.0, 20.0]), np.array([20.0, 20.0]), 10.0,
            "Fish", 12.0, "Fish||Tilapia")
        rows = model.predict_rows(
            np.array([20.0, 20.0]), np.array([20.0, 20.0]),
            np.array([1, 2]), np.array([10.0, 10.0]),
            np.array(["Fish||Tilapia||v||o||kg"] * 2),
            np.array([12.0, 12.0]))
        np.testing.assert_allclose(path, np.array([16.0, 16.0]))
        np.testing.assert_allclose(rows, path)

    def test_specialist_fit_skips_zero_error_reference_without_warnings(self):
        rows = []
        for origin in pd.date_range("2025-01-01", periods=4, freq="30D"):
            for _ in range(20):
                rows.append({
                    "origin": origin, "series": "Fish||Tilapia||Standard||Local||kg",
                    "horizon": 1, "actual": 10.0, "ensemble": 10.0,
                    "lstm": 9.0, "anchor": 10.0, "moving_average7": 10.0,
                })
        model = EnsembleModel()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", RuntimeWarning)
            result = model._fit_stable_specialists(pd.DataFrame(rows))
        self.assertEqual(result, {})
        self.assertEqual(caught, [])

    def test_short_history_fallback_returns_only_persistence_points(self):
        series = panel(2)
        dates, point = PredictionWriter._persistence_fallback(None, series, 2)
        anchor = float(series.price_index.iloc[-1])
        np.testing.assert_allclose(point, np.array([anchor, anchor]))
        np.testing.assert_array_equal(
            dates, np.array(["2025-01-03", "2025-01-04"], dtype="datetime64[D]"))

    def test_ensemble_can_fall_back_to_persistence_by_horizon(self):
        rows = []
        for horizon in range(1, 3):
            for actual in [10.0, 10.0]:
                rows.append({"horizon": horizon, "actual": actual, "anchor": 10.0,
                             "lstm": 20.0, "lgbm": 30.0})
        with tempfile.TemporaryDirectory() as tmp:
            model = EnsembleModel(Path(tmp)).fit(pd.DataFrame(rows), 2)
            np.testing.assert_array_equal(model.trust_weights, np.zeros(2))
            predicted = model.predict_rows(
                np.array([20.0, 20.0]), np.array([30.0, 30.0]),
                np.array([1, 2]), np.array([10.0, 10.0]))
            np.testing.assert_array_equal(predicted, np.array([10.0, 10.0]))

    def test_ensemble_calibrates_category_confidence(self):
        rows = []
        for category, actual, count in [("Stable", 10.0, 12), ("Moving", 20.0, 36)]:
            for _ in range(count):
                rows.append({"series": f"{category}||item||v||o||kg",
                             "horizon": 1, "actual": actual, "anchor": 10.0,
                             "lstm": 20.0, "lgbm": 30.0})
        with tempfile.TemporaryDirectory() as tmp:
            model = EnsembleModel(Path(tmp)).fit(pd.DataFrame(rows), 1)
            self.assertEqual(model.category_trust_weights["Stable"][0], 0)
            self.assertGreater(model.category_trust_weights["Moving"][0], 0)
            prediction = model.predict(
                np.array([20.0]), np.array([30.0]), 10.0, "Stable")
            np.testing.assert_array_equal(prediction, np.array([10.0]))

    def test_ensemble_mean_reverts_anomalous_anchor(self):
        rows = []
        for horizon in range(1, 3):
            for _ in range(12):
                rows.append({"series": "Fish||item||v||o||kg", "horizon": horizon,
                             "actual": 10.0, "anchor": 100.0,
                             "moving_average7": 10.0, "lstm": 100.0, "lgbm": 100.0})
        with tempfile.TemporaryDirectory() as tmp:
            model = EnsembleModel(Path(tmp)).fit(pd.DataFrame(rows), 2)
            self.assertLess(model.anomaly_threshold, 1e9)
            prediction = model.predict(
                np.array([100.0, 100.0]), np.array([100.0, 100.0]),
                100.0, "Fish", 10.0)
            self.assertTrue((prediction < 100.0).all())

    def test_direction_is_measured_against_each_origin(self):
        score = compute_directional_accuracy(
            np.array([11, 9]), np.array([12, 8]), np.array([10, 10]))
        self.assertEqual(score, 100.0)

    def test_promotion_requires_within_10_and_all_three_errors_to_improve(self):
        reference = {"mae": 2.0, "rmse": 3.0, "mape": 4.0,
                     "within_10_accuracy_pct": 85.0}
        self.assertTrue(TrainingPipeline._improves_all(
            {"mae": 1.9, "rmse": 2.9, "mape": 3.9,
             "within_10_accuracy_pct": 86.0}, reference))
        self.assertFalse(TrainingPipeline._improves_all(
            {"mae": 1.9, "rmse": 2.9, "mape": 4.1,
             "within_10_accuracy_pct": 86.0}, reference))
        self.assertFalse(TrainingPipeline._improves_all(
            {"mae": 1.9, "rmse": 2.9, "mape": 3.9,
             "within_10_accuracy_pct": 84.9}, reference))

    def test_promotion_also_requires_improvement_over_active_champion(self):
        test = {
            "ensemble": {"mae": 1.9, "rmse": 2.9, "mape": 3.9,
                         "within_10_accuracy_pct": 90.0},
            "persistence": {"mae": 2.0, "rmse": 3.0, "mape": 4.0,
                             "within_10_accuracy_pct": 85.0},
        }
        champion = {"mae": 1.8, "rmse": 2.8, "mape": 3.8,
                    "within_10_accuracy_pct": 95.0}
        self.assertEqual(
            TrainingPipeline._promotion_decision(test, champion),
            (True, False, False),
        )

    def test_promotion_requires_at_least_five_percent_improvement_on_each_metric(self):
        reference = {"mae": 10.0, "rmse": 20.0, "mape": 5.0,
                     "within_10_accuracy_pct": 80.0}
        self.assertTrue(TrainingPipeline._improves_all_by(
            {"mae": 9.49, "rmse": 18.99, "mape": 4.74,
             "within_10_accuracy_pct": 84.0}, reference, .05))
        self.assertFalse(TrainingPipeline._improves_all_by(
            {"mae": 9.49, "rmse": 18.99, "mape": 4.76,
             "within_10_accuracy_pct": 84.0}, reference, .05))
        self.assertFalse(TrainingPipeline._improves_all_by(
            {"mae": 9.49, "rmse": 18.99, "mape": 4.74,
             "within_10_accuracy_pct": 83.99}, reference, .05))

    def test_development_targets_include_primary_within_10_metric(self):
        good = {"within_10_accuracy_pct": 90.0, "mae": 5.0,
                "rmse": 5.0, "mape": 5.0}
        self.assertTrue(TrainingPipeline._targets_met(good))
        self.assertFalse(TrainingPipeline._targets_met(
            {**good, "within_10_accuracy_pct": 89.99}))
        self.assertFalse(TrainingPipeline._targets_met(
            {**good, "rmse": 5.01}))

    def test_new_lstm_scaling_does_not_normalize_rsi_or_relative_features(self):
        model = LSTMModel()
        model.feature_cols = ["price_lag_1d", "price_rsi_14d", "price_pct_change_1d"]
        model.scaled_features = ["price_lag_1d"]
        row = np.array([[100.0, 50.0, .1]])
        np.testing.assert_allclose(model._scale(row, 100.0), [[1.0, 50.0, .1]])

    def test_bundle_activation_checks_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ModelStore(Path(tmp))
            run = store.begin_run()
            for name in REQUIRED_FILES - {"metadata.json"}:
                (run / name).write_bytes(b"valid")
            (run / "validation_paths.csv").write_bytes(b"path data")
            store.finalize(run, {"ok": True}, {"test": {}}, "abc", activate=False)
            metadata = json.loads((run / "metadata.json").read_text())
            self.assertIn("validation_paths.csv", metadata["sha256"])
            with self.assertRaisesRegex(ValueError, "final-holdout evidence"):
                store.activate(run.name)
            # Existing deployments remain readable; this fixture is not a
            # newly authorized activation or a statistical approval.
            store.manifest.write_text(json.dumps({"active_run": run.name}))
            self.assertEqual(store.active_path(), run)
            (run / "validation_paths.csv").write_bytes(b"tampered path data")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                store.active_path()
            (run / "validation_paths.csv").write_bytes(b"path data")
            (run / "ensemble.json").write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                store.activate(run.name)
            with self.assertRaises(ValueError):
                store.active_path()

    def test_tiny_end_to_end_training_bundle(self):
        cfg = get_settings()
        saved = {name: getattr(cfg, name) for name in [
            "lstm_hidden_size", "lstm_num_layers", "lstm_epochs",
            "lstm_batch_size", "lstm_patience", "evaluation_stride"]}
        saved_params = dict(cfg.lgbm_params)
        try:
            cfg.lstm_hidden_size = 8
            cfg.lstm_num_layers = 1
            cfg.lstm_epochs = 2
            cfg.lstm_batch_size = 32
            cfg.lstm_patience = 2
            cfg.evaluation_stride = 30
            cfg.lgbm_params.update({"n_estimators": 12,
                                    "early_stopping_rounds": 3,
                                    "learning_rate": .1, "num_threads": 1})
            raw = panel(660).drop(columns="observed_price")
            with tempfile.TemporaryDirectory() as tmp:
                pipeline = TrainingPipeline(Path(tmp))
                # Even a successful internal comparison cannot substitute for
                # independent final evidence or authorize automatic activation.
                with patch.object(TrainingPipeline, "_promotion_decision", return_value=(True, True, True)):
                    result = pipeline.run_full_training(raw_df=raw, activate=True)
                run = Path(tmp) / "runs" / result["run_id"]
                self.assertTrue(REQUIRED_FILES.issubset({p.name for p in run.iterdir()}))
                self.assertGreater(result["test_samples"], 0)
                self.assertFalse(result["activated"])
                self.assertTrue(result["promotion_gate"]["development_comparison_passed"])
                self.assertFalse(result["promotion_gate"]["independent_final_holdout_verified"])
                self.assertFalse((Path(tmp) / "manifest.json").exists())
                metadata = json.loads((run / "metadata.json").read_text(encoding="utf-8"))
                configuration = metadata["model_configuration"]
                self.assertEqual(configuration["training_details_status"], "complete")
                self.assertEqual(configuration["lightgbm"]["training"][
                    "requested_boost_rounds"], 12)
                self.assertGreater(configuration["lightgbm"]["training"][
                    "best_iteration"], 0)
                self.assertEqual(configuration["lightgbm"]["training"][
                    "parameters"]["seed"], cfg.random_seed)
                self.assertEqual(configuration["lstm"]["hidden_size"], 8)
                self.assertIn(configuration["lstm"]["training"]["selected_epoch"], [1, 2])
                self.assertEqual(configuration["lstm"]["training"]["random_seed"],
                                 cfg.random_seed)
                self.assertEqual(configuration["lstm"]["training"]["loss"]["name"],
                                 "Huber")
                with patch.object(TrainingPipeline, "_beats_persistence", return_value=True), \
                        patch.object(TrainingPipeline, "_improves_all_by", return_value=True):
                    recalibrated = pipeline.recalibrate_candidate(result["run_id"], activate=True)
                self.assertTrue(recalibrated["promotion_gate"]["development_comparison_passed"])
                self.assertFalse(recalibrated["activated"])
                self.assertFalse((Path(tmp) / "manifest.json").exists())
                recalibrated_run = Path(tmp) / "runs" / recalibrated["run_id"]
                recalibrated_metadata = json.loads(
                    (recalibrated_run / "metadata.json").read_text(encoding="utf-8"))
                recalibrated_configuration = recalibrated_metadata["model_configuration"]
                self.assertEqual(recalibrated_configuration["lstm"], configuration["lstm"])
                saved_ensemble = json.loads(
                    (recalibrated_run / "ensemble.json").read_text(encoding="utf-8"))
                self.assertEqual(recalibrated_configuration["ensemble"]["calibration"],
                                 saved_ensemble["calibration"])
        finally:
            for name, value in saved.items():
                setattr(cfg, name, value)
            cfg.lgbm_params = saved_params


if __name__ == "__main__":
    unittest.main()
