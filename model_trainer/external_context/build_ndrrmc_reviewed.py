"""Build the visually reviewed Ilocos Norte crop rows from a pinned PDF vintage."""
import argparse
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re


def extract(page, spec):
    if f"as of ({spec['as_of_literal']})" not in page:
        raise ValueError("Reference time mismatch")
    if page.count("ILOCOS NORTE") != 1 or page.count("ILOCOS SUR") != 1:
        raise ValueError("Ambiguous province boundaries")
    block = page.split("ILOCOS NORTE", 1)[1].split("ILOCOS SUR", 1)[0]
    if "No breakdown" not in block:
        raise ValueError("Province scope differs")
    number = r"([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)"
    rows = []
    keys = ["affected_farmers_fisherfolk", "area_totally_damaged_ha", "area_partially_damaged_ha",
            "affected_area_ha", "production_loss_mt", "production_loss_or_damage_php"]
    for expected in spec["rows"]:
        label = "High Value" if expected["commodity"] == "High Value Crops" else expected["commodity"]
        pattern = r"Crops[ \t]+"+re.escape(label)+r"[ \t]+"+r"[ \t]+".join([number]*9)
        matches = list(re.finditer(pattern, block))
        if len(matches) != 1:
            raise ValueError("Expected one exact crop row: " + label)
        match = matches[0]
        if label == "High Value" and not re.match(r"\s+Crops\b", block[match.end():]):
            raise ValueError("High Value continuation missing")
        values = [Decimal(s.replace(",", "")) for s in match.groups()]
        if values[4:7] != [Decimal(0)]*3:
            raise ValueError("Unexpected infrastructure counts")
        selected = values[:4]+values[7:]
        if any(value != Decimal(str(expected[key])) for key,value in zip(keys, selected)):
            raise ValueError("Reviewed number mismatch")
        if values[1]+values[2] != values[3]:
            raise ValueError("Affected-area arithmetic mismatch")
        rows.append({**expected, "original_row_text":match.group(),
                     "original_numeric_tokens":list(match.groups())})
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", type=Path, required=True)
    p.add_argument("--spec", type=Path, default=Path(__file__).with_name("ndrrmc_reviewed_specs.json"))
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    spec = json.loads(args.spec.read_text())
    index = json.loads((args.base / "text_v1/index.json").read_text())
    verified_file = args.base / "verified_replays_v1.json"
    if hashlib.sha256(verified_file.read_bytes()).hexdigest() != index["verified_archive_sha256"]:
        raise ValueError("Verified archive changed")
    sources = [r for r in json.loads(verified_file.read_text())["records"] if r["document_id"] == spec["document_id"]]
    entries = [r for r in index["records"] if r["document_id"] == spec["document_id"]]
    if len(sources) != 1 or len(entries) != 1:
        raise ValueError("Expected unique source vintage")
    source, entry = sources[0], entries[0]
    if not source["historical_availability_verified"] or source["decoded_archive_sha256"] != spec["pdf_sha256"]:
        raise ValueError("Historical source mismatch")
    pdf = (args.base / source["pdf_file"]).read_bytes()
    text = (args.base / entry["text_file"]).read_bytes()
    if hashlib.sha256(pdf).hexdigest() != spec["pdf_sha256"] or hashlib.sha256(text).hexdigest() != spec["text_sha256"]:
        raise ValueError("Pinned PDF/text integrity failure")
    page = text.decode("utf-8").split("\f")[spec["physical_page"]-1]
    rows = extract(page, spec)
    age = (date.fromisoformat(source["available_at_utc"][:10])-date.fromisoformat(spec["reference_date"])).days
    if age < 0:
        raise ValueError("Reference after availability")
    result = {"schema_version":1, "review_spec_sha256":hashlib.sha256(args.spec.read_bytes()).hexdigest(),
              "source":source, "reference_date":spec["reference_date"], "as_of_literal":spec["as_of_literal"],
              "geography":spec["geography"], "physical_page":spec["physical_page"],
              "printed_page":spec["printed_page"], "scope_note":spec["scope_note"],
              "age_days_at_first_verified_availability":age, "rows":rows,
              "training_admitted":False,
              "missingness_note":"These three cumulative crop rows do not imply zero damage for unlisted crops or days."}
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps({"rows":len(rows), "numeric_values":len(rows)*6, "age_days_at_availability":age,
                      "available_at_utc":source["available_at_utc"], "training_admitted":False}))


if __name__ == "__main__":
    main()
