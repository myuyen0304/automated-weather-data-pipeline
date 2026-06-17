from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests
from requests import HTTPError, RequestException

from config import (
    CITIES,
    CURRENT_WEATHER_FIELDS,
    OPEN_METEO_BASE_URL,
    RAW_DATA_DIR,
    WEATHER_TIMEZONE,
)


def slugify_city(city: str) -> str:
    slug = city.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    return slug.strip("_")


def build_open_meteo_params(city_config: dict[str, Any]) -> dict[str, Any]:
    # Lấy block "hourly" (24 mốc giờ/ngày) thay vì "current" (1 snapshot) để mỗi
    # ngày có đủ biên độ nhiệt cho mart MAX/MIN/AVG. forecast_days=1 = ngày hôm nay.
    return {
        "latitude": city_config["latitude"],
        "longitude": city_config["longitude"],
        "hourly": ",".join(CURRENT_WEATHER_FIELDS),
        "timezone": WEATHER_TIMEZONE,
        "forecast_days": 1,
    }


def derive_is_day(
    hour_local: int,
    api_value: object | None = None,
    time_str: str | None = None,
    sun_window: tuple[str, str] | None = None,
) -> int:
    """is_day cho một mốc giờ, theo thứ tự ưu tiên độ chính xác:

    1. Giá trị is_day từ API (Forecast hourly có sẵn).
    2. So mốc giờ với sunrise/sunset thực tế của ngày đó (Archive request thêm
       daily=sunrise,sunset). sun_window = (sunrise_iso, sunset_iso) cùng timezone
       nên so sánh chuỗi ISO cùng định dạng là đủ và đúng.
    3. Fallback cuối: heuristic 06:00-18:00 khi không có cả hai nguồn trên.
    """
    if api_value is not None:
        return int(api_value)
    if time_str is not None and sun_window is not None:
        sunrise, sunset = sun_window
        return 1 if sunrise <= time_str < sunset else 0
    return 1 if 6 <= hour_local < 18 else 0


def build_sun_windows(daily: dict[str, Any] | None) -> dict[str, tuple[str, str]]:
    """Map ngày -> (sunrise_iso, sunset_iso) từ block daily của Open-Meteo.

    Trả dict rỗng nếu response không kèm sunrise/sunset (vd Forecast path), khi đó
    derive_is_day tự rơi về api_value hoặc heuristic.
    """
    if not daily:
        return {}
    times = daily.get("time") or []
    sunrises = daily.get("sunrise") or []
    sunsets = daily.get("sunset") or []
    return {
        day: (sunrise, sunset)
        for day, sunrise, sunset in zip(times, sunrises, sunsets)
        if sunrise and sunset
    }


def build_hourly_payloads(
    response: dict[str, Any],
    fields: list[str],
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[list[tuple[str, str, dict[str, Any]]], list[str]]:
    """Tách block "hourly" thành nhiều payload shape "current" (mỗi giờ một bản).

    Mỗi payload giống hệt output forecast cũ ({latitude, longitude, current:{...}})
    nên transform/load chạy lại không cần sửa. Trả (payloads, skipped_hours) với
    payloads = list các (day 'YYYY-MM-DD', hour 'HH', payload). Bỏ giờ thiếu nhiệt độ.
    """
    hourly = response["hourly"]
    times = hourly["time"]
    is_day_series = hourly.get("is_day")
    # Archive request kèm daily=sunrise,sunset -> suy is_day theo khung mặt trời
    # thực tế của từng ngày thay vì mốc cứng 06-18h.
    sun_by_day = build_sun_windows(response.get("daily"))

    payloads: list[tuple[str, str, dict[str, Any]]] = []
    skipped_hours: list[str] = []

    for idx, time_str in enumerate(times):
        day = time_str[:10]
        if start_date is not None and day < start_date:
            continue
        if end_date is not None and day > end_date:
            continue

        if hourly.get("temperature_2m", [None] * len(times))[idx] is None:
            skipped_hours.append(time_str)
            continue

        current = {
            field: hourly[field][idx]
            for field in fields
            if field in hourly
        }
        current["time"] = time_str
        hour_local = int(time_str[11:13])
        api_is_day = is_day_series[idx] if is_day_series is not None else None
        current["is_day"] = derive_is_day(
            hour_local,
            api_is_day,
            time_str=time_str,
            sun_window=sun_by_day.get(day),
        )

        payload = {
            "latitude": response.get("latitude"),
            "longitude": response.get("longitude"),
            "current": current,
        }
        payloads.append((day, f"{hour_local:02d}", payload))

    return payloads, skipped_hours


def fetch_forecast_hourly(city_config: dict[str, Any]) -> dict[str, Any]:
    session = requests.Session()
    session.trust_env = False

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            response = session.get(
                OPEN_METEO_BASE_URL,
                params=build_open_meteo_params(city_config),
                timeout=45,
            )
            response.raise_for_status()
            return response.json()
        except HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code is not None and status_code < 500:
                raise
            if attempt == max_attempts:
                raise
            wait_seconds = attempt * 3
            print(
                f"Open-Meteo returned HTTP {status_code} for "
                f"{city_config['city']}; retrying in {wait_seconds}s..."
            )
            time.sleep(wait_seconds)
        except RequestException as exc:
            if attempt == max_attempts:
                raise
            wait_seconds = attempt * 3
            print(
                f"Open-Meteo request failed for {city_config['city']} "
                f"({exc}); retrying in {wait_seconds}s..."
            )
            time.sleep(wait_seconds)

    raise RuntimeError(f"Failed to fetch weather for {city_config['city']}")


def save_raw_weather_response(
    city_config: dict[str, Any],
    payload: dict[str, Any],
    run_date: str | None = None,
    run_hour: str | None = None,
) -> Path:
    if run_date is None:
        run_date = datetime.now(ZoneInfo(WEATHER_TIMEZONE)).date().isoformat()

    # Layout hourly: date=<day>/hour=HH/<city>.json để 24 file/ngày không ghi đè nhau.
    output_dir = RAW_DATA_DIR / f"date={run_date}"
    if run_hour is not None:
        output_dir = output_dir / f"hour={run_hour}"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"{slugify_city(city_config['city'])}.json"
    temp_path = output_path.with_name(f".{output_path.name}.{os.getpid()}.tmp")
    try:
        temp_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        temp_path.replace(output_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return output_path


def extract_city(city_config: dict[str, Any]) -> list[Path]:
    """Fetch hourly forecast cho 1 city và ghi mỗi giờ thành 1 raw file."""
    response = fetch_forecast_hourly(city_config)
    payloads, _skipped = build_hourly_payloads(response, CURRENT_WEATHER_FIELDS)
    return [
        save_raw_weather_response(city_config, payload, run_date=day, run_hour=hour)
        for day, hour, payload in payloads
    ]


def extract_all_cities() -> list[Path]:
    output_paths: list[Path] = []
    for city_config in CITIES:
        city_paths = extract_city(city_config)
        output_paths.extend(city_paths)
        print(
            f"Saved {len(city_paths)} hourly raw file(s) for {city_config['city']}"
        )
    return output_paths
