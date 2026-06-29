from __future__ import annotations

import io
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import pandas as pd

from config import (
    CLEANED_DATA_DIR,
    CLEANED_LOCAL_WRITE_ENABLED,
    CITIES,
    RAW_DATA_DIR,
    S3_BUCKET,
    S3_RAW_PREFIX,
    WEATHER_TIMEZONE,
)
from extract_weather import slugify_city
from object_storage import (
    is_object_storage_enabled,
    list_object_keys,
    object_key_for_path,
    put_bytes_object,
    read_bytes_object,
    read_json_object,
    upload_file,
)


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


def normalize_weather_payload(
    payload: dict[str, Any],
    *,
    city_slug: str,
    source_file: str,
) -> dict[str, Any]:
    city_config = CITY_BY_FILE_STEM.get(city_slug)
    if city_config is None:
        raise ValueError(f"Cannot map raw source to configured city: {source_file}")

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
        # Biến nông học (FAO-56): et0_fao mm/giờ, soil_moisture m3/m3, soil_temperature °C,
        # shortwave_radiation W/m². Đổ thẳng xuống staging/fact để mart tưới dùng.
        "et0_fao": current.get("et0_fao_evapotranspiration"),
        "soil_moisture": current.get("soil_moisture_0_to_7cm"),
        "soil_temperature": current.get("soil_temperature_0_to_7cm"),
        "shortwave_radiation": current.get("shortwave_radiation"),
        "weather_code": weather_code,
        "weather_condition": WEATHER_CODE_MAP.get(weather_code, "Unknown"),
        "is_day": bool(current.get("is_day")),
        "inserted_at": datetime.now(ZoneInfo(WEATHER_TIMEZONE)).isoformat(
            timespec="seconds"
        ),
        "source_file": source_file,
    }


def normalize_weather_record(raw_path: Path) -> dict[str, Any]:
    return normalize_weather_payload(
        read_raw_weather_file(raw_path),
        city_slug=raw_path.stem,
        source_file=str(raw_path),
    )


def normalize_weather_object(object_key: str) -> dict[str, Any]:
    return normalize_weather_payload(
        read_json_object(object_key),
        city_slug=Path(object_key).stem,
        source_file=f"s3://{S3_BUCKET}/{object_key}",
    )


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


def _date_partition_from_key(object_key: str) -> str | None:
    for part in object_key.split("/"):
        if part.startswith("date="):
            return part.removeprefix("date=")
    return None


def list_raw_weather_object_keys(
    run_date: str | None = None,
    include_history: bool = False,
) -> list[str]:
    if not is_object_storage_enabled():
        raise FileNotFoundError("Object storage is disabled.")

    raw_prefix = S3_RAW_PREFIX.rstrip("/")
    if run_date is not None:
        prefix = f"{raw_prefix}/date={run_date}/"
        keys = sorted(key for key in list_object_keys(prefix) if key.endswith(".json"))
        if not keys:
            raise FileNotFoundError(f"No raw JSON objects found under s3 prefix {prefix}")
        return keys

    keys = sorted(key for key in list_object_keys(raw_prefix) if key.endswith(".json"))
    if not keys:
        raise FileNotFoundError(f"No raw JSON objects found under s3 prefix {raw_prefix}")

    if include_history:
        return keys

    dates = sorted({date for key in keys if (date := _date_partition_from_key(key))})
    if not dates:
        raise FileNotFoundError(f"No date partitions found under s3 prefix {raw_prefix}")

    latest_date = dates[-1]
    return [
        key
        for key in keys
        if _date_partition_from_key(key) == latest_date
    ]


def transform_raw_files(
    raw_dir: Path = RAW_DATA_DIR,
    output_path: Path | None = None,
    parquet_output_path: Path | None = None,
    raw_files: Iterable[Path] | None = None,
    run_date: str | None = None,
    include_history: bool = False,
) -> Path:
    selected_raw_files: list[Path] = []
    selected_raw_keys: list[str] = []
    if raw_files is not None:
        selected_raw_files = sorted(raw_files)
    else:
        try:
            selected_raw_files = list_raw_weather_files(
                raw_dir,
                run_date,
                include_history,
            )
        except FileNotFoundError:
            selected_raw_keys = list_raw_weather_object_keys(run_date, include_history)

    # Đọc file là nghẽn I/O (mở từng JSON nhỏ trên Windows rất chậm), nên đọc song
    # song bằng thread pool. executor.map giữ nguyên thứ tự input để output ổn định.
    selected_count = len(selected_raw_files) + len(selected_raw_keys)
    if selected_raw_keys:
        normalize = normalize_weather_object
        selected_sources = selected_raw_keys
    else:
        normalize = normalize_weather_record
        selected_sources = selected_raw_files

    if selected_count > 1:
        max_workers = min(32, (os.cpu_count() or 4) * 4)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            records = list(executor.map(normalize, selected_sources))
    else:
        records = [normalize(source) for source in selected_sources]
    df = pd.DataFrame(records)
    df["observation_time"] = pd.to_datetime(df["observation_time"])
    df["inserted_at"] = pd.to_datetime(df["inserted_at"])

    if output_path is None:
        output_path = CLEANED_DATA_DIR / "weather_observations.csv"
    if parquet_output_path is None:
        parquet_output_path = output_path.with_suffix(".parquet")

    if CLEANED_LOCAL_WRITE_ENABLED:
        # Mặc định: ghi local rồi mirror lên object storage (no-op nếu storage tắt).
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False, encoding="utf-8")
        upload_file(output_path)

        try:
            df.to_parquet(parquet_output_path, index=False)
            upload_file(parquet_output_path)
            print(f"Saved cleaned Parquet table: {parquet_output_path}")
        except ImportError:
            print(
                "Skipped Parquet output because no Parquet engine is installed. "
                "Install dependencies from requirements.txt to enable it."
            )
        cleaned_target = str(output_path)
    else:
        # MinIO-only: serialize trong RAM rồi put thẳng, KHÔNG để bản cleaned trên SSD.
        if not is_object_storage_enabled():
            raise RuntimeError(
                "CLEANED_LOCAL_WRITE_ENABLED=false requires OBJECT_STORAGE_ENABLED=true "
                "so cleaned data has somewhere to be stored."
            )
        csv_key = object_key_for_path(output_path)
        put_bytes_object(
            df.to_csv(index=False).encode("utf-8"),
            csv_key,
            content_type="text/csv; charset=utf-8",
        )
        try:
            buffer = io.BytesIO()
            df.to_parquet(buffer, index=False)
            put_bytes_object(
                buffer.getvalue(),
                object_key_for_path(parquet_output_path),
                content_type="application/octet-stream",
            )
            print(
                "Saved cleaned Parquet object: "
                f"s3://{S3_BUCKET}/{object_key_for_path(parquet_output_path)}"
            )
        except ImportError:
            print(
                "Skipped Parquet output because no Parquet engine is installed. "
                "Install dependencies from requirements.txt to enable it."
            )
        cleaned_target = f"s3://{S3_BUCKET}/{csv_key}"

    print(
        f"Saved cleaned weather table: {cleaned_target} "
        f"({len(df)} rows from {selected_count} raw files)"
    )
    return output_path


def read_cleaned_dataframe(cleaned_path: Path | None = None) -> pd.DataFrame:
    """Đọc bảng cleaned, ưu tiên file local; fallback sang object storage.

    Khi CLEANED_LOCAL_WRITE_ENABLED=false, transform ghi cleaned thẳng lên MinIO
    nên không có bản local — lúc đó đọc theo object key (đối xứng với raw fallback
    trong transform_raw_files). Dùng chung cho load_postgres và DQ gate để không
    có chỗ nào đọc cleaned mà bỏ sót đường MinIO.
    """
    cleaned_path = cleaned_path or (CLEANED_DATA_DIR / "weather_observations.csv")
    if cleaned_path.exists():
        return pd.read_csv(cleaned_path)
    if is_object_storage_enabled():
        object_key = object_key_for_path(cleaned_path)
        return pd.read_csv(io.BytesIO(read_bytes_object(object_key)))
    raise FileNotFoundError(
        f"Cleaned file not found locally and object storage disabled: {cleaned_path}"
    )
