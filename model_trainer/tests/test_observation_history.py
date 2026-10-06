import unittest
import numpy as np
import pandas as pd
from features.observation_history import observation_history_features, OBSERVATION_FEATURES


def panel():
    return pd.DataFrame({"product_category": "Vegetables", "product_name": "Lettuce",
                         "product_variant": "Romaine", "origin": "Local", "unit": "kg",
                         "report_date": pd.date_range("2024-01-01", periods=10),
                         "observed_price": np.arange(10) * 2. + 100,
                         "price_index": np.arange(10) * 2. + 100, "is_observed": True})


class ObservationHistoryTests(unittest.TestCase):
    def test_linear_slope_uses_calendar_days(self):
        data = panel()
        data.loc[[1, 2, 4], "is_observed"] = False
        result = observation_history_features(data)
        self.assertAlmostEqual(result.loc[7, "observed_slope_7d"], 2.)
        self.assertEqual(result.loc[7, "observed_count_7d"], 4)

    def test_target_and_future_rows_do_not_change_origin_features(self):
        data = panel()
        expected = observation_history_features(data).loc[:6, OBSERVATION_FEATURES]
        data.loc[6:, ["observed_price", "price_index"]] = 10000.
        data.loc[6:, "is_observed"] = False
        actual = observation_history_features(data).loc[:6, OBSERVATION_FEATURES]
        pd.testing.assert_frame_equal(expected, actual)

    def test_filled_prices_are_not_new_observations(self):
        data = panel()
        data.loc[1:8, "is_observed"] = False
        data.loc[1:8, "price_index"] = 9999.
        result = observation_history_features(data)
        self.assertEqual(result.loc[9, "observed_count_7d"], 0)
        self.assertEqual(result.loc[9, "last_observed_age_days"], 9)
        self.assertTrue(np.isnan(result.loc[9, "observed_slope_7d"]))

    def test_no_cross_series_history(self):
        first = panel()
        second = panel().assign(product_variant="Iceberg", observed_price=200.)
        actual = observation_history_features(pd.concat([first, second]))
        last = actual[actual.product_variant.eq("Iceberg")].iloc[-1]
        self.assertEqual(last.observed_slope_7d, 0.)
        self.assertEqual(last.observed_count_7d, 7)

    def test_first_observation_is_not_known_at_its_own_feature_row(self):
        first = observation_history_features(panel()).iloc[0]
        self.assertEqual(first.observed_count_7d, 0)
        self.assertTrue(np.isnan(first.last_observed_age_days))


if __name__ == "__main__":
    unittest.main()
