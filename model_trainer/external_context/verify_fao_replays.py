"""Verify original FAO release values against exact, timestamped archive bytes.

The available-by bound is the replay timestamp, never the article's printed
publication date. This does not certify index base definitions or model utility.
"""
import argparse
import base64
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import gzip
import hashlib
import json
from pathlib import Path

if __package__:
    from .build_context import aware_time, encode, load_capture, sha256
    from .extract_fao_releases import parse_release
    from .prepare_fao_replays import canonical
    from .ocr_customs import write_once
else:
    from build_context import aware_time, encode, load_capture, sha256
    from extract_fao_releases import parse_release
    from prepare_fao_replays import canonical
    from ocr_customs import write_once


def verify(record, raw, release):
    if sha256(raw) != record['artifact_sha256']:
        raise ValueError('Replay artifact hash mismatch')
    stamp = record['archive_timestamp']
    expected = datetime.strptime(stamp, '%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
    if expected > aware_time(record['captured_at_utc']):
        raise ValueError('Archive timestamp after local capture')
    if expected > aware_time(record['cdx_captured_at_utc']):
        raise ValueError('Archive timestamp after CDX evidence capture')
    url = f"https://web.archive.org/web/{stamp}id_/{record['original_url']}"
    if record['url'] != url or record['final_url'] != url:
        raise ValueError('Replay redirected or request does not match exact capture')
    dates = [v for k, v in record['headers'].items() if k.lower() == 'memento-datetime']
    if len(dates) != 1 or parsedate_to_datetime(dates[0]) != expected:
        raise ValueError('Memento timestamp differs from requested capture')
    if record['release_source_id'] != release['source_id'] or canonical(record['original_url']) != canonical(release['source_url']):
        raise ValueError('Replay does not refer to the selected release')
    encodings = {v.lower().strip() for k, v in record['headers'].items() if k.lower() == 'content-encoding'}
    if len(encodings) > 1:
        raise ValueError('Conflicting content encodings')
    encoding = next(iter(encodings), 'identity')
    if encoding not in {'identity', '', 'gzip'}:
        raise ValueError('Unsupported replay content encoding')
    body = gzip.decompress(raw) if encoding == 'gzip' else raw
    digest = base64.b32encode(hashlib.sha1(body).digest()).decode('ascii')
    if digest != record['archive_payload_sha1_base32']:
        raise ValueError('Replay payload differs from CDX digest')
    historical = parse_release(body, record['original_url'], allow_malformed_metadata=True)
    for key in ['metric', 'value', 'unit', 'reference_period', 'declared_publication_date']:
        if historical[key] != release[key]:
            raise ValueError('Historical release differs for ' + key)
    if expected.date().isoformat() < historical['declared_publication_date']:
        raise ValueError('Archive capture precedes declared article date')
    return {**historical, 'source_id': release['source_id'], 'source_url': release['source_url'],
            'current_artifact_sha256': release['artifact_sha256'],
            'historical_availability_verified': True, 'available_at_utc': expected.isoformat(),
            'basis': 'exact_timestamped_replay_with_CDX_payload_digest_and_matching_release_fields',
            'archive_replay_url': url, 'archive_artifact_sha256': record['artifact_sha256'],
            'decoded_archive_sha256': sha256(body), 'cdx_artifact_sha256': record['cdx_artifact_sha256'],
            'cdx_payload_sha1_base32': digest,
            'limitation': 'Available by capture; original publication time and base definition remain unverified.',
            'training_admitted': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', required=True, type=Path)
    parser.add_argument('--releases', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    manifest, capture_sha, artifacts = load_capture(args.capture)
    release_bytes = args.releases.read_bytes()
    releases = {r['source_id']: r for r in json.loads(release_bytes)['records']}
    verified, rejected = [], []
    for record in manifest['records']:
        try:
            if record['status'] != 'archived':
                raise ValueError(record.get('error', 'Acquisition failed'))
            verified.append(verify(record, artifacts[record['id']][1], releases[record['release_source_id']]))
        except (ValueError, KeyError, UnicodeDecodeError, OSError) as exc:
            rejected.append({'source_id': record['id'], 'reason': str(exc), 'training_admitted': False})
    result = {'schema_version': 1, 'capture_manifest_sha256': capture_sha,
              'releases_sha256': sha256(release_bytes), 'builder_sha256': sha256(Path(__file__).read_bytes()),
              'records': verified, 'rejected': rejected,
              'summary': {'replay_requests': len(manifest['records']), 'verified_records': len(verified),
                          'rejected': len(rejected), 'training_admitted': 0}}
    write_once(args.output, encode(result))
    print(json.dumps(result['summary'], indent=2))


if __name__ == '__main__':
    main()
