"""Recover and verify exact historical NDRRMC PDF payloads.

Archive timestamps are conservative available-by bounds. A report's printed
as-of date never substitutes for them, and extraction is not training admission.
"""
import argparse
import base64
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import gzip
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse

if __package__:
    from .build_context import load_capture, aware_time, sha256
else:
    from build_context import load_capture, aware_time, sha256


def canonical(url):
    parsed = urlparse(url)
    if (parsed.scheme not in {"http", "https"} or parsed.hostname != "ndrrmc.gov.ph"
            or not parsed.path.startswith("/attachments/article/")
            or not parsed.path.lower().endswith(".pdf") or parsed.query or parsed.fragment
            or parsed.username or parsed.port):
        raise ValueError("Expected official NDRRMC PDF URL")
    return parsed.hostname + parsed.path


def prepare(cdx_capture):
    manifest, manifest_hash, artifacts = load_capture(cdx_capture)
    sources = []
    checks = []
    for record, raw in artifacts.values():
        table = json.loads(raw)
        if table == []:
            checks.append({"id":record["id"], "captures":0})
            continue
        if not isinstance(table, list) or table[0] != ["timestamp", "original", "digest"]:
            raise ValueError("Invalid CDX columns")
        for row in table[1:]:
            if not isinstance(row, list) or len(row) != 3:
                raise ValueError("Invalid CDX row")
            timestamp, original, digest = row
            if (not re.fullmatch(r"\d{14}", timestamp) or
                    not re.fullmatch(r"[A-Z2-7]{32}", digest)):
                raise ValueError("Invalid CDX timestamp/digest")
            at = datetime.strptime(timestamp, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
            if at > aware_time(record["captured_at_utc"]):
                raise ValueError("Future archive evidence")
            if canonical(original) != canonical(record["original_url"]):
                raise ValueError("CDX original URL differs")
            sources.append({"id": record["document_id"]+"_"+timestamp,
                            "document_id":record["document_id"], "event_id":record["event_id"],
                            "original_url":original, "archive_timestamp":timestamp,
                            "archive_payload_sha1_base32":digest,
                            "cdx_artifact_sha256":record["artifact_sha256"],
                            "cdx_captured_at_utc":record["captured_at_utc"],
                            "url":f"https://web.archive.org/web/{timestamp}id_/{original}"})
        checks.append({"id":record["id"], "captures":len(table)-1})
    if len({r["id"] for r in sources}) != len(sources):
        raise ValueError("Duplicate replay identity")
    return {"schema_version":1, "cdx_capture_sha256":manifest_hash,
            "seed_documents":sources, "checks":checks,
            "failed_queries":[r["id"] for r in manifest["records"] if r["status"] != "archived"]}


def verify(record, raw, expected):
    for key, value in expected.items():
        if record.get(key) != value:
            raise ValueError("Replay request differs from checked CDX: " + key)
    if sha256(raw) != record["artifact_sha256"] or len(raw) != record["bytes"]:
        raise ValueError("Replay byte integrity failure")
    if record["final_url"] != expected["url"]:
        raise ValueError("Replay redirected")
    at = datetime.strptime(expected["archive_timestamp"], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    if at > aware_time(record["captured_at_utc"]):
        raise ValueError("Replay timestamp after capture")
    dates = [v for k,v in record["headers"].items() if k.lower() == "memento-datetime"]
    if len(dates) != 1 or parsedate_to_datetime(dates[0]) != at:
        raise ValueError("Memento timestamp mismatch")
    encodings = [v.strip().lower() for k,v in record["headers"].items() if k.lower() == "content-encoding"]
    if len(encodings) > 1 or (encodings and encodings[0] not in {"", "identity", "gzip"}):
        raise ValueError("Unsupported content encoding")
    body = gzip.decompress(raw) if encodings == ["gzip"] else raw
    digest = base64.b32encode(hashlib.sha1(body).digest()).decode("ascii")
    if digest != expected["archive_payload_sha1_base32"]:
        raise ValueError("CDX payload digest mismatch")
    if not body.startswith(b"%PDF-"):
        raise ValueError("Historical response is not a PDF")
    return {**expected, "available_at_utc":at.isoformat(),
            "historical_availability_verified":True,
            "archive_artifact_sha256":record["artifact_sha256"],
            "decoded_archive_sha256":sha256(body), "training_admitted":False,
            "limitation":"Available by archive timestamp only; as-of date, crop scope and numeric values require review."}, body


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cdx", type=Path, required=True)
    p.add_argument("--capture", type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    result = prepare(args.cdx)
    if args.capture:
        manifest, manifest_hash, artifacts = load_capture(args.capture)
        expected = {r["id"]:r for r in result["seed_documents"]}
        verified, rejected = [], []
        for record in manifest["records"]:
            try:
                if record["status"] != "archived":
                    raise ValueError(record.get("error", "Acquisition failed"))
                item, body = verify(record, artifacts[record["id"]][1], expected[record["id"]])
                pdf = args.output.parent / "verified_pdf" / (item["decoded_archive_sha256"]+".pdf")
                pdf.parent.mkdir(parents=True, exist_ok=True)
                if pdf.exists() and pdf.read_bytes() != body:
                    raise ValueError("Stored PDF mismatch")
                if not pdf.exists():
                    pdf.write_bytes(body)
                item["pdf_file"] = str(pdf.relative_to(args.output.parent))
                verified.append(item)
            except (ValueError, KeyError, OSError) as exc:
                rejected.append({"id":record["id"], "reason":str(exc)})
        result = {"schema_version":1, "cdx_capture_sha256":result["cdx_capture_sha256"],
                  "replay_capture_sha256":manifest_hash, "records":verified, "rejected":rejected,
                  "not_requested":sorted(set(expected)-{r["id"] for r in manifest["records"]}),
                  "training_admitted":False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps({"output":str(args.output), "replays":len(result.get("seed_documents", [])),
                      "verified":len(result.get("records", [])), "rejected":result.get("rejected", [])}))


if __name__ == "__main__":
    main()
