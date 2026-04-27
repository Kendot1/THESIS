"""
Model versioning and persistence management.
Keeps a rolling history of model checkpoints with metadata.
"""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from config.settings import get_settings
from utils.logger import get_logger

log = get_logger(__name__)


class ModelStore:
    """
    Manages versioned model checkpoints.

    Structure:
      artifacts/
        versions/
          v001_2026-04-26T12-00-00/
            lightgbm_model.txt
            lstm_model.pt
            lstm_scaler.npz
            ensemble_meta_model.pkl
            categorical_mappings.json
            metadata.json
          v002_.../
        lightgbm_model.txt  ← latest (symlink / copy)
        lstm_model.pt       ← latest
        ...
    """

    def __init__(self):
        cfg = get_settings()
        self._artifacts = cfg.artifacts_dir
        self._versions_dir = self._artifacts / "versions"
        self._versions_dir.mkdir(parents=True, exist_ok=True)
        self._max_versions = cfg.max_model_versions
        self._manifest_path = self._artifacts / "model_manifest.json"

    # ──────────────────────────────────────────────
    def create_version(self, metrics: Dict[str, float], notes: str = "") -> str:
        """
        Snapshot current artifacts into a new versioned directory.
        Returns the version tag (e.g. "v003_2026-04-26T12-00-00").
        """
        version_num = len(list(self._versions_dir.iterdir())) + 1
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
        version_tag = f"v{version_num:03d}_{timestamp}"
        version_dir = self._versions_dir / version_tag
        version_dir.mkdir(parents=True, exist_ok=True)

        # Copy model files
        model_files = [
            "lightgbm_model.txt",
            "lstm_model.pt",
            "lstm_scaler.npz",
            "ensemble_meta_model.pkl",
            "categorical_mappings.json",
        ]
        copied = []
        for fname in model_files:
            src = self._artifacts / fname
            if src.exists():
                shutil.copy2(str(src), str(version_dir / fname))
                copied.append(fname)

        # Write metadata
        metadata = {
            "version": version_tag,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "metrics": metrics,
            "notes": notes,
            "files": copied,
        }
        with open(version_dir / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)

        # Update manifest
        self._update_manifest(version_tag, metrics)

        # Prune old versions
        self._prune_old_versions()

        log.info(f"Created model version {version_tag} ({len(copied)} files)")
        return version_tag

    def rollback(self, version_tag: str):
        """Restore artifacts from a specific version."""
        version_dir = self._versions_dir / version_tag
        if not version_dir.exists():
            raise FileNotFoundError(f"Version {version_tag} not found.")

        for fpath in version_dir.iterdir():
            if fpath.name == "metadata.json":
                continue
            dest = self._artifacts / fpath.name
            shutil.copy2(str(fpath), str(dest))

        log.info(f"Rolled back to version {version_tag}")

    def list_versions(self) -> List[Dict]:
        """List all saved versions with their metadata."""
        versions = []
        for vdir in sorted(self._versions_dir.iterdir()):
            meta_path = vdir / "metadata.json"
            if meta_path.exists():
                with open(meta_path) as f:
                    versions.append(json.load(f))
        return versions

    def get_latest_metrics(self) -> Optional[Dict[str, float]]:
        """Return metrics from the most recent version."""
        versions = self.list_versions()
        if versions:
            return versions[-1].get("metrics", {})
        return None

    # ──────────────────────────────────────────────
    def _update_manifest(self, version_tag: str, metrics: Dict):
        manifest = {}
        if self._manifest_path.exists():
            with open(self._manifest_path) as f:
                manifest = json.load(f)

        manifest["latest_version"] = version_tag
        manifest["latest_metrics"] = metrics
        manifest["updated_at"] = datetime.now(timezone.utc).isoformat()

        history = manifest.get("history", [])
        history.append({"version": version_tag, "metrics": metrics})
        manifest["history"] = history[-self._max_versions:]

        with open(self._manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

    def _prune_old_versions(self):
        """Delete the oldest versions if we exceed max_versions."""
        versions = sorted(self._versions_dir.iterdir())
        while len(versions) > self._max_versions:
            oldest = versions.pop(0)
            shutil.rmtree(str(oldest))
            log.info(f"Pruned old version: {oldest.name}")
