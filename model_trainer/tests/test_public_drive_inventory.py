import json
import unittest

from external_context.inventory_public_drive import decode_js_string, parse_folder
from external_context.inventory_car_search import parse_results


class PublicDriveInventoryTests(unittest.TestCase):
    def html(self, rows):
        encoded = "".join("\\x%02x" % ord(c) for c in json.dumps([rows]))
        return "window['_DRIVE_ivd'] = '" + encoded + "';"

    def test_literal_listing(self):
        result = parse_folder(self.html([["0123456789id", ["parent"], "2025", "application/vnd.google-apps.folder"]]), "parent")
        self.assertEqual(result[0]["name"], "2025")
        self.assertFalse(result[0]["historical_publication_verified"])

    def test_wrong_parent(self):
        with self.assertRaises(ValueError):
            parse_folder(self.html([["0123456789id", ["other"], "2025", "application/vnd.google-apps.folder"]]), "parent")

    def test_duplicate(self):
        row = ["0123456789id", ["parent"], "2025", "application/vnd.google-apps.folder"]
        with self.assertRaises(ValueError):
            parse_folder(self.html([row, row]), "parent")

    def test_missing_or_multiple_assignments(self):
        for html in ("", self.html([]) * 2):
            with self.assertRaises(ValueError):
                parse_folder(html, "parent")

    def test_invalid_escapes(self):
        for raw in ("\\", "\\x0g", "\\u123", "\\q"):
            with self.assertRaises(ValueError):
                decode_js_string(raw)

    def test_not_code_execution(self):
        with self.assertRaises(json.JSONDecodeError):
            parse_folder("window['_DRIVE_ivd'] = 'alert(1)';", "parent")

    def test_unicode_and_slash(self):
        self.assertEqual(decode_js_string(r"\u20b1\/\x32"), "\u20b1/2")


class CARSearchInventoryTests(unittest.TestCase):
    def html(self, url):
        return ('<div id="content"><article><h2 class="entry-title"><a href="' + url +
                '">Supply</a></h2><div class="entry-summary">Reported supply</div></article></div>')

    def test_post_and_page(self):
        for query in ("p=123", "page_id=456"):
            rows, pagination = parse_results(self.html("https://car.da.gov.ph/?" + query))
            self.assertEqual(len(rows), 1)
            self.assertFalse(rows[0]["historical_publication_verified"])
            self.assertEqual(rows[0]["summary"], "Reported supply")
            self.assertEqual(pagination, [])

    def test_reject_foreign_and_ambiguous_links(self):
        for url in ("https://example.org/?p=123", "https://car.da.gov.ph/?p=1&p=2",
                    "https://car.da.gov.ph/?p=1&page_id=2", "https://car.da.gov.ph/?p=abc"):
            with self.assertRaises(ValueError):
                parse_results(self.html(url))

    def test_ignore_sidebar_articles(self):
        html = self.html("https://car.da.gov.ph/?p=123").replace('id="content"', 'id="sidebar"')
        self.assertEqual(parse_results(html)[0], [])

    def test_empty_search_no_fabricated_rows(self):
        self.assertEqual(parse_results('<div id="content">Nothing found</div>')[0], [])


if __name__ == "__main__":
    unittest.main()
