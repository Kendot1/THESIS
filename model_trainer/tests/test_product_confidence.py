import csv
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from evaluation.product_confidence import validation_confidence


class ProductConfidenceTests(unittest.TestCase):
    SERIES = ("Rice", "Rice", "Regular", "Local", "kg")
    IDS = {SERIES: "rice-id", ("Rice", "Other", "Regular", "Local", "kg"): "other-id"}

    def bundle(self, count=12, scope="calibration_excluded_from_early_stopping", corrupt=False):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        bundle = Path(temp.name)
        rows = []
        for offset in range(count):
            origin = date(2024, 1, 1) + timedelta(days=30*offset)
            for lead in range(1, 31):
                rows.append(dict(series="||".join(self.SERIES), origin=origin.isoformat(),
                                 date=(origin+timedelta(days=lead)).isoformat(), horizon=lead,
                                 actual=100, ensemble=99))
        calibration = dict(scope="held_out_from_ensemble_fit", base_model_scope=scope,
                           start=min(r["date"] for r in rows), end=max(r["date"] for r in rows),
                           sample_count=len(rows)+(1 if corrupt else 0))
        (bundle / "ensemble.json").write_text(json.dumps(dict(calibration=calibration)))
        rows.append(dict(series="||".join(self.SERIES), origin="2023-12-01", date="2023-12-02",
                         horizon=1, actual=100, ensemble=1000))
        with (bundle / "validation_forecasts.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        calibration_rows = [row for row in rows if row["origin"] >= "2024-01-01"]
        with (bundle / "validation_paths.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(calibration_rows)
        return bundle

    def development_test_bundle(self, count=12):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        bundle = Path(temp.name)
        rows = []
        first_origin = date(2024, 1, 1)
        for offset in range(count):
            origin = first_origin + timedelta(days=30*offset)
            for lead in range(1, 31):
                rows.append(dict(series="||".join(self.SERIES), origin=origin.isoformat(),
                                 date=(origin+timedelta(days=lead)).isoformat(), horizon=lead,
                                 actual=100, anchor=100, lstm=99, lgbm=99, persistence=100,
                                 seasonal7=100, moving_average7=100, ensemble=99))
        test_start = (first_origin + timedelta(days=1)).isoformat()
        test_end = (first_origin + timedelta(days=30*(count-1)+30)).isoformat()
        metadata = {
            "split": {
                "train": {"end": "2023-06-30"},
                "validation": {"end": "2023-12-31"},
                "test": {"start": test_start, "end": test_end},
            },
            "metrics": {"test": {"ensemble": {"n": len(rows)}}},
        }
        (bundle / "metadata.json").write_text(json.dumps(metadata))
        with (bundle / "test_forecasts.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        return bundle, rows

    def test_isolates_calibration_and_product_horizon_identity(self):
        bundle = self.bundle()
        result = validation_confidence(bundle, self.IDS)
        for horizon, expected_min in (("daily", 100), ("weekly", 8), ("monthly", 8)):
            metric = result["rice-id"]["confidence_by_horizon"][horizon]
            self.assertEqual(metric["confidence_score"], 99)
            self.assertEqual(metric["mape"], 1)
            self.assertGreaterEqual(metric["sample_count"], expected_min)
            self.assertEqual(metric["model_version"], bundle.name)
            self.assertEqual(metric["evidence_status"], "validated")
            self.assertIsNone(result["other-id"]["confidence_by_horizon"][horizon]["confidence_score"])
        step = result["rice-id"]["confidence_by_step"]["daily"][1]
        self.assertEqual(step["forecast_step"], 1)
        self.assertEqual(step["sample_count"], 12)
        self.assertEqual(step["confidence_score"], 99)

    def test_refuses_legacy_or_mismatched_provenance(self):
        for bundle in (self.bundle(scope="parent_validation_used_for_early_stopping"),
                       self.bundle(corrupt=True)):
            result = validation_confidence(bundle, self.IDS)["rice-id"]
            for metric in result["confidence_by_horizon"].values():
                self.assertIsNone(metric["confidence_score"])
                self.assertEqual(metric["evidence_status"], "unverified_provenance")

    def test_missing_full_paths_withholds_confidence_for_unknown_coverage(self):
        bundle = self.bundle()
        (bundle / "validation_paths.csv").unlink()

        result = validation_confidence(bundle, self.IDS)["rice-id"]

        for metric in result["confidence_by_horizon"].values():
            self.assertIsNone(metric["confidence_score"])
            self.assertEqual(metric["evidence_status"], "unverified_provenance")
            self.assertIn("Complete 30-day validation paths are required",
                          metric["path_evidence_issue"])

    def test_sparse_evidence_does_not_invent_a_high_confidence_score(self):
        metric = validation_confidence(self.bundle(count=4), self.IDS)["rice-id"]["confidence_by_horizon"]["daily"]
        self.assertEqual(metric["sample_count"], 120)
        self.assertEqual(metric["mape"], 1)
        self.assertIsNone(metric["confidence_score"])
        self.assertEqual(metric["evidence_status"], "insufficient_data")
        self.assertIn("fewer than 8 distinct forecast origins",
                      metric["insufficient_data_reason"])

    def test_later_outcomes_are_not_available_at_their_forecast_origin(self):
        metric = validation_confidence(self.bundle(count=8), self.IDS)["rice-id"]["confidence_by_step"]["monthly"][2]
        self.assertEqual(metric["forecast_step"], 2)
        self.assertIsNone(metric["confidence_score"])
        self.assertLess(metric["formula_validation_origins"], 3)
        self.assertIn("fewer than 3 forward formula-check origins",
                      metric["insufficient_data_reason"])

    def test_complete_paths_validate_publisher_aligned_period_confidence(self):
        bundle = self.bundle()
        with (bundle / "validation_forecasts.csv").open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        calibration_rows = [row for row in rows if row["origin"] >= "2024-01-01"]
        with (bundle / "validation_paths.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(calibration_rows)

        result = validation_confidence(bundle, self.IDS)["rice-id"]
        for horizon in ("daily", "weekly", "monthly"):
            metric = result["confidence_by_horizon"][horizon]
            self.assertEqual(metric["evidence_status"], "validated")
            self.assertEqual(metric["forecast_path_count"], 12)
            self.assertEqual(metric["observed_label_coverage"], 1.0)

    def test_period_confidence_uses_publisher_decimal_rounding(self):
        bundle = self.bundle()
        values = {1: 108.45, 2: 95.45, 3: 109.61,
                  4: 91.15, 5: 101.16, 6: 101.17}
        forecast_path = bundle / "validation_forecasts.csv"
        with forecast_path.open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        for row in rows:
            if row["origin"] == "2024-01-01" and int(row["horizon"]) in values:
                row["ensemble"] = str(values[int(row["horizon"])])
        with forecast_path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        calibration_rows = [row for row in rows if row["origin"] >= "2024-01-01"]
        with (bundle / "validation_paths.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(calibration_rows)

        metric = validation_confidence(bundle, self.IDS)["rice-id"][
            "confidence_by_horizon"]["weekly"]

        self.assertEqual(metric["sample_count"], 61)
        self.assertAlmostEqual(metric["mae"], (1.16 + 60) / 61, places=10)

    def test_incomplete_full_path_fails_closed(self):
        bundle = self.bundle()
        with (bundle / "validation_forecasts.csv").open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        calibration_rows = [row for row in rows if row["origin"] >= "2024-01-01"]
        calibration_rows = [row for row in calibration_rows
                            if not (row["origin"] == "2024-01-01" and row["horizon"] == "30")]
        with (bundle / "validation_paths.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(calibration_rows)

        result = validation_confidence(bundle, self.IDS)["rice-id"]
        metric = result["confidence_by_horizon"]["daily"]
        self.assertIsNone(metric["confidence_score"])
        self.assertEqual(metric["evidence_status"], "unverified_provenance")
        self.assertIn("Incomplete 30-day forecast path", metric["path_evidence_issue"])

    def test_low_observed_path_coverage_withholds_confidence(self):
        bundle = self.bundle()
        with (bundle / "validation_forecasts.csv").open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        calibration_rows = [row for row in rows if row["origin"] >= "2024-01-01"]
        omitted = {(row["series"], row["origin"], row["date"])
                   for row in calibration_rows if 2 <= int(row["horizon"]) <= 9}
        saved_rows = [row for row in rows
                      if (row["series"], row["origin"], row["date"]) not in omitted]
        path_rows = [dict(row) for row in calibration_rows]
        for row in path_rows:
            if (row["series"], row["origin"], row["date"]) in omitted:
                row["actual"] = ""
        with (bundle / "validation_forecasts.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(saved_rows)
        with (bundle / "validation_paths.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(path_rows)
        ensemble_path = bundle / "ensemble.json"
        ensemble = json.loads(ensemble_path.read_text())
        ensemble["calibration"]["sample_count"] = len(saved_rows) - 1
        ensemble_path.write_text(json.dumps(ensemble))

        metric = validation_confidence(bundle, self.IDS)["rice-id"][
            "confidence_by_horizon"]["daily"]
        self.assertLess(metric["observed_label_coverage"], 0.8)
        self.assertIsNone(metric["confidence_score"])
        self.assertEqual(metric["evidence_status"], "insufficient_data")

    def test_chronological_development_test_supports_confidence_with_full_paths(self):
        bundle, paths = self.development_test_bundle()

        result = validation_confidence(
            bundle, self.IDS, forecast_paths=paths,
            evaluation_partition="development_test")["rice-id"]

        for horizon in ("daily", "weekly", "monthly"):
            metric = result["confidence_by_horizon"][horizon]
            self.assertEqual(metric["evidence_status"], "validated")
            self.assertEqual(metric["confidence_score"], 99)
            self.assertEqual(metric["evaluation_source"], "chronological_development_test")
            self.assertGreaterEqual(metric["formula_validation_origins"], 3)
            self.assertEqual(metric["observed_label_coverage"], 1.0)


if __name__ == "__main__":
    unittest.main()
