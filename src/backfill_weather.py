from __future__ import annotations

import argparse
import time
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import requests
from requests import HTTPError, RequestException

from config import CITIES, CURRENT_WEATHER_FIELDS, WEATHER_TIMEZONE
from extract_weather import build_hourly_payloads, save_raw_weather_response


# Archive API trả mảng "hourly" thay vì block "current" của Forecast API.
ARCHIVE_BASE_URL = "https://archive-api.open-meteo.com/v1/archive"

# is_day KHÔNG có trong archive hourly -> không request; build_hourly_payloads tự
# suy is_day theo giờ địa phương (derive_is_day) cho cả 24 giờ.
HOURLY_FIELDS = [field for field in CURRENT_WEATHER_FIELDS if field != "is_day"]

# Độ trễ ERA5: dữ liệu archive thường trễ ~5 ngày so với hiện tại.
ERA5_DELAY_DAYS = 5


def fetch_archive(
    city_config: dict[str, Any],
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    """Gọi Open-Meteo Archive API cho một city, cover cả khoảng [start, end].

    Retry mirror theo extract_weather.fetch_forecast_hourly: 4xx raise ngay,
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


def backfill_city(
    city_config: dict[str, Any],
    start_date: str,
    end_date: str,
) -> tuple[int, list[str]]:
    """Backfill một city: fetch -> tách 24 giờ/ngày -> ghi mỗi giờ một raw file.

    Tái dùng build_hourly_payloads (chung với forecast) và save_raw_weather_response
    để raw nằm đúng layout data/raw/open-meteo/date=<day>/hour=HH/<slug>.json.
    Trả (số_file_đã_ghi, danh_sách_giờ_bị_bỏ_do_thiếu_dữ_liệu).
    """
    archive_json = fetch_archive(city_config, start_date, end_date)
    payloads, skipped_hours = build_hourly_payloads(
        archive_json, HOURLY_FIELDS, start_date=start_date, end_date=end_date
    )

    for day, hour, payload in payloads:
        save_raw_weather_response(city_config, payload, run_date=day, run_hour=hour)

    return len(payloads), skipped_hours


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
        f"(all 24 hours each day)..."
    )

    total_files = 0
    total_skipped = 0
    for city_config in cities:
        written, skipped_hours = backfill_city(city_config, args.start_date, end_date)
        total_files += written
        total_skipped += len(skipped_hours)
        skipped_note = (
            f", skipped {len(skipped_hours)} null hour(s)" if skipped_hours else ""
        )
        print(f"  {city_config['city']}: wrote {written} raw file(s){skipped_note}")
        if args.sleep:
            time.sleep(args.sleep)

    print(
        f"Done: {total_files} raw file(s) for {len(cities)} cities "
        f"({total_skipped} hour(s) skipped due to missing data)."
    )
    print("Next: python src/main.py --skip-extract --all-raw --load")


if __name__ == "__main__":
    main()
