import base64
import hashlib
import json
import unittest

from external_context.verify_doe_availability import original_url_allowed, parse_cdx, match

RAW=b'%PDF-1.4 test fuel table'
OLD='https://legacy.doe.gov.ph/sites/default/files/pdf/price_watch/petro_nluz_2023.pdf'
DIGEST=base64.b32encode(hashlib.sha1(RAW).digest()).decode()


def fixtures():
    source={'id':'source','url':'https://prod-cms.doe.gov.ph/documents/d/lfo/renamed-cms-file',
            'artifact_sha256':hashlib.sha256(RAW).hexdigest(),'captured_at_utc':'2026-10-04T00:00:00+00:00'}
    cdx={'id':'cdx','artifact_sha256':'c'*64,'captured_at_utc':'2026-10-04T00:00:00+00:00'}
    raw=json.dumps([['timestamp','original','digest'],['20231209000000',OLD,DIGEST]]).encode()
    return source,parse_cdx(cdx,raw)


class DOEAvailabilityTests(unittest.TestCase):
    def test_migrated_filename_requires_identical_payload(self):
        source,evidence=fixtures();r=match(source,RAW,evidence)
        self.assertTrue(r['historical_availability_verified'])
        self.assertEqual(r['available_at_utc'],'2023-12-09T00:00:00+00:00')
        self.assertFalse(r['training_admitted'])
        evidence[0]['payload_sha1_base32']='A'*32
        self.assertFalse(match(source,RAW,evidence)['historical_availability_verified'])

    def test_official_host_and_path_required(self):
        for url in [OLD.replace('legacy.doe.gov.ph','evil.test'),OLD+'?download=1',OLD.replace('price_watch','other')]:
            self.assertFalse(original_url_allowed(url))
        source,evidence=fixtures();evidence[0]['original_url']=OLD.replace('legacy.doe.gov.ph','evil.test')
        with self.assertRaises(ValueError):match(source,RAW,evidence)

    def test_pdf_magic_and_hash_required(self):
        source,evidence=fixtures()
        with self.assertRaises(ValueError):match(source,b'<html>404</html>',evidence)
        source['artifact_sha256']='d'*64
        with self.assertRaises(ValueError):match(source,RAW,evidence)

    def test_earliest_observed_capture_selected(self):
        source,evidence=fixtures();later=dict(evidence[0],available_at_utc='2024-01-01T00:00:00+00:00')
        self.assertEqual(match(source,RAW,[later]+evidence)['available_at_utc'],evidence[0]['available_at_utc'])

    def test_future_evidence_and_bad_schema_rejected(self):
        record={'id':'cdx','artifact_sha256':'c'*64,'captured_at_utc':'2022-01-01T00:00:00+00:00'}
        raw=json.dumps([['timestamp','original','digest'],['20231209000000',OLD,DIGEST]]).encode()
        with self.assertRaises(ValueError):parse_cdx(record,raw)
        with self.assertRaises(ValueError):parse_cdx(record,b'[["wrong"]]')
        self.assertEqual(parse_cdx(record,b'[]'),[])


if __name__=='__main__':unittest.main()
