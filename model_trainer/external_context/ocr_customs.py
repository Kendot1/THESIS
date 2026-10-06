"""Resume page-level OCR of captured official PDFs with verifiable provenance.

OCR text, word boxes and images are intermediate evidence. No extracted number
is certified or admitted to training automatically.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import csv
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile

if __package__:
    from .build_context import encode, load_capture, sha256
else:
    from build_context import encode, load_capture, sha256


def write_once(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise FileExistsError(f"Refusing to replace different output: {path}")
    else:
        with path.open("xb") as stream:
            stream.write(payload)


def checked_completed(path, source_sha, config_sha, expected_page):
    data = json.loads(path.read_bytes())
    if data["artifact_sha256"] != source_sha or data["ocr_config_sha256"] != config_sha:
        raise ValueError("OCR resume input/config mismatch")
    if data["pdf_page"] != expected_page:
        raise ValueError("OCR resume page mismatch")
    for name, digest in data["outputs"].items():
        target = (path.parent / name).resolve()
        if not target.is_relative_to(path.parent.resolve()) or sha256(target.read_bytes()) != digest:
            raise ValueError("OCR resume output hash/path mismatch")
    return data


def indexed_years(source):
    """Read explicit inventory years from Customs or DOE capture schemas."""
    if 'occurrences' in source:
        values=[o['year_literal'] for o in source['occurrences']]
    elif 'index_year_literal' in source:
        values=[source['index_year_literal']]
    else:
        raise ValueError('Source has no explicit inventory year')
    if not values or any(not str(v).isdigit() or len(str(v))!=4 for v in values):
        raise ValueError('Invalid inventory year')
    return {int(v) for v in values}


def ocr_page(source, pdf, page, output, config, config_sha):
    folder = output / source["artifact_sha256"] / f"page_{page:04d}"
    manifest_path = folder / "page.json"
    if manifest_path.exists():
        checked_completed(manifest_path, source["artifact_sha256"], config_sha, page)
        return {"source_id": source["id"], "page": page, "status": "reused", "manifest": manifest_path.relative_to(output).as_posix()}
    folder.mkdir(parents=True, exist_ok=True)
    # Each temporary directory belongs solely to this page task and stays inside
    # the designated output folder. Only its own intermediates are cleaned up.
    with tempfile.TemporaryDirectory(prefix="render_", dir=folder) as temporary:
        temp = Path(temporary)
        image_base = temp / "page"
        subprocess.run(["pdftoppm", "-f", str(page), "-l", str(page), "-r", str(config["dpi"]),
                        "-gray", "-png", "-singlefile", str(pdf), str(image_base)],
                       check=True, capture_output=True, timeout=90)
        environment = dict(os.environ)
        environment["OMP_THREAD_LIMIT"] = "1"
        process = subprocess.run(["tesseract", str(temp / "page.png"), str(temp / "ocr"),
                                  "-l", "eng", "--psm", str(config["psm"]), "txt", "tsv"],
                                 check=True, capture_output=True, timeout=120, env=environment)
        payloads = {"page.png": (temp / "page.png").read_bytes(),
                    "ocr.txt": (temp / "ocr.txt").read_bytes(), "ocr.tsv": (temp / "ocr.tsv").read_bytes()}
    words = [r for r in csv.DictReader(io.StringIO(payloads["ocr.tsv"].decode("utf-8")), delimiter="\t") if r["text"].strip()]
    confidences = [float(r["conf"]) for r in words if float(r["conf"]) >= 0]
    data = {"schema_version": 1, "source_id": source["id"], "source_url": source["url"],
            "artifact_sha256": source["artifact_sha256"], "pdf_page": page,
            "captured_at_utc": source["captured_at_utc"], "ocr_config_sha256": config_sha,
            "outputs": {name: sha256(content) for name, content in payloads.items()},
            "word_count": len(words), "low_confidence_word_count": sum(c < 60 for c in confidences),
            "ocr_stderr": process.stderr.decode("utf-8", errors="replace")[:2000],
            "numeric_accuracy_verified": False, "historical_availability_verified": False,
            "training_admitted": False}
    # The completion manifest is written last. A interrupted page may leave
    # deterministic artifacts, but never a falsely complete result.
    for name, payload in payloads.items():
        write_once(folder / name, payload)
    write_once(manifest_path, encode(data))
    return {"source_id": source["id"], "page": page, "status": "created", "manifest": manifest_path.relative_to(output).as_posix()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--text-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", action="append")
    parser.add_argument("--page", action="append", type=int)
    parser.add_argument("--from-year", type=int, default=2018)
    parser.add_argument("--through-year", type=int, default=2026)
    parser.add_argument("--only-needs-ocr", action="store_true")
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--psm", type=int, choices=[3, 6, 11], default=3)
    parser.add_argument("--workers", type=int, choices=[1, 2, 3], default=2)
    args = parser.parse_args()
    if args.dpi < 150 or args.dpi > 400:
        parser.error("Use 150-400 DPI")
    if args.from_year > args.through_year or (args.page and min(args.page) < 1):
        parser.error("Invalid year/page range")
    _, capture_sha, artifacts = load_capture(args.capture)
    audit_bytes = args.text_audit.read_bytes()
    audit = json.loads(audit_bytes)
    if audit["capture_manifest_sha256"] != capture_sha:
        raise ValueError("Text audit does not describe this capture")
    versions = {}
    for executable, flag in [("tesseract", "--version"), ("pdftoppm", "-v")]:
        process = subprocess.run([executable, flag], capture_output=True, check=True)
        versions[executable] = (process.stdout + process.stderr).decode("utf-8", errors="replace").splitlines()[0]
    config = {"schema_version": 1, "dpi": args.dpi, "psm": args.psm, "language": "eng", "grayscale": True,
              "versions": versions, "builder_sha256": sha256(Path(__file__).read_bytes())}
    config_bytes = encode(config)
    config_sha = sha256(config_bytes)
    write_once(args.output / "ocr_config.json", config_bytes)
    indexed = {r["source_id"]: r for r in audit["records"]}
    if args.source and set(args.source) - set(artifacts):
        raise ValueError("Unknown or uncaptured requested source")
    jobs = []
    for source_id, (source, _) in artifacts.items():
        if args.source and source_id not in args.source:
            continue
        years = indexed_years(source)
        if not any(args.from_year <= year <= args.through_year for year in years):
            continue
        info = indexed[source_id]
        if info["artifact_sha256"] != source["artifact_sha256"] or info["status"] != "text_layer_extracted":
            raise ValueError("Missing/mismatched page inventory")
        pages = info["pages_requiring_ocr_candidate"] if args.only_needs_ocr else range(1, info["pages"] + 1)
        if args.page:
            if max(args.page) > info["pages"]:
                raise ValueError("Requested page beyond source document")
            pages = [p for p in pages if p in args.page]
        for page in pages:
            jobs.append((source, args.capture.parent / source["artifact_file"].replace("\\", "/"), page))
    if not jobs:
        raise ValueError("No eligible OCR jobs selected")
    print(json.dumps({"selected_documents": len({j[0]["id"] for j in jobs}), "selected_pages": len(jobs), "config_sha256": config_sha}), flush=True)
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        pending = {pool.submit(ocr_page, *job, args.output, config, config_sha): (job[0]["id"], job[2]) for job in jobs}
        for future in as_completed(pending):
            source_id, page = pending[future]
            try:
                results.append(future.result())
            except Exception as exc:
                results.append({"source_id": source_id, "page": page, "status": "failed", "error": f"{type(exc).__name__}: {exc}"})
            if len(results) % 10 == 0 or len(results) == len(jobs):
                print(json.dumps({"completed": len(results), "selected": len(jobs), "failed": sum(r["status"] == "failed" for r in results)}), flush=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    manifest = {"schema_version": 1, "capture_manifest_sha256": capture_sha, "text_audit_sha256": sha256(audit_bytes),
                "ocr_config_sha256": config_sha, "records": sorted(results, key=lambda r: (r["source_id"], r["page"]))}
    path = args.output / f"ocr_run_{stamp}.json"
    write_once(path, encode(manifest))
    print(json.dumps({"manifest": str(path), "failures": sum(r["status"] == "failed" for r in results)}), flush=True)
    if any(r["status"] == "failed" for r in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
