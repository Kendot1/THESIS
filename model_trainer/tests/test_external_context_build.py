"""Regression checks for provenance and meaning in the external context seeds."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from external_context.build_context import (
    HERE, ROOT, aware_time, build, document, extract_damage, extract_mapping, load_capture, sha256,
)
from external_context.inventory_customs import inventory
from external_context.build_roadmap_mapping import extract as extract_roadmap


class ExternalContextBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.capture = ROOT / "audits/external_context_20261003/capture_20261003T141356021957Z.json"
        cls.manifest, _, cls.artifacts = load_capture(cls.capture)
        cls.specs_bytes = (HERE / "da_damage_specs.json").read_bytes()
        cls.specs = json.loads(cls.specs_bytes)

    def extract(self, source_id, content=None, spec=None):
        source, original = self.artifacts[source_id]
        return extract_damage(source, original if content is None else content,
                              spec or self.specs["documents"][source_id],
                              self.specs["event_id"], sha256(self.specs_bytes))

    def test_three_distinct_cumulative_vintages(self):
        totals = []
        for source_id in self.specs["documents"]:
            rows = self.extract(source_id)
            totals.append(next(r["value"] for r in rows if r["metric"] == "damage_php"))
        self.assertEqual(totals, [53_000_000, 134_700_000, 454_100_000])

    def test_aid_allocations_not_damage(self):
        values = [r["value"] for s in self.specs["documents"] for r in self.extract(s)]
        self.assertNotIn(495_400_000, values)
        self.assertNotIn(596_500_000, values)
        self.assertNotIn(400_000_000, values)

    def test_preserves_bounds_and_approximation(self):
        rows = self.extract("da_damage_20250720")
        area = next(r for r in rows if r["metric"] == "affected_area_ha")
        self.assertEqual(area["qualifier"], "lower_bound_exclusive")
        self.assertEqual(area["value"], 2400)
        self.assertEqual(rows[0]["qualifier"], "approximate")

    def test_no_assumed_observation_cutoff_or_historical_admission(self):
        for r in self.extract("da_damage_20250724"):
            self.assertIsNone(r["reference_end"])
            self.assertIsNone(r["historical_available_at"])
            self.assertFalse(r["historical_availability_verified"])
            self.assertFalse(r["training_admitted"])
            self.assertEqual(r["prospective_available_at"], r["captured_at_utc"])

    def test_evidence_offsets_recover_exact_match(self):
        source_id = "da_damage_20250724"
        text, _ = document(self.artifacts[source_id][1])
        for r in self.extract(source_id):
            loc = r["evidence_locator"]
            self.assertEqual(text[loc["normalized_text_start"]:loc["normalized_text_end"]], r["evidence_text"])

    def test_changed_numeric_value_requires_review(self):
        content = self.artifacts["da_damage_20250720"][1].replace(b"P53 million", b"P54 million")
        with self.assertRaises(ValueError):
            self.extract("da_damage_20250720", content)

    def test_ambiguous_match_fails(self):
        source_id = "da_damage_20250720"
        content = self.artifacts[source_id][1].replace(b"</article>", b"combined damage from the storm and monsoon at around P53 million</article>")
        with self.assertRaises(ValueError):
            self.extract(source_id, content)

    def test_report_date_is_validated(self):
        spec = copy.deepcopy(self.specs["documents"]["da_damage_20250720"])
        spec["report_date"] = "2025-07-21"
        with self.assertRaises(ValueError):
            self.extract("da_damage_20250720", spec=spec)

    def test_no_naive_time(self):
        with self.assertRaises(ValueError):
            aware_time("2025-07-20T07:08:29")

    def test_mapping_never_invents_ncr_weight(self):
        r = extract_mapping(*self.artifacts["da_cordillera_mapping"])
        self.assertIsNone(r["weight"])
        self.assertEqual(r["foodcast_product_ids"], [])
        self.assertFalse(r["ncr_supply_relationship_verified"])

    def test_build_is_repeatable_and_missingness_is_explicit(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as directory:
            out = Path(directory) / "build"
            coverage = build(self.capture, out)
            first = {p.name: p.read_bytes() for p in out.iterdir()}
            build(self.capture, out)
            self.assertEqual(first, {p.name: p.read_bytes() for p in out.iterdir()})
            self.assertEqual(coverage["normalized_observations"], 17)
            self.assertEqual(coverage["historically_admitted_observations"], 0)
            self.assertEqual(coverage["capture_status_counts"], {"archived": 4, "acquisition_failed": 1})
            self.assertEqual(coverage["missing_reference_cutoffs"], 17)

    def test_existing_outputs_are_preserved(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as directory:
            out = Path(directory) / "build"
            out.mkdir()
            path = out / "observations.json"
            path.write_text("reviewed existing result", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                build(self.capture, out)
            self.assertEqual(path.read_text(encoding="utf-8"), "reviewed existing result")
            self.assertEqual(len(list(out.iterdir())), 1)

    def test_tampered_source_and_path_escape_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as directory:
            root = Path(directory)
            manifest = copy.deepcopy(self.manifest)
            manifest["records"] = [manifest["records"][0]]
            source = manifest["records"][0]
            source["artifact_file"] = "source.html"
            (root / "source.html").write_bytes(b"tampered")
            path = root / "capture.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash/length"):
                load_capture(path)
            source["artifact_file"] = "../outside.html"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "within archive"):
                load_capture(path)


class ExternalDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.source = {"url": "https://customs.gov.ph/memoranda-for-reference-values/",
                       "artifact_sha256": "a" * 64, "captured_at_utc": "2026-10-03T17:31:22+00:00"}

    def table(self, rows):
        return ("<table><tr><th>YEAR</th><th>SUBJECT</th><th>DATE OF ISSUANCE</th><th>DOWNLOAD</th></tr>" + rows + "</table>").encode()

    def row(self, subject="Shipments of Rice", url="https://customs.gov.ph/a.pdf"):
        return f'<tr><td>2025</td><td>{subject}</td><td>December 23, 2024 - December 29, 2024</td><td><a href="{url}">Download</a></td></tr>'

    def test_duplicate_urls_do_not_duplicate_documents(self):
        r = inventory(self.source, self.table(self.row() * 2))
        self.assertEqual(r["unique_documents"], 1)
        self.assertEqual(r["duplicate_url_occurrences"], 1)
        self.assertEqual(len(r["documents"][0]["occurrences"]), 2)

    def test_year_range_never_becomes_publication_date(self):
        r = inventory(self.source, self.table(self.row()))["documents"][0]
        self.assertIsNone(r["publication_at"])
        self.assertFalse(r["reference_period_verified"])
        self.assertFalse(r["historical_availability_verified"])
        self.assertEqual(r["occurrences"][0]["year_literal"], "2025")
        self.assertIn("2024", r["occurrences"][0]["date_of_issuance_literal"])

    def test_nonfood_reference_is_not_rice(self):
        result = inventory(self.source, self.table(self.row(subject="Reference Values for Resin")))
        self.assertEqual(result["rice_candidate_documents"], 0)

    def test_external_downloads_are_quarantined(self):
        result = inventory(self.source, self.table(self.row(url="https://example.com/a.pdf")))
        self.assertEqual(result["unique_documents"], 0)
        self.assertEqual(result["skipped_rows"][0]["reason"], "unexpected_download_url")

    def test_conflicting_duplicate_subject_is_not_rice_candidate(self):
        result = inventory(self.source, self.table(self.row() + self.row(subject="Resin")))
        self.assertEqual(result["rice_candidate_documents"], 0)

    def test_roadmap_changes_require_review(self):
        with self.assertRaises(ValueError):
            extract_roadmap(self.source, "Unverified new roadmap page")


if __name__ == "__main__":
    unittest.main()
