from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from config import CLEANED_DATA_DIR, RAW_DATA_DIR  # noqa: E402
from object_storage import (  # noqa: E402
    is_object_storage_enabled,
    list_object_keys,
    object_key_for_path,
    upload_file,
)


def iter_existing_artifacts() -> list[Path]:
    files: list[Path] = []
    if RAW_DATA_DIR.exists():
        files.extend(sorted(RAW_DATA_DIR.rglob("*.json")))

    for name in ("weather_observations.csv", "weather_observations.parquet"):
        path = CLEANED_DATA_DIR / name
        if path.exists():
            files.append(path)

    return files


def main() -> None:
    if not is_object_storage_enabled():
        raise SystemExit(
            "OBJECT_STORAGE_ENABLED is false. Enable it in .env before syncing to MinIO/S3."
        )

    files = iter_existing_artifacts()
    if not files:
        raise SystemExit("No raw JSON or cleaned artifacts found to upload.")

    existing_keys = list_object_keys()
    to_upload = [
        (path, object_key_for_path(path))
        for path in files
        if object_key_for_path(path) not in existing_keys
    ]

    skipped = len(files) - len(to_upload)
    print(
        f"Found {len(files)} local artifact(s); "
        f"{skipped} already in object storage; {len(to_upload)} to upload."
    )

    for path in files:
        key = object_key_for_path(path)
        if key in existing_keys:
            continue
        upload_file(path, key, quiet=True)
        uploaded = len(existing_keys) + 1
        existing_keys.add(key)
        if uploaded % 1000 == 0 or uploaded == len(files):
            print(f"Synced progress: {uploaded}/{len(files)} object(s) present.")

    print(f"Sync complete: {len(files)} object(s) present in object storage.")


if __name__ == "__main__":
    main()
