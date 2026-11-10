"""Compare two raw food-price source vintages without touching sealed holdouts."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from data.preprocessor import SERIES_KEY


KEY = SERIES_KEY + ["report_date"]
HOLDOUT_START = pd.Timestamp("2026-10-06")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_source(path: Path) -> pd.DataFrame:
    content = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(content, dict):
        content = content.get("rows", content.get("data"))
    frame = pd.DataFrame(content)
    required = set(KEY + ["id", "price_index", "source_pdf"])
    if frame.empty or not required.issubset(frame):
        raise ValueError(f"Source is empty or lacks {sorted(required - set(frame))}")
    frame["report_date"] = pd.to_datetime(frame.report_date, errors="coerce").dt.normalize()
    if frame.report_date.isna().any():
        raise ValueError("Source has unparseable report dates")
    if frame.duplicated(KEY).any() or frame.id.duplicated().any():
        raise ValueError("Source has duplicate series-date keys or row IDs")
    return frame


def compare(active: pd.DataFrame, newer: pd.DataFrame,
            *, cutoff: pd.Timestamp) -> dict:
    cutoff = pd.Timestamp(cutoff).normalize()
    if cutoff >= HOLDOUT_START:
        raise ValueError("Vintage comparison cutoff enters sealed prospective holdout")
    active = active.loc[active.report_date.le(cutoff)]
    newer = newer.loc[newer.report_date.le(cutoff)]
    if active.empty or newer.empty:
        raise ValueError("Comparison has no rows through cutoff")
    paired = active.merge(newer, on=KEY, how="outer", suffixes=("_active", "_new"),
                          indicator=True, validate="one_to_one")
    shared = paired.loc[paired._merge.eq("both")].copy()
    active_only = paired.loc[paired._merge.eq("left_only")]
    newer_only = paired.loc[paired._merge.eq("right_only")]
    changed_price = shared.price_index_active.ne(shared.price_index_new)
    changed_source = shared.source_pdf_active.fillna("").ne(
        shared.source_pdf_new.fillna(""))
    return {
        "cutoff_inclusive": cutoff.date().isoformat(),
        "active_rows": int(len(active)),
        "newer_rows": int(len(newer)),
        "matched_series_date_keys": int(len(shared)),
        "active_only_series_date_keys": int(len(active_only)),
        "newer_only_series_date_keys": int(len(newer_only)),
        "matched_keys_with_changed_price": int(changed_price.sum()),
        "matched_keys_with_changed_source_pdf": int(changed_source.sum()),
        "matched_keys_with_changed_row_id": int(shared.id_active.ne(shared.id_new).sum()),
        "changed_price_by_product": {
            str(name): int(count) for name, count in
            shared.loc[changed_price].product_name.value_counts().items()
        },
        "active_only_by_product": {
            str(name): int(count) for name, count in
            active_only.product_name.value_counts().items()
        },
        "newer_only_by_product": {
            str(name): int(count) for name, count in
            newer_only.product_name.value_counts().items()
        },
    }


def run(active_path: Path, newer_path: Path, output: Path,
        *, cutoff: pd.Timestamp) -> dict:
    active_path, newer_path, output = map(Path, (active_path, newer_path, output))
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite vintage diff: {output}")
    result = compare(load_source(active_path), load_source(newer_path), cutoff=cutoff)
    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "active_source_path": str(active_path),
        "active_source_sha256": _sha256(active_path),
        "newer_source_path": str(newer_path),
        "newer_source_sha256": _sha256(newer_path),
        "script_sha256": _sha256(Path(__file__)),
        "holdout_labels_used": False,
        "comparison": result,
        "interpretation": (
            "Raw series-date keys are compared exactly after date normalization. "
            "Changed row IDs alone are not price changes. This is a source-vintage "
            "diff, not a forecast evaluation or evidence of when a report became available."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n",
                      encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--active-source", required=True, type=Path)
    parser.add_argument("--newer-source", required=True, type=Path)
    parser.add_argument("--through", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = run(args.active_source, args.newer_source, args.output,
                 cutoff=pd.Timestamp(args.through))
    print(json.dumps(report["comparison"], indent=2))


if __name__ == "__main__":
    main()
