"""Build reviewed FAO monthly sector changes from pinned historical paragraphs."""
import argparse
from collections import Counter
from decimal import Decimal
import json
from pathlib import Path
import re

if __package__:
    from .build_context import encode, sha256
    from .ocr_customs import write_once
else:
    from build_context import encode, sha256
    from ocr_customs import write_once


def reviewed_change(paragraph,sector,expected):
    label=r'All[- ]Rice' if sector=='All Rice' else re.escape(sector)+r's?'
    names=list(re.finditer(r'\b(?:FAO\s+)?'+label+r' Price Index\b',paragraph,re.I))
    if len(names)!=1:raise ValueError('Expected one named sector index')
    sentence=re.split(r'(?<=[.!?])\s+(?=[A-Z])',paragraph[names[0].end():])[0]
    matches=list(re.finditer(r'(?P<value>\d+(?:\.\d+)?)\s+percent\b',sentence,re.I))
    if not matches:raise ValueError('No explicit percentage in sector opening sentence')
    match=matches[0];before=sentence[:match.start()];after=sentence[match.end():]
    if re.search(r'\b(?:declined|decreased|dropped|rose|increased)\b[^.]*?\b\d+(?:\.\d+)?\s+points\b',before,re.I):
        raise ValueError('Index change is in points, not percent')
    if re.search(r'\b(?:world|international)\s+(?:wheat|maize|rice|palm|poultry)\b',before,re.I):
        raise ValueError('Percentage belongs to component commodity')
    if re.match(r'\s+(?:above|below).*?(?:year|20\d\d)',after,re.I):
        raise ValueError('Percentage is an annual comparison')
    if re.match(r'\s+(?:from|over|compared to)\s+(?:its\s+)?(?:a |one |the previous )?year',after,re.I):
        raise ValueError('Percentage is an annual comparison')
    up=r'rose|rising|increased|increasing|up|spiked'
    down=r'declined|declining|decreased|decreasing|dropped|dropping|down|fell|falling|dipped|slipped'
    directions=list(re.finditer(r'\b('+up+'|'+down+r')\b',before,re.I))
    if directions:
        sign=1 if re.fullmatch(up,directions[-1][0],re.I) else -1
    elif re.match(r'\s+higher\b',after,re.I):sign=1
    elif re.match(r'\s+lower\b',after,re.I):sign=-1
    else:raise ValueError('No unambiguous price-change direction')
    value=Decimal(match['value'])*sign
    if value!=Decimal(str(expected)):raise ValueError('Reviewed value differs from source percentage/direction')
    return {'value':str(value),'value_literal':match['value'],'evidence_sentence_literal':sentence,
            'paragraph_sha256':sha256(paragraph.encode('utf-8'))}


def build(candidates,spec):
    by_period={r['reference_period']:r for r in candidates['records']}
    if len(by_period)!=len(candidates['records']) or set(by_period)!=set(spec['values']):raise ValueError('Review period scope differs')
    rows=[]
    for period,values in sorted(spec['values'].items()):
        if len(values)!=len(spec['sector_order']):raise ValueError('Review sector count differs')
        source=by_period[period]
        if source.get('historical_availability_verified') is not True:raise ValueError('Historical availability required')
        sectors={s['sector']:s for s in source['sectors']}
        for sector,value in zip(spec['sector_order'],values):
            item=sectors[sector];evidence={}
            if value is not None:
                if item['paragraph_count']!=1:raise ValueError('Ambiguous sector paragraph')
                evidence=reviewed_change(item['paragraphs'][0],sector,value)
            rows.append({k:v for k,v in source.items() if k not in {'sectors'}}|{
                'sector':sector,'metric':spec['metric'],'unit':spec['unit'],
                'value':None if value is None else evidence['value'],**evidence,
                'missing_reason':'no_reviewed_explicit_monthly_percentage' if value is None else None,
                'numeric_reviewed':True,'reviewed_on':spec['reviewed_on'],'training_admitted':False})
    return rows


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidates',type=Path,required=True)
    parser.add_argument('--review',type=Path,default=Path(__file__).with_name('fao_sector_review.json'))
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();raw=args.candidates.read_bytes();review=args.review.read_bytes();spec=json.loads(review)
    if sha256(raw)!=spec['candidates_sha256']:raise ValueError('Reviewed candidate queue hash mismatch')
    rows=build(json.loads(raw),spec)
    result={'schema_version':1,'candidates_sha256':sha256(raw),'review_sha256':sha256(review),
            'builder_sha256':sha256(Path(__file__).read_bytes()),'records':rows,
            'category_mapping':spec['category_mapping'],'mapping_scope':spec['mapping_scope'],
            'vintage_policy':spec['vintage_policy'],
            'summary':{'records':len(rows),'numeric':sum(r['value'] is not None for r in rows),
                       'missing':sum(r['value'] is None for r in rows),'training_admitted':0}}
    write_once(args.output,encode(result));print(json.dumps(result['summary'],indent=2))


if __name__=='__main__':main()
