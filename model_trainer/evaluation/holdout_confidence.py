"""Compare frozen confidence scores with one scored prospective holdout report.

This post-close diagnostic reads only the finalized score report, frozen
contract/forecast, model bundle metadata, and pre-holdout confidence profile.
It does not open the actuals manifest or observations, change any score, or
write model outputs.
"""
import argparse
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path
from statistics import fmean

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "model_trainer"))

from evaluation.frozen_holdout import digest, load_contract
from evaluation.product_confidence import METHOD, level


TIMEFRAMES = ("daily", "weekly", "monthly")


def _finite_number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def _validated_score(metric):
    if (not isinstance(metric, dict) or metric.get("evidence_status") != "validated"
            or metric.get("confidence_method") != METHOD):
        return None
    value = metric.get("confidence_score")
    return float(value) if _finite_number(value) and 0 <= value <= 100 else None


def _aggregate(observations):
    if not observations:
        return {"n": 0, "mean_confidence_score": None,
                "mean_holdout_accuracy_score": None, "mean_signed_error_points": None,
                "mean_absolute_error_points": None}
    confidence = [row["confidence_score"] for row in observations]
    realized = [row["holdout_accuracy_score"] for row in observations]
    signed = [row["signed_error_points"] for row in observations]
    return {
        "n": len(observations),
        "mean_confidence_score": fmean(confidence),
        "mean_holdout_accuracy_score": fmean(realized),
        "mean_signed_error_points": fmean(signed),
        "mean_absolute_error_points": fmean(abs(value) for value in signed),
    }


def _compare_horizon(profile, timeframe_report, timeframe):
    confidence = profile["product_confidence_by_identity"]
    holdout = timeframe_report.get("series", {})
    observations = []
    counts = {"profile_identities": len(confidence), "holdout_series": len(holdout),
              "validated_confidence": 0, "holdout_series_with_mape": 0,
              "matched_with_confidence_and_mape": 0,
              "insufficient_confidence": 0, "missing_holdout_series": 0,
              "missing_holdout_mape": 0}
    for identity, entry in confidence.items():
        metric = entry.get("confidence_by_horizon", {}).get(timeframe, {})
        score = _validated_score(metric)
        if score is None:
            counts["insufficient_confidence"] += 1
        else:
            counts["validated_confidence"] += 1
        outcome = holdout.get(identity)
        if outcome is None:
            counts["missing_holdout_series"] += 1
            continue
        mape = outcome.get("mape")
        if not _finite_number(mape) or mape < 0:
            counts["missing_holdout_mape"] += 1
            continue
        counts["holdout_series_with_mape"] += 1
        if score is None:
            continue
        counts["matched_with_confidence_and_mape"] += 1
        realized = 100.0 - float(mape)
        observations.append({
            "confidence_score": score,
            "holdout_mape_pct": float(mape),
            "holdout_accuracy_score": realized,
            "signed_error_points": score - realized,
        })
    return {"counts": counts, "aggregate": _aggregate(observations),
            "by_confidence_level": _by_level(observations)}


def _compare_steps(profile, timeframe_report, timeframe):
    confidence = profile["product_confidence_by_identity"]
    outcomes = timeframe_report.get("series_forecast_step")
    if not isinstance(outcomes, dict):
        raise ValueError("Scored report lacks per-series forecast-step metrics; use the updated scorer")
    observations = []
    counts = {"profile_series": len(confidence), "profile_step_metrics": 0,
              "validated_confidence": 0, "holdout_series_steps": sum(len(v) for v in outcomes.values()),
              "holdout_series_steps_with_mape": 0,
              "matched_with_confidence_and_mape": 0, "insufficient_confidence": 0,
              "missing_holdout_step": 0, "missing_holdout_mape": 0}
    for identity, entry in confidence.items():
        profile_steps = entry.get("confidence_by_step", {}).get(timeframe, {})
        for step, metric in profile_steps.items():
            counts["profile_step_metrics"] += 1
            score = _validated_score(metric)
            if score is None:
                counts["insufficient_confidence"] += 1
            else:
                counts["validated_confidence"] += 1
            outcome = outcomes.get(identity, {}).get(str(step))
            if outcome is None:
                counts["missing_holdout_step"] += 1
                continue
            mape = outcome.get("mape")
            if not _finite_number(mape) or mape < 0:
                counts["missing_holdout_mape"] += 1
                continue
            counts["holdout_series_steps_with_mape"] += 1
            if score is None:
                continue
            counts["matched_with_confidence_and_mape"] += 1
            realized = 100.0 - float(mape)
            observations.append({
                "confidence_score": score,
                "holdout_mape_pct": float(mape),
                "holdout_accuracy_score": realized,
                "signed_error_points": score - realized,
            })
    return {"counts": counts, "aggregate": _aggregate(observations),
            "by_confidence_level": _by_level(observations)}


def _by_level(observations):
    groups = {name: [] for name in ("Very High", "High", "Moderate", "Low", "Very Low")}
    for row in observations:
        groups[level(row["confidence_score"])].append(row)
    return {name: _aggregate(rows) for name, rows in groups.items() if rows}


def evaluate(contract_path, report_path, profile_path):
    contract, _, integrity = load_contract(contract_path)
    report_path, profile_path = Path(report_path), Path(profile_path)
    report_bytes, profile_bytes = report_path.read_bytes(), profile_path.read_bytes()
    report, profile = json.loads(report_bytes), json.loads(profile_bytes)

    if report.get("schema_version") != 1:
        raise ValueError("Unsupported frozen-holdout report schema")
    if report.get("model_run_id") != contract.get("model_run_id"):
        raise ValueError("Scored report and contract model run IDs differ")
    if report.get("holdout_type") != contract.get("holdout_type"):
        raise ValueError("Scored report and contract holdout types differ")
    if (report.get("holdout_start") != contract.get("holdout_start")
            or report.get("holdout_end") != contract.get("holdout_end")):
        raise ValueError("Scored report and contract dates differ")
    report_integrity = report.get("integrity", {})
    for key in ("contract_sha256", "forecast_sha256"):
        if report_integrity.get(key) != integrity[key]:
            raise ValueError(f"Scored report {key} does not match the frozen contract")
    for key in ("actuals_manifest_sha256", "actuals_sha256"):
        if not isinstance(report.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", report[key]):
            raise ValueError(f"Scored report is missing a valid {key}")
    scored_at = datetime.fromisoformat(report["scored_at_utc"])
    close_at = datetime.fromisoformat(integrity["period_closes_at"])
    if scored_at.tzinfo is None or close_at.tzinfo is None or scored_at < close_at:
        raise ValueError("Scored report timestamp is missing a timezone or precedes close")
    if profile.get("model_run_id") != contract.get("model_run_id"):
        raise ValueError("Confidence profile and contract model run IDs differ")
    if profile.get("confidence_method") != METHOD:
        raise ValueError("Confidence profile method is unsupported")
    if (profile.get("profile_schema_version") != 1
            or profile.get("profile_status") != "development_validated_with_selection_reuse"
            or profile.get("evaluation_source") != "chronological_development_test"
            or profile.get("development_test_reused_for_selection") is not True):
        raise ValueError("Confidence profile is not the expected pre-holdout development-test profile")
    bundle_root = ROOT / "model_trainer" / "artifacts_v2" / "runs"
    bundle_path = (bundle_root / contract["model_run_id"]).resolve()
    if not bundle_path.is_relative_to(bundle_root.resolve()):
        raise ValueError("Contract model run ID points outside the model bundle store")
    metadata_bytes = (bundle_path / "metadata.json").read_bytes()
    metadata = json.loads(metadata_bytes)
    ensemble_bytes = (bundle_path / "ensemble.json").read_bytes()
    if (profile.get("data_fingerprint") != metadata.get("data_fingerprint")
            or profile.get("model_metadata_sha256") != digest(metadata_bytes)
            or profile.get("ensemble_sha256") != digest(ensemble_bytes)):
        raise ValueError("Confidence profile hashes do not match the frozen model bundle")
    if not isinstance(profile.get("product_confidence_by_identity"), dict):
        raise ValueError("Confidence profile is missing product identity scores")
    timeframes = report.get("timeframes")
    if not isinstance(timeframes, dict) or any(name not in timeframes for name in TIMEFRAMES):
        raise ValueError("Scored report is missing one or more published timeframes")

    result = {
        "analysis_schema_version": 1,
        "analysis_type": "read_only_holdout_confidence_reliability",
        "model_run_id": contract["model_run_id"],
        "holdout_start": contract["holdout_start"],
        "holdout_end": contract["holdout_end"],
        "scored_at_utc": report["scored_at_utc"],
        "contract_sha256": integrity["contract_sha256"],
        "forecast_sha256": integrity["forecast_sha256"],
        "score_report_sha256": digest(report_bytes),
        "confidence_profile_sha256": digest(profile_bytes),
        "model_metadata_sha256": digest(metadata_bytes),
        "ensemble_sha256": digest(ensemble_bytes),
        "confidence_method": METHOD,
        "confidence_source": profile["evaluation_source"],
        "development_test_reused_for_selection": profile.get("development_test_reused_for_selection"),
        "full_declared_scope_observed": report.get("full_declared_scope_observed"),
        "score_report_coverage": report.get("coverage"),
        "holdout_outcomes_used_only_as_reported_metrics": True,
        "confidence_scores_modified": False,
        "by_timeframe": {},
    }
    for timeframe in TIMEFRAMES:
        timeframe_report = timeframes[timeframe]
        result["by_timeframe"][timeframe] = {
            "product_horizon": _compare_horizon(profile, timeframe_report, timeframe),
            "product_step": _compare_steps(profile, timeframe_report, timeframe),
        }
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", required=True, help="Frozen contract JSON")
    parser.add_argument("--scored-report", required=True,
                        help="Finalized frozen-holdout score report JSON")
    parser.add_argument("--profile", required=True, help="Hash-bound confidence profile JSON")
    parser.add_argument("--output", help="Optional new JSON artifact path; existing files are preserved")
    args = parser.parse_args(argv)
    payload = json.dumps(evaluate(args.contract, args.scored_report, args.profile),
                         indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
