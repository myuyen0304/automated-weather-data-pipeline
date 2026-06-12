from __future__ import annotations

import argparse
import time
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import requests
from requests import HTTPError, RequestException

from config import CITIES, CURRENT_WEATHER_FIELDS, WEATHER_TIMEZONE
from extract_weather import save_raw_weather_response


# Archive API trả mảng "hourly" thay vì block "current" của Forecast API.
ARCHIVE_BASE_URL = "https://archive-api.open-meteo.com/v1/archive"

# is_day KHÔNG có trong archive hourly -> không request; ta inject is_day=1 khi
# dựng payload vì backfill chọn mốc 12:00 trưa (Asia/Ho_Chi_Minh không có DST).
HOURLY_FIELDS = [field for field in CURRENT_WEATHER_FIELDS if field != "is_day"]

# Mốc giờ lấy cho mỗi ngày, và các giờ fallback nếu 12:00 bị null.
NOON_HOUR = 12
FALLBACK_HOURS = [12, 11, 13, 10, 14, 9, 15]

# Độ trễ ERA5: dữ liệu archive thường trễ ~5 ngày so với hiện tại.
ERA5_DELAY_DAYS = 5


def fetch_archive(
    city_config: dict[str, Any],
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    """Gọi Open-Meteo Archive API cho một city, cover cả khoảng [start, end].

    Retry mirror theo extract_weather.fetch_current_weather: 4xx raise ngay,
    5xx / lỗi mạng thì nghỉ rồi thử lại tối đa 3 lần.
    """
    session = requests.Session()
    session.trust_env = False

    params = {
        "latitude": city_config["latitude"],
        "longitude": city_config["longitude"],
        "start_date": start_date,
        "end_date": end_date,
        "hourly": ",".join(HOURLY_FIELDS),
        "timezone": WEATHER_TIMEZONE,
    }

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            response = session.get(ARCHIVE_BASE_URL, params=params, timeout=60)
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
                f"Archive API returned HTTP {status_code} for "
                f"{city_config['city']}; retrying in {wait_seconds}s..."
            )
            time.sleep(wait_seconds)
        except RequestException as exc:
            if attempt == max_attempts:
                raise
            wait_seconds = attempt * 3
            print(
                f"Archive API request failed for {city_config['city']} "
                f"({exc}); retrying in {wait_seconds}s..."
            )
            time.sleep(wait_seconds)

    raise RuntimeError(f"Failed to fetch archive weather for {city_config['city']}")


def _daterange(start_date: str, end_date: str) -> list[str]:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    days = []
    current = start
    while current <= end:
        days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def _pick_hour_index(
    index_by_time: dict[str, int],
    hourly: dict[str, Any],
    day: str,
) -> int | None:
    """Chọn index của 12:00 cho ngày; nếu temperature null thì thử giờ lân cận."""
    for hour in FALLBACK_HOURS:
        key = f"{day}T{hour:02d}:00"
        index = index_by_time.get(key)
        if index is None:
            continue
        if hourly["temperature_2m"][index] is not None:
            return index
    return None


def build_daily_payloads(
    archive_json: dict[str, Any],
    start_date: str,
    end_date: str,
) -> tuple[list[tuple[str, dict[str, Any]]], list[str]]:
    """Tách response archive thành payload shape "current", mỗi ngày một bản.

    Trả (payloads, skipped_days). Mỗi payload có shape giống output của forecast
    extractor để transform/load chạy lại không cần sửa.
    """
    hourly = archive_json["hourly"]
    times = hourly["time"]
    index_by_time = {time_str: idx for idx, time_str in enumerate(times)}

    payloads: list[tuple[str, dict[str, Any]]] = []
    skipped_days: list[str] = []

    for day in _daterange(start_date, end_date):
        index = _pick_hour_index(index_by_time, hourly, day)
        if index is None:
            skipped_days.append(day)
            continue

        current = {field: hourly[field][index] for field in HOURLY_FIELDS}
        current["time"] = times[index]
        current["is_day"] = 1  # mốc trưa luôn là ban ngày

        payload = {
            "latitude": archive_json.get("latitude"),
            "longitude": archive_json.get("longitude"),
            "current": current,
        }
        payloads.append((day, payload))

    return payloads, skipped_days


def backfill_city(
    city_config: dict[str, Any],
    start_date: str,
    end_date: str,
) -> tuple[int, list[str]]:
    """Backfill một city: fetch -> build -> ghi raw theo từng ngày.

    Tái dùng save_raw_weather_response để file raw nằm đúng layout
    data/raw/open-meteo/date=<day>/<slug>.json giống forecast extractor.
    """
    archive_json = fetch_archive(city_config, start_date, end_date)
    payloads, skipped_days = build_daily_payloads(archive_json, start_date, end_date)

    for day, payload in payloads:
        save_raw_weather_response(city_config, payload, run_date=day)

    return len(payloads), skipped_days


def _resolve_end_date(end_date: str) -> str:
    """Kẹp end_date về today - ERA5_DELAY_DAYS để tránh null do trễ reanalysis."""
    today = datetime.now(ZoneInfo(WEATHER_TIMEZONE)).date()
    safe_end = today - timedelta(days=ERA5_DELAY_DAYS)
    requested = date.fromisoformat(end_date)
    if requested > safe_end:
        print(
            f"Warning: end-date {end_date} is within the ERA5 delay window "
            f"(~{ERA5_DELAY_DAYS} days); clamping to {safe_end.isoformat()}."
        )
        return safe_end.isoformat()
    return end_date


def _select_cities(names: list[str] | None) -> list[dict[str, Any]]:
    if not names:
        return CITIES
    wanted = {name.strip().lower() for name in names}
    selected = [city for city in CITIES if city["city"].strip().lower() in wanted]
    if not selected:
        raise SystemExit(f"No configured city matches: {names}")
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill historical weather from the Open-Meteo Archive API "
        "into the same raw JSON layout the forecast extractor produces."
    )
    parser.add_argument("--start-date", required=True, help="Start date (YYYY-MM-DD).")
    parser.add_argument("--end-date", required=True, help="End date (YYYY-MM-DD).")
    parser.add_argument(
        "--cities",
        nargs="+",
        help="Filter by configured city name for smoke tests. Default: all 34 cities.",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.0,
        help="Seconds to sleep between city requests to reduce rate-limit pressure.",
    )
    args = parser.parse_args()

    end_date = _resolve_end_date(args.end_date)
    if date.fromisoformat(args.start_date) > date.fromisoformat(end_date):
        raise SystemExit(
            f"start-date {args.start_date} sau end-date {end_date}; không có gì để backfill."
        )

    cities = _select_cities(args.cities)
    print(
        f"Backfilling {len(cities)} cities from {args.start_date} to {end_date} "
        f"(picking {NOON_HOUR:02d}:00 each day)..."
    )

    total_files = 0
    total_skipped = 0
    for city_config in cities:
        written, skipped_days = backfill_city(city_config, args.start_date, end_date)
        total_files += written
        total_skipped += len(skipped_days)
        skipped_note = f", skipped {len(skipped_days)} null day(s)" if skipped_days else ""
        print(f"  {city_config['city']}: wrote {written} raw file(s){skipped_note}")
        if args.sleep:
            time.sleep(args.sleep)

    print(
        f"Done: {total_files} raw file(s) for {len(cities)} cities "
        f"({total_skipped} day(s) skipped due to missing data)."
    )
    print("Next: python src/main.py --skip-extract --all-raw --load")


if __name__ == "__main__":
    main()
