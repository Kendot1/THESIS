"""Match migrated DOE fuel PDFs to historical official payload captures.

CMS document names need not resemble legacy filenames. Only identical PDF
payloads on explicitly allowed DOE publisher hosts establish an available-by
bound. An index year, filename or PDF creation date never establishes timing.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlparse

if __package__:
    from .build_context import aware_time, encode, load_capture, sha256
    from .ocr_customs import write_once
else:
    from build_context import aware_time, encode, load_capture, sha256
    from ocr_customs import write_once


def original_url_allowed(url):
    p=urlparse(url)
    return (p.scheme in {'http','https'} and p.hostname in {'doe.gov.ph','www.doe.gov.ph','legacy.doe.gov.ph'}
            and p.path.startswith('/sites/default/files/pdf/price_watch/')
            and unquote(p.path).lower().endswith('.pdf') and 'nluz' in unquote(p.path).lower()
            and not p.query and not p.fragment)


def parse_cdx(record, raw):
    table=json.loads(raw)
    if table==[]:return []
    if not isinstance(table,list) or table[0]!=['timestamp','original','digest']:
        raise ValueError('Unexpected DOE CDX schema')
    result=[]
    for row in table[1:]:
        if len(row)!=3:raise ValueError('Malformed CDX row')
        stamp,url,digest=row
        if not re.fullmatch(r'\d{14}',stamp) or not re.fullmatch(r'[A-Z2-7]{32}',digest) or not original_url_allowed(url):
            raise ValueError('Invalid DOE archive evidence')
        available=datetime.strptime(stamp,'%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
        if available>aware_time(record['captured_at_utc']):raise ValueError('Archive evidence lies after retrieval')
        result.append({'archive_timestamp':stamp,'available_at_utc':available.isoformat(),
                       'original_url':url,'payload_sha1_base32':digest,'cdx_source_id':record['id'],
                       'cdx_artifact_sha256':record['artifact_sha256']})
    return result


def match(source, raw, evidence):
    p=urlparse(source['url'])
    if p.scheme!='https' or p.hostname!='prod-cms.doe.gov.ph' or not p.path.startswith('/documents/'):
        raise ValueError('Expected indexed DOE CMS document')
    if not raw.startswith(b'%PDF-') or sha256(raw)!=source['artifact_sha256']:
        raise ValueError('Expected hash-checked original PDF')
    digest=base64.b32encode(hashlib.sha1(raw).digest()).decode('ascii')
    candidates=[]
    for item in evidence:
        if not original_url_allowed(item['original_url']):raise ValueError('Unapproved original publisher')
        if item['payload_sha1_base32']==digest:
            if aware_time(item['available_at_utc'])>aware_time(source['captured_at_utc']):
                raise ValueError('Historical capture after local retrieval')
            candidates.append(item)
    selected=min(candidates,key=lambda e:e['available_at_utc'],default=None)
    return {'source_id':source['id'],'source_url':source['url'],'artifact_sha256':source['artifact_sha256'],
            'payload_sha1_base32':digest,'index_year_literal':source.get('index_year_literal'),
            'historical_availability_verified':selected is not None,
            'available_at_utc':selected['available_at_utc'] if selected else None,
            'basis':'identical_PDF_payload_on_allowed_official_DOE_legacy_publisher' if selected else None,
            'archive_evidence':selected,'matching_capture_count':len(candidates),
            'original_publication_time':None,'numeric_accuracy_verified':False,'training_admitted':False,
            'limitation':'Earliest matching payload found in queried scope, not proven first release. Exact payload identity establishes the bytes despite CMS migration; numerical extraction and mapping require separate review.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',required=True,type=Path)
    parser.add_argument('--evidence-capture',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    manifest,source_sha,artifacts=load_capture(args.capture)
    _,evidence_sha,evidence=load_capture(args.evidence_capture)
    entries=[item for record,raw in evidence.values() for item in parse_cdx(record,raw)]
    # DOE and www.DOE searches may return the same canonical CDX records.
    entries=list({(e['archive_timestamp'],e['original_url'],e['payload_sha1_base32']):e for e in entries}.values())
    rows=[];rejected=[]
    for source,raw in artifacts.values():
        try:rows.append(match(source,raw,entries))
        except ValueError as exc:rejected.append({'source_id':source['id'],'reason':str(exc)})
    result={'schema_version':1,'source_capture_sha256':source_sha,'evidence_capture_sha256':evidence_sha,
            'builder_sha256':sha256(Path(__file__).read_bytes()),'records':rows,'rejected':rejected,
            'summary':{'captured_documents':len(artifacts),'acquisition_failures':sum(r['status']!='archived' for r in manifest['records']),
                       'unique_cdx_rows':len(entries),'matched_documents':sum(r['historical_availability_verified'] for r in rows),
                       'rejected_documents':len(rejected),'training_admitted':0}}
    write_once(args.output,encode(result));print(json.dumps(result['summary'],indent=2))


if __name__=='__main__':main()
