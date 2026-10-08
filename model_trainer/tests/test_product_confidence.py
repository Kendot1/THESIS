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
            for lead in (1, 7, 30):
                rows.append(dict(series="||".join(self.SERIES), origin=origin.isoformat(),
                                 date=(origin+timedelta(days=lead)).isoformat(), horizon=lead,
                                 actual=100, ensemble=100-lead))
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
        return bundle

    def test_isolates_calibration_and_product_horizon_identity(self):
        bundle = self.bundle()
        result = validation_confidence(bundle, self.IDS)
        for horizon, lead in (("daily", 1), ("weekly", 7), ("monthly", 30)):
            metric = result["rice-id"][horizon]
            self.assertEqual(metric["confidence_score"], 100-lead)
            self.assertAlmostEqual(metric["mape"], lead)
            self.assertEqual(metric["sample_count"], 12)
            self.assertEqual(metric["model_version"], bundle.name)
            self.assertEqual(metric["evidence_status"], "validated")
            self.assertIsNone(result["other-id"][horizon]["confidence_score"])

    def test_refuses_legacy_or_mismatched_provenance(self):
        for bundle in (self.bundle(scope="parent_validation_used_for_early_stopping"),
                       self.bundle(corrupt=True)):
            result = validation_confidence(bundle, self.IDS)["rice-id"]
            for metric in result.values():
                self.assertIsNone(metric["confidence_score"])
                self.assertEqual(metric["evidence_status"], "unverified_provenance")

    def test_sparse_evidence_does_not_invent_a_high_confidence_score(self):
        metric = validation_confidence(self.bundle(count=4), self.IDS)["rice-id"]["daily"]
        self.assertEqual(metric["sample_count"], 4)
        self.assertEqual(metric["mape"], 1)
        self.assertIsNone(metric["confidence_score"])
        self.assertEqual(metric["evidence_status"], "insufficient_data")

    def test_later_outcomes_are_not_available_at_their_forecast_origin(self):
        metric = validation_confidence(self.bundle(count=8), self.IDS)["rice-id"]["monthly"]
        self.assertIsNone(metric["confidence_score"])


if __name__ == "__main__":
    unittest.main()
