"""Normalize visually reviewed Customs rows without treating OCR as ground truth."""
import argparse
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import re

if __package__:
    from .build_context import encode, load_capture, sha256
    from .ocr_customs import checked_completed, write_once
else:
    from build_context import encode, load_capture, sha256
    from ocr_customs import checked_completed, write_once

HERE = Path(__file__).resolve().parent
COUNTRIES = {"TH": "Thailand", "VN": "Viet Nam", "KH": "Cambodia", "PK": "Pakistan", "IN": "India", "MM": "Myanmar"}


def normalize(document, page, source, review):
    start, end, issue = [date.fromisoformat(document[k]) for k in ("reference_start", "reference_end", "issue_date")]
    if start > end:
        raise ValueError("Invalid reviewed reference dates")
    if page["unit_literal"] != "US$ Per kg":
        raise ValueError("Unexpected unit; add an explicitly reviewed transformation")
    seen = set()
    rows = []
    for ordinal, (commodity, country, original) in enumerate(page["rows"], start=1):
        if not commodity.strip() or country not in COUNTRIES or (original != "NA" and not re.fullmatch(r"\$\d+\.\d{3}", original)):
            raise ValueError("Invalid commodity, country or decimal in reviewed row")
        value = None if original == "NA" else Decimal(original[1:])
        if value is not None and value <= 0:
            raise ValueError("Reference price must be positive")
        key = (commodity, country)
        if key in seen:
            raise ValueError("Duplicate grade-country row")
        seen.add(key)
        rows.append({
            "record_id": f"{source['id']}:page{page['pdf_page']}:row{ordinal}",
            "dataset": "boc_rice_reference_prices", "metric": "customs_reference_value_usd_per_kg",
            "commodity": "rice", "grade_literal": commodity, "country_code_literal": country,
            "country_of_origin": COUNTRIES[country], "destination_scope": "Philippine imports",
            "reference_start": start.isoformat(), "reference_end": end.isoformat(),
            "reference_period_kind": "stated_applicability_period_not_import_observation_window",
            "issue_date": issue.isoformat(), "published_at": None,
            "memo_identifier_literal": document["memo_identifier_literal"],
            "revision_order_literal": document["revision_order_literal"], "date_note": document["date_note"],
            "tariff_heading": page.get("tariff_headings_by_row", {}).get(str(ordinal)),
            "tariff_note": "Visually reviewed row heading when supplied; otherwise unknown and not inferred from another grade.",
            "original_value": original, "original_unit": page["unit_literal"],
            "value": float(value) if value is not None else None, "value_decimal": str(value) if value is not None else None, "unit": "USD/kg",
            "missing_reason": "source_reports_NA" if value is None else None,
            "transformation": "Source NA retained as null." if value is None else "Remove dollar symbol; preserve decimal value. No currency conversion or imputation.",
            "source_url": source["url"], "artifact_sha256": source["artifact_sha256"],
            "evidence_pdf_page": page["pdf_page"], "evidence_annex_page": page["annex_page"],
            "evidence_table_row": ordinal, "evidence_image_sha256": page["image_sha256"],
            "cover_image_sha256": document["cover_image_sha256"],
            "captured_at_utc": source["captured_at_utc"],
            "review_method": review["review_method"], "review_date_local": review["review_date_local"],
            "numeric_visual_reviewed": True, "historical_availability_verified": False,
            "historical_available_at": None, "prospective_available_at": source["captured_at_utc"],
            "foodcast_grade_mapping_verified": False, "training_admitted": False,
        })
    return rows


def build(capture, ocr_root, output, review_path=HERE / "customs_reviewed_rows.json"):
    _, capture_sha, artifacts = load_capture(capture)
    review_bytes = Path(review_path).read_bytes()
    review = json.loads(review_bytes)
    if review["schema_version"] != 1:
        raise ValueError("Unknown review schema")
    rows = []
    for document in review["documents"]:
        source, _ = artifacts[document["source_id"]]
        if source["artifact_sha256"] != document["artifact_sha256"]:
            raise ValueError("Reviewed source hash mismatch")
        folder = Path(ocr_root) / document["artifact_sha256"]
        cover = checked_completed(folder / f"page_{document['cover_page']:04d}" / "page.json",
                                  source["artifact_sha256"], document["ocr_config_sha256"], document["cover_page"])
        if cover["outputs"]["page.png"] != document["cover_image_sha256"]:
            raise ValueError("Reviewed cover image changed")
        for page in document["pages"]:
            completed = checked_completed(folder / f"page_{page['pdf_page']:04d}" / "page.json",
                                          source["artifact_sha256"], document["ocr_config_sha256"], page["pdf_page"])
            if completed["outputs"]["page.png"] != page["image_sha256"]:
                raise ValueError("Reviewed annex image changed")
            rows.extend(normalize(document, page, source, review))
    keys = [r["record_id"] for r in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate reviewed record IDs")
    result = {"schema_version": 1, "capture_manifest_sha256": capture_sha,
              "review_specs_sha256": sha256(review_bytes), "builder_sha256": sha256(Path(__file__).read_bytes()),
              "records": rows, "summary": {"reviewed_rows": len(rows), "reviewed_numeric_rows": sum(r["value"] is not None for r in rows), "source_reported_missing_rows": sum(r["value"] is None for r in rows), "historically_admitted_rows": 0,
                                           "grade_mapping_verified_rows": 0}}
    write_once(Path(output), encode(result))
    return result["summary"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--ocr-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--review", type=Path, default=HERE / "customs_reviewed_rows.json")
    args = parser.parse_args()
    print(json.dumps(build(args.capture, args.ocr_root, args.output, args.review), indent=2))


if __name__ == "__main__":
    main()
