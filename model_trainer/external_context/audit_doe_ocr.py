"""Validate DOE OCR provenance and make a date/text review index, not features."""
import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import re

if __package__:
    from .build_context import encode, load_capture, sha256
    from .ocr_customs import checked_completed, write_once
    from .extract_doe_diesel import parse_period
else:
    from build_context import encode, load_capture, sha256
    from ocr_customs import checked_completed, write_once
    from extract_doe_diesel import parse_period


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',type=Path,required=True)
    parser.add_argument('--availability',type=Path,required=True)
    parser.add_argument('--ocr-run',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    _,capture_sha,artifacts=load_capture(args.capture)
    avail_raw=args.availability.read_bytes();availability=json.loads(avail_raw)
    run_raw=args.ocr_run.read_bytes();run=json.loads(run_raw);root=args.ocr_run.parent.resolve()
    config_raw=(root/'ocr_config.json').read_bytes()
    if run['capture_manifest_sha256']!=capture_sha or availability['source_capture_sha256']!=capture_sha:
        raise ValueError('Capture provenance mismatch')
    if sha256(config_raw)!=run['ocr_config_sha256']:raise ValueError('OCR config hash mismatch')
    known={r['source_id']:r for r in availability['records'] if r['historical_availability_verified']}
    rows=[];seen=set()
    for entry in run['records']:
        if entry['status'] not in {'created','reused'}:raise ValueError('Incomplete OCR run')
        key=(entry['source_id'],entry['page'])
        if key in seen:raise ValueError('Duplicate OCR page')
        seen.add(key)
        source,raw=artifacts[entry['source_id']]
        if source['id'] not in known:raise ValueError('OCR source lacks historical availability')
        path=(root/entry['manifest']).resolve()
        if not path.is_relative_to(root):raise ValueError('OCR manifest path escapes output')
        page=checked_completed(path,source['artifact_sha256'],sha256(config_raw),entry['page'])
        text=(path.parent/'ocr.txt').read_text(encoding='utf-8')
        dates=[]
        for line in text.splitlines():
            if not re.search(r'Date of Monitoring|For the week',line,re.I):continue
            candidate={'literal':line,'verified':False}
            try:
                start,end=parse_period(line);candidate.update(reference_start=start,reference_end=end)
            except ValueError as exc:candidate['reason']=str(exc)
            dates.append(candidate)
        rows.append({'source_id':source['id'],'artifact_sha256':source['artifact_sha256'],
                     'index_year_literal':source['index_year_literal'],'pdf_page':entry['page'],
                     'available_at_utc':known[source['id']]['available_at_utc'],
                     'ocr_page_manifest':entry['manifest'],'ocr_page_manifest_sha256':sha256(path.read_bytes()),
                     'word_count':page['word_count'],'low_confidence_word_count':page['low_confidence_word_count'],
                     'date_candidates':dates,
                     'diesel_lines_literal':[line for line in text.splitlines() if 'DIESEL' in line.upper()],
                     'numeric_accuracy_verified':False,'training_admitted':False})
    result={'schema_version':1,'capture_manifest_sha256':capture_sha,'availability_sha256':sha256(avail_raw),
            'ocr_run_sha256':sha256(run_raw),'ocr_config_sha256':sha256(config_raw),
            'builder_sha256':sha256(Path(__file__).read_bytes()),'records':rows,
            'summary':{'documents':len({r['source_id'] for r in rows}),'pages':len(rows),
                       'pages_with_parseable_date_candidates':sum(any('reference_start' in d for d in r['date_candidates']) for r in rows),
                       'pages_with_diesel_lines':sum(bool(r['diesel_lines_literal']) for r in rows),
                       'low_confidence_words':sum(r['low_confidence_word_count'] for r in rows),
                       'numeric_values_certified':0,'training_admitted':0},
            'limitation':'OCR decimal loss, merged columns and digit substitutions require visual review. Confidence scores are not numeric-accuracy certification; dates here are candidates only.'}
    write_once(args.output,encode(result));print(json.dumps(result['summary'],indent=2))


if __name__=='__main__':main()
