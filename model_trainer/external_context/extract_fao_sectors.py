"""Index sector-price paragraphs in independently verified FAO release bytes.

This queue preserves monthly/yearly comparisons for explicit semantic review.
No number is inferred from the aggregate FFPI or admitted to training here.
"""
import argparse
import gzip
import json
from pathlib import Path
import re

from bs4 import BeautifulSoup

if __package__:
    from .build_context import encode, load_capture, sha256
    from .extract_fao_releases import parse_release
    from .ocr_customs import write_once
else:
    from build_context import encode, load_capture, sha256
    from extract_fao_releases import parse_release
    from ocr_customs import write_once

SECTORS=['Cereal','Vegetable Oil','Sugar','Meat','Dairy','All Rice']


def sector_paragraphs(raw):
    soup=BeautifulSoup(raw.decode('utf-8'),'html.parser')
    bodies=soup.select('div.news-detail__body')
    if len(bodies)!=1:raise ValueError('Expected one release body')
    body=bodies[0]
    for tag in body.select('br'):tag.replace_with('\u001e')
    for tag in body.select('p'):tag.insert_before('\u001e');tag.insert_after('\u001e')
    paragraphs=[' '.join(p.split()) for p in body.get_text(' ',strip=False).split('\u001e') if p.strip()]
    result=[]
    for sector in SECTORS:
        label=r'All[- ]Rice' if sector=='All Rice' else re.escape(sector)+r's?'
        pattern=re.compile(r'\b(?:FAO\s+)?'+label+r' Price Index\b',re.I)
        matches=[text for text in paragraphs if pattern.search(text)]
        result.append({'sector':sector,'paragraphs':matches,'paragraph_count':len(matches),'numeric_reviewed':False})
    return result


def build(capture_paths,verified_paths):
    replay_by_sha={};inputs=[]
    for path in capture_paths:
        _,capture_sha,artifacts=load_capture(path)
        inputs.append({'kind':'replay_capture','path':str(path),'sha256':capture_sha})
        for record,raw in artifacts.values():
            digest=record['artifact_sha256']
            if digest in replay_by_sha and replay_by_sha[digest][1]!=raw:raise ValueError('Conflicting replay payload')
            replay_by_sha[digest]=(record,raw)
    records=[];seen=set()
    for path in verified_paths:
        raw=path.read_bytes();inputs.append({'kind':'verified_replays','path':str(path),'sha256':sha256(raw)})
        data=json.loads(raw)
        for verified in data['records']:
            if verified.get('historical_availability_verified') is not True:raise ValueError('Historical verification required')
            if verified['source_id'] in seen:raise ValueError('Duplicate verified source')
            seen.add(verified['source_id'])
            source,payload=replay_by_sha[verified['archive_artifact_sha256']]
            if source['final_url']!=verified['archive_replay_url']:raise ValueError('Replay URL mismatch')
            encodings={v.lower().strip() for k,v in source['headers'].items() if k.lower()=='content-encoding'}
            if encodings-{'identity','','gzip'} or len(encodings)>1:raise ValueError('Unsupported encoding')
            body=gzip.decompress(payload) if 'gzip' in encodings else payload
            if sha256(body)!=verified['decoded_archive_sha256']:raise ValueError('Decoded payload hash mismatch')
            release=parse_release(body,verified['source_url'],allow_malformed_metadata=True)
            for field in ['reference_period','declared_publication_date','value']:
                if release[field]!=verified[field]:raise ValueError('Verified release field differs: '+field)
            records.append({'source_id':verified['source_id'],'source_url':verified['source_url'],
                            'archive_replay_url':verified['archive_replay_url'],
                            'archive_artifact_sha256':verified['archive_artifact_sha256'],
                            'decoded_archive_sha256':verified['decoded_archive_sha256'],
                            'available_at_utc':verified['available_at_utc'],
                            'historical_availability_verified':True,
                            'reference_period':verified['reference_period'],
                            'declared_publication_date':verified['declared_publication_date'],
                            'sectors':sector_paragraphs(body),'training_admitted':False})
    records.sort(key=lambda r:r['reference_period'])
    return {'schema_version':1,'builder_sha256':sha256(Path(__file__).read_bytes()),'inputs':inputs,
            'records':records,'summary':{'verified_releases':len(records),
            'sector_slots':sum(len(r['sectors']) for r in records),
            'single_paragraph_slots':sum(s['paragraph_count']==1 for r in records for s in r['sectors']),
            'training_admitted':0}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',type=Path,action='append',required=True)
    parser.add_argument('--verified',type=Path,action='append',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=build(args.capture,args.verified)
    write_once(args.output,encode(result));print(json.dumps(result['summary'],indent=2))


if __name__=='__main__':main()
