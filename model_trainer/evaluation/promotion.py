"""Verify reviewed final evidence before changing a local model pointer.

Hashes bind artifacts; reviewer attestations document provenance review, not
cryptographic proof that a person never inspected future outcomes.
"""
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

from .frozen_holdout import METRICS, PHILIPPINE_TIME, calendar_date, error_metrics, load_contract, relative_file, score

COMPONENTS = {"categorical_mappings.json", "lightgbm_model.txt", "lightgbm_meta.json",
              "lstm_model.pt", "lstm_meta.json", "ensemble.json"}
POLICY_VERSION = 2
VALIDATION_METRICS = ("within_10_accuracy_pct", *METRICS)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def timestamp(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Promotion timestamps require a timezone")
    return parsed


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def validation_comparison(path, holdout_start):
    """Recompute four matched metrics and stability across chronological origins."""
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"series", "origin", "target_date", "actual", "prediction", "champion", "anchor"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("Validation CSV lacks matched candidate/champion/persistence columns")
        rows, keys, by_origin = [], set(), {}
        for row in reader:
            origin, target = calendar_date(row["origin"]), calendar_date(row["target_date"])
            if not origin < target < holdout_start:
                raise ValueError("Validation overlaps holdout or uses a nonfuture target")
            key = (row["series"], origin, target)
            if key in keys:
                raise ValueError("Duplicate matched validation key")
            keys.add(key)
            for column in ("actual", "prediction", "champion", "anchor"):
                row[column] = float(row[column])
                if not math.isfinite(row[column]) or row[column] <= 0:
                    raise ValueError("Invalid validation price")
            rows.append(row)
            by_origin.setdefault(row["origin"], []).append(row)
    if len(by_origin) < 3:
        raise ValueError("Stable improvement requires at least three validation origins")

    def better(block):
        candidate = error_metrics(block)
        for reference in ("champion", "anchor"):
            baseline = error_metrics(block, reference)
            for key in VALIDATION_METRICS:
                if candidate[key] is None or baseline[key] is None:
                    return False
                if key == "within_10_accuracy_pct":
                    if candidate[key] <= baseline[key]:
                        return False
                elif candidate[key] >= baseline[key]:
                    return False
        return True

    wins = sum(better(block) for block in by_origin.values())
    if not better(rows) or wins < math.ceil(2 * len(by_origin) / 3):
        raise ValueError("Candidate lacks stable matched improvement on all four metrics")
    return {"origins": len(by_origin), "origins_improving_all_metrics": wins,
            "candidate": error_metrics(rows), "champion": error_metrics(rows, "champion"),
            "persistence": error_metrics(rows, "anchor")}


def verify_promotion_evidence(run_dir, evidence_dir, *, now=None):
    run_dir, evidence_dir = Path(run_dir), Path(evidence_dir)
    if not evidence_dir.is_dir():
        raise ValueError("A reviewed final-evidence directory is required for activation")
    now = datetime.now(timezone.utc) if now is None else now
    if now.tzinfo is None:
        raise ValueError("Promotion clock requires a timezone")
    review_path = evidence_dir / "promotion_review.json"
    review = read_json(review_path)
    if review.get("schema_version") != 1 or review.get("model_run_id") != run_dir.name:
        raise ValueError("Promotion review names a different model or schema")
    if review.get("promotion_policy_version") != POLICY_VERSION:
        raise ValueError("Promotion review uses an unknown policy version")
    if not str(review.get("reviewed_by", "")).strip():
        raise ValueError("Promotion requires an identified provenance reviewer")
    reviewed_at = timestamp(review["reviewed_at"])
    if reviewed_at > now:
        raise ValueError("Promotion review is dated in the future")
    for field in ("selection_provenance_checked", "actuals_provenance_checked", "holdout_not_used_for_selection"):
        if review.get(field) is not True:
            raise ValueError(f"Missing provenance review: {field}")
    paths = {}
    for name in ("contract", "actuals_manifest", "score_report", "selection_record", "validation_forecasts"):
        reference = review[name]
        path = relative_file(evidence_dir, reference["file"])
        # Do not read actuals or their manifest before checking the closed period.
        paths[name] = path
        if name not in {"actuals_manifest", "score_report"} and digest(path) != reference["sha256"]:
            raise ValueError(f"Promotion evidence hash mismatch: {name}")
    contract, _, integrity = load_contract(paths["contract"])
    if now < timestamp(integrity["period_closes_at"]):
        raise ValueError("Holdout still open; promotion actuals were not opened")
    if contract["model_run_id"] != run_dir.name:
        raise ValueError("Final forecasts belong to another model")
    if contract["holdout_type"] != "prospective" or not integrity["frozen_before_first_target_day"]:
        raise ValueError("Promotion requires forecasts frozen before a prospective period")
    if contract["horizon_days"] != 30 or integrity["series_coverage"] != 1:
        raise ValueError("Promotion requires complete declared 30-day forecast coverage")
    hashes = contract.get("model_bundle_sha256", {})
    if set(hashes) != COMPONENTS or any(digest(run_dir / name) != expected for name, expected in hashes.items()):
        raise ValueError("Frozen forecast model components do not match candidate")
    metadata_hash = digest(run_dir / "metadata.json")
    if contract.get("model_metadata_sha256") != metadata_hash:
        raise ValueError("Frozen model metadata does not match candidate")
    selection = read_json(paths["selection_record"])
    if selection.get("promotion_policy_version") != POLICY_VERSION:
        raise ValueError("Promotion policy was not recorded at model selection")
    if (contract.get("selection_record_sha256") != digest(paths["selection_record"])
            or selection.get("model_metadata_sha256") != metadata_hash
            or selection.get("model_run_id") != run_dir.name
            or selection.get("validation_forecasts_sha256") != digest(paths["validation_forecasts"])):
        raise ValueError("Selection record is not bound to the candidate and validation")
    frozen_at = timestamp(contract["forecasts_frozen_at_utc"])
    selected_at = timestamp(selection["selected_at"])
    if not timestamp(read_json(run_dir / "metadata.json")["created_at"]) <= selected_at <= frozen_at <= reviewed_at:
        raise ValueError("Selection, freeze and review chronology is invalid")
    _, predictions, _ = load_contract(paths["contract"])
    declared = selection.get("declared_series", [])
    if len(declared) != len(set(declared)) or set(declared) != {key[0] for key in predictions}:
        raise ValueError("Selection and forecast populations differ")
    validation = validation_comparison(paths["validation_forecasts"],
                                      min(calendar_date(contract["holdout_start"]), selected_at.astimezone(PHILIPPINE_TIME).date()))
    if digest(paths["actuals_manifest"]) != review["actuals_manifest"]["sha256"]:
        raise ValueError("Promotion evidence hash mismatch: actuals_manifest")
    if digest(paths["score_report"]) != review["score_report"]["sha256"]:
        raise ValueError("Promotion evidence hash mismatch: score_report")
    recorded = read_json(paths["score_report"])
    if not timestamp(integrity["period_closes_at"]) <= timestamp(recorded["scored_at_utc"]) <= reviewed_at:
        raise ValueError("Review predates final scoring")
    recomputed = score(paths["contract"], paths["actuals_manifest"], now=now)
    # Wall-clock evaluation time changes; every data-derived field must agree.
    expected = {k: v for k, v in recorded.items() if k != "scored_at_utc"}
    actual = {k: v for k, v in recomputed.items() if k != "scored_at_utc"}
    if actual != expected:
        raise ValueError("Saved final report does not reproduce from sealed inputs")
    if not recomputed["target_met_for_full_declared_scope"]:
        raise ValueError("Final holdout fails the metric target or declared coverage")
    persistence = recomputed["persistence_on_same_rows"]
    if (recomputed["overall"]["within_10_accuracy_pct"]
            < persistence["within_10_accuracy_pct"]
            or not all(recomputed["overall"][k] < persistence[k] for k in METRICS)):
        raise ValueError("Final candidate does not improve on matched persistence")
    return {"review_sha256": digest(review_path), "model_metadata_sha256": metadata_hash,
            "contract_sha256": integrity["contract_sha256"],
            "forecast_sha256": integrity["forecast_sha256"],
            "score_report_sha256": digest(paths["score_report"]),
            "validation": validation, "verified_at_utc": now.astimezone(timezone.utc).isoformat()}
