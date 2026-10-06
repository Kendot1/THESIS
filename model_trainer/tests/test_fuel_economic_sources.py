import unittest

from external_context.inventory_fuel_economic import extract_links, build_registry
from external_context.extract_fao_newsletters import extract


def source(host):
    return {'id': 'test', 'url': 'https://' + host + '/index', 'final_url': 'https://' + host + '/index',
            'artifact_sha256': 'a' * 64, 'captured_at_utc': '2026-10-04T00:00:00+00:00'}


class FuelEconomicSourcesTests(unittest.TestCase):
    def test_doe_context_and_no_availability_inference(self):
        html = b'<table><tr><td>2024</td><td><ul><li>November<ul><li>27 to December 2<ul><li><a href="https://prod-cms.doe.gov.ph/documents/d/lfo/car">CAR</a></li></ul></li></ul></li></ul></td></tr></table>'
        rows = extract_links(source('doe.gov.ph'), html, 'doe')
        self.assertEqual(rows[0]['index_year_literal'], '2024')
        self.assertEqual(rows[0]['anchor_literal'], 'CAR')
        self.assertIn('27 to December 2 CAR', rows[0]['ancestor_list_literals'])
        self.assertFalse(rows[0]['historical_publication_verified'])
        self.assertFalse(rows[0]['training_admitted'])

    def test_doe_unknown_year_fails(self):
        with self.assertRaisesRegex(ValueError, 'year row'):
            extract_links(source('doe.gov.ph'), b'<a href="https://prod-cms.doe.gov.ph/documents/d/x">2024</a>', 'doe')

    def test_publisher_and_external_link_rejected(self):
        with self.assertRaises(ValueError):
            extract_links(source('evil.test'), b'', 'doe')
        with self.assertRaises(ValueError):
            extract_links(source('www.fao.org'), b'<a href="https://newsletters.fao.org.evil.test/q/1">fake</a>', 'fao')

    def test_fao_literal_encoding_and_whitespace(self):
        rows = extract_links(source('www.fao.org'), '<a href="https://newsletters.fao.org/q/1/wv  ">Newsletter – December 2024</a>'.encode(), 'fao')
        self.assertEqual(rows[0]['url'], 'https://newsletters.fao.org/q/1/wv')
        self.assertIn('–', rows[0]['anchor_literal'])
        self.assertIsNone(rows[0]['index_year_literal'])

    def test_sampling_deduplicates_and_preserves_index_order(self):
        rows = [{'url': url, 'index_year_literal': year} for url, year in [('a','2024'),('a','2024'),('b','2024'),('c','2023')]]
        registry = build_registry(rows, 'doe', 1)
        self.assertEqual([s['url'] for s in registry['seed_documents']], ['a', 'c'])
        with self.assertRaises(ValueError):
            build_registry(rows, 'fao', 1)

    def test_newsletter_numbers_remain_candidates(self):
        html = b'<h3>Highest since July 2011</h3><h4>November 2021</h4><p>The FAO Food Price Index averaged 133.2 points in October.</p><a href="https://newsletters.fao.org/c/one">Read more</a>'
        row = extract(source('newsletters.fao.org'), html)
        self.assertEqual(row['issue_month_literals'], ['November 2021'])
        self.assertEqual(row['level_candidates'][0]['value_literal'], '133.2')
        self.assertIsNone(row['level_candidates'][0]['base_period'])
        self.assertIsNone(row['level_candidates'][0]['reference_period'])
        self.assertFalse(row['training_admitted'])

    def test_script_numbers_and_unapproved_links_excluded(self):
        row = extract(source('newsletters.fao.org'), b'<script>averaged 9 points</script><p>No value</p><a href="https://evil.test/c/one">Read more</a>')
        self.assertEqual(row['level_candidates'], [])
        self.assertEqual(row['read_more_links'], [])

    def test_multiple_levels_not_silently_selected(self):
        row = extract(source('newsletters.fao.org'), b'<h5>March 2024</h5><p>Food averaged 117.3 points; cereal averaged 113.8 points.</p>')
        self.assertEqual(len(row['level_candidates']), 2)


if __name__ == '__main__':
    unittest.main()
