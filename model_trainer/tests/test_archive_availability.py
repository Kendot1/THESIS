import base64
import hashlib
import json
import unittest

from external_context.build_context import sha256
from external_context.verify_archive_availability import canonical_original, match_source, parse_cdx


class ArchiveAvailabilityTests(unittest.TestCase):
    def setUp(self):
        self.content = b"%PDF-1.4 fake PDF bytes for digest unit tests"
        self.url = "https://customs.gov.ph/wp-content/uploads/2024/04/Ref_Val_2024_04_001.pdf"
        self.source = {"id": "test", "url": self.url, "artifact_sha256": sha256(self.content)}
        self.digest = base64.b32encode(hashlib.sha1(self.content).digest()).decode("ascii")

    def rows(self, timestamp="20250424102843", digest=None, url=None):
        return parse_cdx(json.dumps([["timestamp", "original", "digest"], [timestamp, url or self.url, digest or self.digest]]).encode())

    def test_exact_pdf_match_uses_capture_time(self):
        result = match_source(self.source, self.content, self.rows())
        self.assertTrue(result["historical_availability_verified"])
        self.assertEqual(result["available_at_utc"], "2025-04-24T10:28:43+00:00")
        self.assertIsNone(result["original_published_at"])
        self.assertFalse(result["training_admitted"])

    def test_same_url_changed_payload_is_unverified(self):
        result = match_source(self.source, self.content, self.rows(digest="A" * 32))
        self.assertFalse(result["historical_availability_verified"])
        self.assertEqual(result["archive_url_matches"], 1)
        self.assertIsNone(result["available_at_utc"])

    def test_same_payload_other_url_not_silently_mapped(self):
        result = match_source(self.source, self.content, self.rows(url="https://customs.gov.ph/other.pdf"))
        self.assertFalse(result["historical_availability_verified"])

    def test_first_matching_capture_selected(self):
        rows = self.rows("20250424102843") + self.rows("20240714162614")
        result = match_source(self.source, self.content, rows)
        self.assertEqual(result["available_at_utc"], "2024-07-14T16:26:14+00:00")

    def test_empty_index_not_invented_evidence(self):
        self.assertEqual(parse_cdx(b"[]"), [])
        self.assertFalse(match_source(self.source, self.content, [])["historical_availability_verified"])

    def test_invalid_date_and_digest_rejected(self):
        with self.assertRaises(ValueError):
            self.rows("20250230000000")
        with self.assertRaises(ValueError):
            self.rows(digest="not_a_digest")

    def test_foreign_host_rejected(self):
        with self.assertRaises(ValueError):
            canonical_original("https://example.com/file.pdf")

    def test_wrong_original_bytes_rejected(self):
        with self.assertRaises(ValueError):
            match_source(self.source, self.content + b"changed", self.rows())

    def test_explicit_official_migration_requires_same_filename_and_payload(self):
        old = self.url.replace("/2024/04/", "/2023/01/")
        rows = self.rows(url=old)
        self.assertFalse(match_source(self.source, self.content, rows)["historical_availability_verified"])
        result = match_source(self.source, self.content, rows, allow_official_migration_matches=True)
        self.assertTrue(result["historical_availability_verified"])
        self.assertEqual(result["migrated_payload_matches"], 1)
        self.assertIn("migrated", result["basis"])

    def test_similar_migrated_filename_is_not_accepted(self):
        rows = self.rows(url=self.url.replace(".pdf", "-1.pdf"))
        self.assertFalse(match_source(self.source, self.content, rows, allow_official_migration_matches=True)["historical_availability_verified"])

    def test_migration_with_changed_payload_not_accepted(self):
        old = self.url.replace("/2024/04/", "/2023/01/")
        rows = self.rows(url=old, digest="A" * 32)
        self.assertFalse(match_source(self.source, self.content, rows, allow_official_migration_matches=True)["historical_availability_verified"])


if __name__ == "__main__":
    unittest.main()
