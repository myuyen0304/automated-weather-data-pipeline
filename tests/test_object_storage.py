from __future__ import annotations

import shutil
from uuid import uuid4

import config
import extract_weather
import object_storage


def test_object_key_for_raw_and_cleaned_paths() -> None:
    raw_path = (
        config.RAW_DATA_DIR
        / "date=2026-06-16"
        / "hour=00"
        / "hanoi.json"
    )
    cleaned_path = config.CLEANED_DATA_DIR / "weather_observations.parquet"

    assert (
        object_storage.object_key_for_path(raw_path)
        == "raw/open-meteo/date=2026-06-16/hour=00/hanoi.json"
    )
    assert (
        object_storage.object_key_for_path(cleaned_path)
        == "cleaned/weather_observations.parquet"
    )


def test_upload_file_is_noop_when_object_storage_disabled(monkeypatch) -> None:
    test_dir = config.PROJECT_ROOT / ".test-tmp" / f"object-storage-{uuid4().hex}"
    test_dir.mkdir(parents=True, exist_ok=True)
    try:
        local_path = test_dir / "sample.txt"
        local_path.write_text("sample", encoding="utf-8")
        monkeypatch.setattr(config, "OBJECT_STORAGE_ENABLED", False)

        assert object_storage.upload_file(local_path) is None
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


def test_upload_file_uses_s3_compatible_client(monkeypatch) -> None:
    test_dir = config.PROJECT_ROOT / ".test-tmp" / f"object-storage-{uuid4().hex}"
    local_path = test_dir / "weather_observations.csv"
    try:
        test_dir.mkdir(parents=True, exist_ok=True)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text("city,temperature\nHanoi,30\n", encoding="utf-8")
        uploads = []

        class FakeClient:
            def upload_file(self, filename, bucket, key):
                uploads.append((filename, bucket, key))

        monkeypatch.setattr(config, "OBJECT_STORAGE_ENABLED", True)
        monkeypatch.setattr(config, "CLEANED_DATA_DIR", test_dir)
        monkeypatch.setattr(config, "S3_BUCKET", "weather-pipeline-test")
        monkeypatch.setattr(object_storage, "ensure_bucket_exists", lambda: None)
        monkeypatch.setattr(object_storage, "get_s3_client", lambda: FakeClient())

        key = object_storage.upload_file(local_path)

        assert key == "cleaned/weather_observations.csv"
        assert uploads == [
            (
                str(local_path),
                "weather-pipeline-test",
                "cleaned/weather_observations.csv",
            )
        ]
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


def test_put_and_read_json_object_use_s3_client(monkeypatch) -> None:
    stored_objects = {}

    class FakeBody:
        def __init__(self, body: bytes):
            self.body = body

        def read(self):
            return self.body

    class FakeClient:
        def put_object(self, Bucket, Key, Body, ContentType):
            stored_objects[(Bucket, Key)] = {
                "Body": Body,
                "ContentType": ContentType,
            }

        def get_object(self, Bucket, Key):
            return {"Body": FakeBody(stored_objects[(Bucket, Key)]["Body"])}

    monkeypatch.setattr(config, "OBJECT_STORAGE_ENABLED", True)
    monkeypatch.setattr(config, "S3_BUCKET", "weather-pipeline-test")
    monkeypatch.setattr(object_storage, "ensure_bucket_exists", lambda: None)
    monkeypatch.setattr(object_storage, "get_s3_client", lambda: FakeClient())

    key = object_storage.put_json_object({"city": "Hanoi"}, "raw/open-meteo/sample.json")

    assert key == "raw/open-meteo/sample.json"
    assert object_storage.read_json_object("raw/open-meteo/sample.json") == {
        "city": "Hanoi"
    }
    assert stored_objects[
        ("weather-pipeline-test", "raw/open-meteo/sample.json")
    ]["ContentType"] == "application/json; charset=utf-8"


def test_save_raw_can_write_directly_to_object_storage_without_local_file(
    monkeypatch,
) -> None:
    test_dir = config.PROJECT_ROOT / ".test-tmp" / f"raw-s3-only-{uuid4().hex}"
    raw_dir = test_dir / "raw" / "open-meteo"
    uploaded = []
    try:
        city = config.CITIES[0]
        monkeypatch.setattr(config, "RAW_DATA_DIR", raw_dir)
        monkeypatch.setattr(extract_weather, "RAW_DATA_DIR", raw_dir)
        monkeypatch.setattr(extract_weather, "RAW_LOCAL_WRITE_ENABLED", False)
        monkeypatch.setattr(extract_weather, "is_object_storage_enabled", lambda: True)
        monkeypatch.setattr(
            extract_weather,
            "put_json_object",
            lambda payload, key: uploaded.append((payload, key)) or key,
        )

        output_path = extract_weather.save_raw_weather_response(
            city,
            {"current": {"time": "2026-06-14T00:00"}},
            run_date="2026-06-14",
            run_hour="00",
        )

        assert output_path == (
            raw_dir
            / "date=2026-06-14"
            / "hour=00"
            / f"{extract_weather.slugify_city(city['city'])}.json"
        )
        assert not output_path.exists()
        assert uploaded == [
            (
                {"current": {"time": "2026-06-14T00:00"}},
                "raw/open-meteo/date=2026-06-14/hour=00/"
                f"{extract_weather.slugify_city(city['city'])}.json",
            )
        ]
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
