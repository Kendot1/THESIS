"""Read saved validation predictions only; never reads frozen/test outcomes."""
import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

from evaluation.product_confidence import HORIZONS, validation_confidence


def metrics(rows):
    errors = [abs(float(r["ensemble"])-float(r["actual"])) for r in rows]
    return (len(rows), mean(errors), math.sqrt(mean(e*e for e in errors)),
            mean(e/float(r["actual"])*100 for e, r in zip(errors, rows)))


def table(rows):
    n, mae, rmse, mape = metrics(rows)
    return f"{n} | {mae:.3f} | {rmse:.3f} | {mape:.3f}%"


def audit(bundle):
    with (bundle / "validation_forecasts.csv").open(newline="", encoding="utf-8") as stream:
        rows = [r for r in csv.DictReader(stream) if float(r["actual"]) > 0]
    identities = {tuple(r["series"].split("||")): r["series"] for r in rows}
    confidence = validation_confidence(bundle, identities)
    counts = Counter(m["evidence_status"] for block in confidence.values() for m in block.values())
    lines = [f"## {bundle.name}", "", "Saved chronological validation; includes model selection rows.",
             "These are diagnostic scores, not independent final-holdout evidence.", "",
             "| Horizon | Rows | MAE | RMSE | MAPE |", "|---|---:|---:|---:|---:|",
             f"| Overall (all leads 1–30) | {table(rows)} |"]
    for lead, name in HORIZONS.items():
        selected = [r for r in rows if int(r["horizon"]) == lead]
        if selected:
            lines.append(f"| {name} (t+{lead}) | {table(selected)} |")
    lines += ["", f"Confidence evidence status (product × horizon): `{dict(counts)}`.",
              "", "### Worst five products by validation RMSE, all leads", "",
              "| Exact product series | Rows | MAE | RMSE | MAPE |", "|---|---:|---:|---:|---:|"]
    groups = defaultdict(list)
    for row in rows:
        groups[row["series"]].append(row)
    for name, selected in sorted(groups.items(), key=lambda item: metrics(item[1])[2], reverse=True)[:5]:
        lines.append(f"| {name.replace('||', ' / ')} | {table(selected)} |")
    lines += ["", "### Per-product exact horizon metrics", "",
              "| Exact product series | Horizon | Rows | MAE | RMSE | MAPE |", "|---|---|---:|---:|---:|---:|"]
    for name, group in sorted(groups.items()):
        for lead, horizon in HORIZONS.items():
            selected = [r for r in group if int(r["horizon"]) == lead]
            if selected:
                lines.append(f"| {name.replace('||', ' / ')} | {horizon} | {table(selected)} |")
    return "\n".join(lines), counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundles", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    sections = ["# Daily / Weekly / Monthly validation audit", "",
                "No model was selected or changed by this report. Baseline and final retained-model metrics are identical.",
                "Frozen holdout outcomes are not read. MAE/RMSE retain each product's price unit; overall pooling mixes units.", ""]
    for bundle in args.bundles:
        report, counts = audit(bundle)
        sections += [report, ""]
        print(json.dumps(dict(model=bundle.name, confidence_status=dict(counts))))
        print(report.split("### Per-product")[0])
    args.output.write_text("\n".join(sections), encoding="utf-8")


if __name__ == "__main__":
    main()
