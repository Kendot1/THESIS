"""Archive configured official source documents without overwriting older bytes."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "audits/external_context_20261003"


def collect(source, root):
    started = datetime.now(timezone.utc).isoformat()
    record = {**source, "retrieval_started_at_utc": started, "historical_publication_verified": False}
    try:
        request = Request(source["url"], headers={"User-Agent": "Foodcast academic external-data provenance research/1.0"})
        with urlopen(request, timeout=35) as response:
            content = response.read()
            record.update(final_url=response.url, headers=dict(response.headers.items()), http_status=response.status)
        digest = hashlib.sha256(content).hexdigest()
        path = root / "raw" / digest
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
        else:
            with path.open("xb") as stream:
                stream.write(content)
        record.update(status="archived", artifact_sha256=digest, artifact_file=str(path.relative_to(root)), bytes=len(content),
                      captured_at_utc=datetime.now(timezone.utc).isoformat())
    except Exception as exc:
        record.update(status="acquisition_failed", error=f"{type(exc).__name__}: {exc}")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--registry", type=Path, default=Path(__file__).with_name("sources.json"))
    parser.add_argument("--source", action="append", help="Seed ID; default all configured seeds")
    args = parser.parse_args()
    registry_path = args.registry
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    sources = [s for s in registry["seed_documents"] if not args.source or s["id"] in args.source]
    if args.source and set(args.source) - {s["id"] for s in sources}:
        raise ValueError("Unknown source ID")
    args.output.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        records = list(pool.map(lambda source: collect(source, args.output), sources))
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    manifest = {"schema_version": 1, "registry_sha256": hashlib.sha256(registry_path.read_bytes()).hexdigest(),
                "records": records, "note": "Capture time proves availability at capture, not original historical availability. No missing source is replaced with generated observations."}
    path = args.output / f"capture_{timestamp}.json"
    with path.open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2)
    print(json.dumps({"manifest": str(path), "results": [{"id": r["id"], "status": r["status"], "error": r.get("error")} for r in records]}, indent=2))


if __name__ == "__main__":
    main()
