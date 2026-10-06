"""Attach a reviewed index definition and audit causal FAO feature coverage.

No target prices are read, no imputation uses later releases, and no production
training admission is granted. Freshness and lag combinations are diagnostics.
"""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

if __package__:
    from .build_context import encode, load_capture, sha256
    from .fao_features import FAOArchive
    from .ocr_customs import write_once
else:
    from build_context import encode, load_capture, sha256
    from fao_features import FAOArchive
    from ocr_customs import write_once


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verified', type=Path, action='append', required=True)
    parser.add_argument('--methodology-capture', type=Path, required=True)
    parser.add_argument('--definition', type=Path, default=Path(__file__).with_name('fao_definition_review.json'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    spec_bytes = args.definition.read_bytes()
    spec = json.loads(spec_bytes)
    _, method_capture_sha, artifacts = load_capture(args.methodology_capture)
    record, raw = artifacts[spec['source_id']]
    if record['artifact_sha256'] != spec['artifact_sha256'] or record['url'] != spec['source_url'] or not raw.startswith(b'%PDF-'):
        raise ValueError('Reviewed definition source does not match original methodology')
    rows, excluded, inputs = [], [], []
    for path in args.verified:
        data = path.read_bytes()
        verified = json.loads(data)
        inputs.append({'path': str(path), 'sha256': sha256(data)})
        for row in verified['records']:
            if row['declared_publication_date'] < spec['release_not_before'] or row['reference_period'] < spec['reference_not_before']:
                excluded.append({'source_id': row['source_id'], 'reason': 'outside_reviewed_base_definition'})
                continue
            rows.append({**row, 'base_period': spec['base_period'], 'base_definition_verified': True,
                         'definition_spec_sha256': sha256(spec_bytes), 'definition_source_sha256': spec['artifact_sha256'],
                         'definition_reviewed_on': spec['reviewed_on'], 'geography': spec['geography'],
                         'mapping': spec['mapping'], 'training_admitted': False})
    archive = FAOArchive(rows)
    splits = {'early_tuning': ['2024-08-26','2024-09-25','2024-10-25'],
              'calibration': ['2024-11-24','2024-12-24','2025-01-23'],
              'development': ['2025-02-22','2025-03-24','2025-04-23','2025-05-23','2025-06-22','2025-07-22']}
    lookups = []
    for split, days in splits.items():
        for day in days:
            origin = datetime.fromisoformat(day).replace(tzinfo=timezone(timedelta(hours=8)))
            for lag in [0,1,3,7,14,30]:
                for age in [45,60,90,180]:
                    lookups.append({'split': split, 'origin': origin.isoformat(),
                                    **archive.at(origin, lag_days=lag, max_age_days=age)})
    summary = []
    for split in splits:
        for lag in [0,1,3,7,14,30]:
            for age in [45,60,90,180]:
                cells = [r for r in lookups if r['split']==split and r['lag_days']==lag and r['max_age_days']==age]
                summary.append({'split': split, 'lag_days': lag, 'max_age_days': age, 'origins': len(cells),
                                'nonmissing': sum(r['missing']==0 for r in cells),
                                'reasons': dict(Counter(r['reason'] for r in cells))})
    result = {'schema_version': 1, 'builder_sha256': sha256(Path(__file__).read_bytes()),
              'methodology_capture_sha256': method_capture_sha, 'verified_inputs': inputs,
              'definition_sha256': sha256(spec_bytes), 'records': sorted(rows,key=lambda r:r['reference_period']),
              'excluded': excluded, 'training_admitted': False,
              'scope': 'Initial-release global FFPI; current reconstructed subset only; no local price labels accessed',
              'missingness_policy': 'Latest reference month known by origin minus lag; age at actual origin from reference month end. Stale/unknown values stay missing. No backfill or cross-base splicing.',
              'summary': summary, 'lookups': lookups}
    write_once(args.output, encode(result))
    print(json.dumps({'verified_months':len(rows), 'lookups':len(lookups),
                      'zero_lag_summary':[s for s in summary if s['lag_days']==0]}, indent=2))


if __name__ == '__main__':
    main()
