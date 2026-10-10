"""Audit saved chronological validation rows and observed-date period summaries."""
import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from statistics import mean

from evaluation.product_confidence import (
    _period_bounds, _period_step, validation_confidence,
)

PERCENTAGE_ACTUAL_FLOOR = 1e-8
WITHIN_10_TOLERANCE = 0.10


def metrics(rows):
    valid, invalid_count = [], 0
    for row in rows:
        try:
            actual, predicted = float(row["actual"]), float(row["ensemble"])
        except (KeyError, TypeError, ValueError):
            invalid_count += 1
            continue
        if not math.isfinite(actual) or not math.isfinite(predicted) or actual < 0:
            invalid_count += 1
            continue
        valid.append((actual, predicted, bool(row.get("partial_period", False))))

    errors = [abs(predicted - actual) for actual, predicted, _ in valid]
    percentage_errors = [abs(predicted - actual) / actual
                         for actual, predicted, _ in valid
                         if actual >= PERCENTAGE_ACTUAL_FLOOR]
    hits = sum(error <= WITHIN_10_TOLERANCE for error in percentage_errors)
    return {
        "n": len(valid),
        "within_10_count": hits,
        "percentage_n": len(percentage_errors),
        "excluded_near_zero": len(valid) - len(percentage_errors),
        "excluded_invalid": invalid_count,
        "mae": mean(errors) if errors else None,
        "rmse": math.sqrt(mean(error * error for error in errors)) if errors else None,
        "mape": mean(percentage_errors) * 100 if percentage_errors else None,
        "partial_periods": sum(partial for _, _, partial in valid),
    }


def table(rows):
    score = metrics(rows)
    if not score["n"]:
        return "0 | n/a | n/a | n/a | n/a | 0"
    if score["percentage_n"]:
        accuracy = (f"{score['within_10_count']}/{score['percentage_n']} "
                    f"({score['within_10_count'] / score['percentage_n'] * 100:.2f}%; "
                    f"{score['excluded_near_zero']} near-zero excluded)")
        mape = f"{score['mape']:.3f}%"
    else:
        accuracy = f"n/a (0 eligible; {score['excluded_near_zero']} near-zero excluded)"
        mape = "n/a"
    return (f"{score['n']} | {accuracy} | {score['mae']:.3f} | "
            f"{score['rmse']:.3f} | {mape} | {score['partial_periods']}")


def sequence_rows(rows):
    result = {"daily": [], "weekly": [], "monthly": []}
    periods = defaultdict(list)
    for row in rows:
        origin = date.fromisoformat(row["origin"][:10])
        target = date.fromisoformat(row["date"][:10])
        row = {**row, "forecast_step": int(row["horizon"])}
        result["daily"].append(row)
        for horizon in ("weekly", "monthly"):
            start, end = _period_bounds(target, horizon)
            periods[(row["series"], origin, horizon, start, end)].append(
                (float(row["actual"]), float(row["ensemble"]), target))
    for (series, origin, horizon, start, end), samples in periods.items():
        result[horizon].append({
            "series": series,
            "origin": origin.isoformat(),
            "date": end.isoformat(),
            "forecast_step": _period_step(origin, start, horizon),
            "actual": mean(sample[0] for sample in samples),
            "ensemble": mean(sample[1] for sample in samples),
            "covered_days": len({sample[2] for sample in samples}),
            "period_days": (end - start).days + 1,
            "partial_period": len({sample[2] for sample in samples}) < (end - start).days + 1,
        })
    return result


def audit(bundle):
    with (bundle / "validation_forecasts.csv").open(newline="", encoding="utf-8") as stream:
        raw_rows = list(csv.DictReader(stream))
    rows, invalid_count = [], 0
    for row in raw_rows:
        try:
            actual, predicted = float(row["actual"]), float(row["ensemble"])
        except (KeyError, TypeError, ValueError):
            invalid_count += 1
            continue
        if not math.isfinite(actual) or not math.isfinite(predicted) or actual < 0:
            invalid_count += 1
            continue
        rows.append({**row, "actual": actual, "ensemble": predicted})
    identities = {tuple(row["series"].split("||")): row["series"] for row in rows}
    confidence = validation_confidence(bundle, identities)
    confidence_metrics = []
    for product in confidence.values():
        confidence_metrics.extend(product["confidence_by_horizon"].values())
        confidence_metrics.extend(metric for horizon in product["confidence_by_step"].values()
                                  for metric in horizon.values())
    evidence_counts = Counter(metric["evidence_status"] for metric in confidence_metrics)
    sequences = sequence_rows(rows)

    lines = [
        f"## {bundle.name}", "",
        "Saved chronological validation. These diagnostic rows include model-selection data;",
        "they are not independent final-holdout evidence.", "",
        "Weekly/monthly rows below are observed-date diagnostic reconstructions from the saved",
        "daily validation rows; they are not exact published period predictions because the",
        "validation CSV omits forecasts on dates without observed labels. Partial periods are",
        "retained and counted. MAE/RMSE use all finite nonnegative actual prices.",
        f"Zero/near-zero actuals (<{PERCENTAGE_ACTUAL_FLOOR:g} PHP) are excluded only from "
        "Within-10% accuracy and MAPE. Invalid rows excluded from all metrics: "
        f"{invalid_count} of {len(raw_rows)}.", "",
        "Daily metrics below cover all saved validation lead steps. Weekly/monthly metrics use",
        "the observed-date reconstructions described above.",
        "| Target statistic | Samples (PHP errors) | Within-10% hits / eligible (near-zero excluded) | MAE (PHP) | RMSE (PHP) | MAPE | Partial periods |",
        "|---|---:|---|---:|---:|---:|---:|",
    ]
    for horizon, label in (
        ("daily", "Daily price at every forecast step (saved rows)"),
        ("weekly", "Observed-date weekly mean (Monday-Sunday; reconstructed)"),
        ("monthly", "Observed-date monthly mean (reconstructed)"),
    ):
        lines.append(f"| {label} | {table(sequences[horizon])} |")
    lines += [
        "", f"Confidence evidence status (product x horizon and step): `{dict(evidence_counts)}`.",
        "", "### Performance by forecast step", "",
        "| Horizon | Step | Samples (PHP errors) | Within-10% hits / eligible (near-zero excluded) | MAE (PHP) | RMSE (PHP) | MAPE | Partial periods |",
        "|---|---:|---:|---|---:|---:|---:|---:|",
    ]
    for horizon, selected_horizon in sequences.items():
        by_step = defaultdict(list)
        for row in selected_horizon:
            by_step[row["forecast_step"]].append(row)
        for step, selected in sorted(by_step.items()):
            lines.append(f"| {horizon} | {step} | {table(selected)} |")

    by_product = defaultdict(list)
    by_product_horizon = defaultdict(list)
    for row in sequences["daily"]:
        by_product[row["series"]].append(row)
    for horizon, selected_horizon in sequences.items():
        for row in selected_horizon:
            by_product_horizon[(row["series"], horizon)].append(row)
    lines += [
        "", "### Worst five products by daily-sequence RMSE", "",
        "| Exact product series | Samples (PHP errors) | Within-10% hits / eligible (near-zero excluded) | MAE (PHP) | RMSE (PHP) | MAPE | Partial periods |",
        "|---|---:|---|---:|---:|---:|---:|",
    ]
    for series, selected in sorted(by_product.items(),
                                   key=lambda item: metrics(item[1])["rmse"] or -1, reverse=True)[:5]:
        lines.append(f"| {series.replace('||', ' / ')} | {table(selected)} |")
    lines += [
        "", "### Per-product daily, weekly and monthly metrics", "",
        "| Exact product series | Horizon | Samples (PHP errors) | Within-10% hits / eligible (near-zero excluded) | MAE (PHP) | RMSE (PHP) | MAPE | Partial periods |",
        "|---|---|---:|---|---:|---:|---:|---:|",
    ]
    for (series, horizon), selected in sorted(by_product_horizon.items()):
        lines.append(f"| {series.replace('||', ' / ')} | {horizon} | {table(selected)} |")
    return "\n".join(lines), evidence_counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundles", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    sections = [
        "# Daily / weekly / monthly validation audit", "",
        "Frozen holdout outcomes are not read. Overall metrics pool original price units.",
        "MAE/RMSE use all finite nonnegative actuals in original PHP; Within-10% accuracy and MAPE",
        "exclude actuals below 1e-8 PHP and report their count. No denominator is substituted.", "",
    ]
    for bundle in args.bundles:
        report, evidence_counts = audit(bundle)
        sections.extend([report, ""])
        print(json.dumps({"model": bundle.name,
                          "confidence_status": dict(evidence_counts)}))
    args.output.write_text("\n".join(sections), encoding="utf-8")


if __name__ == "__main__":
    main()
