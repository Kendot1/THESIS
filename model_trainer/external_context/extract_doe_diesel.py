"""Reconstruct a review queue from DOE vertical product/range PDF tables.

Horizontal old/new/difference layouts and scanned pages are not guessed. Word
coordinates, literal values, date text and rejection reasons remain auditable.
Extracted ranges require unit and numerical review before feature admission.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

if __package__:
    from .build_context import encode, load_capture, sha256
    from .ocr_customs import write_once
else:
    from build_context import encode, load_capture, sha256
    from ocr_customs import write_once

NS={'x':'http://www.w3.org/1999/xhtml'}
NUMBER=re.compile(r'\d+(?:\.\d+)?')
MONTHS='January|February|March|April|May|June|July|August|September|October|November|December'


def parse_period(text):
    text=' '.join(text.split()).replace('–','-').replace('—','-')
    match=re.search(r'('+MONTHS+r')\s+(\d{1,2})\s*(?:-|to)\s*(?:('+MONTHS+r')\s+)?(\d{1,2}),?\s+(20\d{2})\b',text,re.I)
    if match:
        month,a,other,b,year=match.groups()
        start=datetime.strptime(f'{month} {a} {year}','%B %d %Y').date()
        end=datetime.strptime(f'{other or month} {b} {year}','%B %d %Y').date()
    else:
        match=re.search(r'('+MONTHS+r')\s+(\d{1,2}),?\s+(20\d{2})\b',text,re.I)
        if not match:raise ValueError('Unsupported explicit monitoring date')
        start=end=datetime.strptime(' '.join(match.groups()),'%B %d %Y').date()
    if end<start or (end-start).days>14:raise ValueError('Monitoring period reversed or unexpectedly long')
    return start.isoformat(),end.isoformat()


def page_lines(page):
    lines=[]
    for line in page.findall('.//x:line',NS):
        words=[]
        for w in line.findall('x:word',NS):
            words.append({'text':w.text or '',**{k:float(w.attrib[k]) for k in ['xMin','xMax','yMin','yMax']}})
        if words:lines.append({'text':' '.join(w['text'] for w in words),'words':words,
                               **{k:float(line.attrib[k]) for k in ['xMin','xMax','yMin','yMax']}})
    return lines


def monitoring_headers(lines):
    """Keep dated report headers; blank signature fields are not dates."""
    headers=[]
    for line in lines:
        text=line['text']
        if 'Date of Monitoring:' in text:
            suffix=text.split('Date of Monitoring:',1)[1].strip(' _')
            if suffix:headers.append(text)
        elif re.match(r'\(For the week:',text,re.I) and re.search(r'\bas of\b',text,re.I):
            headers.append(text)
    return headers


def joined_header(lines, first, second, product):
    """Accept one vertically stacked header with overlapping horizontal boxes."""
    pairs=[]
    for a in lines:
        if a['text'].upper()!=first or abs(a['yMin']-product['yMin'])>=30:continue
        for b in lines:
            if b['text'].upper()!=second:continue
            if 0<b['yMin']-a['yMin']<25 and max(a['xMin'],b['xMin'])<min(a['xMax'],b['xMax']):
                pairs.append({'text':first+' '+second,
                              'xMin':min(a['xMin'],b['xMin']),'xMax':max(a['xMax'],b['xMax']),
                              'yMin':a['yMin'],'yMax':b['yMax']})
    if len(pairs)!=1:raise ValueError('Missing/ambiguous '+first+' '+second+' header')
    return pairs[0]


def overall_header(lines, product):
    """Recognize the source's RANGE/RAINGE spellings, retaining the literal."""
    candidates=[]
    for line in lines:
        if abs(line['yMin']-product['yMin'])>=30:continue
        words=line['words']
        for i,word in enumerate(words[:-1]):
            following=words[i+1]
            if word['text'].upper()=='OVERALL' and following['text'].upper() in {'RANGE','RAINGE'}:
                candidates.append({'text':word['text']+' '+following['text'],
                                   'xMin':word['xMin'],'xMax':following['xMax'],
                                   'yMin':word['yMin'],'yMax':max(word['yMax'],following['yMax'])})
        if line['text'].upper() in {'OVERALL RANGE','OVERALL RAINGE'} and len(words)==1:
            candidates.append(line)
    if not candidates:
        for spelling in ['RANGE','RAINGE']:
            try:candidates.append(joined_header(lines,'OVERALL',spelling,product))
            except ValueError:pass
    if len(candidates)!=1:raise ValueError('Missing/ambiguous OVERALL RANGE header')
    return candidates[0]


def separated_headers(lines):
    """Recover known column phrases from lines merging adjacent header cells."""
    labels={'PRODUCT','PROVINCE','CITIES','CITY /','CITY / MUNICIPALITY',
            'MUNICIPALITY','OVERALL','RANGE','RAINGE','COMMON'}
    out=list(lines);seen={(l['text'],l['xMin'],l['yMin']) for l in lines}
    for line in lines:
        words=line['words']
        for i in range(len(words)):
            for count in range(1,5):
                group=words[i:i+count]
                if len(group)!=count:continue
                text=' '.join(w['text'] for w in group)
                if text.upper() not in labels:continue
                key=(text,group[0]['xMin'],group[0]['yMin'])
                if key in seen:continue
                seen.add(key)
                out.append({'text':text,'words':group,'xMin':group[0]['xMin'],'xMax':group[-1]['xMax'],
                            'yMin':min(w['yMin'] for w in group),'yMax':max(w['yMax'] for w in group)})
    return out


def parse_page(page, page_number, document_monitoring=None):
    lines=page_lines(page);words=[w for line in lines for w in line['words']]
    headers=separated_headers(lines)
    def unique(label):
        found=[l for l in headers if l['text'].upper()==label]
        if label in {'CITIES','PROVINCE'}:
            found=[w for w in words if w['text'].upper()==label]
            # Some PDFs repeat geography headers between region sections.
            # Select the header accompanying this page's unique product header.
            product_headers=[l for l in headers if l['text'].upper()=='PRODUCT']
            if len(product_headers)==1:
                found=[w for w in found if abs(w['yMin']-product_headers[0]['yMin'])<30]
            if found and max(w['xMin'] for w in found)-min(w['xMin'] for w in found)<1 and max(w['yMin'] for w in found)-min(w['yMin'] for w in found)<12:
                found=[min(found,key=lambda w:w['yMin'])]
        if len(found)!=1:raise ValueError('Missing/ambiguous '+label+' header')
        return found[0]
    product=unique('PRODUCT')
    overall=overall_header(headers,product)
    if any(w['text'].upper()=='CITIES' for w in words):city=unique('CITIES')
    elif any(l['text'].upper()=='CITY / MUNICIPALITY' for l in headers):city=unique('CITY / MUNICIPALITY')
    else:city=joined_header(headers,'CITY /','MUNICIPALITY',product)
    province=unique('PROVINCE')
    common=unique('COMMON')
    left_labels=[w for w in words if w['xMax']<overall['xMin'] and abs(w['yMin']-product['yMin'])<8]
    previous=max(left_labels,key=lambda l:l['xMax'])
    center=lambda l:(l['xMin']+l['xMax'])/2
    range_left=(center(previous)+center(overall))/2
    range_right=(center(overall)+center(common))/2
    city_left=(center(province)+center(city))/2
    company_headers=[l for l in left_labels if l['xMin']>product['xMax']]
    if not company_headers:raise ValueError('Missing company-price headers')
    product_right=(product['xMax']+min(l['xMin'] for l in company_headers))/2
    product_rows=[]
    for line in lines:
        if abs(line['xMin']-product['xMin'])>=15:continue
        label_words=[w for w in line['words'] if w['xMax']<product_right]
        label=' '.join(w['text'] for w in label_words)
        if re.fullmatch(r'RON (?:100|97|95|91)|DIESEL(?: PLUS)?|KEROSENE',label):
            product_rows.append({**line,'text':label,'xMax':label_words[-1]['xMax']})
    product_rows.sort(key=lambda l:l['yMin'])
    if not product_rows:raise ValueError('No vertical product rows')
    product_left=min(l['xMin'] for l in product_rows)
    dates=monitoring_headers(lines)
    period_basis='page_monitoring_header'
    if not dates and document_monitoring:
        dates=[document_monitoring];period_basis='unique_monitoring_header_in_same_PDF'
    if len(dates)!=1:raise ValueError('Missing/ambiguous page monitoring date')
    start,end=parse_period(dates[0])
    rows=[]
    for pos,diesel in enumerate(product_rows):
        if diesel['text']!='DIESEL':continue
        try:
            prior=[l for l in product_rows[:pos] if l['text']=='KEROSENE']
            following=[l for l in product_rows[pos+1:] if l['text']=='KEROSENE']
            if not following:raise ValueError('Incomplete product group')
            top=(prior[-1]['yMax']+.01) if prior else product_rows[0]['yMin']
            bottom=following[0]['yMax']
            group=[l['text'] for l in product_rows if top<=l['yMin']<=bottom]
            allowed=['RON 100','RON 97','RON 95','RON 91','DIESEL','DIESEL PLUS','KEROSENE']
            if group!=[name for name in allowed if name in group] or not {'RON 95','RON 91','DIESEL','KEROSENE'}<=set(group):
                raise ValueError('Unexpected product group ordering')
            city_lines=[l for l in lines if l['xMin']>=city_left and l['xMax']<product_left and top<=l['yMin']<=bottom]
            if len(city_lines)!=1:raise ValueError('Missing/ambiguous city label in product block')
            tolerance=(diesel['yMax']-diesel['yMin'])*.4
            row_words=sorted([w for w in words if abs(w['yMin']-diesel['yMin'])<=tolerance],key=lambda w:w['xMin'])
            selected=[w for w in row_words if range_left<=(w['xMin']+w['xMax'])/2<=range_right]
            tokens=[w['text'] for w in selected]
            if len(tokens)!=3 or tokens[1]!='-' or not NUMBER.fullmatch(tokens[0]) or not NUMBER.fullmatch(tokens[2]):
                raise ValueError('Overall range is not two explicit numeric bounds')
            low,high=map(Decimal,[tokens[0],tokens[2]])
            if low>high:raise ValueError('Reversed source range')
            company=[Decimal(w['text']) for w in row_words if w['xMin']>product['xMax'] and w['xMax']<range_left and NUMBER.fullmatch(w['text'])]
            positive=[v for v in company if v>0]
            missing=low==high==0 and not positive
            if not missing and (low<=0 or not positive or min(positive)!=low or max(positive)!=high):
                raise ValueError('Overall bounds disagree with visible company-price extrema')
            regions=[l for l in lines if l['yMin']<top and re.fullmatch(r'Region [IVX]+|CAR|Cordillera Administrative Region \(CAR\)',l['text'])]
            region=max(regions,key=lambda l:l['yMin'])['text'] if regions else None
            provinces=[l for l in lines if l['xMax']<city_left and top<=l['yMin']<=bottom]
            rows.append({'pdf_page':page_number,'city_literal':city_lines[0]['text'],'region_literal':region,
                         'province_literal':provinces[0]['text'] if len(provinces)==1 else None,
                         'overall_header_literal':overall['text'],
                         'product_literal':'DIESEL','monitoring_literal':dates[0],
                         'monitoring_period_basis':period_basis,
                         'reference_start':start,'reference_end':end,'range_low_literal':tokens[0],
                         'range_high_literal':tokens[2],'range_low':None if missing else float(low),
                         'range_high':None if missing else float(high),'missing_reason':'zero_placeholder_no_outlet_prices' if missing else None,
                         'visible_company_numeric_cells':len(company),'company_extrema_consistent':True,
                         'row_y':diesel['yMin'],'range_word_boxes':selected,'unit':None,'unit_verified':False,
                         'numeric_visual_reviewed':False,'training_admitted':False,'status':'candidate'})
        except ValueError as exc:
            rows.append({'pdf_page':page_number,'row_y':diesel['yMin'],'status':'rejected','reason':str(exc),'training_admitted':False})
    return rows


def inspect(source, raw, capture_root, output):
    result={'source_id':source['id'],'artifact_sha256':source['artifact_sha256'],'source_url':source['url'],
            'index_year_literal':source.get('index_year_literal'),'rows':[],'rejected_pages':[],'training_admitted':False}
    try:
        if not raw.startswith(b'%PDF-'):raise ValueError('Not a PDF')
        process=subprocess.run(['pdftotext','-bbox-layout',str(capture_root/source['artifact_file']),'-'],capture_output=True,check=True,timeout=60)
        xml_sha=sha256(process.stdout);write_once(output/'bbox'/(xml_sha+'.html'),process.stdout)
        result['bbox_sha256']=xml_sha;result['bbox_file']='bbox/'+xml_sha+'.html'
        pages=ET.fromstring(process.stdout).findall('.//x:page',NS);result['pages']=len(pages)
        date_headers={text for page in pages for text in monitoring_headers(page_lines(page))}
        document_monitoring=next(iter(date_headers)) if len(date_headers)==1 else None
        for n,page in enumerate(pages,1):
            try:result['rows'].extend(parse_page(page,n,document_monitoring))
            except ValueError as exc:result['rejected_pages'].append({'pdf_page':n,'reason':str(exc)})
    except (ValueError,ET.ParseError,subprocess.SubprocessError) as exc:result['error']=str(exc)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',required=True,type=Path)
    parser.add_argument('--availability',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--source',action='append')
    args=parser.parse_args()
    _,capture_sha,artifacts=load_capture(args.capture)
    availability_bytes=args.availability.read_bytes();availability=json.loads(availability_bytes)
    if availability['source_capture_sha256']!=capture_sha:raise ValueError('Availability capture mismatch')
    known={r['source_id']:r for r in availability['records'] if r['historical_availability_verified']}
    chosen=[pair for id,pair in artifacts.items() if id in known and (not args.source or id in args.source)]
    if args.source and set(args.source)-{r['id'] for r,_ in chosen}:raise ValueError('Requested source lacks verified availability')
    with ThreadPoolExecutor(max_workers=3) as pool:
        records=list(pool.map(lambda pair:inspect(*pair,args.capture.parent,args.output),chosen))
    for r in records:r['available_at_utc']=known[r['source_id']]['available_at_utc']
    rows=[row for r in records for row in r['rows']]
    result={'schema_version':1,'capture_manifest_sha256':capture_sha,'availability_sha256':sha256(availability_bytes),
            'builder_sha256':sha256(Path(__file__).read_bytes()),'records':records,
            'summary':{'documents':len(records),'pages':sum(r.get('pages',0) for r in records),
                       'candidate_rows':sum(r['status']=='candidate' for r in rows),'rejected_rows':sum(r['status']=='rejected' for r in rows),
                       'rejected_pages':sum(len(r['rejected_pages']) for r in records),'training_admitted':0}}
    write_once(args.output/'candidates.json',encode(result));print(json.dumps(result['summary'],indent=2))


if __name__=='__main__':main()
