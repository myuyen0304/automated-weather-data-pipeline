from __future__ import annotations

import json
import shutil
from uuid import uuid4

import pandas as pd

from config import CITIES, PROJECT_ROOT
from extract_weather import slugify_city
import transform_weather
from transform_weather import transform_raw_files


def test_transform_raw_files_normalizes_open_meteo_payload(monkeypatch) -> None:
    # Test đường ghi cleaned local: ép flag bật để không phụ thuộc .env của máy dev.
    monkeypatch.setattr(transform_weather, "CLEANED_LOCAL_WRITE_ENABLED", True)
    test_dir = PROJECT_ROOT / ".test-tmp" / f"transform-{uuid4().hex}"
    test_dir.mkdir(parents=True, exist_ok=True)
    try:
        _assert_transform_raw_files_normalizes_open_meteo_payload(test_dir)
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


def _assert_transform_raw_files_normalizes_open_meteo_payload(test_dir) -> None:
    city = CITIES[0]
    raw_path = test_dir / f"{slugify_city(city['city'])}.json"
    raw_path.write_text(
        json.dumps(
            {
                "latitude": city["latitude"],
                "longitude": city["longitude"],
                "current": {
                    "time": "2026-06-13T08:30",
                    "temperature_2m": 31.2,
                    "relative_humidity_2m": 72,
                    "apparent_temperature": 35.0,
                    "precipitation": 0.0,
                    "rain": 0.0,
                    "weather_code": 3,
                    "cloud_cover": 80,
                    "pressure_msl": 1007.0,
                    "surface_pressure": 1004.0,
                    "wind_speed_10m": 9.4,
                    "wind_direction_10m": 170,
                    "wind_gusts_10m": 18.2,
                    "is_day": 1,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    output_path = test_dir / "weather_observations.csv"

    transform_raw_files(raw_files=[raw_path], output_path=output_path)

    df = pd.read_csv(output_path)
    assert len(df) == 1
    assert df.loc[0, "city"] == city["city"]
    assert df.loc[0, "temperature"] == 31.2
    assert df.loc[0, "humidity"] == 72
    assert df.loc[0, "weather_condition"] == "Overcast"
    assert str(raw_path) in df.loc[0, "source_file"]


def _write_hourly_raw(raw_dir, city, day: str, hour: str, temperature: float) -> None:
    hour_dir = raw_dir / f"date={day}" / f"hour={hour}"
    hour_dir.mkdir(parents=True, exist_ok=True)
    (hour_dir / f"{slugify_city(city['city'])}.json").write_text(
        json.dumps(
            {
                "latitude": city["latitude"],
                "longitude": city["longitude"],
                "current": {
                    "time": f"{day}T{hour}:00",
                    "temperature_2m": temperature,
                    "relative_humidity_2m": 70,
                    "apparent_temperature": temperature + 2,
                    "precipitation": 0.0,
                    "rain": 0.0,
                    "weather_code": 0,
                    "cloud_cover": 10,
                    "pressure_msl": 1010.0,
                    "surface_pressure": 1007.0,
                    "wind_speed_10m": 6.0,
                    "wind_direction_10m": 90,
                    "wind_gusts_10m": 12.0,
                    "is_day": 1 if 6 <= int(hour) < 18 else 0,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_transform_reads_nested_hour_partitions(monkeypatch) -> None:
    monkeypatch.setattr(transform_weather, "CLEANED_LOCAL_WRITE_ENABLED", True)
    test_dir = PROJECT_ROOT / ".test-tmp" / f"transform-hourly-{uuid4().hex}"
    raw_dir = test_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    try:
        city = CITIES[0]
        _write_hourly_raw(raw_dir, city, "2026-06-13", "00", 25.0)
        _write_hourly_raw(raw_dir, city, "2026-06-13", "14", 34.0)
        output_path = test_dir / "weather_observations.csv"

        transform_raw_files(
            raw_dir=raw_dir, include_history=True, output_path=output_path
        )

        df = pd.read_csv(output_path)
        # Both hourly files under date=/hour=HH/ are discovered via rglob.
        assert len(df) == 2
        assert df["observation_time"].nunique() == 2
        assert df["temperature"].min() == 25.0
        assert df["temperature"].max() == 34.0
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


def test_transform_writes_cleaned_parquet_sidecar(monkeypatch) -> None:
    monkeypatch.setattr(transform_weather, "CLEANED_LOCAL_WRITE_ENABLED", True)
    test_dir = PROJECT_ROOT / ".test-tmp" / f"transform-parquet-{uuid4().hex}"
    test_dir.mkdir(parents=True, exist_ok=True)
    try:
        city = CITIES[0]
        raw_path = test_dir / f"{slugify_city(city['city'])}.json"
        raw_path.write_text(
            json.dumps(
                {
                    "latitude": city["latitude"],
                    "longitude": city["longitude"],
                    "current": {
                        "time": "2026-06-13T08:00",
                        "temperature_2m": 30.0,
                        "relative_humidity_2m": 70,
                        "apparent_temperature": 33.0,
                        "precipitation": 0.0,
                        "rain": 0.0,
                        "weather_code": 1,
                        "cloud_cover": 20,
                        "pressure_msl": 1008.0,
                        "surface_pressure": 1005.0,
                        "wind_speed_10m": 7.0,
                        "wind_direction_10m": 120,
                        "wind_gusts_10m": 14.0,
                        "is_day": 1,
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        output_path = test_dir / "weather_observations.csv"
        parquet_calls = []

        def fake_to_parquet(self, path, index=False):
            parquet_calls.append((path, index, len(self)))

        monkeypatch.setattr(pd.DataFrame, "to_parquet", fake_to_parquet)
        # to_parquet bị giả lập (không tạo file thật) nên bỏ qua bước mirror upload.
        monkeypatch.setattr(transform_weather, "upload_file", lambda *args, **kwargs: None)

        transform_raw_files(raw_files=[raw_path], output_path=output_path)

        assert output_path.exists()
        assert parquet_calls == [(output_path.with_suffix(".parquet"), False, 1)]
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


def test_transform_reads_raw_from_object_storage_when_local_partition_missing(
    monkeypatch,
) -> None:
    # Đọc raw từ S3 nhưng vẫn ghi cleaned local (ép flag) để assert output_path.
    monkeypatch.setattr(transform_weather, "CLEANED_LOCAL_WRITE_ENABLED", True)
    test_dir = PROJECT_ROOT / ".test-tmp" / f"transform-s3-{uuid4().hex}"
    raw_dir = test_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    try:
        city = CITIES[0]
        city_slug = slugify_city(city["city"])
        object_key = f"raw/open-meteo/date=2026-06-14/hour=00/{city_slug}.json"

        monkeypatch.setattr(
            transform_weather,
            "is_object_storage_enabled",
            lambda: True,
        )
        monkeypatch.setattr(
            transform_weather,
            "list_object_keys",
            lambda prefix=None: {object_key},
        )
        monkeypatch.setattr(
            transform_weather,
            "read_json_object",
            lambda key: {
                "latitude": city["latitude"],
                "longitude": city["longitude"],
                "current": {
                    "time": "2026-06-14T00:00",
                    "temperature_2m": 26.0,
                    "relative_humidity_2m": 82,
                    "apparent_temperature": 29.0,
                    "precipitation": 0.0,
                    "rain": 0.0,
                    "weather_code": 0,
                    "cloud_cover": 10,
                    "pressure_msl": 1009.0,
                    "surface_pressure": 1006.0,
                    "wind_speed_10m": 5.0,
                    "wind_direction_10m": 90,
                    "wind_gusts_10m": 10.0,
                    "is_day": 0,
                },
            },
        )
        monkeypatch.setattr(transform_weather, "upload_file", lambda *args, **kwargs: None)

        output_path = test_dir / "weather_observations.csv"
        transform_raw_files(
            raw_dir=raw_dir,
            run_date="2026-06-14",
            output_path=output_path,
        )

        df = pd.read_csv(output_path)
        assert len(df) == 1
        assert df.loc[0, "city"] == city["city"]
        assert df.loc[0, "source_file"] == f"s3://weather-pipeline/{object_key}"
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


def test_transform_writes_cleaned_directly_to_object_storage_without_local_file(
    monkeypatch,
) -> None:
    test_dir = PROJECT_ROOT / ".test-tmp" / f"transform-cleaned-s3-{uuid4().hex}"
    test_dir.mkdir(parents=True, exist_ok=True)
    put_calls = []
    try:
        city = CITIES[0]
        raw_path = test_dir / f"{slugify_city(city['city'])}.json"
        raw_path.write_text(
            json.dumps(
                {
                    "latitude": city["latitude"],
                    "longitude": city["longitude"],
                    "current": {
                        "time": "2026-06-13T08:00",
                        "temperature_2m": 30.0,
                        "relative_humidity_2m": 70,
                        "apparent_temperature": 33.0,
                        "precipitation": 0.0,
                        "rain": 0.0,
                        "weather_code": 1,
                        "cloud_cover": 20,
                        "pressure_msl": 1008.0,
                        "surface_pressure": 1005.0,
                        "wind_speed_10m": 7.0,
                        "wind_direction_10m": 120,
                        "wind_gusts_10m": 14.0,
                        "is_day": 1,
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        output_path = test_dir / "weather_observations.csv"

        # MinIO-only: cleaned put thẳng lên object storage, không ghi local.
        monkeypatch.setattr(transform_weather, "CLEANED_LOCAL_WRITE_ENABLED", False)
        monkeypatch.setattr(transform_weather, "is_object_storage_enabled", lambda: True)
        monkeypatch.setattr(
            transform_weather,
            "put_bytes_object",
            lambda body, key, **kwargs: put_calls.append((key, len(body))) or key,
        )

        transform_raw_files(raw_files=[raw_path], output_path=output_path)

        assert not output_path.exists()
        assert not output_path.with_suffix(".parquet").exists()
        put_keys = [key for key, _ in put_calls]
        assert any(key.endswith("weather_observations.csv") for key in put_keys)
        assert any(key.endswith("weather_observations.parquet") for key in put_keys)
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
