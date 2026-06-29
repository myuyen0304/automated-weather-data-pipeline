from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import config


def is_object_storage_enabled() -> bool:
    return config.OBJECT_STORAGE_ENABLED


@lru_cache(maxsize=1)
def get_s3_client():
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=config.S3_ENDPOINT_URL or None,
        region_name=config.S3_REGION,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )


@lru_cache(maxsize=1)
def ensure_bucket_exists() -> None:
    from botocore.exceptions import ClientError

    client = get_s3_client()
    try:
        client.head_bucket(Bucket=config.S3_BUCKET)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        status_code = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if error_code not in {"404", "NoSuchBucket"} and status_code != 404:
            raise
        client.create_bucket(Bucket=config.S3_BUCKET)


def _relative_to(path: Path, parent: Path) -> Path | None:
    try:
        return path.resolve().relative_to(parent.resolve())
    except ValueError:
        return None


def object_key_for_path(local_path: Path) -> str:
    raw_relative = _relative_to(local_path, config.RAW_DATA_DIR)
    if raw_relative is not None:
        return f"{config.S3_RAW_PREFIX}/{raw_relative.as_posix()}"

    cleaned_relative = _relative_to(local_path, config.CLEANED_DATA_DIR)
    if cleaned_relative is not None:
        return f"{config.S3_CLEANED_PREFIX}/{cleaned_relative.as_posix()}"

    project_relative = _relative_to(local_path, config.PROJECT_ROOT)
    if project_relative is not None:
        return project_relative.as_posix()

    return local_path.name


def list_object_keys(prefix: str | None = None) -> set[str]:
    ensure_bucket_exists()
    paginator = get_s3_client().get_paginator("list_objects_v2")
    kwargs = {"Bucket": config.S3_BUCKET}
    if prefix:
        kwargs["Prefix"] = prefix

    keys: set[str] = set()
    for page in paginator.paginate(**kwargs):
        keys.update(obj["Key"] for obj in page.get("Contents", []))
    return keys


def put_json_object(
    payload: dict[str, Any],
    object_key: str,
    *,
    quiet: bool = False,
) -> str | None:
    if not is_object_storage_enabled():
        return None

    ensure_bucket_exists()
    body = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
    get_s3_client().put_object(
        Bucket=config.S3_BUCKET,
        Key=object_key,
        Body=body,
        ContentType="application/json; charset=utf-8",
    )
    if not quiet:
        print(f"Uploaded to object storage: s3://{config.S3_BUCKET}/{object_key}")
    return object_key


def read_json_object(object_key: str) -> dict[str, Any]:
    ensure_bucket_exists()
    response = get_s3_client().get_object(Bucket=config.S3_BUCKET, Key=object_key)
    return json.loads(response["Body"].read().decode("utf-8"))


def put_bytes_object(
    body: bytes,
    object_key: str,
    *,
    content_type: str = "application/octet-stream",
    quiet: bool = False,
) -> str | None:
    """Ghi thẳng một blob (CSV/Parquet đã serialize) lên object storage.

    Dùng cho cleaned artifact khi CLEANED_LOCAL_WRITE_ENABLED=false: serialize
    DataFrame vào bộ nhớ rồi put, không cần file tạm trên SSD.
    """
    if not is_object_storage_enabled():
        return None

    ensure_bucket_exists()
    get_s3_client().put_object(
        Bucket=config.S3_BUCKET,
        Key=object_key,
        Body=body,
        ContentType=content_type,
    )
    if not quiet:
        print(f"Uploaded to object storage: s3://{config.S3_BUCKET}/{object_key}")
    return object_key


def read_bytes_object(object_key: str) -> bytes:
    ensure_bucket_exists()
    response = get_s3_client().get_object(Bucket=config.S3_BUCKET, Key=object_key)
    return response["Body"].read()


def upload_file(
    local_path: Path,
    object_key: str | None = None,
    *,
    quiet: bool = False,
) -> str | None:
    if not is_object_storage_enabled():
        return None

    if not local_path.exists():
        raise FileNotFoundError(f"Cannot upload missing file to object storage: {local_path}")

    ensure_bucket_exists()
    key = object_key or object_key_for_path(local_path)
    get_s3_client().upload_file(str(local_path), config.S3_BUCKET, key)
    if not quiet:
        print(f"Uploaded to object storage: s3://{config.S3_BUCKET}/{key}")
    return key
