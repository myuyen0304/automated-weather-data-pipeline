from __future__ import annotations

import json
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
    return {
        "latitude": city_config["latitude"],
        "longitude": city_config["longitude"],
        "current": ",".join(CURRENT_WEATHER_FIELDS),
        "timezone": WEATHER_TIMEZONE,
        "forecast_days": 1,
    }


def fetch_current_weather(city_config: dict[str, Any]) -> dict[str, Any]:
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
) -> Path:
    if run_date is None:
        run_date = datetime.now(ZoneInfo(WEATHER_TIMEZONE)).date().isoformat()

    output_dir = RAW_DATA_DIR / f"date={run_date}"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"{slugify_city(city_config['city'])}.json"
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return output_path


def extract_city(city_config: dict[str, Any]) -> Path:
    payload = fetch_current_weather(city_config)
    return save_raw_weather_response(city_config, payload)


def extract_all_cities() -> list[Path]:
    output_paths = []
    for city_config in CITIES:
        output_path = extract_city(city_config)
        output_paths.append(output_path)
        print(f"Saved raw weather JSON for {city_config['city']}: {output_path}")
    return output_paths
