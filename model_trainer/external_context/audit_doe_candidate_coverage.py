"""Audit potential DOE timing coverage; unreviewed candidates are not features.

No target prices are loaded. Counts are an upper bound pending numerical, unit
and geographic review. No prices, averages, city mappings or weights are made.
"""
import argparse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path

if __package__:
    from .build_context import encode, sha256
    from .ocr_customs import write_once
else:
    from build_context import encode, sha256
    from ocr_customs import write_once

MANILA=timezone(timedelta(hours=8))
SPLITS={'early_tuning':['2024-08-26','2024-09-25','2024-10-25'],
        'calibration':['2024-11-24','2024-12-24','2025-01-23'],
        'development':['2025-02-22','2025-03-24','2025-04-23','2025-05-23','2025-06-22','2025-07-22']}


def at(records, origin, lag_days, max_age_days):
    if origin.tzinfo is None or origin.utcoffset() is None:raise ValueError('Origin requires timezone')
    if lag_days<0 or max_age_days<0:raise ValueError('Lag and age must be nonnegative')
    cutoff=origin-timedelta(days=lag_days)
    eligible=[];invalid=0
    for document in records:
        available=datetime.fromisoformat(document['available_at_utc'])
        if available.tzinfo is None or available.utcoffset() is None:raise ValueError('Availability requires timezone')
        for row in document['rows']:
            if row.get('status')!='candidate' or row.get('range_low') is None:continue
            start=date.fromisoformat(row['reference_start']);end=date.fromisoformat(row['reference_end'])
            if start>end or available.astimezone(MANILA).date()<end:
                invalid+=1;continue
            age=(origin.astimezone(MANILA).date()-end).days
            if available<=cutoff and end<=cutoff.astimezone(MANILA).date() and 0<=age<=max_age_days:
                eligible.append((document,row))
    return {'origin':origin.isoformat(),'cutoff':cutoff.isoformat(),'lag_days':lag_days,
            'max_age_days':max_age_days,'potential_numeric_rows':len(eligible),
            'source_ids':sorted({d['source_id'] for d,r in eligible}),
            'city_labels':sorted({r['city_literal'] for d,r in eligible}),
            'reference_periods':sorted({(r['reference_start'],r['reference_end']) for d,r in eligible}),
            'invalid_timing_candidates':invalid,'training_admitted':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidates',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();raw=args.candidates.read_bytes();data=json.loads(raw)
    lookups=[]
    for split,days in SPLITS.items():
        for day in days:
            origin=datetime.fromisoformat(day).replace(tzinfo=MANILA)
            for lag in [0,1,3,7,14,30]:
                for age in [14,30,60,90]:
                    lookups.append({'split':split,**at(data['records'],origin,lag,age)})
    summary=[]
    for split in SPLITS:
        for lag in [0,1,3,7,14,30]:
            for age in [14,30,60,90]:
                cells=[r for r in lookups if r['split']==split and r['lag_days']==lag and r['max_age_days']==age]
                summary.append({'split':split,'lag_days':lag,'max_age_days':age,'origins':len(cells),
                                'origins_with_candidates':sum(r['potential_numeric_rows']>0 for r in cells)})
    result={'schema_version':1,'candidates_sha256':sha256(raw),'builder_sha256':sha256(Path(__file__).read_bytes()),
            'status':'diagnostic_upper_bound_not_feature_eligibility','training_admitted':False,
            'missingness_policy':'Only actual records known by origin minus lag; age measured from reference end at actual origin. Missing dates/places are not filled.',
            'limitations':'Candidates remain numerically/unit/geographically unverified. No city aliases, province corrections, regional averages or shipment weights are inferred. Availability is a conservative historical archive bound.',
            'lookups':lookups,'summary':summary}
    write_once(args.output,encode(result))
    print(json.dumps({'lookups':len(lookups),'zero_lag_summary':[s for s in summary if s['lag_days']==0]},indent=2))


if __name__=='__main__':main()
