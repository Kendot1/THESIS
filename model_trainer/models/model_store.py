"""Immutable, hash-verified v2 model bundles with an atomic active pointer."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from config.settings import get_settings


REQUIRED_FILES = {
    "categorical_mappings.json", "lightgbm_model.txt", "lightgbm_meta.json",
    "lstm_model.pt", "lstm_meta.json", "lstm_history.json", "ensemble.json",
    "validation_forecasts.csv", "test_forecasts.csv", "metadata.json",
}
OPTIONAL_RUNTIME_FILES = {"validation_forecasts.csv", "test_forecasts.csv"}
OPTIONAL_BUNDLE_FILES = {"validation_paths.csv", "test_paths.csv"}
HASHED_REQUIRED_FILES = REQUIRED_FILES - {"metadata.json"}


class ModelStore:
    def __init__(self, root=None):
        self.root = Path(root or get_settings().artifacts_dir)
        self.runs = self.root / "runs"
        self.manifest = self.root / "manifest.json"
        self.runs.mkdir(parents=True, exist_ok=True)

    def begin_run(self):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = self.runs / f"{stamp}_{uuid4().hex[:8]}"
        path.mkdir(parents=False)
        return path

    @staticmethod
    def _digest(path):
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def finalize(self, run_dir, metrics, split, data_fingerprint, activate=True,
                 model_configuration=None):
        run_dir = Path(run_dir)
        metadata = {
            "schema_version": 2,
            "run_id": run_dir.name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "split": split,
            "data_fingerprint": data_fingerprint,
            "metrics": metrics,
        }
        if model_configuration is not None:
            metadata["model_configuration"] = model_configuration
        (run_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        missing = REQUIRED_FILES - {p.name for p in run_dir.iterdir() if p.is_file()}
        if missing:
            raise ValueError(f"Incomplete model bundle: {sorted(missing)}")
        present = {p.name for p in run_dir.iterdir() if p.is_file()}
        metadata["sha256"] = {
            name: self._digest(run_dir / name)
            for name in sorted(HASHED_REQUIRED_FILES | (OPTIONAL_BUNDLE_FILES & present))
        }
        (run_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        if activate:
            self.activate(run_dir.name)
        return run_dir.name

    def activate(self, run_id, *, evidence_dir=None):
        path = self.runs / run_id
        if not path.is_dir():
            raise FileNotFoundError(run_id)
        metadata = json.loads((path / "metadata.json").read_text(encoding="utf-8"))
        hashes = set(metadata.get("sha256", {}))
        if (metadata.get("run_id") != run_id
                or not HASHED_REQUIRED_FILES.issubset(hashes)
                or hashes - HASHED_REQUIRED_FILES - OPTIONAL_BUNDLE_FILES):
            raise ValueError("Model bundle identity or required hashes are incomplete")
        for name, expected in metadata.get("sha256", {}).items():
            if self._digest(path / name) != expected:
                raise ValueError(f"Hash mismatch in {name}")
        if evidence_dir is None:
            raise ValueError("Reviewed final-holdout evidence is required for activation")
        from evaluation.promotion import verify_promotion_evidence
        evidence = verify_promotion_evidence(path, evidence_dir)
        payload = {"schema_version": 2, "active_run": run_id,
                   "promotion_evidence": evidence,
                   "updated_at": datetime.now(timezone.utc).isoformat()}
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.root / "manifest.json.tmp"
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.replace(self.manifest)

    def active_path(self):
        if not self.manifest.exists():
            raise FileNotFoundError("No active v2 model bundle")
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        path = self.runs / data["active_run"]
        if not path.is_dir():
            raise FileNotFoundError(f"Active bundle is missing: {path}")
        metadata = json.loads((path / "metadata.json").read_text(encoding="utf-8"))
        hashes = set(metadata.get("sha256", {}))
        if (metadata.get("run_id") != path.name
                or not HASHED_REQUIRED_FILES.issubset(hashes)
                or hashes - HASHED_REQUIRED_FILES - OPTIONAL_BUNDLE_FILES):
            raise ValueError("Active bundle identity or required hashes are incomplete")
        evidence = data.get("promotion_evidence")
        if evidence and self._digest(path / "metadata.json") != evidence.get("model_metadata_sha256"):
            raise ValueError("Active model metadata changed after reviewed promotion")
        for name, expected in metadata.get("sha256", {}).items():
            if name in OPTIONAL_RUNTIME_FILES and not (path / name).exists():
                continue
            if self._digest(path / name) != expected:
                raise ValueError(f"Active bundle hash mismatch in {name}")
        return path

    def rollback(self, run_id, *, evidence_dir=None):
        self.activate(run_id, evidence_dir=evidence_dir)

    def list_versions(self):
        results = []
        for path in self.runs.iterdir():
            meta = path / "metadata.json"
            if meta.exists():
                results.append(json.loads(meta.read_text(encoding="utf-8")))
        return sorted(results, key=lambda row: row["created_at"])

    def get_latest_metrics(self):
        try:
            meta = json.loads((self.active_path() / "metadata.json").read_text(encoding="utf-8"))
            return meta.get("metrics")
        except FileNotFoundError:
            return None
