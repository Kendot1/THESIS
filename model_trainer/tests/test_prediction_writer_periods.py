import unittest

import numpy as np
import pandas as pd

from pipeline.prediction_writer import (
    PUBLISHED_FORECAST_STEPS,
    PredictionWriter,
)


class TestPredictionWriterPeriods(unittest.TestCase):
    def test_period_averages_use_stable_decimal_rounding(self):
        dates = np.array(["2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08"],
                         dtype="datetime64[D]")
        points = np.array([108.45, 95.45, 109.61, 91.15])

        rows = PredictionWriter._rows("product-1", dates, points,
                                      np.datetime64("2026-10-04", "D"), {})
        weekly = next(row for row in rows if row["forecast_horizon"] == "weekly")
        monthly = next(row for row in rows if row["forecast_horizon"] == "monthly")

        self.assertEqual(weekly["predicted_price"], 101.16)
        self.assertEqual(monthly["predicted_price"], 101.16)

    def test_persists_daily_and_calendar_period_point_sequences(self):
        origin = np.datetime64("2026-09-27", "D")
        dates = origin + np.arange(1, 31).astype("timedelta64[D]")
        points = np.arange(101, 131, dtype=float)
        product_metrics = {"confidence_by_step": {
            "daily": {"1": {"evidence_status": "validated",
                             "evaluation_source": "chronological_validation",
                             "confidence_score": 83.0,
                             "confidence_level": "High"}},
            "weekly": {"1": {"evidence_status": "validated",
                              "evaluation_source": "chronological_validation",
                              "confidence_score": 76.0,
                              "confidence_level": "Moderate"}},
        }}

        rows = PredictionWriter._rows("product-1", dates, points, origin, product_metrics)
        daily = [row for row in rows if row["forecast_horizon"] == "daily"]
        weekly = [row for row in rows if row["forecast_horizon"] == "weekly"]
        monthly = [row for row in rows if row["forecast_horizon"] == "monthly"]

        self.assertEqual(len(daily), 30)
        self.assertEqual(len(weekly), 5)
        self.assertEqual(len(monthly), 2)
        self.assertEqual([row["forecast_step"] for row in daily], list(range(1, 31)))
        self.assertEqual([row["predicted_price"] for row in weekly],
                         [104.0, 111.0, 118.0, 125.0, 129.5])
        self.assertEqual((weekly[-1]["target_period_start"], weekly[-1]["target_period_end"],
                          weekly[-1]["covered_days"], weekly[-1]["period_days"]),
                         ("2026-10-26", "2026-11-01", 2, 7))
        self.assertEqual([row["predicted_price"] for row in monthly], [102.0, 117.0])
        self.assertEqual((monthly[0]["target_period_start"], monthly[0]["covered_days"],
                          monthly[0]["period_days"]), ("2026-09-01", 3, 30))
        self.assertEqual((daily[0]["confidence_score"], daily[0]["confidence_level"]),
                         (83.0, "High"))
        self.assertEqual((weekly[0]["confidence_score"], weekly[0]["confidence_level"]),
                         (76.0, "Moderate"))
        self.assertIsNone(monthly[0]["confidence_score"])
        self.assertEqual(monthly[0]["confidence_level"], "Insufficient data")
        self.assertTrue(all("lower_bound" not in row and "upper_bound" not in row for row in rows))

    def test_persistence_fallback_withholds_ensemble_confidence(self):
        origin = np.datetime64("2026-09-27", "D")
        dates = origin + np.arange(1, 31).astype("timedelta64[D]")
        points = np.full(30, 42.0)
        product_metrics = {"confidence_by_horizon": {
            horizon: {"evidence_status": "validated", "confidence_score": 95.0,
                      "confidence_level": "Very High"}
            for horizon in ("daily", "weekly", "monthly")
        }}

        rows = PredictionWriter._rows(
            "product-1", dates, points, origin, product_metrics,
            allow_confidence=False)

        self.assertTrue(rows)
        self.assertTrue(all(row["confidence_score"] is None for row in rows))
        self.assertTrue(all(row["confidence_level"] == "Insufficient data"
                            for row in rows))

    def test_inputs_extend_to_issue_date_only_within_causal_fill_limit(self):
        columns = {
            "product_category": "Rice", "product_variant": "Standard",
            "origin": "Local", "unit": "kg",
        }
        clean = pd.DataFrame([
            {**columns, "product_name": "Fresh", "report_date": "2026-10-01",
             "price_index": 10.0, "observed_price": 10.0, "is_observed": True},
            {**columns, "product_name": "Stale", "report_date": "2026-09-30",
             "price_index": 20.0, "observed_price": 20.0, "is_observed": True},
        ])

        extended = PredictionWriter._extend_inputs_to_origin(
            clean, pd.Timestamp("2026-10-08"), max_fill_days=7)
        latest = extended[extended.report_date.eq(pd.Timestamp("2026-10-08"))]
        prices = latest.set_index("product_name").price_index

        self.assertEqual(set(prices.index), {"Fresh", "Stale"})
        self.assertEqual(prices["Fresh"], 10.0)
        self.assertTrue(np.isnan(prices["Stale"]))
        self.assertTrue((latest.report_date == pd.Timestamp("2026-10-08")).all())

    def test_production_rows_have_exact_objective_horizon_counts(self):
        origin = pd.Timestamp("2026-10-05")
        history = pd.DataFrame({
            "report_date": pd.date_range("2026-08-01", origin, freq="D"),
            "observed_price": np.linspace(40.0, 60.0, 66),
            "is_observed": True,
        })
        dates = origin.to_datetime64() + np.arange(1, 8).astype("timedelta64[D]")
        points = np.linspace(61.0, 67.0, 7)
        metrics = {"prediction_intervals": {"daily": {
            "1": {"nominal_level": 0.8, "lower_error_php": -2.0,
                  "upper_error_php": 3.0, "reliability_status": "limited"},
        }}}

        rows = PredictionWriter._production_rows(
            "product-1", dates, points, origin, history, metrics,
        )
        counts = {name: sum(row["forecast_horizon"] == name for row in rows)
                  for name in PUBLISHED_FORECAST_STEPS}
        self.assertEqual(counts, {"daily": 7, "weekly": 4, "monthly": 1})
        self.assertEqual(PUBLISHED_FORECAST_STEPS, counts)
        daily = [row for row in rows if row["forecast_horizon"] == "daily"]
        weekly = [row for row in rows if row["forecast_horizon"] == "weekly"]
        monthly = [row for row in rows if row["forecast_horizon"] == "monthly"]
        self.assertEqual(daily[0]["prediction_date"], "2026-10-06")
        self.assertEqual(daily[-1]["prediction_date"], "2026-10-12")
        self.assertEqual((weekly[0]["target_period_start"], weekly[0]["target_period_end"]),
                         ("2026-10-06", "2026-10-12"))
        self.assertEqual(weekly[-1]["forecast_step"], 4)
        self.assertEqual((monthly[0]["target_period_start"], monthly[0]["target_period_end"]),
                         ("2026-10-06", "2026-11-04"))
        self.assertEqual((daily[0]["lower_bound"], daily[0]["upper_bound"]), (59.0, 64.0))
        self.assertTrue(all(row["confidence_level"] == "Insufficient data" for row in weekly + monthly))


if __name__ == "__main__":
    unittest.main()
