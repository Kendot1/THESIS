"""Synthetic promotion evidence only; never reads production or holdout data."""
import csv
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation.frozen_holdout import score
from evaluation.promotion import (
    COMPONENTS, digest, validation_comparison, verify_promotion_evidence,
)
from models.model_store import ModelStore, REQUIRED_FILES


class PromotionEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = ModelStore(self.root / "store")
        self.run = self.store.begin_run()
        for name in REQUIRED_FILES - {"metadata.json"}:
            (self.run / name).write_text("synthetic model fixture")
        self.store.finalize(self.run, {}, {}, "synthetic", activate=False)
        metadata = self.read(self.run / "metadata.json")
        metadata["created_at"] = "2024-12-01T00:00:00+00:00"
        self.write(self.run / "metadata.json", metadata)
        self.evidence = self.root / "evidence"
        self.evidence.mkdir()
        self.series = "Rice||Rice||Regular||Local||kg"
        self.now = datetime(2025, 2, 2, tzinfo=timezone.utc)
        self.forecasts = [dict(series=self.series, origin="2025-01-01", target_date=f"2025-01-{d:02}",
            horizon=d-1, anchor=110, prediction=101) for d in range(2, 32)]
        self.actuals = [dict(series=self.series, target_date=f"2025-01-{d:02}", actual=100,
                             is_observed="true") for d in range(2, 32)]
        validation = [dict(series=self.series, origin=f"2024-{m:02}-01", target_date=f"2024-{m:02}-{d:02}",
                           actual=100, prediction=101, champion=111, anchor=112)
                      for m in (9, 10, 11) for d in (5, 10)]
        self.csv("validation.csv", validation)
        self.selection = dict(model_run_id=self.run.name, model_metadata_sha256=digest(self.run / "metadata.json"),
            promotion_policy_version=2,
            selected_at="2024-12-31T00:00:00+00:00", declared_series=[self.series],
            validation_forecasts_sha256=digest(self.evidence / "validation.csv"))
        self.write(self.evidence / "selection.json", self.selection)
        self.csv("forecasts.csv", self.forecasts)
        self.contract = dict(forecast_origin="2025-01-01", holdout_start="2025-01-02", holdout_end="2025-01-31",
            horizon_days=30, model_run_id=self.run.name, holdout_type="prospective",
            forecasts_frozen_at_utc="2025-01-01T12:00:00+00:00", forecast_file="forecasts.csv",
            forecast_rows=30, forecast_series=1, total_input_series=1, series_coverage=1.,
            skipped_series_count=0, skipped_series=[], forecast_sha256=digest(self.evidence / "forecasts.csv"),
            model_bundle_sha256={n: digest(self.run / n) for n in COMPONENTS},
            model_metadata_sha256=digest(self.run / "metadata.json"), selection_record_sha256=digest(self.evidence / "selection.json"))
        self.write(self.evidence / "contract.json", self.contract)
        self.csv("actuals.csv", self.actuals)
        self.actual_manifest = dict(data_file="actuals.csv", sha256=digest(self.evidence / "actuals.csv"),
            reconciled_through="2025-01-31", source="Synthetic fixture", is_observed_definition="Synthetic measured rows")
        self.write(self.evidence / "actuals.json", self.actual_manifest)
        self.rescore()
        self.review = dict(schema_version=1, model_run_id=self.run.name, reviewed_by="Synthetic test reviewer",
            promotion_policy_version=2,
            reviewed_at="2025-02-02T00:00:00+00:00", selection_provenance_checked=True,
            actuals_provenance_checked=True, holdout_not_used_for_selection=True)
        self.refresh_review()

    def read(self, path):
        return json.loads(path.read_text())

    def write(self, path, value):
        path.write_text(json.dumps(value))

    def csv(self, name, rows):
        with (self.evidence / name).open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    def rescore(self):
        result = score(self.evidence / "contract.json", self.evidence / "actuals.json", now=self.now)
        self.write(self.evidence / "score.json", result)

    def refresh_review(self):
        for name, file in [("contract", "contract.json"), ("actuals_manifest", "actuals.json"),
                           ("score_report", "score.json"), ("selection_record", "selection.json"),
                           ("validation_forecasts", "validation.csv")]:
            self.review[name] = dict(file=file, sha256=digest(self.evidence / file))
        self.write(self.evidence / "promotion_review.json", self.review)

    def verify(self):
        return verify_promotion_evidence(self.run, self.evidence, now=self.now)

    def test_valid_synthetic_evidence_reproduces_and_activates(self):
        result = self.verify()
        self.assertEqual(result["validation"]["origins_improving_all_metrics"], 3)
        self.store.activate(self.run.name, evidence_dir=self.evidence)
        self.assertEqual(self.store.active_path(), self.run)
        self.assertEqual(self.read(self.store.manifest)["promotion_evidence"]["contract_sha256"], digest(self.evidence / "contract.json"))

    def test_no_evidence_cannot_activate_finalize_or_rollback(self):
        for action in (lambda: self.store.activate(self.run.name), lambda: self.store.rollback(self.run.name),
                       lambda: self.store.finalize(self.run, {}, {}, "x", activate=True)):
            with self.assertRaisesRegex(ValueError, "evidence"):
                action()
            self.assertFalse(self.store.manifest.exists())

    def test_missing_or_false_review_not_approval(self):
        for name in ("selection_provenance_checked", "actuals_provenance_checked", "holdout_not_used_for_selection"):
            self.review[name] = False
            self.refresh_review()
            with self.assertRaisesRegex(ValueError, "provenance review"):
                self.verify()
            self.review[name] = True

    def test_different_model_rejected_even_with_new_review_hash(self):
        self.contract["model_run_id"] = "another-model"
        self.write(self.evidence / "contract.json", self.contract)
        self.refresh_review()
        with self.assertRaisesRegex(ValueError, "another model"):
            self.verify()

    def test_model_component_change_rejected(self):
        (self.run / "ensemble.json").write_text("changed")
        with self.assertRaisesRegex(ValueError, "components"):
            self.verify()

    def test_late_freeze_rejected(self):
        self.contract["forecasts_frozen_at_utc"] = "2025-01-02T12:00:00+00:00"
        self.write(self.evidence / "contract.json", self.contract)
        self.refresh_review()
        with self.assertRaisesRegex(ValueError, "frozen before"):
            self.verify()

    def test_open_period_does_not_read_actuals_manifest(self):
        self.review["reviewed_at"] = "2025-01-15T00:00:00+00:00"
        self.refresh_review()
        (self.evidence / "actuals.json").unlink()
        (self.evidence / "score.json").unlink()
        with self.assertRaisesRegex(ValueError, "still open"):
            verify_promotion_evidence(self.run, self.evidence, now=datetime(2025, 1, 15, tzinfo=timezone.utc))

    def test_forged_passing_report_rejected_after_rehash(self):
        report = self.read(self.evidence / "score.json")
        report["overall"]["mae"] = .01
        self.write(self.evidence / "score.json", report)
        self.refresh_review()
        with self.assertRaisesRegex(ValueError, "does not reproduce"):
            self.verify()

    def test_failed_final_metrics_rejected_even_with_true_attestations(self):
        for row in self.actuals:
            row["actual"] = 80
        self.csv("actuals.csv", self.actuals)
        self.actual_manifest["sha256"] = digest(self.evidence / "actuals.csv")
        self.write(self.evidence / "actuals.json", self.actual_manifest)
        self.rescore()
        self.refresh_review()
        with self.assertRaisesRegex(ValueError, "fails the metric"):
            self.verify()

    def test_final_within_10_regression_vs_persistence_is_rejected(self):
        for index, row in enumerate(self.forecasts):
            row["anchor"] = 105
            row["prediction"] = 111 if index < 3 else 100
        self.csv("forecasts.csv", self.forecasts)
        self.contract["forecast_sha256"] = digest(self.evidence / "forecasts.csv")
        self.write(self.evidence / "contract.json", self.contract)
        self.rescore()
        self.refresh_review()
        score_report = self.read(self.evidence / "score.json")
        self.assertTrue(score_report["target_met_for_full_declared_scope"])
        self.assertLess(
            score_report["overall"]["within_10_accuracy_pct"],
            score_report["persistence_on_same_rows"]["within_10_accuracy_pct"])
        with self.assertRaisesRegex(ValueError, "does not improve on matched persistence"):
            self.verify()

    def test_validation_regression_blocks_promotion(self):
        path = self.evidence / "validation.csv"
        path.write_text(path.read_text().replace(",100,101,111,112", ",100,120,111,112"))
        self.selection["validation_forecasts_sha256"] = digest(path)
        self.write(self.evidence / "selection.json", self.selection)
        self.contract["selection_record_sha256"] = digest(self.evidence / "selection.json")
        self.write(self.evidence / "contract.json", self.contract)
        self.refresh_review()
        with self.assertRaisesRegex(ValueError, "stable matched"):
            self.verify()

    def test_within_10_regression_blocks_validation_despite_lower_error_metrics(self):
        rows = []
        for month in (9, 10, 11):
            origin = f"2024-{month:02}-01"
            for offset, (prediction, champion, anchor) in enumerate((
                    (100, 130, 140), (111, 100, 100), (111, 100, 100)), start=2):
                rows.append(dict(
                    series=self.series, origin=origin,
                    target_date=f"2024-{month:02}-{offset:02}", actual=100,
                    prediction=prediction, champion=champion, anchor=anchor))
        path = self.evidence / "validation_within_10_regression.csv"
        self.csv(path.name, rows)
        with self.assertRaisesRegex(ValueError, "stable matched improvement on all four"):
            validation_comparison(path, date(2025, 1, 2))

    def test_population_cannot_shrink_after_selection(self):
        self.selection["declared_series"].append("Fish||Fish||Standard||Local||kg")
        self.write(self.evidence / "selection.json", self.selection)
        self.contract["selection_record_sha256"] = digest(self.evidence / "selection.json")
        self.write(self.evidence / "contract.json", self.contract)
        self.refresh_review()
        with self.assertRaisesRegex(ValueError, "populations differ"):
            self.verify()

    def test_rejected_activation_preserves_existing_pointer(self):
        self.store.manifest.write_text('{"active_run":"previous"}')
        previous = self.store.manifest.read_bytes()
        self.review["holdout_not_used_for_selection"] = False
        self.refresh_review()
        with self.assertRaises(ValueError):
            self.store.activate(self.run.name, evidence_dir=self.evidence)
        self.assertEqual(self.store.manifest.read_bytes(), previous)

    def test_missing_hashes_cannot_create_an_unchecked_bundle(self):
        metadata = self.read(self.run / "metadata.json")
        metadata["sha256"] = {}
        self.write(self.run / "metadata.json", metadata)
        with self.assertRaisesRegex(ValueError, "required hashes"):
            self.store.activate(self.run.name, evidence_dir=self.evidence)

    def test_reviewed_metadata_cannot_be_changed_after_activation(self):
        self.store.activate(self.run.name, evidence_dir=self.evidence)
        metadata = self.read(self.run / "metadata.json")
        metadata["metrics"] = {"mae": 0}
        self.write(self.run / "metadata.json", metadata)
        with self.assertRaisesRegex(ValueError, "metadata changed"):
            self.store.active_path()


if __name__ == "__main__":
    unittest.main()
