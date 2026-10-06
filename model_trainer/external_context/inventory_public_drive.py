"""Inventory files embedded in a captured public Drive folder, without executing JS.

This is discovery only: names, folders and present-day metadata are not evidence
that the contained values were publicly available at a historical forecast date.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse


def decode_js_string(raw):
    out = []
    i = 0
    escapes = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f",
               "\\": "\\", "'": "'", '"': '"', "/": "/"}
    while i < len(raw):
        if raw[i] != "\\":
            out.append(raw[i]); i += 1
            continue
        i += 1
        if i == len(raw):
            raise ValueError("Truncated JS escape")
        code = raw[i]
        if code in ("x", "u"):
            width = 2 if code == "x" else 4
            digits = raw[i + 1:i + 1 + width]
            if len(digits) != width or not re.fullmatch(r"[0-9a-fA-F]+", digits):
                raise ValueError("Invalid JS hex escape")
            out.append(chr(int(digits, 16))); i += width + 1
        elif code in escapes:
            out.append(escapes[code]); i += 1
        else:
            raise ValueError(f"Unsupported JS escape: {code}")
    return "".join(out)


def parse_folder(html, parent_id):
    assignments = re.findall(r"window\['_DRIVE_ivd'\]\s*=\s*'((?:\\.|[^'\\])*)'\s*;", html)
    if len(assignments) != 1:
        raise ValueError("Expected exactly one public folder inventory")
    payload = json.loads(decode_js_string(assignments[0]))
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], list):
        raise ValueError("Unsupported folder inventory shape")
    result = []
    seen = set()
    for row in payload[0]:
        if not isinstance(row, list) or len(row) < 4:
            raise ValueError("Unsupported file metadata")
        file_id, parents, name, mime = row[:4]
        if (not isinstance(file_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{10,}", file_id)
                or not isinstance(parents, list) or parent_id not in parents
                or not isinstance(name, str) or not isinstance(mime, str)
                or "/" not in mime or file_id in seen):
            raise ValueError("Invalid, duplicate or foreign-parent file")
        seen.add(file_id)
        folder = mime == "application/vnd.google-apps.folder"
        result.append({"id": file_id, "name": name, "mime_type": mime,
                       "parent_id": parent_id,
                       "url": f"https://drive.google.com/drive/folders/{file_id}" if folder
                       else f"https://drive.google.com/file/d/{file_id}/view",
                       "raw_metadata": row,
                       "historical_publication_verified": False})
    return result


def inventory(capture_path, source_id):
    capture = json.loads(capture_path.read_text(encoding="utf-8"))
    records = [r for r in capture["records"] if r["id"] == source_id and r["status"] == "archived"]
    if len(records) != 1:
        raise ValueError("Expected one successful source capture")
    record = records[0]
    url = urlparse(record["final_url"])
    if url.hostname != "drive.google.com" or not url.path.startswith("/drive/folders/"):
        raise ValueError("Expected public Drive folder URL")
    parent_id = url.path.rstrip("/").split("/")[-1]
    root = capture_path.parent.resolve()
    path = (root / record["artifact_file"].replace("\\", "/")).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Capture artifact outside archive root")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != record["artifact_sha256"] or len(content) != record["bytes"]:
        raise ValueError("Capture hash/length mismatch")
    items = parse_folder(content.decode("utf-8"), parent_id)
    return {"schema_version": 1, "source_id": source_id, "source_url": record["url"],
            "capture_file": str(capture_path), "artifact_sha256": record["artifact_sha256"],
            "captured_at_utc": record["captured_at_utc"], "items": items,
            "note": "Only embedded visible listing is inventoried; pagination/completeness unproven. Metadata timestamps and filename dates are not verified publication times."}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--capture", type=Path, required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    result = inventory(args.capture, args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps({"output": str(args.output), "items": [
        {k: r[k] for k in ("id", "name", "mime_type")} for r in result["items"]]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
