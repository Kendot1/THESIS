"""Create exact archive replay requests from checked FAO CDX records."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from urllib.parse import urlparse

if __package__:
    from .build_context import aware_time, encode, load_capture, sha256
    from .ocr_customs import write_once
else:
    from build_context import aware_time, encode, load_capture, sha256
    from ocr_customs import write_once


def canonical(url):
    parsed = urlparse(url)
    if parsed.scheme not in {'http', 'https'} or parsed.hostname != 'www.fao.org' or not parsed.path.startswith('/newsroom/detail/') or parsed.query or parsed.fragment:
        raise ValueError('Expected original FAO newsroom URL')
    return parsed.hostname + parsed.path.rstrip('/')


def replay_sources(record, raw):
    table = json.loads(raw)
    if table == []:
        return []
    if not isinstance(table, list) or table[0] != ['timestamp', 'original', 'digest']:
        raise ValueError('Unexpected CDX schema')
    sources = []
    for row in table[1:]:
        if len(row) != 3:
            raise ValueError('Malformed CDX row')
        timestamp, original, digest = row
        if not re.fullmatch(r'\d{14}', timestamp) or not re.fullmatch(r'[A-Z2-7]{32}', digest):
            raise ValueError('Invalid archive timestamp or digest')
        when = datetime.strptime(timestamp, '%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
        if when > aware_time(record['captured_at_utc']):
            raise ValueError('Archive timestamp after evidence capture')
        if canonical(original) != canonical(record['original_url']):
            raise ValueError('CDX returned a different original URL')
        sources.append({'id': 'fao_replay_' + sha256((timestamp+original).encode())[:16],
                        'dataset': 'fao_ffpi_historical_replay',
                        'url': f'https://web.archive.org/web/{timestamp}id_/{original}',
                        'original_url': original, 'archive_timestamp': timestamp,
                        'archive_payload_sha1_base32': digest, 'release_source_id': record['release_source_id'],
                        'cdx_artifact_sha256': record['artifact_sha256'],
                        'cdx_captured_at_utc': record['captured_at_utc']})
    return sources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    manifest, capture_sha, artifacts = load_capture(args.capture)
    sources = [s for record, raw in artifacts.values() for s in replay_sources(record, raw)]
    result = {'schema_version': 1, 'capture_manifest_sha256': capture_sha,
              'builder_sha256': sha256(Path(__file__).read_bytes()), 'seed_documents': sources,
              'summary': {'cdx_queries': len(manifest['records']), 'successful_queries': len(artifacts),
                          'historical_replay_candidates': len(sources)}}
    write_once(args.output, encode(result))
    print(json.dumps(result['summary'], indent=2))


if __name__ == '__main__':
    main()
