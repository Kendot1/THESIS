"""Integrity checks on small synthetic fixtures; never accesses real holdout labels."""
import csv
import io
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

# This suite runs both from the repository root and from model_trainer/.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from model_trainer.evaluation.frozen_holdout import (
    _timeframe_rows, digest, load_contract, main, score, scoring_attempt_path,
)


class FrozenHoldoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.contract_path = self.root / "contract.json"
        self.actuals_manifest_path = self.root / "actuals.json"
        self.series = ["Rice||Rice||Regular||Local||kg", "Fish||Fish||Standard||Local||kg"]
        self.forecasts = []
        self.actuals = []
        for i, series in enumerate(self.series, start=1):
            for step in (1, 2):
                self.forecasts.append({"series": series, "origin": "2026-10-01",
                    "target_date": f"2026-10-0{step+1}", "horizon": step, "anchor": i * 100,
                    "prediction": i * 100 + 3 - step})
                self.actuals.append({"series": series, "target_date": f"2026-10-0{step+1}",
                                     "actual": i * 100, "is_observed": "true"})
        self.contract = {"forecast_origin": "2026-10-01", "holdout_start": "2026-10-02",
            "holdout_end": "2026-10-03", "horizon_days": 2, "model_run_id": "synthetic",
            "holdout_type": "prospective", "forecasts_frozen_at_utc": "2026-10-01T12:00:00+00:00",
            "forecast_file": "forecasts.csv", "forecast_rows": 4, "forecast_series": 2,
            "total_input_series": 2, "series_coverage": 1.0, "skipped_series_count": 0,
            "skipped_series": []}
        self.actuals_manifest = {"data_file": "actuals.csv", "reconciled_through": "2026-10-03",
            "source": "synthetic test only", "is_observed_definition": "Measured, never imputed"}
        self.now = datetime(2026, 10, 4, tzinfo=timezone.utc)
        self.write_forecasts()
        self.write_actuals()

    def csv_bytes(self, rows):
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        return out.getvalue().encode("utf-8")

    def write_forecasts(self):
        data = self.csv_bytes(self.forecasts)
        (self.root / "forecasts.csv").write_bytes(data)
        self.contract["forecast_sha256"] = digest(data)
        self.contract_path.write_text(json.dumps(self.contract), encoding="utf-8")

    def write_actuals(self):
        data = self.csv_bytes(self.actuals)
        (self.root / "actuals.csv").write_bytes(data)
        self.actuals_manifest["sha256"] = digest(data)
        self.actuals_manifest_path.write_text(json.dumps(self.actuals_manifest), encoding="utf-8")

    def evaluate(self):
        return score(self.contract_path, self.actuals_manifest_path, now=self.now)

    def test_known_errors_original_units_and_group_counts(self):
        result = self.evaluate()
        self.assertEqual(result["overall"]["n"], 4)
        self.assertEqual(result["overall"]["mae"], 1.5)
        self.assertAlmostEqual(result["overall"]["rmse"], math.sqrt(2.5))
        self.assertEqual(result["overall"]["mape"], 1.125)
        self.assertEqual(result["overall"]["within_10_count"], 4)
        self.assertEqual(result["overall"]["within_10_accuracy_pct"], 100)
        self.assertIn("Daily", result["overall_basis"])
        self.assertEqual(result["published_outputs_overall"]["n"], 8)
        self.assertNotIn("range_hit_rate_80", result["overall"])
        self.assertEqual(result["persistence_on_same_rows"]["mae"], 0)
        self.assertEqual(result["groups"]["horizon"]["1"]["mae"], 2)
        self.assertEqual(result["groups"]["category"]["Rice"]["n"], 2)
        for timeframe, expected_periods in (("daily", 4), ("weekly", 2), ("monthly", 2)):
            summary = result["timeframes"][timeframe]
            self.assertEqual(summary["overall"]["within_10_accuracy_pct"], 100)
            self.assertTrue(summary["metric_target_met_on_scored_rows"])
            self.assertEqual(summary["coverage"]["periods_with_observed_actual"], expected_periods)
        self.assertEqual(result["timeframes"]["weekly"]["forecast_step"]["1"]["n"], 2)
        self.assertEqual(result["timeframes"]["monthly"]["forecast_step"]["1"]["n"], 2)
        self.assertEqual(
            result["timeframes"]["daily"]["series_forecast_step"][self.series[0]]["1"]["n"], 1)
        self.assertEqual(
            result["timeframes"]["weekly"]["series_forecast_step"][self.series[0]]["1"]["n"], 1)
        self.assertEqual(result["timeframes"]["weekly"]["coverage"]["partial_periods"], 2)
        self.assertEqual(result["timeframes"]["monthly"]["coverage"]["partial_periods"], 2)
        self.assertTrue(result["target_met_for_full_declared_scope"])

    def test_within_10_boundary_is_inclusive(self):
        self.forecasts[0]["prediction"] = 110
        self.write_forecasts()
        result = self.evaluate()
        self.assertEqual(result["overall"]["within_10_count"], 4)

    def test_period_price_rounding_matches_publisher_sum_order(self):
        series = self.series[0]
        cents = (10845, 9545, 10961, 9115)
        forecasts = {}
        for step, amount in enumerate(cents, start=1):
            target = date(2026, 10, 5) + timedelta(days=step - 1)
            forecasts[(series, target)] = {
                "series": series, "target_date": target.isoformat(),
                "horizon": step, "prediction": amount / 100, "anchor": 100,
            }
        rows = _timeframe_rows(forecasts, {})
        self.assertEqual(rows["weekly"][0]["prediction"], 101.16)
        self.assertEqual(rows["monthly"][0]["prediction"], 101.16)

    def test_no_actuals_opened_before_philippine_day_closes(self):
        self.actuals_manifest_path.unlink()
        early = datetime(2026, 10, 3, 15, 59, 59, tzinfo=timezone.utc)
        with self.assertRaisesRegex(ValueError, "Holdout still open"):
            score(self.contract_path, self.actuals_manifest_path, now=early)

    def test_boundary_is_philippine_midnight(self):
        self.now = datetime(2026, 10, 3, 16, tzinfo=timezone.utc)
        self.assertEqual(self.evaluate()["overall"]["n"], 4)

    def test_incomplete_reconciliation_rejected(self):
        self.actuals_manifest["reconciled_through"] = "2026-10-02"
        self.write_actuals()
        with self.assertRaisesRegex(ValueError, "reconciled"):
            self.evaluate()

    def test_tampered_forecasts_and_actuals_rejected(self):
        with (self.root / "forecasts.csv").open("ab") as out:
            out.write(b"\n")
        with self.assertRaisesRegex(ValueError, "forecast SHA-256"):
            self.evaluate()
        self.write_forecasts()
        with (self.root / "actuals.csv").open("ab") as out:
            out.write(b"\n")
        with self.assertRaisesRegex(ValueError, "Actuals SHA-256"):
            self.evaluate()

    def test_duplicate_actuals_cannot_reweight_errors(self):
        self.actuals.append(dict(self.actuals[0]))
        self.write_actuals()
        with self.assertRaisesRegex(ValueError, "Duplicate actual"):
            self.evaluate()

    def test_duplicate_forecasts_rejected_even_with_updated_hash(self):
        self.forecasts.append(dict(self.forecasts[0]))
        self.write_forecasts()
        with self.assertRaisesRegex(ValueError, "Duplicate frozen"):
            self.evaluate()

    def test_incomplete_forecast_horizon_rejected(self):
        self.forecasts.pop()
        self.contract["forecast_rows"] = 3
        self.write_forecasts()
        with self.assertRaisesRegex(ValueError, "full forecast horizon"):
            self.evaluate()

    def test_imputed_prices_never_score_as_observed_truth(self):
        self.actuals[0].update(is_observed="false", actual="NaN")
        self.write_actuals()
        result = self.evaluate()
        self.assertEqual(result["overall"]["n"], 3)
        self.assertEqual(result["coverage"]["unobserved_rows_excluded"], 1)
        self.assertEqual(result["coverage"]["forecast_rows_with_observed_actual"], .75)
        self.assertFalse(result["full_declared_scope_observed"])

    def test_zero_and_near_zero_prices_are_reported_outside_percentage_metrics(self):
        self.actuals[0]["actual"] = "0"
        self.actuals[1]["actual"] = "0.000000001"
        self.write_actuals()
        result = self.evaluate()
        overall = result["overall"]
        self.assertEqual(overall["n"], 4)
        self.assertEqual(overall["percentage_n"], 2)
        self.assertEqual(overall["excluded_near_zero"], 2)
        self.assertEqual(overall["within_10_count"], 2)
        self.assertEqual(overall["within_10_accuracy_pct"], 100)
        self.assertAlmostEqual(overall["mape"], 0.75)
        self.assertAlmostEqual(overall["mae"], 51.5)
        self.assertEqual(result["coverage"][
            "near_zero_observed_forecasts_excluded_from_percentage_metrics"], 2)
        self.assertEqual(result["timeframes"]["weekly"]["overall"]["excluded_near_zero"], 1)

    def test_invalid_observed_price_requires_reconciliation(self):
        for value in ("NaN", "Infinity", "-1"):
            with self.subTest(value=value):
                self.actuals[0]["actual"] = value
                self.write_actuals()
                with self.assertRaises(ValueError):
                    self.evaluate()

    def test_skipped_series_prevents_full_population_success(self):
        skipped = "Vegetables||Tomato||Standard||Local||kg"
        self.contract.update(total_input_series=3, series_coverage=2/3, skipped_series_count=1,
                             skipped_series=[{"series": skipped, "reason": "insufficient history"}])
        self.actuals.append({"series": skipped, "target_date": "2026-10-02", "actual": 100,
                             "is_observed": "true"})
        self.write_forecasts()
        self.write_actuals()
        result = self.evaluate()
        self.assertTrue(result["metric_target_met_on_scored_rows"])
        self.assertFalse(result["target_met_for_full_declared_scope"])
        self.assertEqual(result["coverage"]["observed_outcomes_missing_forecasts"], 1)

    def test_forecast_series_without_outcomes_is_disclosed(self):
        self.actuals = self.actuals[:2]
        self.write_actuals()
        result = self.evaluate()
        self.assertFalse(result["full_declared_scope_observed"])
        self.assertEqual(result["coverage"]["forecast_series_without_observed_outcomes"], [self.series[1]])

    def test_dates_and_point_prices_are_validated(self):
        self.forecasts[0]["horizon"] = 2
        self.write_forecasts()
        with self.assertRaisesRegex(ValueError, "origin/date/horizon"):
            self.evaluate()
        self.forecasts[0].update(horizon=1, prediction=-5)
        self.write_forecasts()
        with self.assertRaisesRegex(ValueError, "point prediction"):
            self.evaluate()

    def test_input_paths_cannot_escape_manifest_directory(self):
        self.contract["forecast_file"] = "../outside.csv"
        self.write_forecasts()
        with self.assertRaisesRegex(ValueError, "manifest directory"):
            load_contract(self.contract_path)

    def test_cli_cannot_overwrite_a_saved_evaluation(self):
        output = self.root / "result.json"
        output.write_text("sealed")
        with patch("sys.argv", ["score", "score", str(self.contract_path),
                               str(self.actuals_manifest_path), str(output)]):
            with self.assertRaises(FileExistsError):
                main(now=self.now)
        self.assertEqual(output.read_text(), "sealed")
        self.assertFalse(scoring_attempt_path(self.contract_path).exists())

    def test_cli_reserves_one_scoring_attempt_across_output_paths(self):
        first_output = self.root / "first-score.json"
        args = ["score", "score", str(self.contract_path),
                str(self.actuals_manifest_path), str(first_output)]
        with patch("sys.argv", args):
            main(now=self.now)
        self.assertTrue(first_output.exists())
        marker = scoring_attempt_path(self.contract_path)
        self.assertEqual(json.loads(marker.read_text())["status"], "completed")

        second_output = self.root / "alternate-score-name.json"
        with patch("sys.argv", ["score", "score", str(self.contract_path),
                               str(self.actuals_manifest_path), str(second_output)]), \
                patch("model_trainer.evaluation.frozen_holdout.score") as scorer:
            with self.assertRaisesRegex(FileExistsError, "another output path"):
                main(now=self.now)
        scorer.assert_not_called()
        self.assertFalse(second_output.exists())

    def test_cli_does_not_reserve_or_open_actuals_before_close(self):
        self.actuals_manifest_path.unlink()
        output = self.root / "too-early.json"
        early = datetime(2026, 10, 3, 15, 59, 59, tzinfo=timezone.utc)
        with patch("sys.argv", ["score", "score", str(self.contract_path),
                               str(self.actuals_manifest_path), str(output)]):
            with self.assertRaisesRegex(ValueError, "Holdout still open"):
                main(now=early)
        self.assertFalse(scoring_attempt_path(self.contract_path).exists())
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
