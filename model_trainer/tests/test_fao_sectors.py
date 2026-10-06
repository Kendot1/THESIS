from datetime import datetime
import unittest
from external_context.build_fao_sector_context import reviewed_change
from external_context.extract_fao_sectors import sector_paragraphs
from external_context.fao_sector_features import FAOSectorArchive


def fixture(period='2024-07',value='-2.4',available='2024-08-02T10:00:00+00:00'):
    return {'historical_availability_verified':True,'numeric_reviewed':True,
            'metric':'reported_month_on_month_percent_change','unit':'percent',
            'sector':'All Rice','reference_period':period,'value':value,
            'available_at_utc':available,'declared_publication_date':available[:10],
            'source_id':period,'missing_reason':'not_reported' if value is None else None}


class FAOSectorTests(unittest.TestCase):
    def test_percent_differs_from_points_and_component_price(self):
        text='The FAO Cereal Price Index declined by 0.7 points in April, nudged down by a 3.0 percent decline in world maize prices.'
        with self.assertRaises(ValueError):reviewed_change(text,'Cereal',-0.7)
        with self.assertRaises(ValueError):reviewed_change(text,'Cereal',-3.0)

    def test_direction_and_reviewed_value_must_match(self):
        text='FAO All-Rice Price Index declined by 2.4 percent from June.'
        self.assertEqual(reviewed_change(text,'All Rice',-2.4)['value'],'-2.4')
        for expected in [2.4,-3.4]:
            with self.assertRaises(ValueError):reviewed_change(text,'All Rice',expected)

    def test_monthly_value_selected_before_annual_comparison(self):
        text='FAO Sugar Price Index declined by 2.2 percent but remained 46.6 percent above its year-earlier level.'
        self.assertEqual(reviewed_change(text,'Sugar',-2.2)['value'],'-2.2')
        with self.assertRaises(ValueError):reviewed_change(text,'Sugar',46.6)

    def test_approximate_unchanged_is_not_zero(self):
        for qualifier in ['virtually','almost']:
            with self.assertRaises(ValueError):reviewed_change('FAO Cereal Price Index remained '+qualifier+' unchanged from January.','Cereal',0)

    def test_specific_index_not_earlier_cereal_number(self):
        text='FAO Cereal Price Index rose 3.0 percent. The FAO All Rice Price Index declined by 0.7 percent.'
        self.assertEqual(reviewed_change(text,'All Rice',-0.7)['value'],'-0.7')

    def test_sector_queue_preserves_absent_rice_index(self):
        rows=sector_paragraphs(b'<div class="news-detail__body"><p>FAO Cereal Price Index rose 3.0 percent.</p></div>')
        self.assertEqual(next(r for r in rows if r['sector']=='All Rice')['paragraph_count'],0)

    def test_latest_explicit_missing_blocks_older_number(self):
        archive=FAOSectorArchive([fixture(),fixture('2024-08',None,'2024-09-06T10:00:00+00:00')])
        got=archive.at('All Rice',datetime.fromisoformat('2024-09-10T00:00:00+08:00'),lag_days=0,max_age_days=90)
        self.assertIsNone(got['value']);self.assertEqual(got['reason'],'not_reported')

    def test_no_future_release_and_lag_cutoff(self):
        archive=FAOSectorArchive([fixture()]);origin=datetime.fromisoformat('2024-08-03T00:00:00+08:00')
        self.assertEqual(archive.at('All Rice',origin,lag_days=0,max_age_days=60)['value'],-2.4)
        self.assertIsNone(archive.at('All Rice',origin,lag_days=1,max_age_days=60)['value'])

    def test_reference_age_not_capture_age(self):
        archive=FAOSectorArchive([fixture(available='2024-09-05T10:00:00+00:00')])
        got=archive.at('All Rice',datetime.fromisoformat('2024-09-06T00:00:00+08:00'),lag_days=0,max_age_days=30)
        self.assertEqual(got['reason'],'stale_reference')

    def test_validity_and_duplicate_guards(self):
        for edit in [{'value':float('nan')},{'value':True},{'value':-100},{'numeric_reviewed':False},
                     {'unit':'index_points'},{'available_at_utc':'2024-08-02T10:00:00'},
                     {'declared_publication_date':'2024-07-31'}]:
            with self.assertRaises(ValueError):FAOSectorArchive([{**fixture(),**edit}])
        with self.assertRaises(ValueError):FAOSectorArchive([fixture(),fixture()])


if __name__=='__main__':unittest.main()
