"""Extract reviewed source-route relationships from the DA vegetable roadmap.

Requires Poppler pdftotext. PDF page 95 (printed page 68) was visually inspected.
No numerical flow share is turned into a source-region model weight.
"""
import argparse
import json
from pathlib import Path
import subprocess

if __package__:
    from .build_context import encode, load_capture, sha256
else:
    from build_context import encode, load_capture, sha256


def extract(source, page_text):
    text = " ".join(page_text.split())
    evidence = "Kabayan, Benguet bring their cauliflower and cabbage in Nueva Vizcaya Agricultural Terminal (NVAT) in Bambang, Nueva Vizcaya and from there the products are bought by traders from Metro Manila and delivered to the various marketplaces in Metro Manila"
    if text.count(evidence) != 1 or "2017" not in text or "48.10%" not in text:
        raise ValueError("Reviewed page content changed; inspect the source PDF")
    records = []
    for commodity in ["cabbage", "cauliflower"]:
        records.append({
            "mapping_id": f"da_roadmap_kabayan_{commodity}_ncr",
            "commodity": commodity, "foodcast_product_ids": [],
            "foodcast_series_match": {"category": "Vegetables", "product_name": commodity.title(), "origin": "Local"},
            "product_match_note": "Commodity-level candidate applies to local cabbage variants or local cauliflower; actual source locality is not present in Foodcast labels.",
            "source_locality": "Kabayan", "source_province": "Benguet",
            "source_region": "Cordillera Administrative Region",
            "intermediate_market": "Nueva Vizcaya Agricultural Terminal, Bambang, Nueva Vizcaya",
            "destination": "Metro Manila marketplaces", "relationship": "documented commodity supply route",
            "ncr_supply_relationship_verified": True,
            "relationship_scope_note": "Existence of route only; does not prove the origin of an individual Foodcast retail observation or that all supply takes this route.",
            "weight": None, "weight_reason": "Figure 48 gives aggregate highland vegetable destination shares. 48.10% is not this commodity's Benguet share of NCR supply.",
            "source_url": source["url"], "artifact_sha256": source["artifact_sha256"],
            "evidence_pdf_page": 95, "evidence_printed_page": 68, "evidence_text": evidence,
            "related_figure": "Figure 48; DA-CAR-RFO, 2017 (aggregate highland flow diagram)",
            "reference_date": None, "published_at": None,
            "publication_note": "2021-2025 is the roadmap planning period. URL upload path is not release proof; current Last-Modified is 2026-03-30.",
            "captured_at_utc": source["captured_at_utc"], "historical_availability_verified": False,
            "training_admitted": False,
        })
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    _, manifest_sha, artifacts = load_capture(args.capture)
    source, _ = artifacts["da_vegetable_roadmap"]
    pdf = args.capture.parent / source["artifact_file"].replace("\\", "/")
    process = subprocess.run(["pdftotext", "-f", "95", "-l", "95", "-layout", str(pdf), "-"], check=True, capture_output=True)
    records = extract(source, process.stdout.decode("utf-8"))
    result = {"schema_version": 1, "capture_manifest_sha256": manifest_sha,
              "builder_sha256": sha256(Path(__file__).read_bytes()), "records": records}
    payload = encode(result)
    if args.output.exists() and args.output.read_bytes() != payload:
        raise FileExistsError("Choose a new mapping output path")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not args.output.exists():
        with args.output.open("xb") as stream:
            stream.write(payload)
    print(json.dumps({"mappings": len(records), "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
