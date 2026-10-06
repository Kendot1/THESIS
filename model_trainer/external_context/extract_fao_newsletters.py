"""Build a review queue of FAO newsletter index levels and release links.

Numbers are candidates, never historical training observations. In particular,
issue-month labels are not publication timestamps and the 2020 base change must
be reviewed before combining levels. No reference year is inferred here.
"""
import argparse
import calendar
import json
from pathlib import Path
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

if __package__:
    from .build_context import encode, load_capture, sha256
    from .ocr_customs import write_once
else:
    from build_context import encode, load_capture, sha256
    from ocr_customs import write_once

MONTHS = "|".join(calendar.month_name[1:])
ISSUE = re.compile(rf"(?:{MONTHS})\s+20\d{{2}}")
LEVEL = re.compile(r"\b(?:averaged|averaging|stood at)\s+(?P<value>\d+(?:\.\d+)?)\s+points\b", re.I)


def extract(record, raw):
    if urlparse(record["final_url"]).hostname != "newsletters.fao.org":
        raise ValueError("Unexpected newsletter publisher")
    soup = BeautifulSoup(raw.decode("utf-8"), "html.parser")
    for node in soup.select("script,style"):
        node.decompose()
    text = " ".join(soup.get_text(" ", strip=True).split())
    headings = [" ".join(h.get_text(" ", strip=True).split()) for h in soup.select("h1,h2,h3,h4,h5,h6")]
    # Exact short headings only; do not match e.g. a headline comparing July 2011.
    issue_labels = sorted({m.group() for h in headings if len(h) < 85
                           and (ISSUE.fullmatch(h) or "newsletter" in h.lower()) for m in ISSUE.finditer(h)})
    levels = []
    for match in LEVEL.finditer(text):
        levels.append({"value_literal": match['value'], "unit_literal": "points",
                       "match_start": match.start(), "match_end": match.end(),
                       "context_literal": text[max(0, match.start()-260):match.end()+180],
                       "metric_confirmed": False, "reference_period": None, "base_period": None,
                       "numeric_observation_validated": False})
    release_links = []
    for anchor in soup.select("a[href]"):
        label = " ".join(anchor.get_text(" ", strip=True).split())
        if label.lower() != "read more":
            continue
        url = anchor['href'].strip()
        parsed = urlparse(url)
        if parsed.scheme in {'http', 'https'} and parsed.hostname == 'newsletters.fao.org' and parsed.path.startswith('/c/'):
            release_links.append({"url": url, "anchor_literal": label})
    return {"source_id": record['id'], "source_url": record['url'], "artifact_sha256": record['artifact_sha256'],
            "captured_at_utc": record['captured_at_utc'], "normalized_text_sha256": sha256(text.encode('utf-8')),
            "issue_month_literals": issue_labels, "level_candidates": levels,
            "read_more_links": release_links, "historical_publication_verified": False,
            "training_admitted": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    _, capture_sha, artifacts = load_capture(args.capture)
    records = [extract(record, raw) for record, raw in artifacts.values()]
    seeds = []
    for record in records:
        if record['read_more_links']:
            # First article link is a discovery candidate, not a certified release.
            link = record['read_more_links'][0]
            seeds.append({'id': 'fao_release_' + record['source_id'].removeprefix('fao_document_'),
                          'dataset': 'fao_ffpi_release_candidate', **link,
                          'newsletter_source_id': record['source_id'],
                          'newsletter_artifact_sha256': record['artifact_sha256']})
    result = {'schema_version': 1, 'capture_manifest_sha256': capture_sha,
              'builder_sha256': sha256(Path(__file__).read_bytes()), 'records': records,
              'summary': {'newsletters': len(records),
                          'newsletters_with_level_candidates': sum(bool(r['level_candidates']) for r in records),
                          'level_candidates': sum(len(r['level_candidates']) for r in records),
                          'single_issue_month': sum(len(r['issue_month_literals']) == 1 for r in records),
                          'release_link_candidates': len(seeds), 'training_admitted': 0}}
    write_once(args.output / 'candidates.json', encode(result))
    write_once(args.output / 'release_sources.json', encode({'schema_version': 1, 'seed_documents': seeds}))
    print(json.dumps(result['summary'], indent=2))


if __name__ == '__main__':
    main()
