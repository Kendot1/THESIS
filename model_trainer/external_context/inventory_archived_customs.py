"""Reconstruct original rice-PDF links from dated historical Customs indexes.

This proves an archived link, not the PDF's contents. Original URLs are retained
so a separate PDF capture query can test pre-migration historical availability.
"""
import argparse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import gzip
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlparse, unquote, urlencode

from bs4 import BeautifulSoup

if __package__:
    from .build_context import encode, load_capture, sha256
    from .ocr_customs import write_once
else:
    from build_context import encode, load_capture, sha256
    from ocr_customs import write_once


def decode_body(record, raw):
    encodings = {str(v).lower().strip() for k, v in record["headers"].items() if k.lower() == "content-encoding"}
    if len(encodings) > 1:
        raise ValueError("Conflicting content-encoding headers")
    encoding = next(iter(encodings), "identity")
    if encoding == "gzip":
        return gzip.decompress(raw)
    if encoding not in {"identity", ""}:
        raise ValueError("Unsupported archived HTTP content encoding")
    return raw


def extract_links(record, raw):
    timestamp = record["archive_timestamp"]
    expected = datetime.strptime(timestamp, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    mementos = [v for k, v in record["headers"].items() if k.lower() == "memento-datetime"]
    if len(mementos) != 1 or parsedate_to_datetime(mementos[0]) != expected:
        raise ValueError("Replay date does not match requested historical capture")
    if record["final_url"] != record["url"]:
        raise ValueError("Replay redirected; inspect the actual capture before use")
    original = record["original_url"]
    if urlparse(original).hostname != "customs.gov.ph":
        raise ValueError("Not an official original Customs index")
    body = decode_body(record, raw)
    soup = BeautifulSoup(body, "html.parser")
    records = []
    for ordinal, row in enumerate(soup.find_all("tr")):
        literal = " ".join(row.get_text(" ", strip=True).split())
        if "rice" not in literal.lower():
            continue
        for anchor in row.find_all("a", href=True):
            url = urljoin(original, anchor["href"])
            parsed = urlparse(url)
            if parsed.scheme not in {"https", "http"} or parsed.hostname != "customs.gov.ph" or not parsed.path.lower().endswith(".pdf"):
                continue
            records.append({"original_pdf_url": url, "index_row_literal": literal, "index_row_ordinal": ordinal,
                            "index_available_at_utc": expected.isoformat(), "index_replay_url": record["url"],
                            "index_artifact_sha256": record["artifact_sha256"], "decoded_index_sha256": sha256(body),
                            "pdf_historical_payload_verified": False, "training_admitted": False})
    if not records:
        raise ValueError("No original rice PDF links found")
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    _, capture_sha, artifacts = load_capture(args.capture)
    links = [link for record, raw in artifacts.values() for link in extract_links(record, raw)]
    folders = sorted({re.match(r"/wp-content/uploads/(\d{4})/", urlparse(r["original_pdf_url"]).path).group(1)
                      for r in links if re.match(r"/wp-content/uploads/(\d{4})/", urlparse(r["original_pdf_url"]).path)})
    seeds = []
    for year in folders:
        query = urlencode({"url": f"customs.gov.ph/wp-content/uploads/{year}/", "matchType": "prefix", "output": "json",
                           "fl": "timestamp,original,digest", "collapse": "urlkey", "to": "20251231"})
        query += "&filter=statuscode%3A200&filter=mimetype%3Aapplication%2Fpdf&filter=original%3A.*%28Rice%7Crice%7CRICE%29.*"
        seeds.append({"id": f"customs_pdf_cdx_original_{year}", "dataset": "publication_evidence",
                      "url": "https://web.archive.org/cdx/search/cdx?" + query})
    result = {"schema_version": 1, "capture_manifest_sha256": capture_sha,
              "builder_sha256": sha256(Path(__file__).read_bytes()), "records": links,
              "summary": {"index_captures": len(artifacts), "rice_link_occurrences": len(links),
                          "unique_original_pdf_urls": len({r["original_pdf_url"] for r in links}), "original_upload_years": folders}}
    write_once(args.output / "original_links.json", encode(result))
    write_once(args.output / "cdx_queries.json", encode({"schema_version": 1, "seed_documents": seeds}))
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
