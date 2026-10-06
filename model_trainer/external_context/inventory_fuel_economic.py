"""Inventory official DOE reports and FAO newsletters without dating their values.

Index year and labels are retained literally. They do not establish publication
dates, numerical contents, or historical availability of the linked documents.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

if __package__:
    from .build_context import encode, load_capture, sha256
    from .ocr_customs import write_once
else:
    from build_context import encode, load_capture, sha256
    from ocr_customs import write_once


def literal(node):
    return " ".join(node.get_text(" ", strip=True).split())


def extract_links(record, raw, kind):
    expected_host = "doe.gov.ph" if kind == "doe" else "www.fao.org"
    if urlparse(record["final_url"]).hostname != expected_host:
        raise ValueError("Unexpected index publisher")
    soup = BeautifulSoup(raw.decode("utf-8"), "html.parser")
    occurrences = []
    for anchor in soup.select("a[href]"):
        url = urljoin(record["final_url"], anchor["href"].strip())
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            continue
        if kind == "doe":
            if parsed.hostname != "prod-cms.doe.gov.ph" or not parsed.path.startswith("/documents/"):
                continue
            row = anchor.find_parent("tr")
            cells = row.find_all("td", recursive=False) if row else []
            year = literal(cells[0]) if cells else ""
            if not re.fullmatch(r"20\d{2}", year):
                raise ValueError("DOE document outside a recognized year row")
            # Ordered nearest first; nesting distinguishes month, period, region.
            context = [literal(p) for p in anchor.parents if p.name == "li"]
        else:
            if parsed.hostname != "newsletters.fao.org" or not parsed.path.startswith("/q/"):
                continue
            year = None  # Titles may name reference month rather than issue date.
            context = []
        occurrences.append({"url": url, "anchor_literal": literal(anchor), "index_year_literal": year,
                            "ancestor_list_literals": context,
                            "index_source_id": record["id"], "index_url": record["url"],
                            "index_artifact_sha256": record["artifact_sha256"],
                            "index_captured_at_utc": record["captured_at_utc"],
                            "historical_publication_verified": False, "training_admitted": False})
    if not occurrences:
        raise ValueError("No recognized document links")
    return occurrences


def build_registry(links, kind, sample_per_year=None):
    unique = {}
    for item in links:
        unique.setdefault(item["url"], item)
    selected = list(unique.values())
    if sample_per_year is not None:
        if kind != "doe" or sample_per_year < 1:
            raise ValueError("Positive year sampling is only supported for DOE")
        counts = Counter()
        selected = []
        for item in unique.values():
            year = item["index_year_literal"]
            if counts[year] < sample_per_year:
                selected.append(item)
                counts[year] += 1
    return {"schema_version": 1, "selection": "all unique links" if sample_per_year is None else
            f"first {sample_per_year} unique links in index order per year; format pilot only",
            "seed_documents": [{"id": kind + "_document_" + sha256(item["url"].encode())[:16],
                                "dataset": "doe_fuel" if kind == "doe" else "fao_ffpi_newsletter",
                                **item} for item in selected]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", required=True, type=Path)
    parser.add_argument("--source", required=True)
    parser.add_argument("--kind", choices=["doe", "fao"], required=True)
    parser.add_argument("--sample-per-year", type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    _, capture_sha, artifacts = load_capture(args.capture)
    record, raw = artifacts[args.source]
    links = extract_links(record, raw, args.kind)
    registry = build_registry(links, args.kind, args.sample_per_year)
    result = {"schema_version": 1, "capture_manifest_sha256": capture_sha,
              "builder_sha256": sha256(Path(__file__).read_bytes()), "records": links,
              "summary": {"link_occurrences": len(links), "unique_urls": len({r['url'] for r in links}),
                          "occurrences_by_index_year": dict(Counter(r['index_year_literal'] or 'unspecified' for r in links)),
                          "selected_downloads": len(registry['seed_documents'])}}
    write_once(args.output / "inventory.json", encode(result))
    write_once(args.output / "document_sources.json", encode(registry))
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
