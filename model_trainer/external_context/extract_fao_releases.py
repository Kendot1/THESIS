"""Extract declared-date FAO index releases, requiring newsletter corroboration.

Current release text and newsletter agreement is not historical-version proof.
Outputs remain research records until an independently dated historical capture
supports the same metric, period, value, and base definition.
"""
import argparse
import calendar
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
import re
from urllib.parse import urlencode, urlparse

from bs4 import BeautifulSoup

if __package__:
    from .build_context import encode, load_capture, sha256
    from .extract_fao_newsletters import LEVEL
    from .ocr_customs import write_once
else:
    from build_context import encode, load_capture, sha256
    from extract_fao_newsletters import LEVEL
    from ocr_customs import write_once


def normalized(node):
    return ' '.join(node.get_text(' ', strip=True).split())


def parse_release(raw, url, *, allow_malformed_metadata=False):
    parsed_url = urlparse(url)
    if parsed_url.hostname != 'www.fao.org' or not parsed_url.path.startswith('/newsroom/detail/'):
        raise ValueError('Not a supported official FAO newsroom release')
    soup = BeautifulSoup(raw.decode('utf-8'), 'html.parser')
    bodies = soup.select('div.news-detail__body')
    if len(bodies) != 1:
        raise ValueError('Expected one FAO release body')
    dates = soup.select('span[class*="detail__date"]')
    if len(dates) != 1:
        raise ValueError('Expected one visible release date')
    published = datetime.strptime(normalized(dates[0]), '%d/%m/%Y').date()
    structured_dates = []
    metadata_basis = 'valid_Article_JSON_and_visible_date_agree'
    for tag in soup.select('script[type="application/ld+json"]'):
        metadata_text = tag.string or tag.get_text()
        try:
            data = json.loads(metadata_text)
        except json.JSONDecodeError:
            # Some original 2021-2022 pages omit a publisher-closing brace.
            # Preserve those original bytes; only an explicit historical path
            # may use a unique literal date, corroborated by the visible field.
            if not allow_malformed_metadata:
                raise
            types = re.findall(r'"@type"\s*:\s*"Article"', metadata_text)
            values = re.findall(r'"datePublished"\s*:\s*"([^"\r\n]+)"', metadata_text)
            if len(types) != 1 or len(values) != 1 or metadata_text.count('"datePublished"') != 1:
                raise ValueError('Ambiguous malformed Article date metadata')
            structured_dates.append(values[0])
            metadata_basis = 'malformed_Article_JSON_unique_date_literal_matches_visible_date'
            continue
        if isinstance(data, dict) and data.get('@type') == 'Article':
            structured_dates.append(data.get('datePublished'))
    if structured_dates != [published.strftime('%d/%m/%Y')]:
        raise ValueError('Visible and structured publication dates disagree')
    body = bodies[0]
    for tag in body.select('br'):
        tag.replace_with('\u001e')
    for tag in body.select('p'):
        tag.insert_before('\u001e')
        tag.insert_after('\u001e')
    paragraphs = [' '.join(part.split()) for part in body.get_text(' ', strip=False).split('\u001e')]
    candidates = []
    for text in paragraphs:
        if 'FAO Food Price Index' not in text:
            continue
        matches = list(LEVEL.finditer(text))
        if matches:
            if len(matches) != 1:
                raise ValueError('Ambiguous index-level paragraph')
            candidates.append((text, matches[0]))
    if len(candidates) != 1:
        raise ValueError('Expected exactly one FFPI level paragraph')
    paragraph, match = candidates[0]
    value = Decimal(match['value'])
    if not value.is_finite() or value <= 0:
        raise ValueError('Nonpositive or invalid index level')
    # This narrowly supported monthly release format explicitly names the prior
    # month in the same paragraph. Reject rather than infer any other period.
    reference_year = published.year if published.month > 1 else published.year - 1
    reference_month = published.month - 1 if published.month > 1 else 12
    month_name = calendar.month_name[reference_month]
    period = re.match(r'\s+(?:in|during(?: the month of)?)\s+(' + '|'.join(calendar.month_name[1:]) + r')(?:\s+(20\d{2}))?\b', paragraph[match.end():])
    if period:
        named_month, stated_year = period.groups()
    else:
        # E.g. "declined in January, averaging 124.9 points during the month".
        before = re.findall(r'\b(' + '|'.join(calendar.month_name[1:]) + r')(?:\s+(20\d{2}))?\b', paragraph[:match.start()])
        if not before:
            raise ValueError('Explicit reference month not adjacent to level clause')
        named_month, stated_year = before[-1]
    if named_month != month_name:
        raise ValueError('Prior reference month not stated in level paragraph')
    # Ignore later year-on-year comparison clauses, but check the level's year.
    if stated_year and stated_year != str(reference_year):
        raise ValueError('Reference year conflicts with release chronology')
    return {'metric': 'FAO Food Price Index', 'value': str(value), 'value_literal': match['value'],
            'unit': 'index_points', 'reference_period': f'{reference_year:04d}-{reference_month:02d}',
            'reference_period_resolution': 'Named prior month in FFPI paragraph; year resolved against visible release date',
            'declared_publication_date': published.isoformat(), 'publication_time_known': False,
            'publication_date_extraction_basis': metadata_basis,
            'level_paragraph_literal': paragraph, 'base_period': None,
            'base_definition_verified': False}


def corroborate(release, newsletter):
    issue = datetime.strptime(release['declared_publication_date'], '%Y-%m-%d').strftime('%B %Y')
    if newsletter['issue_month_literals'] != [issue]:
        raise ValueError('Newsletter issue month differs from linked release month')
    # Require the metric name, equal level and named reference month inside the
    # newsletter's bounded level context; numeric coincidence alone is insufficient.
    matches = [c for c in newsletter['level_candidates'] if
               Decimal(c['value_literal']) == Decimal(release['value']) and
               'FAO Food Price Index' in c['context_literal']]
    if len(matches) != 1:
        raise ValueError('Newsletter does not uniquely corroborate FFPI value')
    month = calendar.month_name[int(release['reference_period'][-2:])]
    if not re.search(r'\b' + month + r'\b', matches[0]['context_literal']):
        raise ValueError('Newsletter candidate does not corroborate reference month')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', required=True, type=Path)
    parser.add_argument('--newsletters', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    manifest, capture_sha, artifacts = load_capture(args.capture)
    newsletter_bytes = args.newsletters.read_bytes()
    newsletters = {r['source_id']: r for r in json.loads(newsletter_bytes)['records']}
    records, rejected = [], []
    for record in manifest['records']:
        try:
            if record['status'] != 'archived':
                raise ValueError(record.get('error', 'Source acquisition failed'))
            raw = artifacts[record['id']][1]
            release = parse_release(raw, record['final_url'])
            newsletter = newsletters[record['newsletter_source_id']]
            if newsletter['artifact_sha256'] != record['newsletter_artifact_sha256']:
                raise ValueError('Newsletter provenance mismatch')
            corroborate(release, newsletter)
            records.append({**release, 'source_id': record['id'], 'source_url': record['final_url'],
                            'artifact_sha256': record['artifact_sha256'], 'captured_at_utc': record['captured_at_utc'],
                            'newsletter_source_id': newsletter['source_id'],
                            'newsletter_artifact_sha256': newsletter['artifact_sha256'],
                            'historical_publication_verified': False, 'training_admitted': False})
        except (ValueError, KeyError, UnicodeDecodeError) as exc:
            rejected.append({'source_id': record['id'], 'reason': str(exc), 'training_admitted': False})
    seeds = []
    for record in records:
        query = urlencode({'url': record['source_url'], 'output': 'json', 'fl': 'timestamp,original,digest',
                           'collapse': 'urlkey', 'to': '20251231', 'filter': 'statuscode:200'})
        seeds.append({'id': 'fao_cdx_' + record['source_id'].removeprefix('fao_release_'),
                      'dataset': 'publication_evidence', 'url': 'https://web.archive.org/cdx/search/cdx?' + query,
                      'original_url': record['source_url'], 'release_source_id': record['source_id']})
    result = {'schema_version': 1, 'capture_manifest_sha256': capture_sha,
              'newsletter_candidates_sha256': sha256(newsletter_bytes),
              'builder_sha256': sha256(Path(__file__).read_bytes()), 'records': records, 'rejected': rejected,
              'summary': {'release_candidates': len(manifest['records']), 'corroborated_declared_date_records': len(records),
                          'rejected': len(rejected), 'training_admitted': 0}}
    write_once(args.output / 'releases.json', encode(result))
    write_once(args.output / 'archive_queries.json', encode({'schema_version': 1, 'seed_documents': seeds}))
    print(json.dumps({'summary': result['summary'], 'rejected': rejected}, indent=2))


if __name__ == '__main__':
    main()
