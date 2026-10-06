import gzip
import unittest

from external_context.inventory_archived_customs import decode_body, extract_links


class ArchivedIndexTests(unittest.TestCase):
    def setUp(self):
        self.url = "https://web.archive.org/web/20210124152842id_/https://customs.gov.ph/memoranda-for-reference-values/"
        self.record = {"archive_timestamp": "20210124152842", "url": self.url, "final_url": self.url,
                       "original_url": "https://customs.gov.ph/memoranda-for-reference-values/",
                       "artifact_sha256": "a" * 64, "headers": {"memento-datetime": "Sun, 24 Jan 2021 15:28:42 GMT"}}
        self.body = b'<table><tr><td>Shipments of Rice - January 4-10, 2021</td><td><a href="/wp-content/uploads/2021/01/rice.pdf">Download</a></td></tr></table>'

    def test_relative_original_link_not_replay_link(self):
        row = extract_links(self.record, self.body)[0]
        self.assertEqual(row["original_pdf_url"], "https://customs.gov.ph/wp-content/uploads/2021/01/rice.pdf")
        self.assertEqual(row["index_available_at_utc"], "2021-01-24T15:28:42+00:00")
        self.assertFalse(row["pdf_historical_payload_verified"])

    def test_gzip_response_decoded_with_raw_provenance(self):
        self.record["headers"]["content-encoding"] = "gzip"
        self.assertEqual(decode_body(self.record, gzip.compress(self.body)), self.body)
        self.assertEqual(len(extract_links(self.record, gzip.compress(self.body))), 1)

    def test_capture_date_mismatch_rejected(self):
        self.record["headers"]["memento-datetime"] = "Mon, 25 Jan 2021 15:28:42 GMT"
        with self.assertRaises(ValueError):
            extract_links(self.record, self.body)

    def test_replay_redirect_requires_review(self):
        self.record["final_url"] = self.url.replace("20210124", "20210125")
        with self.assertRaises(ValueError):
            extract_links(self.record, self.body)

    def test_no_rice_links_fails(self):
        with self.assertRaises(ValueError):
            extract_links(self.record, b"<html>Unavailable snapshot</html>")


if __name__ == "__main__":
    unittest.main()
