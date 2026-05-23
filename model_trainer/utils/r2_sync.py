"""
Sync artifacts directory with Cloudflare R2 for state persistence.
"""

import os
import sys
import boto3
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def get_s3_client():
    account_id = os.getenv("CLOUDFLARE_R2_ACCOUNT_ID")
    access_key = os.getenv("CLOUDFLARE_R2_ACCESS_KEY_ID")
    secret_key = os.getenv("CLOUDFLARE_R2_SECRET_ACCESS_KEY")
    
    if not all([account_id, access_key, secret_key]):
        print("Missing R2 credentials in environment variables.")
        sys.exit(1)
        
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto"
    )

def upload_artifacts(bucket_name: str, local_dir: Path):
    s3 = get_s3_client()
    prefix = "model_artifacts/"
    
    print(f"Uploading {local_dir} to R2 bucket '{bucket_name}' under prefix '{prefix}'...")
    
    for root, dirs, files in os.walk(local_dir):
        for file in files:
            local_path = os.path.join(root, file)
            rel_path = os.path.relpath(local_path, local_dir)
            # R2 uses forward slashes
            r2_key = prefix + rel_path.replace("\\", "/")
            
            print(f"  Uploading: {rel_path} -> {r2_key}")
            s3.upload_file(local_path, bucket_name, r2_key)
            
    print("Upload complete.")

def download_artifacts(bucket_name: str, local_dir: Path):
    s3 = get_s3_client()
    prefix = "model_artifacts/"
    
    print(f"Downloading from R2 bucket '{bucket_name}' prefix '{prefix}' to {local_dir}...")
    
    local_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        paginator = s3.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
            if 'Contents' not in page:
                continue
                
            for obj in page['Contents']:
                r2_key = obj['Key']
                # Skip exact prefix match if it's a "directory"
                if r2_key == prefix or r2_key.endswith('/'):
                    continue
                    
                rel_path = r2_key[len(prefix):]
                local_path = local_dir / rel_path
                
                local_path.parent.mkdir(parents=True, exist_ok=True)
                
                print(f"  Downloading: {r2_key} -> {local_path}")
                s3.download_file(bucket_name, r2_key, str(local_path))
                
        print("Download complete.")
    except Exception as e:
        print(f"Error during download: {e}")
        print("This may be the first run, or the prefix doesn't exist yet. Proceeding with empty artifacts directory.")

def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ["upload", "download"]:
        print("Usage: python r2_sync.py [upload|download]")
        sys.exit(1)
        
    action = sys.argv[1]
    
    bucket_name = os.getenv("CLOUDFLARE_R2_BUCKET_NAME")
    if not bucket_name:
        print("CLOUDFLARE_R2_BUCKET_NAME is not set.")
        sys.exit(1)
        
    project_root = Path(__file__).resolve().parent.parent
    artifacts_dir = project_root / "artifacts"
    
    if action == "upload":
        if not artifacts_dir.exists():
            print(f"Artifacts directory {artifacts_dir} does not exist. Nothing to upload.")
            sys.exit(1)
        upload_artifacts(bucket_name, artifacts_dir)
    elif action == "download":
        download_artifacts(bucket_name, artifacts_dir)

if __name__ == "__main__":
    main()
