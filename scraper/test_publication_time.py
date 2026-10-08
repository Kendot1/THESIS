import unittest

from publication_time import publication_metadata


class PublicationMetadataTests(unittest.TestCase):
    def test_timezone_aware_timestamp_is_preserved(self):
        result = publication_metadata(
            {"published_at": "2025-07-22T16:40:00+08:00"}, None, None)
        self.assertEqual(result["published_at"], "2025-07-22T16:40:00+08:00")
        self.assertEqual(result["published_date"], "2025-07-22")
        self.assertEqual(result["publication_precision"], "timestamp")
        self.assertEqual(result["publication_source"], "crawler_metadata")

    def test_date_only_metadata_is_not_promoted_to_midnight_timestamp(self):
        result = publication_metadata(
            {"published_at": "2025-07-22"}, None, "https://news.example/2025/7/22/story")
        self.assertIsNone(result["published_at"])
        self.assertEqual(result["published_date"], "2025-07-22")
        self.assertEqual(result["publication_precision"], "date")

    def test_json_ld_date_only_is_kept_as_date(self):
        result = publication_metadata(
            None, '<script type="application/ld+json">{"datePublished":"2025-07-22"}</script>', None)
        self.assertIsNone(result["published_at"])
        self.assertEqual(result["published_date"], "2025-07-22")
        self.assertEqual(result["publication_source"], "json_ld_date_published")

    def test_url_date_is_recorded_as_date_only(self):
        result = publication_metadata(None, None, "https://news.example/2025/7/22/story")
        self.assertIsNone(result["published_at"])
        self.assertEqual(result["published_date"], "2025-07-22")
        self.assertEqual(result["publication_source"], "url_date")

    def test_undated_story_remains_unavailable_instead_of_using_scrape_time(self):
        result = publication_metadata({}, "<html>undated story</html>", "https://news.example/story")
        self.assertEqual(result, {
            "published_at": None,
            "published_date": None,
            "publication_precision": "unknown",
            "publication_source": "unknown",
        })


if __name__ == "__main__":
    unittest.main()
