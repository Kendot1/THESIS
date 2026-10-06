"""Preserve PDF text layers and identify pages needing OCR/review.

This is an extraction coverage audit, not a numeric table parser. Presence of
text never certifies OCR accuracy, a historical release date, or model admission.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess

if __package__:
    from .build_context import encode, load_capture, sha256
else:
    from build_context import encode, load_capture, sha256


def inspect_pdf(source, content, root, output):
    result = {"source_id": source["id"], "source_url": source["url"],
              "artifact_sha256": source["artifact_sha256"],
              "year_labels": sorted({o["year_literal"] for o in source.get("occurrences", [])}),
              "numeric_observations_extracted": 0, "training_admitted": False}
    try:
        if not content.startswith(b"%PDF-"):
            raise ValueError("Archived response is not a PDF")
        path = root / source["artifact_file"].replace("\\", "/")
        process = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, check=True, timeout=45)
        text = process.stdout.decode("utf-8")
        pages = text.split("\f")
        if pages and not pages[-1].strip():
            pages.pop()
        if not pages:
            raise ValueError("No PDF pages extracted")
        counts = [sum(c.isalnum() for c in page) for page in pages]
        text_digest = sha256(process.stdout)
        destination = output / "text" / (text_digest + ".txt")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if destination.read_bytes() != process.stdout:
                raise ValueError("Text digest collision or corrupt stored extraction")
        else:
            try:
                with destination.open("xb") as stream:
                    stream.write(process.stdout)
            except FileExistsError:
                # Identical empty/scanned PDFs can have identical text layers.
                if destination.read_bytes() != process.stdout:
                    raise ValueError("Concurrent extraction mismatch")
        result.update(status="text_layer_extracted", pages=len(pages), page_alphanumeric_counts=counts,
                      pages_requiring_ocr_candidate=[i + 1 for i, n in enumerate(counts) if n < 40],
                      text_file=destination.relative_to(output).as_posix(), text_sha256=text_digest,
                      text_accuracy_verified=False, extractor_stderr=process.stderr.decode("utf-8", errors="replace")[:2000])
    except Exception as exc:
        result.update(status="extraction_failed", error=f"{type(exc).__name__}: {exc}")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest, manifest_sha, artifacts = load_capture(args.capture)
    with ThreadPoolExecutor(max_workers=3) as pool:
        records = list(pool.map(lambda pair: inspect_pdf(*pair, args.capture.parent, args.output), artifacts.values()))
    summary = {
        "captured_documents": len(artifacts), "capture_failed": sum(r["status"] != "archived" for r in manifest["records"]),
        "extraction_status_counts": dict(Counter(r["status"] for r in records)),
        "pdf_pages": sum(r.get("pages", 0) for r in records),
        "documents_needing_ocr_candidate": sum(bool(r.get("pages_requiring_ocr_candidate")) for r in records),
        "pages_needing_ocr_candidate": sum(len(r.get("pages_requiring_ocr_candidate", [])) for r in records),
        "numerical_values_validated": 0,
    }
    result = {"schema_version": 1, "capture_manifest_sha256": manifest_sha,
              "builder_sha256": sha256(Path(__file__).read_bytes()), "summary": summary,
              "method": "pdftotext -layout; pages with fewer than 40 alphanumeric characters flagged for OCR assessment. Text-rich pages still require numeric/row alignment review.",
              "records": records}
    payload = encode(result)
    path = args.output / "text_layer_audit.json"
    args.output.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != payload:
        raise FileExistsError("Use a new output directory for changed text extraction")
    if not path.exists():
        with path.open("xb") as stream:
            stream.write(payload)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
