import base64
import gzip
import hashlib
import json
import unittest

from external_context.prepare_fao_replays import canonical, replay_sources
from external_context.verify_fao_replays import verify
from external_context.extract_fao_releases import parse_release

URL = 'https://www.fao.org/newsroom/detail/example/en'
BODY = b'<span class="detail__date">02/02/2024</span><script type="application/ld+json">{"@type":"Article","datePublished":"02/02/2024"}</script><div class="news-detail__body"><p>FAO Food Price Index averaged 118 points in January.</p></div>'
DIGEST = base64.b32encode(hashlib.sha1(BODY).digest()).decode()


def fixtures():
    evidence = {'original_url': URL, 'release_source_id': 'release', 'artifact_sha256': 'c' * 64,
                'captured_at_utc': '2026-10-04T00:00:00+00:00'}
    table = [['timestamp', 'original', 'digest'], ['20240202120755', URL, DIGEST]]
    record = replay_sources(evidence, json.dumps(table).encode())[0]
    record.update(final_url=record['url'], artifact_sha256=hashlib.sha256(BODY).hexdigest(),
                  captured_at_utc='2026-10-04T00:00:00+00:00',
                  headers={'Memento-Datetime': 'Fri, 02 Feb 2024 12:07:55 GMT'})
    release = {**parse_release(BODY, URL), 'source_id': 'release', 'source_url': URL,
               'artifact_sha256': 'd' * 64}
    return evidence, table, record, release


class FAOReplayTests(unittest.TestCase):
    def test_canonical_only_official_release(self):
        self.assertEqual(canonical(URL + '/'), canonical(URL))
        for url in ['https://evil.test/newsroom/detail/a', URL + '?version=new', 'https://www.fao.org/other']:
            with self.assertRaises(ValueError):
                canonical(url)

    def test_empty_cdx_and_wrong_schema(self):
        evidence, _, _, _ = fixtures()
        self.assertEqual(replay_sources(evidence, b'[]'), [])
        with self.assertRaises(ValueError):
            replay_sources(evidence, b'[["timestamp"]]')

    def test_wrong_cdx_url_and_future_timestamp(self):
        evidence, table, _, _ = fixtures()
        for replacement in [['20240202120755', URL + 'other', DIGEST], ['20270202120755', URL, DIGEST]]:
            with self.assertRaises(ValueError):
                replay_sources(evidence, json.dumps([table[0], replacement]).encode())

    def test_verified_available_by_capture_not_article_date(self):
        _, _, record, release = fixtures()
        result = verify(record, BODY, release)
        self.assertEqual(result['available_at_utc'], '2024-02-02T12:07:55+00:00')
        self.assertTrue(result['historical_availability_verified'])
        self.assertFalse(result['training_admitted'])
        self.assertFalse(result['base_definition_verified'])

    def test_gzip_decoded_payload_checked(self):
        _, _, record, release = fixtures()
        raw = gzip.compress(BODY)
        record['headers']['content-encoding'] = 'gzip'
        record['artifact_sha256'] = hashlib.sha256(raw).hexdigest()
        self.assertTrue(verify(record, raw, release)['historical_availability_verified'])

    def test_wrong_digest_rejected(self):
        _, _, record, release = fixtures()
        record['archive_payload_sha1_base32'] = 'A' * 32
        with self.assertRaisesRegex(ValueError, 'CDX digest'):
            verify(record, BODY, release)

    def test_redirect_or_wrong_memento_rejected(self):
        for field, value in [('final_url', 'https://web.archive.org/other'),
                             ('headers', {'Memento-Datetime': 'Sat, 03 Feb 2024 12:07:55 GMT'})]:
            _, _, record, release = fixtures()
            record[field] = value
            with self.assertRaises(ValueError):
                verify(record, BODY, release)

    def test_changed_value_rejected(self):
        _, _, record, release = fixtures()
        release['value'] = '117.7'
        with self.assertRaisesRegex(ValueError, 'differs for value'):
            verify(record, BODY, release)


if __name__ == '__main__':
    unittest.main()
