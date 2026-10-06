import unittest
from external_context.ocr_customs import indexed_years


class OCRInventoryYearTests(unittest.TestCase):
    def test_customs_multiple_index_years(self):
        self.assertEqual(indexed_years({'occurrences':[{'year_literal':'2024'},{'year_literal':'2025'}]}),{2024,2025})

    def test_doe_explicit_index_year(self):
        self.assertEqual(indexed_years({'index_year_literal':'2024'}),{2024})

    def test_filename_not_used_as_year_evidence(self):
        for source in [{'url':'https://doe.gov.ph/2024.pdf'},{'index_year_literal':'2024-ish'},
                       {'occurrences':[]},{'index_year_literal':202.4}]:
            with self.assertRaises(ValueError):indexed_years(source)


if __name__=='__main__':unittest.main()
