from datetime import date, datetime, timezone
import unittest

from external_context.customs_features import QuoteArchive, ReferenceQuote, join_reviewed_availability


class CustomsFeatureTests(unittest.TestCase):
    def quote(self, value=.579, available="2024-07-14T15:31:02+00:00", start="2024-02-19", record="quote1"):
        return ReferenceQuote(record, "White Rice 25% Broken", "VN", date.fromisoformat(start), date(2024, 2, 25),
                              datetime.fromisoformat(available), value, "source_reports_NA" if value is None else None,
                              "a" * 64, "https://customs.gov.ph/file.pdf")

    def at(self, archive, origin, lag=0, age=180):
        return archive.at(datetime.fromisoformat(origin), grade="White Rice 25% Broken", country="VN",
                          lag_days=lag, max_age_days=age)

    def test_reference_period_does_not_grant_early_access(self):
        result = self.at(QuoteArchive([self.quote()]), "2024-02-25T00:00:00+00:00")
        self.assertIsNone(result["value"])
        self.assertEqual(result["reason"], "no_available_quote")

    def test_exact_availability_boundary(self):
        archive = QuoteArchive([self.quote()])
        self.assertIsNone(self.at(archive, "2024-07-14T15:31:01+00:00")["value"])
        self.assertEqual(self.at(archive, "2024-07-14T15:31:02+00:00")["value"], .579)

    def test_recent_capture_does_not_refresh_old_quote(self):
        result = self.at(QuoteArchive([self.quote()]), "2024-07-15T00:00:00+00:00", age=30)
        self.assertEqual(result["reason"], "stale_reference")
        self.assertGreater(result["reference_age_days"], 140)

    def test_lag_shifts_information_cutoff(self):
        archive = QuoteArchive([self.quote()])
        self.assertIsNone(self.at(archive, "2024-07-15T00:00:00+00:00", lag=1)["value"])
        self.assertEqual(self.at(archive, "2024-07-16T00:00:00+00:00", lag=1)["value"], .579)

    def test_source_missing_revision_does_not_reuse_old_price(self):
        archive = QuoteArchive([self.quote(), self.quote(None, "2024-07-16T00:00:00+00:00", record="quote2")])
        result = self.at(archive, "2024-07-17T00:00:00+00:00")
        self.assertIsNone(result["value"])
        self.assertEqual(result["reason"], "source_reports_NA")

    def test_naive_origin_and_negative_lag_fail(self):
        archive = QuoteArchive([self.quote()])
        with self.assertRaises(ValueError):
            self.at(archive, "2024-07-15T00:00:00")
        with self.assertRaises(ValueError):
            self.at(archive, "2024-07-15T00:00:00+00:00", lag=-1)

    def test_duplicate_vintage_fails(self):
        with self.assertRaises(ValueError):
            QuoteArchive([self.quote(), self.quote()])

    def test_mismatched_capture_cannot_join(self):
        with self.assertRaises(ValueError):
            join_reviewed_availability({"capture_manifest_sha256": "a"}, {"source_capture_sha256": "b"})


if __name__ == "__main__":
    unittest.main()
