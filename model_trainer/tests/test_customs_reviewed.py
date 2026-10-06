import copy
import json
import unittest

from external_context.build_customs_reviewed import HERE, normalize


class ReviewedCustomsTests(unittest.TestCase):
    def setUp(self):
        self.review = json.loads((HERE / "customs_reviewed_rows.json").read_bytes())
        self.doc = self.review["documents"][0]
        self.page = self.doc["pages"][0]
        self.source = {"id": self.doc["source_id"], "url": "https://customs.gov.ph/source.pdf",
                       "artifact_sha256": self.doc["artifact_sha256"], "captured_at_utc": "2026-10-03T17:40:04+00:00"}

    def test_reviewed_values_units_and_country(self):
        rows = normalize(self.doc, self.page, self.source, self.review)
        self.assertEqual(len(rows), 26)
        self.assertEqual(rows[0]["value_decimal"], "0.404")
        self.assertEqual(rows[0]["unit"], "USD/kg")
        self.assertEqual(rows[0]["country_of_origin"], "Thailand")
        self.assertEqual(rows[16]["original_value"], "$0.750")
        self.assertEqual(rows[19]["country_code_literal"], "TH")

    def test_no_invented_publication_or_product_grade_mapping(self):
        rows = normalize(self.doc, self.page, self.source, self.review)
        for row in rows:
            self.assertTrue(row["numeric_visual_reviewed"])
            self.assertFalse(row["historical_availability_verified"])
            self.assertFalse(row["training_admitted"])
            self.assertFalse(row["foodcast_grade_mapping_verified"])
            self.assertIsNone(row["published_at"])
            self.assertIsNone(row["tariff_heading"])

    def test_issue_year_is_not_inferred_from_memo_identifier(self):
        row = normalize(self.doc, self.page, self.source, self.review)[0]
        self.assertEqual(row["issue_date"], "2019-12-23")
        self.assertIn("2020", row["memo_identifier_literal"])

    def test_invalid_country_rejected(self):
        page = copy.deepcopy(self.page)
        page["rows"][0][1] = "TM"
        with self.assertRaises(ValueError):
            normalize(self.doc, page, self.source, self.review)

    def test_decimal_punctuation_not_silently_repaired(self):
        page = copy.deepcopy(self.page)
        page["rows"][0][2] = "$0,404"
        with self.assertRaises(ValueError):
            normalize(self.doc, page, self.source, self.review)

    def test_unit_changes_require_review(self):
        page = copy.deepcopy(self.page)
        page["unit_literal"] = "US$ Per ton"
        with self.assertRaises(ValueError):
            normalize(self.doc, page, self.source, self.review)

    def test_duplicate_grade_country_rejected(self):
        page = copy.deepcopy(self.page)
        page["rows"].append(page["rows"][0])
        with self.assertRaises(ValueError):
            normalize(self.doc, page, self.source, self.review)

    def test_reversed_period_rejected(self):
        doc = copy.deepcopy(self.doc)
        doc["reference_start"] = "2019-12-30"
        with self.assertRaises(ValueError):
            normalize(doc, self.page, self.source, self.review)

    def test_late_issue_date_is_preserved_without_backdating(self):
        doc = copy.deepcopy(self.doc)
        doc["issue_date"] = "2020-01-03"
        row = normalize(doc, self.page, self.source, self.review)[0]
        self.assertEqual(row["reference_end"], "2019-12-29")
        self.assertEqual(row["issue_date"], "2020-01-03")
        self.assertIsNone(row["historical_available_at"])

    def test_explicit_source_na_is_null_not_zero(self):
        page = copy.deepcopy(self.page)
        page["rows"][0][2] = "NA"
        row = normalize(self.doc, page, self.source, self.review)[0]
        self.assertIsNone(row["value"])
        self.assertIsNone(row["value_decimal"])
        self.assertEqual(row["missing_reason"], "source_reports_NA")


if __name__ == "__main__":
    unittest.main()
