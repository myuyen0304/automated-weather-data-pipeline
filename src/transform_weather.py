from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import pandas as pd

from config import CLEANED_DATA_DIR, CITIES, RAW_DATA_DIR, WEATHER_TIMEZONE
from extract_weather import slugify_city


WEATHER_CODE_MAP = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


CITY_BY_FILE_STEM = {slugify_city(city["city"]): city for city in CITIES}


def read_raw_weather_file(raw_path: Path) -> dict[str, Any]:
    return json.loads(raw_path.read_text(encoding="utf-8"))


def normalize_weather_record(raw_path: Path) -> dict[str, Any]:
    payload = read_raw_weather_file(raw_path)
    city_config = CITY_BY_FILE_STEM.get(raw_path.stem)
    if city_config is None:
        raise ValueError(f"Cannot map raw file to configured city: {raw_path}")

    current = payload.get("current", {})
    weather_code = current.get("weather_code")

    return {
        "city": city_config["city"],
        "country": city_config["country"],
        "latitude": payload.get("latitude"),
        "longitude": payload.get("longitude"),
        "observation_time": current.get("time"),
        "temperature": current.get("temperature_2m"),
        "humidity": current.get("relative_humidity_2m"),
        "apparent_temperature": current.get("apparent_temperature"),
        "pressure_msl": current.get("pressure_msl"),
        "surface_pressure": current.get("surface_pressure"),
        "wind_speed": current.get("wind_speed_10m"),
        "wind_direction": current.get("wind_direction_10m"),
        "wind_gusts": current.get("wind_gusts_10m"),
        "precipitation": current.get("precipitation") or 0,
        "rain": current.get("rain") or 0,
        "cloud_cover": current.get("cloud_cover"),
        "weather_code": weather_code,
        "weather_condition": WEATHER_CODE_MAP.get(weather_code, "Unknown"),
        "is_day": bool(current.get("is_day")),
        "inserted_at": datetime.now(ZoneInfo(WEATHER_TIMEZONE)).isoformat(timespec="seconds"),
        "source_file": str(raw_path),
    }


def list_raw_weather_files(
    raw_dir: Path = RAW_DATA_DIR,
    run_date: str | None = None,
    include_history: bool = False,
) -> list[Path]:
    # rglob để thấy cả layout hourly lồng nhau date=<day>/hour=HH/<city>.json
    # lẫn layout phẳng cũ date=<day>/<city>.json.
    if run_date is not None:
        target_dir = raw_dir / f"date={run_date}"
        raw_files = sorted(target_dir.rglob("*.json"))
        if not raw_files:
            raise FileNotFoundError(f"No raw JSON files found under {target_dir}")
        return raw_files

    if include_history:
        raw_files = sorted(raw_dir.rglob("*.json"))
        if not raw_files:
            raise FileNotFoundError(f"No raw JSON files found under {raw_dir}")
        return raw_files

    date_dirs = sorted(path for path in raw_dir.glob("date=*") if path.is_dir())
    if not date_dirs:
        raise FileNotFoundError(f"No date partitions found under {raw_dir}")

    latest_dir = date_dirs[-1]
    raw_files = sorted(latest_dir.rglob("*.json"))
    if not raw_files:
        raise FileNotFoundError(f"No raw JSON files found under {latest_dir}")
    return raw_files


def transform_raw_files(
    raw_dir: Path = RAW_DATA_DIR,
    output_path: Path | None = None,
    raw_files: Iterable[Path] | None = None,
    run_date: str | None = None,
    include_history: bool = False,
) -> Path:
    selected_raw_files = (
        sorted(raw_files)
        if raw_files is not None
        else list_raw_weather_files(raw_dir, run_date, include_history)
    )

    # Đọc file là nghẽn I/O (mở từng JSON nhỏ trên Windows rất chậm), nên đọc song
    # song bằng thread pool. executor.map giữ nguyên thứ tự input để output ổn định.
    if len(selected_raw_files) > 1:
        max_workers = min(32, (os.cpu_count() or 4) * 4)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            records = list(executor.map(normalize_weather_record, selected_raw_files))
    else:
        records = [normalize_weather_record(raw_path) for raw_path in selected_raw_files]
    df = pd.DataFrame(records)
    df["observation_time"] = pd.to_datetime(df["observation_time"])
    df["inserted_at"] = pd.to_datetime(df["inserted_at"])

    if output_path is None:
        output_path = CLEANED_DATA_DIR / "weather_observations.csv"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, encoding="utf-8")
    print(
        f"Saved cleaned weather table: {output_path} "
        f"({len(df)} rows from {len(selected_raw_files)} raw files)"
    )
    return output_path
