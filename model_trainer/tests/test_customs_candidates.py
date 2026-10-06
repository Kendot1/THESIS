import unittest

from external_context.extract_customs_candidates import parse_page


def tsv(words):
    header = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
    root = "1\t1\t0\t0\t0\t0\t0\t0\t1000\t1400\t-1\t\n"
    rows = [f"5\t1\t1\t1\t1\t{i}\t{x}\t{y}\t70\t20\t{conf}\t{text}\n"
            for i, (text, x, y, conf) in enumerate(words, 1)]
    return (header + root + "".join(rows)).encode()


class CustomsCandidateTests(unittest.TestCase):
    def parse(self, words, text=b"REFERENCE VALUE FOR RICE US$ Per kg"):
        return parse_page(tsv(words), text)

    def test_country_alignment_and_no_automatic_numeric_admission(self):
        result = self.parse([("VN", 580, 300, 95), ("$0.340", 750, 300, 95)])
        row = result["candidates"][0]
        self.assertEqual(row["country_code_candidate"], "VN")
        self.assertEqual(row["original_ocr_value"], "$0.340")
        self.assertIsNone(row["normalized_value"])
        self.assertIsNone(row["grade"])
        self.assertFalse(row["training_admitted"])

    def test_neighboring_row_not_used_as_country(self):
        result = self.parse([("VN", 580, 260, 95), ("$0.340", 750, 300, 95)])
        self.assertIsNone(result["candidates"][0]["country_code_candidate"])

    def test_ambiguous_country_requires_review(self):
        result = self.parse([("VN", 580, 300, 95), ("TH", 600, 300, 95), ("$0.340", 750, 300, 95)])
        self.assertIsNone(result["candidates"][0]["country_code_candidate"])

    def test_decimal_comma_is_preserved_and_flagged(self):
        row = self.parse([("$0,340", 750, 300, 95)])["candidates"][0]
        self.assertEqual(row["original_ocr_value"], "$0,340")
        self.assertIn("decimal_comma_requires_review", row["review_flags"])

    def test_unrecognized_currency_token_rejected(self):
        result = self.parse([("$0:340", 750, 300, 95)])
        self.assertEqual(result["candidates"], [])
        self.assertEqual(len(result["rejected_price_tokens"]), 1)

    def test_missing_unit_never_assumed(self):
        row = self.parse([("$0.340", 750, 300, 95)], text=b"US$ Per ton")["candidates"][0]
        self.assertIsNone(row["unit_text_candidate"])
        self.assertIn("unit_not_recognized", row["review_flags"])

    def test_low_confidence_flag_preserved(self):
        row = self.parse([("$0.340", 750, 300, 45)])["candidates"][0]
        self.assertIn("low_ocr_confidence", row["review_flags"])


if __name__ == "__main__":
    unittest.main()
