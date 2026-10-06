import unittest
from datetime import datetime
from external_context.audit_doe_candidate_coverage import at


def fixture():
    return [{'source_id':'s','available_at_utc':'2025-04-16T00:35:10+00:00',
             'rows':[{'status':'candidate','reference_start':'2025-02-25','reference_end':'2025-03-03',
                      'city_literal':'BANGUED','range_low':60.04}]}]


class DOECandidateCoverageTests(unittest.TestCase):
    def test_late_capture_never_backfilled(self):
        row=at(fixture(),datetime.fromisoformat('2025-03-24T00:00:00+08:00'),0,60)
        self.assertEqual(row['potential_numeric_rows'],0)

    def test_age_uses_reference_not_capture(self):
        origin=datetime.fromisoformat('2025-04-23T00:00:00+08:00')
        self.assertEqual(at(fixture(),origin,0,30)['potential_numeric_rows'],0)
        self.assertEqual(at(fixture(),origin,0,60)['potential_numeric_rows'],1)

    def test_lag_obeys_exact_timestamp(self):
        origin=datetime.fromisoformat('2025-04-23T00:00:00+08:00')
        self.assertEqual(at(fixture(),origin,7,90)['potential_numeric_rows'],0)
        self.assertEqual(at(fixture(),origin,3,90)['potential_numeric_rows'],1)

    def test_missing_and_invalid_timing_excluded(self):
        data=fixture();data[0]['rows'][0]['range_low']=None
        origin=datetime.fromisoformat('2025-04-23T00:00:00+08:00')
        self.assertEqual(at(data,origin,0,60)['potential_numeric_rows'],0)
        data=fixture();data[0]['available_at_utc']='2025-02-01T00:00:00+00:00'
        row=at(data,origin,0,90)
        self.assertEqual(row['potential_numeric_rows'],0)
        self.assertEqual(row['invalid_timing_candidates'],1)

    def test_requires_aware_clock_and_nonnegative_parameters(self):
        with self.assertRaises(ValueError):at(fixture(),datetime(2025,4,23),0,60)
        origin=datetime.fromisoformat('2025-04-23T00:00:00+08:00')
        with self.assertRaises(ValueError):at(fixture(),origin,-1,60)
        with self.assertRaises(ValueError):at(fixture(),origin,0,-1)
        data=fixture();data[0]['available_at_utc']='2025-04-16T00:35:10'
        with self.assertRaises(ValueError):at(data,origin,0,60)


if __name__=='__main__':unittest.main()
