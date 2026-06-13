from __future__ import annotations

import json
import shutil
from uuid import uuid4

import pandas as pd

from config import CITIES, PROJECT_ROOT
from extract_weather import slugify_city
from transform_weather import transform_raw_files


def test_transform_raw_files_normalizes_open_meteo_payload() -> None:
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
