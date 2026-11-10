"""Review policy-12, multi-origin independent-horizon promotion evidence.

This verifies hashes, chronology, reproducible scoring, and a predeclared
matched performance screen. Human provenance attestations are not proof that
forecast generation was causal or future labels were never viewed.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from .frozen_holdout import digest, relative_file
from .prospective_admission import screen
from .prospective_freeze import (
    ACCEPTANCE_CRITERIA, POLICY_VERSION, verify_seal,
)
from .prospective_horizons import _timestamp, load_contract, score
from .prospective_validation import compare_validation

REVIEW_FLAGS = (
    "selection_provenance_checked", "source_snapshot_provenance_checked",
    "forecast_replay_checked", "actuals_provenance_checked",
    "holdout_not_used_for_selection", "interval_width_reviewed",
)


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _reference(parent, item):
    path = relative_file(parent, item["file"])
    if digest(path.read_bytes()) != item["sha256"]:
        raise ValueError(f"Reviewed evidence hash mismatch: {item['file']}")
    return path


def verify_promotion_evidence(run_dir, evidence_dir, *, now=None):
    """Return a receipt only for closed, reproducible 14/4/1 vintages."""
    run_dir, evidence_dir = Path(run_dir), Path(evidence_dir)
    now = datetime.now(timezone.utc) if now is None else now
    if now.tzinfo is None:
        raise ValueError("Promotion clock requires a timezone")
    review_path = evidence_dir / "promotion_review.json"
    review = _read_json(review_path)
    if (review.get("schema_version") != 2
            or review.get("promotion_policy_version") != POLICY_VERSION
            or review.get("model_run_id") != run_dir.name):
        raise ValueError("Unknown policy-12 review or candidate model")
    if not str(review.get("reviewed_by", "")).strip():
        raise ValueError("An identified provenance reviewer is required")
    reviewed_at = _timestamp(review["reviewed_at"])
    if reviewed_at > now:
        raise ValueError("Promotion review is dated in the future")
    if any(review.get(flag) is not True for flag in REVIEW_FLAGS):
        raise ValueError("Promotion provenance and interval-width review is incomplete")
    packages = review.get("packages")
    if (not isinstance(packages, list)
            or len(packages) < ACCEPTANCE_CRITERIA["minimum_prospective_origins"]):
        raise ValueError("Policy 12 requires at least three prospective vintages")
    opened = []
    seen_dirs, seen_origins = set(), set()
    selected_records, monthly_targets = set(), set()
    period_keys = {"daily": set(), "weekly": set(), "monthly": set()}
    # All prospective windows must close before even opening an actuals manifest.
    for package in packages:
        directory = relative_file(evidence_dir, package["directory"])
        if not directory.is_dir() or directory in seen_dirs:
            raise ValueError("Duplicate or missing prospective evidence directory")
        seen_dirs.add(directory)
        contract_path = _reference(directory, package["contract"])
        if contract_path.name != "contract.json":
            raise ValueError("Package must reference its sealed contract.json")
        seal_receipt = verify_seal(contract_path, run_dir)
        contract, forecasts, integrity = load_contract(contract_path)
        origin = contract["forecast_origin"]
        if origin in seen_origins:
            raise ValueError("Duplicate prospective forecast origin")
        seen_origins.add(origin)
        selected = _read_json(directory / "selection.json")
        if selected.get("acceptance_criteria") != ACCEPTANCE_CRITERIA:
            raise ValueError("Selection did not predeclare policy-12 acceptance criteria")
        selected_records.add((selected["selected_at"], selected["validation_forecasts_sha256"],
                              selected["model_metadata_sha256"],
                              tuple(selected["declared_series"])))
        for row in forecasts.values():
            key = (row["series"], row["target_period_start"], row["target_period_end"])
            horizon = row["forecast_horizon"]
            if key in period_keys[horizon]:
                raise ValueError("Prospective vintages reuse a target period")
            period_keys[horizon].add(key)
            if horizon == "monthly":
                monthly_targets.add(row["target_period_start"])
        if now < _timestamp(integrity["period_closes_at"]):
            raise ValueError("A prospective period is still open; actuals were not opened")
        opened.append((directory, package, contract, integrity, seal_receipt))
    if len(selected_records) != 1 or len(monthly_targets) < len(packages):
        raise ValueError("Selection or independent monthly target periods differ across vintages")
    declared_series = list(next(iter(selected_records))[3])
    # Validate the same pre-selection comparison, then recompute every final score.
    first_dir = opened[0][0]
    first_selection = _read_json(first_dir / "selection.json")
    validation_path = relative_file(first_dir, first_selection["validation_forecasts_file"])
    validation = compare_validation(validation_path, first_selection)
    final_rows, package_receipts = [], []
    for directory, package, contract, integrity, seal_receipt in opened:
        actuals_path = _reference(directory, package["actuals_manifest"])
        score_path = _reference(directory, package["score_report"])
        recorded = _read_json(score_path)
        scored_at = _timestamp(recorded["scored_at_utc"])
        if not _timestamp(integrity["period_closes_at"]) <= scored_at <= reviewed_at:
            raise ValueError("Saved scoring and review chronology is invalid")
        recomputed = score(directory / "contract.json", actuals_path,
                           now=now, include_rows=True)
        rows = recomputed.pop("matched_rows")
        if ({key: value for key, value in recorded.items() if key != "scored_at_utc"}
                != {key: value for key, value in recomputed.items() if key != "scored_at_utc"}):
            raise ValueError("Saved 14/4/1 score does not reproduce from sealed inputs")
        final_rows.extend(rows)
        package_receipts.append({"origin": contract["forecast_origin"],
                                 "contract_sha256": seal_receipt["contract_sha256"],
                                 "score_sha256": digest(score_path.read_bytes()),
                                 "scored_rows": len(rows)})
    decision = screen(validation, final_rows, declared_series)
    return {"promotion_policy_version": POLICY_VERSION,
            "review_sha256": digest(review_path.read_bytes()),
            "model_metadata_sha256": next(iter(selected_records))[2],
            "packages": package_receipts, "screen": decision,
            "verified_at_utc": now.astimezone(timezone.utc).isoformat()}
