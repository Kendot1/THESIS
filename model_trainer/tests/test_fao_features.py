from datetime import datetime
import unittest

from external_context.fao_features import FAOArchive


def row(period='2024-01', available='2024-02-02T12:07:55+00:00', value='118'):
    return {'metric':'FAO Food Price Index','unit':'index_points','base_period':'2014-2016=100',
            'historical_availability_verified':True,'base_definition_verified':True,
            'reference_period':period,'available_at_utc':available,'value':value,
            'declared_publication_date':available[:10],'source_id':period+'_'+value}


class FAOFeatureTests(unittest.TestCase):
    def test_no_use_before_exact_capture_time(self):
        archive=FAOArchive([row()])
        before=datetime.fromisoformat('2024-02-02T20:07:54+08:00')
        after=datetime.fromisoformat('2024-02-02T20:07:55+08:00')
        self.assertEqual(archive.at(before,lag_days=0,max_age_days=60)['missing'],1)
        self.assertEqual(archive.at(after,lag_days=0,max_age_days=60)['value'],118)

    def test_lag_delays_release_and_does_not_refresh_old_value(self):
        archive=FAOArchive([row()])
        origin=datetime.fromisoformat('2024-03-10T00:00:00+08:00')
        self.assertEqual(archive.at(origin,lag_days=0,max_age_days=30)['reason'],'stale_reference')
        self.assertEqual(archive.at(origin,lag_days=7,max_age_days=30)['reason'],'stale_reference')
        origin=datetime.fromisoformat('2024-02-03T00:00:00+08:00')
        self.assertEqual(archive.at(origin,lag_days=1,max_age_days=60)['missing'],1)

    def test_latest_reference_preferred_to_later_old_release(self):
        archive=FAOArchive([row(),row('2023-12','2024-02-10T12:00:00+00:00','118.5')])
        selected=archive.at(datetime.fromisoformat('2024-02-15T00:00:00+00:00'),lag_days=0,max_age_days=60)
        self.assertEqual(selected['reference_period'],'2024-01')

    def test_later_vintage_not_backfilled(self):
        archive=FAOArchive([row(),row(available='2024-02-10T12:00:00+00:00',value='117.7')])
        selected=archive.at(datetime.fromisoformat('2024-02-05T00:00:00+00:00'),lag_days=0,max_age_days=60)
        self.assertEqual(selected['value'],118)

    def test_definition_and_finite_positive_values_required(self):
        for field,value in [('base_definition_verified',False),('historical_availability_verified',False),
                            ('base_period','2002-2004=100'),('value','NaN'),('value','0'),('value',True)]:
            item=row();item[field]=value
            with self.assertRaises(ValueError):FAOArchive([item])

    def test_duplicate_and_inconsistent_dates_rejected(self):
        with self.assertRaises(ValueError):FAOArchive([row(),row()])
        with self.assertRaises(ValueError):FAOArchive([row(available='2024-01-31T12:00:00+00:00')])
        item=row();item['declared_publication_date']='2024-02-03'
        with self.assertRaises(ValueError):FAOArchive([item])

    def test_timezone_and_integral_lags_required(self):
        archive=FAOArchive([row()])
        with self.assertRaises(ValueError):archive.at(datetime(2024,2,3),lag_days=0,max_age_days=60)
        for lag,age in [(-1,60),(True,60),(1,-1),(0,1.5)]:
            with self.assertRaises(ValueError):archive.at(datetime.fromisoformat('2024-02-03T00:00:00+00:00'),lag_days=lag,max_age_days=age)


if __name__=='__main__':unittest.main()
