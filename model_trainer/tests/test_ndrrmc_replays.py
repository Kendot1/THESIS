import base64
from copy import deepcopy
import gzip
import hashlib
import unittest

from external_context.ndrrmc_replays import canonical, verify
from external_context.build_ndrrmc_reviewed import extract


class NDRRMCReplayTests(unittest.TestCase):
    def fixture(self, body=b"%PDF-1.7\noriginal test bytes", compressed=False):
        original = "https://ndrrmc.gov.ph/attachments/article/1/report.pdf"
        expected = {"id":"test", "document_id":"report", "event_id":"event",
                    "original_url":original, "archive_timestamp":"20250102030405",
                    "archive_payload_sha1_base32":base64.b32encode(hashlib.sha1(body).digest()).decode(),
                    "cdx_artifact_sha256":"cdx", "cdx_captured_at_utc":"2026-01-01T00:00:00+00:00",
                    "url":"https://web.archive.org/web/20250102030405id_/"+original}
        raw = gzip.compress(body) if compressed else body
        record = {**expected, "final_url":expected["url"],
                  "artifact_sha256":hashlib.sha256(raw).hexdigest(), "bytes":len(raw),
                  "captured_at_utc":"2026-01-01T00:00:00+00:00",
                  "headers":{"Memento-Datetime":"Thu, 02 Jan 2025 03:04:05 GMT"}}
        if compressed:
            record["headers"]["Content-Encoding"] = "gzip"
        return record, raw, expected

    def test_valid_identity_and_gzip(self):
        for compressed in (False, True):
            result, body = verify(*self.fixture(compressed=compressed))
            self.assertTrue(result["historical_availability_verified"])
            self.assertFalse(result["training_admitted"])
            self.assertEqual(result["available_at_utc"], "2025-01-02T03:04:05+00:00")
            self.assertTrue(body.startswith(b"%PDF-"))

    def test_redirect_rejected(self):
        record, raw, expected = self.fixture()
        record["final_url"] += "?redirected=1"
        with self.assertRaisesRegex(ValueError, "redirected"):
            verify(record, raw, expected)

    def test_timestamp_mismatch_rejected(self):
        record, raw, expected = self.fixture()
        record["headers"]["Memento-Datetime"] = "Fri, 03 Jan 2025 03:04:05 GMT"
        with self.assertRaisesRegex(ValueError, "Memento"):
            verify(record, raw, expected)

    def test_cdx_digest_mismatch(self):
        record, raw, expected = self.fixture()
        expected["archive_payload_sha1_base32"] = "A" * 32
        record["archive_payload_sha1_base32"] = "A" * 32
        with self.assertRaisesRegex(ValueError, "digest"):
            verify(record, raw, expected)

    def test_non_pdf_rejected(self):
        with self.assertRaisesRegex(ValueError, "not a PDF"):
            verify(*self.fixture(body=b"<html>unavailable</html>"))

    def test_cdx_fields_cannot_be_changed(self):
        record, raw, expected = self.fixture()
        record["event_id"] = "different"
        with self.assertRaisesRegex(ValueError, "checked CDX"):
            verify(record, raw, expected)

    def test_local_integrity_and_future(self):
        record, raw, expected = self.fixture()
        bad = deepcopy(record)
        bad["bytes"] += 1
        with self.assertRaisesRegex(ValueError, "integrity"):
            verify(bad, raw, expected)
        record["captured_at_utc"] = "2024-01-01T00:00:00+00:00"
        with self.assertRaisesRegex(ValueError, "after capture"):
            verify(record, raw, expected)

    def test_encoding_rejected(self):
        record, raw, expected = self.fixture()
        record["headers"]["Content-Encoding"] = "br"
        with self.assertRaisesRegex(ValueError, "encoding"):
            verify(record, raw, expected)

    def test_official_document_scope(self):
        good = "https://ndrrmc.gov.ph/attachments/article/1/file.pdf"
        self.assertEqual(canonical(good), canonical(good.replace("https:", "http:")))
        for bad in (good+"?x=1", good+"#x", good.replace("ndrrmc.gov.ph", "example.com"),
                    good.replace("file.pdf", "file.html")):
            with self.assertRaises(ValueError):
                canonical(bad)


class NDRRMCReviewedTests(unittest.TestCase):
    def fixture(self):
        spec = {"as_of_literal":"August 03, 2024 08:00", "rows":[{
            "commodity":"High Value Crops", "affected_farmers_fisherfolk":339,
            "area_totally_damaged_ha":1.99, "area_partially_damaged_ha":38.98,
            "affected_area_ha":40.97, "production_loss_mt":43,
            "production_loss_or_damage_php":1994206}]}
        page = ("as of (August 03, 2024 08:00)\nILOCOS NORTE\nNo breakdown\n"
                "Crops   High Value   339  1.99  38.98  40.97  0  0  0  43  1,994,206\n"
                "        Crops\nILOCOS SUR\n")
        return page, spec

    def test_reviewed_values_and_scope(self):
        rows = extract(*self.fixture())
        self.assertEqual(rows[0]["commodity"], "High Value Crops")
        self.assertEqual(rows[0]["production_loss_mt"], 43)

    def test_changed_numeric_value(self):
        page, spec = self.fixture()
        with self.assertRaisesRegex(ValueError, "number mismatch"):
            extract(page.replace("1,994,206", "1,994,260"), spec)

    def test_date_and_geography_guards(self):
        page, spec = self.fixture()
        for changed in (page.replace("August 03", "August 04"), page.replace("ILOCOS NORTE", "ABRA")):
            with self.assertRaises(ValueError):
                extract(changed, spec)

    def test_missing_commodity_continuation(self):
        page, spec = self.fixture()
        with self.assertRaisesRegex(ValueError, "continuation"):
            extract(page.replace("        Crops\n", ""), spec)

    def test_duplicate_crop_row(self):
        page, spec = self.fixture()
        row = "Crops High Value 339 1.99 38.98 40.97 0 0 0 43 1,994,206\n Crops\n"
        with self.assertRaisesRegex(ValueError, "exact crop row"):
            extract(page.replace("ILOCOS SUR", row+"ILOCOS SUR"), spec)


if __name__ == "__main__":
    unittest.main()
