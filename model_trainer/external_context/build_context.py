"""Rebuild reviewed DA seed observations from content-addressed original HTML.

Offline and deterministic. Curated extraction specifications are intentional:
unreviewed wording changes fail instead of silently changing metric meaning.
No training admission or historical release verification is implied by extraction.
"""
import argparse
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def sha256(content):
    return hashlib.sha256(content).hexdigest()


def aware_time(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timestamp must include timezone")
    return parsed


def load_capture(manifest_path):
    manifest_path = Path(manifest_path).resolve()
    root = manifest_path.parent
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("schema_version") != 1:
        raise ValueError("Unknown capture schema")
    ids = [r["id"] for r in manifest["records"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate source IDs in capture")
    artifacts = {}
    for record in manifest["records"]:
        if record["status"] != "archived":
            continue
        path = (root / record["artifact_file"].replace("\\", "/")).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Artifact must stay within archive directory")
        content = path.read_bytes()
        if sha256(content) != record["artifact_sha256"] or len(content) != record["bytes"]:
            raise ValueError("Source artifact hash/length mismatch")
        aware_time(record["captured_at_utc"])
        artifacts[record["id"]] = (record, content)
    return manifest, sha256(manifest_bytes), artifacts


def document(content):
    soup = BeautifulSoup(content, "html.parser")
    articles = soup.select("article")
    if len(articles) != 1:
        raise ValueError("Expected exactly one DA article")
    text = " ".join(articles[0].get_text(" ", strip=True).split())
    dates = {}
    for field, prop in (("published_at", "article:published_time"), ("modified_at", "article:modified_time")):
        tags = soup.find_all("meta", attrs={"property": prop})
        if len(tags) != 1:
            raise ValueError(f"Expected one {prop} metadata tag")
        dates[field] = tags[0]["content"]
        aware_time(dates[field])
    if aware_time(dates["modified_at"]) < aware_time(dates["published_at"]):
        raise ValueError("Modification predates publication")
    return text, dates


def extract_damage(source, content, spec, event_id, specs_sha):
    text, dates = document(content)
    report_date = date.fromisoformat(spec["report_date"])
    if aware_time(dates["published_at"]).date() != report_date:
        raise ValueError("Reviewed report date disagrees with publication metadata")
    if aware_time(dates["modified_at"]) > aware_time(source["captured_at_utc"]):
        raise ValueError("Page modification lies after archive capture")
    records = []
    for metric in spec["metrics"]:
        matches = list(re.finditer(metric["pattern"], text))
        if len(matches) != 1:
            raise ValueError(f"{source['id']} {metric['metric']} requires one exact reviewed match")
        match = matches[0]
        original = match.group("value")
        value = Decimal(original.replace(",", "")) * Decimal(str(metric["multiplier"]))
        if not value.is_finite() or value < 0:
            raise ValueError("Damage observation must be finite and nonnegative")
        records.append({
            "schema_version": 1,
            "record_id": f"{source['id']}:{metric['commodity']}:{metric['metric']}:{source['artifact_sha256'][:12]}",
            "dataset": "da_damage", "event_id": event_id,
            "report_date": report_date.isoformat(), "reference_start": None, "reference_end": None,
            "reference_date_note": "Exact damage assessment cutoff not stated; report_date is not an observation cutoff.",
            **dates, "captured_at_utc": source["captured_at_utc"],
            "source_url": source["url"], "artifact_sha256": source["artifact_sha256"],
            "artifact_file": source["artifact_file"].replace("\\", "/"),
            "extraction_specs_sha256": specs_sha,
            "geography_literal": spec["geography_literal"],
            "geography_interpretation": spec["geography_interpretation"],
            "commodity_scope": metric["commodity"], "metric": metric["metric"],
            "original_value": original, "original_unit": metric["unit"],
            "value": float(value), "unit": metric["normalized_unit"], "qualifier": metric["qualifier"],
            "transformation": f"Remove thousands separators; multiply by {metric['multiplier']}; no imputation.",
            "estimate_status": "preliminary_subject_to_validation", "aggregation": "cumulative_event_snapshot_do_not_sum_updates",
            "evidence_text": match.group(), "evidence_locator": {"selector": "article", "normalized_text_start": match.start(), "normalized_text_end": match.end()},
            "historical_availability_verified": False, "historical_available_at": None,
            "prospective_available_at": source["captured_at_utc"],
            "availability_note": "Current page has publication and later modification metadata; original historical numerical vintage not yet corroborated. Capture proves only current availability.",
            "training_admitted": False,
        })
    return records


def extract_mapping(source, content):
    text, dates = document(content)
    evidence = "producer of almost 80 percent of highland vegetables in the country"
    if text.count(evidence) != 1:
        raise ValueError("Cordillera mapping evidence changed")
    return {
        "mapping_id": "da_cordillera_highland_vegetables_20240128",
        "commodity_group": "highland vegetables", "foodcast_product_ids": [],
        "source_region": "Cordillera Administrative Region", "relationship": "major national production region",
        "destination": None, "ncr_supply_relationship_verified": False,
        "weight": None, "weight_reason": "Almost 80% is a broad national production claim; not a product-specific NCR supply share.",
        "evidence_text": evidence, "source_url": source["url"],
        "artifact_sha256": source["artifact_sha256"], **dates,
        "captured_at_utc": source["captured_at_utc"], "historical_availability_verified": False,
        "training_admitted": False,
    }


def encode(value):
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def build(manifest_path, output, specs_path=HERE / "da_damage_specs.json", registry_path=HERE / "sources.json"):
    manifest, manifest_sha, artifacts = load_capture(manifest_path)
    specs_bytes = Path(specs_path).read_bytes()
    specs = json.loads(specs_bytes)
    if specs["schema_version"] != 1:
        raise ValueError("Unknown extraction specification schema")
    observations = []
    for source_id, spec in specs["documents"].items():
        if source_id in artifacts:
            source, content = artifacts[source_id]
            observations.extend(extract_damage(source, content, spec, specs["event_id"], sha256(specs_bytes)))
    mappings = []
    if "da_cordillera_mapping" in artifacts:
        mappings.append(extract_mapping(*artifacts["da_cordillera_mapping"]))
    registry_bytes = Path(registry_path).read_bytes()
    registry = json.loads(registry_bytes)
    capture_counts = Counter(r["status"] for r in manifest["records"])
    counts = Counter(r["report_date"] for r in observations)
    coverage = {
        "capture_status_counts": dict(capture_counts), "normalized_observations": len(observations),
        "report_dates_and_metric_counts": dict(sorted(counts.items())), "unique_events": len({r["event_id"] for r in observations}),
        "historically_admitted_observations": 0, "historically_admitted_mappings": 0,
        "missing_reference_cutoffs": sum(r["reference_end"] is None for r in observations),
        "missing_geographic_allocation": sum(r["geography_literal"] is None for r in observations),
        "unacquired_sources": [{"id": r["id"], "error": r.get("error")} for r in manifest["records"] if r["status"] != "archived"],
        "unreviewed_sources": sorted(set(artifacts) - set(specs["documents"]) - {"da_cordillera_mapping"}),
        "treatments": ["Keep unavailable values null; never substitute zero damage.", "Do not sum successive cumulative event estimates.", "Approximate and lower-bound quantities retain their qualifiers.", "No calendar coverage percentage: event archive completeness has not been established.", "No backward fill, interpolation, regional allocation, or training admission."],
    }
    availability = []
    for source_id, (source, content) in artifacts.items():
        if source_id not in specs["documents"] and source_id != "da_cordillera_mapping":
            continue
        _, dates = document(content)
        availability.append({"source_id": source_id, **dates, "captured_at_utc": source["captured_at_utc"], "historical_available_at": None, "historical_availability_verified": False, "training_admitted": False})
    products = {
        "observations.json": observations, "commodity_region_mapping.json": mappings,
        "availability_matrix.json": availability, "missing_data_report.json": coverage,
        "dataset_inventory.json": registry,
    }
    payloads = {name: encode(value) for name, value in products.items()}
    payloads["build_manifest.json"] = encode({
        "schema_version": 1, "capture_manifest_sha256": manifest_sha,
        "extraction_specs_sha256": sha256(specs_bytes), "registry_sha256": sha256(registry_bytes),
        "capture_registry_sha256": manifest["registry_sha256"],
        "builder_sha256": sha256(Path(__file__).read_bytes()),
        "outputs": {name: sha256(content) for name, content in payloads.items()},
        "status": "seed_reconstruction_not_training_admitted",
    })
    output = Path(output)
    # Preflight all destinations before creating anything: preserve reviewed runs.
    for name, content in payloads.items():
        path = output / name
        if path.exists() and path.read_bytes() != content:
            raise FileExistsError(f"Use a new output directory; refusing to replace {path}")
    output.mkdir(parents=True, exist_ok=True)
    for name, content in payloads.items():
        path = output / name
        if not path.exists():
            with path.open("xb") as stream:
                stream.write(content)
    return coverage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.capture, args.output), indent=2))


if __name__ == "__main__":
    main()
