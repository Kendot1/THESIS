"""Create a review queue from OCR word boxes; never auto-certify table rows.

Country/value alignment uses image coordinates. Commodity cells can span many
country rows, so nearby text is retained as context, not assigned as a grade.
"""
import argparse
import csv
import io
import json
from pathlib import Path
import re

if __package__:
    from .build_context import encode, sha256
    from .ocr_customs import checked_completed, write_once
else:
    from build_context import encode, sha256
    from ocr_customs import checked_completed, write_once

COUNTRY_CODES = {"TH", "VN", "KH", "PK", "IN", "MM"}
PRICE = re.compile(r"\$\d+[.,]\d{3}")


def parse_page(tsv_bytes, text_bytes):
    entries = list(csv.DictReader(io.StringIO(tsv_bytes.decode("utf-8")), delimiter="\t"))
    roots = [r for r in entries if r["level"] == "1"]
    if len(roots) != 1:
        raise ValueError("Expected one OCR image root")
    width = int(roots[0]["width"])
    height = int(roots[0]["height"])
    if width <= 0 or height <= 0:
        raise ValueError("Invalid OCR image dimensions")
    words = []
    for entry in entries:
        if entry["level"] != "5" or not entry["text"].strip():
            continue
        word = {k: int(entry[k]) for k in ("left", "top", "width", "height")}
        word.update(text=entry["text"], confidence=float(entry["conf"]))
        word["center_y"] = word["top"] + word["height"] / 2
        words.append(word)
    normalized_text = " ".join(text_bytes.decode("utf-8").split())
    unit_match = re.search(r"US\$\s*Per\s*kg\b", normalized_text, flags=re.IGNORECASE)
    candidates = []
    rejected = []
    for price in words:
        if "$" not in price["text"] or price["left"] < .50 * width:
            continue
        if not PRICE.fullmatch(price["text"]):
            rejected.append({"word": price, "reason": "unrecognized_price_punctuation_or_precision"})
            continue
        matches = [w for w in words if w["text"] in COUNTRY_CODES and .35 * width <= w["left"] < price["left"]
                   and abs(w["center_y"] - price["center_y"]) <= max(price["height"], w["height"]) * .65]
        country = matches[0] if len(matches) == 1 else None
        nearby = sorted([w for w in words if .15 * width < w["left"] < .60 * width
                         and abs(w["center_y"] - price["center_y"]) <= 2 * price["height"]], key=lambda w: (w["top"], w["left"]))
        flags = ["grade_cell_requires_review", "numeric_visual_review_required", "publication_review_required"]
        if not unit_match:
            flags.append("unit_not_recognized")
        if country is None:
            flags.append("country_missing_or_ambiguous")
        if "," in price["text"]:
            flags.append("decimal_comma_requires_review")
        if price["confidence"] < 60 or (country and country["confidence"] < 60):
            flags.append("low_ocr_confidence")
        candidates.append({
            "original_ocr_value": price["text"], "country_code_candidate": country["text"] if country else None,
            "value_word": price, "country_word": country, "country_alignment_candidates": matches,
            "nearby_grade_context_unassigned": " ".join(w["text"] for w in nearby),
            "grade": None, "unit_text_candidate": unit_match.group() if unit_match else None,
            "normalized_value": None, "reference_date": None, "published_at": None,
            "review_flags": flags, "numeric_visual_reviewed": False, "training_admitted": False,
        })
    return {"image_width": width, "image_height": height, "candidates": candidates, "rejected_price_tokens": rejected}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ocr-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()
    config_sha = sha256((args.ocr_root / "ocr_config.json").read_bytes())
    run_paths = sorted(args.ocr_root.glob("ocr_run_*.json"))
    if not run_paths and not args.allow_partial:
        raise ValueError("OCR has no completed run; use --allow-partial for an explicitly partial review queue")
    completed_run = None
    if not args.allow_partial:
        completed_run = json.loads(run_paths[-1].read_bytes())
        if completed_run["ocr_config_sha256"] != config_sha or any(r["status"] not in {"created", "reused"} for r in completed_run["records"]):
            raise ValueError("OCR run has failures or uses different settings")
    pages = []
    for path in sorted(args.ocr_root.glob("*/page_*/page.json")):
        expected_page = int(path.parent.name.removeprefix("page_"))
        metadata = checked_completed(path, path.parent.parent.name, config_sha, expected_page)
        result = parse_page((path.parent / "ocr.tsv").read_bytes(), (path.parent / "ocr.txt").read_bytes())
        pages.append({"source_id": metadata["source_id"], "source_url": metadata["source_url"],
                      "artifact_sha256": metadata["artifact_sha256"], "pdf_page": expected_page,
                      "page_manifest": path.relative_to(args.ocr_root).as_posix(), "page_manifest_sha256": sha256(path.read_bytes()),
                      "image_sha256": metadata["outputs"]["page.png"], **result})
    if completed_run is not None:
        expected = [(r["source_id"], r["page"]) for r in completed_run["records"]]
        actual = [(r["source_id"], r["pdf_page"]) for r in pages]
        if len(expected) != len(set(expected)) or sorted(expected) != sorted(actual):
            raise ValueError("OCR page set disagrees with completed run; use partial mode only for an intentional subset")
    result = {"schema_version": 1, "builder_sha256": sha256(Path(__file__).read_bytes()),
              "ocr_config_sha256": config_sha, "scope": "completed OCR pages observed during scan; not full-archive completeness proof",
              "allow_partial_requested": args.allow_partial,
              "completed_run_sha256": sha256(run_paths[-1].read_bytes()) if completed_run is not None else None,
              "summary": {"processed_pages": len(pages), "price_tokens_for_review": sum(len(p["candidates"]) for p in pages),
                          "rejected_price_tokens": sum(len(p["rejected_price_tokens"]) for p in pages),
                          "numeric_rows_certified": 0, "training_admitted_rows": 0}, "pages": pages}
    write_once(args.output, encode(result))
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
