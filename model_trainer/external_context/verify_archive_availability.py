"""Link current original PDF bytes to independently timestamped archive digests.

A matching CDX payload SHA1 establishes availability by the capture timestamp,
not the original issue date. Keep local SHA256 and CDX evidence SHA256 too.
Nonmatching/missing archive evidence remains unverified.
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
    from .build_context import encode, load_capture, sha256
    from .ocr_customs import write_once
else:
    from build_context import encode, load_capture, sha256
    from ocr_customs import write_once


def canonical_original(url):
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"customs.gov.ph", "www.customs.gov.ph"}:
        raise ValueError("Archive evidence must refer to the official Customs host")
    if parsed.query or parsed.fragment or not parsed.path.lower().endswith(".pdf"):
        raise ValueError("Expected an original static PDF URL")
    return "customs.gov.ph" + unquote(parsed.path)


def parse_cdx(content):
    table = json.loads(content)
    if table == []:
        return []
    if not isinstance(table, list) or table[0] != ["timestamp", "original", "digest"]:
        raise ValueError("Unexpected CDX schema")
    rows = []
    for row in table[1:]:
        if len(row) != 3:
            raise ValueError("Malformed CDX row")
        stamp, original, digest = row
        if not re.fullmatch(r"\d{14}", stamp) or not re.fullmatch(r"[A-Z2-7]{32}", digest):
            raise ValueError("Invalid archive timestamp or SHA1 digest")
        when = datetime.strptime(stamp, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        rows.append({"archive_timestamp": stamp, "available_at_utc": when.isoformat(),
                     "original_url": original, "canonical_url": canonical_original(original), "payload_sha1_base32": digest})
    return rows


def match_source(source, content, archive_rows, *, allow_official_migration_matches=False):
    if not content.startswith(b"%PDF-") or sha256(content) != source["artifact_sha256"]:
        raise ValueError("Source must be a hash-verified original PDF")
    canonical = canonical_original(source["url"])
    digest = base64.b32encode(hashlib.sha1(content).digest()).decode("ascii")
    matching_url = [r for r in archive_rows if r["canonical_url"] == canonical]
    matching_payload = [r for r in matching_url if r["payload_sha1_base32"] == digest]
    migrated = []
    if allow_official_migration_matches:
        filename = canonical.rsplit("/", 1)[-1]
        for record in archive_rows:
            # Revalidate the original URL even for direct callers. Match only
            # files within the same publisher's upload tree, with identical
            # filename AND payload. Similar names alone are not evidence.
            old = canonical_original(record["original_url"])
            if (old != canonical and old.startswith("customs.gov.ph/wp-content/uploads/")
                    and canonical.startswith("customs.gov.ph/wp-content/uploads/")
                    and old.rsplit("/", 1)[-1] == filename and record["payload_sha1_base32"] == digest):
                migrated.append(record)
        matching_payload += migrated
    selected = min(matching_payload, key=lambda r: r["archive_timestamp"], default=None)
    return {
        "source_id": source["id"], "source_url": source["url"], "artifact_sha256": source["artifact_sha256"],
        "payload_sha1_base32": digest, "historical_availability_verified": selected is not None,
        "available_at_utc": selected["available_at_utc"] if selected else None,
        "original_published_at": None,
        "basis": ("matching_official_migrated_PDF_filename_and_payload_in_CDX" if selected and selected["canonical_url"] != canonical else "matching_original_PDF_payload_in_Internet_Archive_CDX") if selected else None,
        "allow_official_migration_matches": allow_official_migration_matches,
        "archive_evidence": selected, "archive_url_matches": len(matching_url),
        "archive_payload_matches": len(matching_payload),
        "migrated_payload_matches": len(migrated),
        "limitation": "First matching capture found in queried archive scope; may be much later than issue date. Does not establish original publication time, table extraction accuracy, geographic mapping or predictive value.",
        "numeric_accuracy_verified": False, "training_admitted": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--evidence-capture", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-official-migration-matches", action="store_true")
    args = parser.parse_args()
    _, source_capture_sha, artifacts = load_capture(args.capture)
    archive_rows = []
    evidence_manifests = []
    for path in args.evidence_capture:
        _, evidence_sha, evidence = load_capture(path)
        evidence_manifests.append({"path": path.as_posix(), "sha256": evidence_sha})
        for record, content in evidence.values():
            if not record["id"].startswith("customs_pdf_cdx_"):
                continue
            for row in parse_cdx(content):
                if datetime.fromisoformat(row["available_at_utc"]) > datetime.fromisoformat(record["captured_at_utc"]):
                    raise ValueError("Archive timestamp lies after evidence retrieval")
                archive_rows.append({**row, "cdx_source_url": record["url"], "cdx_artifact_sha256": record["artifact_sha256"],
                                     "cdx_captured_at_utc": record["captured_at_utc"]})
    records = [match_source(source, content, archive_rows, allow_official_migration_matches=args.allow_official_migration_matches) for source, content in artifacts.values()]
    result = {"schema_version": 1, "source_capture_sha256": source_capture_sha, "evidence_manifests": evidence_manifests,
              "builder_sha256": sha256(Path(__file__).read_bytes()),
              "summary": {"source_documents": len(records), "cdx_rows": len(archive_rows),
                          "historical_payload_matches": sum(r["historical_availability_verified"] for r in records),
                          "url_found_payload_different": sum(r["archive_url_matches"] > 0 and not r["historical_availability_verified"] for r in records),
                          "training_admitted_documents": 0}, "records": records}
    write_once(args.output, encode(result))
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
