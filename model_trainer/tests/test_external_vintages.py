"""Synthetic publication/revision safety tests; no forecast labels accessed."""
from datetime import date, datetime, timedelta, timezone
import unittest

from features.external_vintages import ObservationArchive, ObservationRelease


def release(period="2024-01-31", available="2024-02-05T09:00:00+08:00", value=20., **kwargs):
    return ObservationRelease(date.fromisoformat(period), datetime.fromisoformat(available),
                              {"temperature": value}, "https://example.gov/bulletin.pdf",
                              "a" * 64, kwargs.get("verified", True), "Synthetic evidence")


def lookup(rows, when, **kwargs):
    return ObservationArchive(rows).at(datetime.fromisoformat(when), max_age=timedelta(days=90), **kwargs)


class ExternalVintageTests(unittest.TestCase):
    def test_publication_time_not_reference_month_controls_access(self):
        row = release()
        self.assertIsNone(lookup([row], "2024-02-05T08:59:59+08:00"))
        self.assertIs(lookup([row], "2024-02-05T09:00:00+08:00"), row)

    def test_revision_never_rewrites_an_earlier_origin(self):
        first = release()
        corrected = release(available="2024-03-03T00:00:00+08:00", value=99.)
        self.assertIs(lookup([first, corrected], "2024-02-10T00:00:00+08:00"), first)
        self.assertIs(lookup([first, corrected], "2024-03-04T00:00:00+08:00"), corrected)

    def test_late_old_revision_does_not_replace_newer_period(self):
        newer = release(period="2024-02-29", available="2024-03-05T00:00:00+08:00")
        old = release(available="2024-03-10T00:00:00+08:00")
        self.assertIs(lookup([newer, old], "2024-03-11T00:00:00+08:00"), newer)

    def test_unverified_archive_excluded_by_default(self):
        row = release(verified=False)
        self.assertIsNone(lookup([row], "2024-02-06T00:00:00+08:00"))
        self.assertIs(lookup([row], "2024-02-06T00:00:00+08:00",
                             allow_unverified_for_diagnostics=True), row)

    def test_same_instant_in_another_timezone(self):
        row = release()
        self.assertIs(lookup([row], "2024-02-05T01:00:00+00:00"), row)

    def test_staleness_uses_reference_date(self):
        row = release(available="2024-05-30T00:00:00+08:00")
        self.assertIsNone(lookup([row], "2024-06-01T00:00:00+08:00"))

    def test_day_boundary_age_uses_release_timezone(self):
        row = release(available="2024-01-31T00:00:00+08:00")
        self.assertIs(lookup([row], "2024-01-30T16:00:00+00:00"), row)

    def test_missing_revision_value_is_not_filled_from_old_value(self):
        first = release()
        corrected = release(available="2024-02-06T00:00:00+08:00", value=None)
        result = lookup([first, corrected], "2024-02-07T00:00:00+08:00")
        self.assertIsNone(result.features["temperature"])

    def test_invalid_observation_date_rejected(self):
        with self.assertRaisesRegex(ValueError, "reference period"):
            release(available="2023-02-05T00:00:00+08:00")

    def test_ambiguous_vintages_rejected(self):
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            ObservationArchive([release(), release(value=21.)])

    def test_naive_datetime_rejected(self):
        with self.assertRaisesRegex(ValueError, "time zone"):
            release(available="2024-02-05T00:00:00")
        with self.assertRaisesRegex(ValueError, "time zone"):
            ObservationArchive([]).at(datetime(2024, 2, 5), max_age=timedelta(days=90))

    def test_nonfinite_and_boolean_measurements_rejected(self):
        for value in [float("nan"), float("inf"), True]:
            with self.assertRaisesRegex(ValueError, "finite"):
                release(value=value)

    def test_caller_cannot_mutate_saved_features(self):
        row = release()
        with self.assertRaises(TypeError):
            row.features["temperature"] = 99.


if __name__ == "__main__":
    unittest.main()
