"""Publish and restore immutable v2 bundles; upload the active pointer last."""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import truststore

# Use the operating-system trust store so R2 works on managed Windows hosts
# whose organization CA is not bundled with Python/certifi.
truststore.inject_into_ssl()

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

from config.settings import get_settings
from models.model_store import ModelStore

load_dotenv(override=False)
PREFIX = "model_artifacts_v2"


def client():
    required = {
        "account": os.getenv("CLOUDFLARE_R2_ACCOUNT_ID"),
        "access": os.getenv("CLOUDFLARE_R2_ACCESS_KEY_ID"),
        "secret": os.getenv("CLOUDFLARE_R2_SECRET_ACCESS_KEY"),
    }
    if not all(required.values()):
        raise RuntimeError("Missing Cloudflare R2 credentials")
    return boto3.client(
        "s3", endpoint_url=f"https://{required['account']}.r2.cloudflarestorage.com",
        aws_access_key_id=required["access"], aws_secret_access_key=required["secret"],
        region_name="auto")


def upload(bucket, root):
    store = ModelStore(root)
    run = store.active_path()
    metadata = json.loads((run / "metadata.json").read_text(encoding="utf-8"))
    for name, expected in metadata["sha256"].items():
        if store._digest(run / name) != expected:
            raise ValueError(f"Refusing to upload corrupt artifact: {name}")
    s3 = client()
    for path in sorted(run.iterdir()):
        if path.is_file():
            s3.upload_file(str(path), bucket, f"{PREFIX}/runs/{run.name}/{path.name}")
    s3.upload_file(str(store.manifest), bucket, f"{PREFIX}/manifest.json")
    print(f"Uploaded and activated immutable bundle {run.name}")


def download(bucket, root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    s3 = client()
    with tempfile.TemporaryDirectory(dir=root) as temporary:
        staging = Path(temporary)
        remote_manifest = staging / "manifest.json"
        try:
            s3.download_file(bucket, f"{PREFIX}/manifest.json", str(remote_manifest))
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchKey", "NotFound"}:
                raise RuntimeError(
                    "No active v2 model bundle exists in Cloudflare R2. "
                    "Daily training stages candidates and cannot activate one "
                    "without reviewed independent frozen-holdout evidence. "
                    "Restore or publish an approved active bundle before the "
                    "workflow trains and publishes forecasts."
                ) from exc
            raise
        manifest = json.loads(remote_manifest.read_text(encoding="utf-8"))
        run_id = manifest["active_run"]
        run_stage = staging / run_id
        run_stage.mkdir()
        response = s3.list_objects_v2(Bucket=bucket, Prefix=f"{PREFIX}/runs/{run_id}/")
        for item in response.get("Contents", []):
            name = Path(item["Key"]).name
            if name:
                s3.download_file(bucket, item["Key"], str(run_stage / name))
        metadata = json.loads((run_stage / "metadata.json").read_text(encoding="utf-8"))
        for name, expected in metadata["sha256"].items():
            if ModelStore._digest(run_stage / name) != expected:
                raise ValueError(f"Downloaded artifact failed hash verification: {name}")
        destination = root / "runs" / run_id
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            existing = json.loads((destination / "metadata.json").read_text(encoding="utf-8"))
            if existing.get("sha256") != metadata.get("sha256"):
                raise ValueError(f"Local bundle ID collision: {run_id}")
            for name, expected in metadata["sha256"].items():
                if ModelStore._digest(destination / name) != expected:
                    raise ValueError(f"Existing local bundle is corrupt: {name}")
        else:
            shutil.move(str(run_stage), str(destination))
        remote_manifest.replace(root / "manifest.json")
    print(f"Restored and activated immutable bundle {run_id}")


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {"upload", "download"}:
        raise SystemExit("Usage: python -m utils.r2_sync [upload|download]")
    bucket = os.getenv("CLOUDFLARE_R2_BUCKET_NAME")
    if not bucket:
        raise RuntimeError("CLOUDFLARE_R2_BUCKET_NAME is not set")
    root = get_settings().artifacts_dir
    upload(bucket, root) if sys.argv[1] == "upload" else download(bucket, root)


if __name__ == "__main__":
    main()
