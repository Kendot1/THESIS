"""Read-only holdout-confidence report checks using synthetic score metrics."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "model_trainer"))
sys.path.insert(0, str(ROOT / "audits" / "confidence_20261010"))

import evaluate_holdout_confidence as evaluator


class HoldoutConfidenceTests(unittest.TestCase):
    SERIES = "Rice||Rice||Regular||Local||kg"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = self.root / "model_trainer" / "artifacts_v2" / "runs" / "synthetic"
        self.bundle.mkdir(parents=True)
        self.contract = {
            "model_run_id": "synthetic", "holdout_type": "prospective",
            "holdout_start": "2026-10-06", "holdout_end": "2026-11-04",
        }
        self.integrity = {
            "contract_sha256": "a" * 64, "forecast_sha256": "b" * 64,
            "period_closes_at": "2026-11-05T00:00:00+08:00",
        }
        metadata_bytes = json.dumps({"data_fingerprint": "synthetic-fingerprint"}).encode()
        ensemble_bytes = b'{"weights":{}}'
        (self.bundle / "metadata.json").write_bytes(metadata_bytes)
        (self.bundle / "ensemble.json").write_bytes(ensemble_bytes)
        metric = {
            "confidence_score": 98.0,
            "confidence_method": evaluator.METHOD,
            "evidence_status": "validated",
        }
        step_metric = {**metric, "confidence_score": 97.0}
        self.profile = {
            "profile_schema_version": 1,
            "profile_status": "development_validated_with_selection_reuse",
            "model_run_id": "synthetic",
            "data_fingerprint": "synthetic-fingerprint",
            "model_metadata_sha256": evaluator.digest(metadata_bytes),
            "ensemble_sha256": evaluator.digest(ensemble_bytes),
            "confidence_method": evaluator.METHOD,
            "evaluation_source": "chronological_development_test",
            "development_test_reused_for_selection": True,
            "product_confidence_by_identity": {
                self.SERIES: {
                    "confidence_by_horizon": {name: metric for name in evaluator.TIMEFRAMES},
                    "confidence_by_step": {
                        name: {"1": step_metric} for name in evaluator.TIMEFRAMES},
                },
            },
        }
        self.report = {
            "schema_version": 1,
            "model_run_id": "synthetic",
            "holdout_type": "prospective",
            "holdout_start": "2026-10-06",
            "holdout_end": "2026-11-04",
            "scored_at_utc": "2026-11-05T00:01:00+08:00",
            "integrity": {
                "contract_sha256": self.integrity["contract_sha256"],
                "forecast_sha256": self.integrity["forecast_sha256"],
            },
            "actuals_manifest_sha256": "c" * 64,
            "actuals_sha256": "d" * 64,
            "full_declared_scope_observed": True,
            "coverage": {"forecast_rows_with_observed_actual": 1.0},
            "timeframes": {
                name: {
                    "series": {self.SERIES: {"n": 30, "mape": 1.0}},
                    "series_forecast_step": {
                        self.SERIES: {"1": {"n": 1, "mape": 2.0}},
                    },
                }
                for name in evaluator.TIMEFRAMES
            },
        }
        self.report_path = self.root / "score-report.json"
        self.profile_path = self.root / "confidence-profile.json"
        self._write_inputs()

    def _write_inputs(self):
        self.report_path.write_text(json.dumps(self.report), encoding="utf-8")
        self.profile_path.write_text(json.dumps(self.profile), encoding="utf-8")

    def evaluate(self):
        with patch.object(evaluator, "ROOT", self.root), patch.object(
                evaluator, "load_contract",
                return_value=(self.contract, {}, self.integrity)):
            return evaluator.evaluate("synthetic-contract.json", self.report_path, self.profile_path)

    def test_matches_product_horizon_and_step_scores_after_close(self):
        result = self.evaluate()
        self.assertEqual(result["by_timeframe"]["daily"]["product_horizon"][
            "aggregate"]["mean_signed_error_points"], -1.0)
        self.assertEqual(result["by_timeframe"]["daily"]["product_step"][
            "aggregate"]["mean_signed_error_points"], -1.0)
        self.assertTrue(result["holdout_outcomes_used_only_as_reported_metrics"])
        self.assertFalse(result["confidence_scores_modified"])

    def test_rejects_report_scored_before_contract_close(self):
        self.report["scored_at_utc"] = "2026-11-04T23:59:59+08:00"
        self._write_inputs()
        with self.assertRaisesRegex(ValueError, "precedes close"):
            self.evaluate()

    def test_rejects_profile_with_mismatched_bundle_hash(self):
        self.profile["ensemble_sha256"] = "e" * 64
        self._write_inputs()
        with self.assertRaisesRegex(ValueError, "hashes do not match"):
            self.evaluate()


if __name__ == "__main__":
    unittest.main()
