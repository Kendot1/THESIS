"""Apply explicit visual review to DOE range candidates without inferring units."""
import argparse
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path

if __package__:
    from .build_context import encode, sha256
    from .ocr_customs import write_once
else:
    from build_context import encode, sha256
    from ocr_customs import write_once


def reviewed_rows(candidates, spec):
    documents=[r for r in candidates['records'] if r['source_id']==spec['source_id']]
    if len(documents)!=1 or documents[0]['artifact_sha256']!=spec['artifact_sha256']:
        raise ValueError('Reviewed original PDF mismatch')
    document=documents[0]
    available=datetime.fromisoformat(document['available_at_utc'])
    if available.tzinfo is None or available.utcoffset() is None:
        raise ValueError('Historical availability needs timezone')
    if available.astimezone(timezone(timedelta(hours=8))).date()<date.fromisoformat(spec['reference_end']):
        raise ValueError('Availability predates monitoring completion')
    rows=[];seen=set()
    for reviewed in spec['rows']:
        key=reviewed['city_literal']
        if key in seen:raise ValueError('Duplicate reviewed city')
        seen.add(key)
        matches=[r for r in document['rows'] if r.get('status')=='candidate' and
                 r['pdf_page']==spec['pdf_page'] and r['city_literal']==key]
        if len(matches)!=1:raise ValueError('Missing/ambiguous reviewed city candidate')
        row=matches[0]
        if (row['reference_start'],row['reference_end'])!=(spec['reference_start'],spec['reference_end']):
            raise ValueError('Reviewed monitoring dates differ')
        for bound in ['range_low','range_high']:
            if row[bound] is None or Decimal(str(row[bound]))!=Decimal(reviewed[bound]):
                raise ValueError('Reviewed numeric range differs')
        rows.append({**row,'source_id':spec['source_id'],'source_url':document['source_url'],
                     'artifact_sha256':spec['artifact_sha256'],'available_at_utc':document['available_at_utc'],
                     'numeric_visual_reviewed':True,'reviewed_on':spec['reviewed_on'],
                     'unit':spec['unit'],'unit_verified':spec['unit_verified'],
                     'historical_availability_verified':True,'training_admitted':False})
    return rows


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidates',type=Path,required=True)
    parser.add_argument('--review',type=Path,default=Path(__file__).with_name('doe_diesel_review.json'))
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();candidate_bytes=args.candidates.read_bytes();review_bytes=args.review.read_bytes()
    rows=reviewed_rows(json.loads(candidate_bytes),json.loads(review_bytes))
    result={'schema_version':1,'candidates_sha256':sha256(candidate_bytes),'review_spec_sha256':sha256(review_bytes),
            'builder_sha256':sha256(Path(__file__).read_bytes()),'records':rows,
            'summary':{'visually_reviewed_ranges':len(rows),'unit_verified':sum(r['unit_verified'] for r in rows),'training_admitted':0}}
    write_once(args.output,encode(result));print(json.dumps(result['summary'],indent=2))


if __name__=='__main__':main()
