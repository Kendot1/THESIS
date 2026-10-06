import json
import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from data.preprocessor import DataPreprocessor, SERIES_KEY
from features.builder import FEATURE_COLUMNS, LEGACY_FEATURE_COLUMNS, CausalFeatureState, FeatureBuilder
from models.ensemble import EnsembleModel
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


class CausalPipelineTests(unittest.TestCase):
    def test_published_quality_counts_each_target_date_once(self):
        identity = ("Rice", "Rice", "Standard", "NCR", "kg")
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "example-run"
            run_dir.mkdir()
            (run_dir / "metadata.json").write_text(json.dumps({
                "metrics": {
                    "test": {"ensemble": {"n": 3}},
                    "test_interval_metrics": {"0.8": {"observed_coverage": 0.75}},
                },
            }), encoding="utf-8")
            (run_dir / "ensemble.json").write_text(json.dumps({
                "interval_widths": {"0.8": [0.5, 0.5]},
            }), encoding="utf-8")
            rows = [
                ["||".join(identity), "2025-01-01", "2025-01-03", 2, 100, 100, 100],
                ["||".join(identity), "2025-01-02", "2025-01-03", 1, 100, 120, 100],
                ["||".join(identity), "2025-01-03", "2025-01-04", 1, 100, 100, 100],
            ]
            with (run_dir / "test_forecasts.csv").open("w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow(["series", "origin", "date", "horizon", "actual", "ensemble", "anchor"])
                writer.writerows(rows)
            with patch("pipeline.prediction_writer.ModelStore") as store:
                store.return_value.runs = Path(tmp)
                metrics = PredictionWriter._quality_metrics("example-run", {identity: "rice-id"})

        self.assertEqual(metrics["product_metrics"]["rice-id"]["sample_count"], 2)
        self.assertEqual(metrics["product_metrics"]["rice-id"]["interval_coverage"], 1.0)
        self.assertEqual(metrics["product_metrics"]["rice-id"]["sample_basis"], "unique_actual_dates")
        self.assertEqual(metrics["prediction_success"], 0.5)
        self.assertEqual(metrics["sample_count"], 2)
        self.assertEqual(metrics["mae"], 10.)
        self.assertEqual(metrics["mape"], 10.)

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

    def test_category_intervals_roundtrip_and_sparse_category_fallback(self):
        model = EnsembleModel()
        model.weights = np.zeros(2)
        model.trust_weights = np.zeros(2)
        rows = []
        for category, count, error in [('Stable', 120, 1), ('Volatile', 120, 30), ('Sparse', 2, 2)]:
            for i in range(count):
                rows.append({'series': category+'||item||v||o||kg', 'horizon': i % 2+1,
                             'actual': 100+error, 'anchor': 100, 'lstm': 100, 'lgbm': 100})
        model.calibrate_intervals(pd.DataFrame(rows), 2, independent=True)
        np.testing.assert_allclose(model.category_interval_widths['Stable']['0.8'], [.01, .01])
        np.testing.assert_allclose(model.category_interval_widths['Volatile']['0.8'], [.3, .3])
        np.testing.assert_array_equal(model.category_interval_widths['Sparse']['0.8'], model.widths)
        with tempfile.TemporaryDirectory() as tmp:
            model.path = Path(tmp)
            model.save()
            loaded = EnsembleModel(Path(tmp))
            loaded.load()
            path = loaded.intervals(np.array([100., 100.]), 100., category='Stable')
            rows = loaded.intervals_rows(np.array([100., 100.]), np.array([100., 100.]),
                                         np.array([1, 2]), series=['Stable||item', 'Stable||item'])
            np.testing.assert_allclose(path, rows)
            np.testing.assert_allclose(path, [[99., 99.], [101., 101.]])
            with self.assertRaises(ValueError):
                loaded.intervals_rows(np.array([100.]), np.array([100.]), np.array([0]))

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
            self.assertGreater(changed.widths[0], original.widths[0])

    def test_point_success_uses_fixed_tolerance(self):
        from utils.metrics import compute_all_metrics
        metrics = compute_all_metrics([100., 100.], [105., 150.])
        self.assertEqual(metrics['prediction_success'], .5)
        self.assertEqual(metrics['success_tolerance'], .05)

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

    def test_ensemble_calibrates_nested_confidence_levels(self):
        rows = []
        for actual in np.linspace(5, 15, 40):
            rows.append({"horizon": 1, "actual": actual, "anchor": 10.0,
                         "lstm": 10.0, "lgbm": 10.0})
        with tempfile.TemporaryDirectory() as tmp:
            model = EnsembleModel(Path(tmp)).fit(pd.DataFrame(rows), 1)
            self.assertLessEqual(model.interval_widths["0.8"][0],
                                 model.interval_widths["0.9"][0])
            self.assertLessEqual(model.interval_widths["0.9"][0],
                                 model.interval_widths["0.95"][0])
            lower80, upper80 = model.intervals(np.array([10.0]), 10.0, .8)
            lower95, upper95 = model.intervals(np.array([10.0]), 10.0, .95)
            self.assertLessEqual(lower95[0], lower80[0])
            self.assertGreaterEqual(upper95[0], upper80[0])

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

    def test_short_history_fallback_uses_persistence_and_calibrated_intervals(self):
        ensemble = EnsembleModel()
        ensemble.interval_widths = {"0.8": np.array([.1, .2])}
        engine = type("Engine", (), {"ensemble": ensemble})()
        series = panel(2)
        dates, point, lower, upper = PredictionWriter._persistence_fallback(
            engine, series, 2)
        anchor = float(series.price_index.iloc[-1])
        np.testing.assert_allclose(point, np.array([anchor, anchor]))
        np.testing.assert_array_equal(
            dates, np.array(["2025-01-03", "2025-01-04"], dtype="datetime64[D]"))
        np.testing.assert_allclose(lower, anchor*np.array([.9, .8]))
        np.testing.assert_allclose(upper, anchor*np.array([1.1, 1.2]))

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

    def test_promotion_requires_all_three_errors_to_improve(self):
        reference = {"mae": 2.0, "rmse": 3.0, "mape": 4.0}
        self.assertTrue(TrainingPipeline._improves_all(
            {"mae": 1.9, "rmse": 2.9, "mape": 3.9}, reference))
        self.assertFalse(TrainingPipeline._improves_all(
            {"mae": 1.9, "rmse": 2.9, "mape": 4.1}, reference))

    def test_promotion_also_requires_improvement_over_active_champion(self):
        test = {
            "ensemble": {"mae": 1.9, "rmse": 2.9, "mape": 3.9},
            "persistence": {"mae": 2.0, "rmse": 3.0, "mape": 4.0},
        }
        champion = {"mae": 1.8, "rmse": 2.8, "mape": 3.8}
        self.assertEqual(
            TrainingPipeline._promotion_decision(test, champion),
            (True, False, False),
        )

    def test_promotion_requires_at_least_five_percent_improvement_on_each_metric(self):
        reference = {"mae": 10.0, "rmse": 20.0, "mape": 5.0}
        self.assertTrue(TrainingPipeline._improves_all_by(
            {"mae": 9.49, "rmse": 18.99, "mape": 4.74}, reference, .05))
        self.assertFalse(TrainingPipeline._improves_all_by(
            {"mae": 9.49, "rmse": 18.99, "mape": 4.76}, reference, .05))

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
            store.finalize(run, {"ok": True}, {"test": {}}, "abc", activate=False)
            with self.assertRaisesRegex(ValueError, "final-holdout evidence"):
                store.activate(run.name)
            # Existing deployments remain readable; this fixture is not a
            # newly authorized activation or a statistical approval.
            store.manifest.write_text(json.dumps({"active_run": run.name}))
            self.assertEqual(store.active_path(), run)
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
                with patch.object(TrainingPipeline, "_beats_persistence", return_value=True), \
                        patch.object(TrainingPipeline, "_improves_all_by", return_value=True):
                    recalibrated = pipeline.recalibrate_candidate(result["run_id"], activate=True)
                self.assertTrue(recalibrated["promotion_gate"]["development_comparison_passed"])
                self.assertFalse(recalibrated["activated"])
                self.assertFalse((Path(tmp) / "manifest.json").exists())
        finally:
            for name, value in saved.items():
                setattr(cfg, name, value)
            cfg.lgbm_params = saved_params


if __name__ == "__main__":
    unittest.main()
