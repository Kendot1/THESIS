import copy
import unittest

from external_context.build_doe_reviewed import reviewed_rows


def fixtures():
    row={'status':'candidate','pdf_page':1,'city_literal':'Batac City','reference_start':'2023-12-05',
         'reference_end':'2023-12-07','range_low':58.7,'range_high':61.25}
    data={'records':[{'source_id':'s','source_url':'https://prod-cms.doe.gov.ph/documents/d/lfo/s',
                     'artifact_sha256':'a'*64,'available_at_utc':'2023-12-08T13:16:42+00:00','rows':[row]}]}
    spec={'source_id':'s','artifact_sha256':'a'*64,'pdf_page':1,'reference_start':'2023-12-05',
          'reference_end':'2023-12-07','unit':None,'unit_verified':False,'reviewed_on':'2026-10-04',
          'rows':[{'city_literal':'Batac City','range_low':'58.70','range_high':'61.25'}]}
    return data,spec


class DOEReviewedTests(unittest.TestCase):
    def test_numeric_review_does_not_certify_unit_or_training(self):
        data,spec=fixtures();r=reviewed_rows(data,spec)[0]
        self.assertTrue(r['numeric_visual_reviewed']);self.assertTrue(r['historical_availability_verified'])
        self.assertFalse(r['unit_verified']);self.assertFalse(r['training_admitted']);self.assertIsNone(r['unit'])

    def test_changed_original_rejected(self):
        data,spec=fixtures();spec['artifact_sha256']='b'*64
        with self.assertRaises(ValueError):reviewed_rows(data,spec)

    def test_wrong_value_or_monitoring_period_rejected(self):
        for key,value in [('range_low',58.8),('reference_end','2023-12-08')]:
            data,spec=fixtures();data['records'][0]['rows'][0][key]=value
            with self.assertRaises(ValueError):reviewed_rows(data,spec)

    def test_duplicate_city_rejected(self):
        data,spec=fixtures();spec['rows'].append(copy.deepcopy(spec['rows'][0]))
        with self.assertRaises(ValueError):reviewed_rows(data,spec)

    def test_missing_candidate_rejected(self):
        data,spec=fixtures();data['records'][0]['rows'][0]['status']='rejected'
        with self.assertRaises(ValueError):reviewed_rows(data,spec)

    def test_invalid_availability_rejected(self):
        for value in ['2023-12-06T00:00:00+00:00','2023-12-08T13:16:42']:
            data,spec=fixtures();data['records'][0]['available_at_utc']=value
            with self.assertRaises(ValueError):reviewed_rows(data,spec)


if __name__=='__main__':unittest.main()
