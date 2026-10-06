"""Inventory exact Customs table rows and optionally capture a sample of PDFs.

The table's DATE OF ISSUANCE often contains a date range. It is preserved as
literal text, not converted to a historical publication timestamp.
"""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

if __package__:
    from .archive_sources import collect
    from .build_context import encode, load_capture, sha256
else:
    from archive_sources import collect
    from build_context import encode, load_capture, sha256


def inventory(source, content):
    soup = BeautifulSoup(content, "html.parser")
    tables = [t for t in soup.find_all("table") if "DATE OF ISSUANCE" in t.get_text(" ", strip=True)]
    if len(tables) != 1:
        raise ValueError("Expected one Customs reference-value table")
    documents = {}
    skipped = []
    for ordinal, row in enumerate(tables[0].find_all("tr")):
        cells = row.find_all("td", recursive=False)
        if not cells:
            continue
        if len(cells) != 4:
            skipped.append({"table_row": ordinal, "reason": "unexpected_cell_count", "text": row.get_text(" ", strip=True)})
            continue
        year, subject, period, _ = [" ".join(c.get_text(" ", strip=True).split()) for c in cells]
        links = cells[3].find_all("a", href=True)
        if len(links) != 1:
            skipped.append({"table_row": ordinal, "reason": "ambiguous_link_count", "text": row.get_text(" ", strip=True)})
            continue
        url = urljoin(source["url"], links[0]["href"])
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "customs.gov.ph" or not parsed.path.lower().endswith(".pdf"):
            skipped.append({"table_row": ordinal, "reason": "unexpected_download_url", "url": url})
            continue
        occurrence = {"table_row": ordinal, "year_literal": year, "subject_literal": subject, "date_of_issuance_literal": period}
        if url not in documents:
            documents[url] = {
                "id": "boc_reference_" + sha256(url.encode())[:16], "dataset": "boc_reference_values", "url": url,
                "index_source_url": source["url"], "index_artifact_sha256": source["artifact_sha256"],
                "index_captured_at_utc": source["captured_at_utc"], "occurrences": [],
                "reference_period_verified": False, "publication_at": None,
                "historical_availability_verified": False, "training_admitted": False,
            }
        documents[url]["occurrences"].append(occurrence)
    records = list(documents.values())
    counts = Counter()
    for r in records:
        r["rice_candidate"] = all("rice" in o["subject_literal"].lower() for o in r["occurrences"])
        for year in {o["year_literal"] for o in r["occurrences"]}:
            counts[year] += 1
    return {
        "schema_version": 1, "source_url": source["url"], "artifact_sha256": source["artifact_sha256"],
        "unique_documents": len(records), "unique_document_year_labels": dict(sorted(counts.items())),
        "rice_candidate_documents": sum(r["rice_candidate"] for r in records),
        "duplicate_url_occurrences": sum(len(r["occurrences"]) - 1 for r in records),
        "skipped_rows": skipped, "documents": records,
        "note": "Discovery inventory, not extracted trade observations. Duplicate URLs retained as occurrences but fetched once. Year/period labels can disagree; original PDF review required.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--download-sample-per-year", type=int, default=0)
    parser.add_argument("--download-all-rice", action="store_true")
    args = parser.parse_args()
    if args.download_sample_per_year < 0:
        parser.error("sample count must be nonnegative")
    if args.download_all_rice and args.download_sample_per_year:
        parser.error("Choose all rice or a yearly sample")
    _, manifest_sha, artifacts = load_capture(args.capture)
    result = inventory(*artifacts["boc_reference_index"])
    result["capture_manifest_sha256"] = manifest_sha
    payload = encode(result)
    args.output.mkdir(parents=True, exist_ok=True)
    path = args.output / "customs_document_inventory.json"
    if path.exists() and path.read_bytes() != payload:
        raise FileExistsError("Inventory changed; choose new output directory")
    if not path.exists():
        path.write_bytes(payload)
    print(json.dumps({k: v for k, v in result.items() if k not in {"documents", "skipped_rows"}}, indent=2), flush=True)
    if args.download_sample_per_year or args.download_all_rice:
        groups = defaultdict(list)
        for record in result["documents"]:
            year = record["occurrences"][0]["year_literal"]
            groups[year].append(record)
        selected = ([r for r in result["documents"] if r["rice_candidate"]] if args.download_all_rice else
                    [r for year in sorted(groups) for r in groups[year][:args.download_sample_per_year]])
        with ThreadPoolExecutor(max_workers=3) as pool:
            captures = list(pool.map(lambda s: collect(s, args.output), selected))
        capture = {"schema_version": 1, "registry_sha256": sha256(payload), "records": captures,
                   "selection": ("All unique links whose subject labels contain rice; actual PDF content requires review." if args.download_all_rice else "First unique links per literal year in the source table; acquisition sample, not representative statistical sampling.")}
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        capture_path = args.output / f"capture_{stamp}.json"
        with capture_path.open("xb") as stream:
            stream.write(encode(capture))
        print(json.dumps({"capture_manifest": str(capture_path), "counts": dict(Counter(r["status"] for r in captures))}, indent=2))


if __name__ == "__main__":
    main()
