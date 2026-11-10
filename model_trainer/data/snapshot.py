"""Lossless, hash-checked raw training-input snapshots for new model bundles.

Legacy bundles without these files remain readable. The snapshot is the raw
DataFrame actually passed to training, before cleaning or imputation; it does
not reconstruct source ingestion timestamps that were never recorded.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pandas as pd
from pandas.testing import assert_frame_equal


SNAPSHOT_FILE = "source_snapshot.json.gz"
MANIFEST_FILE = "source_snapshot_manifest.json"
SNAPSHOT_SCHEMA_VERSION = 1


def serialize_frame(raw: pd.DataFrame) -> bytes:
    """Encode table schema, values and row order with deterministic gzip."""
    if raw.empty or not raw.columns.is_unique:
        raise ValueError("Source snapshot requires rows and unique columns")
    table = json.loads(raw.to_json(
        orient="table", date_format="iso", date_unit="ms", double_precision=15,
    ))
    table["foodcast_dtypes"] = list(raw.dtypes.astype(str))
    payload = json.dumps(table, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return gzip.compress(payload, compresslevel=6, mtime=0)


def deserialize_frame(encoded: bytes) -> pd.DataFrame:
    """Use precise float parsing; the default parser can shift PHP values."""
    try:
        payload = gzip.decompress(encoded).decode("utf-8")
        table = json.loads(payload)
        dtypes = table.pop("foodcast_dtypes")
        frame = pd.read_json(io.StringIO(json.dumps(table)), orient="table", precise_float=True)
        if len(dtypes) != len(frame.columns):
            raise ValueError("Source snapshot dtype count mismatch")
        for column, dtype in zip(frame.columns, dtypes):
            if str(frame[column].dtype) != dtype:
                frame[column] = frame[column].astype(dtype)
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        raise ValueError("Invalid source snapshot encoding") from exc
    if frame.empty or not frame.columns.is_unique:
        raise ValueError("Source snapshot has no rows or has duplicate columns")
    return frame


def assert_equivalent(original: pd.DataFrame, restored: pd.DataFrame,
                      fingerprint: str, fingerprint_fn: Callable[[pd.DataFrame], str]) -> None:
    """Fail closed if any model input value, dtype, row order or digest changes."""
    try:
        assert_frame_equal(original, restored, check_exact=True, check_dtype=True)
    except AssertionError as exc:
        raise ValueError("Source snapshot does not exactly reproduce training input") from exc
    if fingerprint_fn(restored) != fingerprint:
        raise ValueError("Source snapshot does not exactly reproduce training input")


def read_snapshot(run_dir: str | Path, *, fingerprint_fn=None) -> tuple[pd.DataFrame, dict]:
    """Verify the archived bytes and optional model-input fingerprint."""
    run_dir = Path(run_dir)
    manifest = json.loads((run_dir / MANIFEST_FILE).read_text(encoding="utf-8"))
    if manifest.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("Unsupported source snapshot manifest schema")
    if manifest.get("snapshot_file") != SNAPSHOT_FILE:
        raise ValueError("Source snapshot manifest filename mismatch")
    encoded = (run_dir / SNAPSHOT_FILE).read_bytes()
    if (len(encoded) != manifest.get("byte_length")
            or hashlib.sha256(encoded).hexdigest() != manifest.get("sha256")):
        raise ValueError("Source snapshot SHA-256 mismatch")
    frame = deserialize_frame(encoded)
    if (len(frame) != manifest.get("row_count")
            or list(frame.columns) != manifest.get("columns")
            or list(frame.dtypes.astype(str)) != manifest.get("dtypes")):
        raise ValueError("Source snapshot shape or dtype mismatch")
    if fingerprint_fn is not None and fingerprint_fn(frame) != manifest.get("data_fingerprint"):
        raise ValueError("Source snapshot training fingerprint mismatch")
    return frame, manifest


def capture_snapshot(run_dir: str | Path, raw: pd.DataFrame, fingerprint: str,
                     fingerprint_fn: Callable[[pd.DataFrame], str]) -> dict:
    """Archive new input once, or verify an existing staged archive without overwriting."""
    run_dir = Path(run_dir)
    snapshot_path = run_dir / SNAPSHOT_FILE
    manifest_path = run_dir / MANIFEST_FILE
    if snapshot_path.exists() or manifest_path.exists():
        if not snapshot_path.is_file() or not manifest_path.is_file():
            raise ValueError("Staged source snapshot is incomplete")
        restored, manifest = read_snapshot(run_dir, fingerprint_fn=fingerprint_fn)
        assert_equivalent(raw, restored, fingerprint, fingerprint_fn)
        return manifest

    encoded = serialize_frame(raw)
    restored = deserialize_frame(encoded)
    assert_equivalent(raw, restored, fingerprint, fingerprint_fn)
    dates = pd.to_datetime(raw["report_date"], errors="coerce")
    valid_dates = dates.dropna()
    manifest = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "snapshot_file": SNAPSHOT_FILE,
        "serialization": "pandas_table_json_gzip_mtime0_precise_float",
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "byte_length": len(encoded),
        "row_count": int(len(raw)),
        "columns": list(raw.columns),
        "dtypes": list(raw.dtypes.astype(str)),
        "report_date_min": (valid_dates.min().date().isoformat()
                            if not valid_dates.empty else None),
        "report_date_max": (valid_dates.max().date().isoformat()
                            if not valid_dates.empty else None),
        "invalid_report_date_count": int(dates.isna().sum()),
        "data_fingerprint": fingerprint,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "provenance": "exact raw DataFrame passed to candidate training; no ingestion-time assertion",
    }
    snapshot_path.write_bytes(encoded)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return manifest
