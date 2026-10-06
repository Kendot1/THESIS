import unittest

from external_context.extract_fao_releases import parse_release, corroborate

URL = 'https://www.fao.org/newsroom/detail/test/en'


def html(body, date='02/02/2024', structured=None):
    structured = date if structured is None else structured
    return (f'<span class="news - detail__date">{date}</span>'
            '<script type="application/ld+json">'
            '{"@type":"Article","datePublished":"' + structured + '"}</script>'
            '<div class="news-detail__body">' + body + '</div>').encode()


class FAOReleaseTests(unittest.TestCase):
    def test_historical_malformed_metadata_requires_explicit_mode(self):
        raw = html('<p>FAO Food Price Index averaged 118 points in January.</p>')
        raw = raw.replace(b'"datePublished":', b'"publisher":{"name":"FAO","datePublished":')
        with self.assertRaises(ValueError):
            parse_release(raw, URL)
        r = parse_release(raw, URL, allow_malformed_metadata=True)
        self.assertEqual(r['declared_publication_date'], '2024-02-02')
        self.assertIn('malformed', r['publication_date_extraction_basis'])

    def test_malformed_conflicting_or_duplicate_dates_rejected(self):
        for dates in ['"datePublished":"03/02/2024"',
                      '"datePublished":"02/02/2024","datePublished":"02/02/2024"']:
            raw = ('<span class="detail__date">02/02/2024</span>'
                   '<div class="news-detail__body"><p>FAO Food Price Index averaged 118 points in January.</p></div>'
                   '<script type="application/ld+json">{"@type":"Article","publisher":{' + dates + '}</script>').encode()
            with self.assertRaises(ValueError):
                parse_release(raw, URL, allow_malformed_metadata=True)

    def test_inline_links_and_comparison_year(self):
        r = parse_release(html('<p>The <a>FAO Food Price Index</a> averaged 118 points in January, below January 2023.</p>'), URL)
        self.assertEqual(r['value'], '118')
        self.assertEqual(r['reference_period'], '2024-01')
        self.assertEqual(r['declared_publication_date'], '2024-02-02')
        self.assertIsNone(r['base_period'])
        self.assertFalse(r['publication_time_known'])

    def test_br_paragraph_boundaries_and_multiple_metrics(self):
        r = parse_release(html('FAO Food Price Index averaged 118 points in January.<br/><br/>FAO Dairy Price Index averaged 130 points in January.'), URL)
        self.assertEqual(r['value'], '118')

    def test_p_paragraph_boundaries_and_multiple_metrics(self):
        r = parse_release(html('<p>FAO Food Price Index averaged 118 points in January.</p><p>FAO Dairy Price Index averaged 130 points in January.</p>'), URL)
        self.assertEqual(r['value'], '118')

    def test_reference_month_before_level(self):
        r = parse_release(html('<p>FAO Food Price Index declined in January, averaging 118 points during the month.</p>'), URL)
        self.assertEqual(r['reference_period'], '2024-01')

    def test_year_rollover(self):
        r = parse_release(html('<p>FAO Food Price Index averaged 118.5 points in December 2023.</p>', date='05/01/2024'), URL)
        self.assertEqual(r['reference_period'], '2023-12')

    def test_wrong_level_year_rejected(self):
        with self.assertRaisesRegex(ValueError, 'year conflicts'):
            parse_release(html('<p>FAO Food Price Index averaged 118 points in January 2023.</p>'), URL)

    def test_wrong_month_and_ambiguous_level_rejected(self):
        for body in ['<p>FAO Food Price Index averaged 118 points in December.</p>',
                     '<p>FAO Food Price Index averaged 118 points in January and averaged 117 points in December.</p>']:
            with self.assertRaises(ValueError):
                parse_release(html(body), URL)

    def test_dates_and_publisher_must_agree(self):
        with self.assertRaisesRegex(ValueError, 'dates disagree'):
            parse_release(html('x', structured='03/02/2024'), URL)
        with self.assertRaisesRegex(ValueError, 'official FAO'):
            parse_release(html('x'), 'https://fake.test/newsroom/detail/test/en')

    def test_wrong_newsletter_link_rejected(self):
        r = parse_release(html('<p>FAO Food Price Index averaged 118 points in January.</p>'), URL)
        newsletter = {'issue_month_literals': ['March 2024'], 'level_candidates': [
            {'value_literal': '118', 'context_literal': 'FAO Food Price Index averaged 118 points in January'}]}
        with self.assertRaisesRegex(ValueError, 'issue month'):
            corroborate(r, newsletter)
        newsletter['issue_month_literals'] = ['February 2024']
        corroborate(r, newsletter)
        newsletter['level_candidates'][0]['value_literal'] = '117.7'
        with self.assertRaisesRegex(ValueError, 'corroborate'):
            corroborate(r, newsletter)


if __name__ == '__main__':
    unittest.main()
