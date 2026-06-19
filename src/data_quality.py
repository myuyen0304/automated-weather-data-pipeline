from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from config import CITIES


REQUIRED_DASHBOARD_COLUMNS = [
    "city",
    "country",
    "latitude",
    "longitude",
    "observation_time",
    "temperature",
    "humidity",
    "apparent_temperature",
    "pressure_msl",
    "surface_pressure",
    "wind_speed",
    "wind_direction",
    "wind_gusts",
    "precipitation",
    "rain",
    "cloud_cover",
    "weather_code",
    "weather_condition",
    "is_day",
    "inserted_at",
]

EXPECTED_CITIES = {str(city["city"]) for city in CITIES}
EXPECTED_CITY_COUNT = len(EXPECTED_CITIES)

TEMPERATURE_MIN_C = -20
TEMPERATURE_MAX_C = 60

# Hourly grain: mỗi (city, ngày) phải đủ 24 giờ thì mart daily (và delivery risk
# suy ra từ nó) mới đúng — thiếu đúng giờ mưa -> total_rain thấp giả -> báo "Low"
# sai. Để strict=24 cho batch daily T-5 (thường đủ); hạ ngưỡng tại đây nếu Archive
# hay skip giờ null hợp lệ gây false-fail.
EXPECTED_HOURS_PER_DAY = 24


@dataclass(frozen=True)
class DataQualityResult:
    row_count: int
    observation_dates: int
    expected_city_count: int


def _format_values(values: set[object], limit: int = 8) -> str:
    ordered = sorted(str(value) for value in values)
    suffix = "" if len(ordered) <= limit else f", ... (+{len(ordered) - limit} more)"
    return ", ".join(ordered[:limit]) + suffix


def validate_weather_observations(df: pd.DataFrame) -> DataQualityResult:
    """Validate cleaned weather observations before loading them to PostgreSQL."""
    errors: list[str] = []

    missing_columns = [column for column in REQUIRED_DASHBOARD_COLUMNS if column not in df.columns]
    if missing_columns:
        errors.append(f"missing required columns: {', '.join(missing_columns)}")
        raise ValueError("Data quality check failed: " + "; ".join(errors))

    if df.empty:
        errors.append("batch has no rows")

    working = df.copy()
    working["observation_time"] = pd.to_datetime(working["observation_time"], errors="coerce")

    null_columns = [
        column
        for column in REQUIRED_DASHBOARD_COLUMNS
        if working[column].isna().any()
    ]
    if null_columns:
        errors.append(f"null values in required columns: {', '.join(null_columns)}")

    invalid_times = int(working["observation_time"].isna().sum())
    if invalid_times:
        errors.append(f"invalid observation_time values: {invalid_times}")

    observed_cities = set(working["city"].dropna().astype(str))
    missing_cities = EXPECTED_CITIES - observed_cities
    unknown_cities = observed_cities - EXPECTED_CITIES
    if missing_cities:
        errors.append(f"missing configured cities: {_format_values(missing_cities)}")
    if unknown_cities:
        errors.append(f"unknown cities: {_format_values(unknown_cities)}")

    duplicate_mask = working.duplicated(subset=["city", "observation_time"], keep=False)
    if duplicate_mask.any():
        duplicate_count = int(duplicate_mask.sum())
        errors.append(f"duplicate city/observation_time rows: {duplicate_count}")

    humidity = pd.to_numeric(working["humidity"], errors="coerce")
    invalid_humidity = humidity.isna() | ~humidity.between(0, 100)
    if invalid_humidity.any():
        errors.append(f"humidity outside 0-100: {int(invalid_humidity.sum())} row(s)")

    temperature = pd.to_numeric(working["temperature"], errors="coerce")
    invalid_temperature = temperature.isna() | ~temperature.between(
        TEMPERATURE_MIN_C,
        TEMPERATURE_MAX_C,
    )
    if invalid_temperature.any():
        errors.append(
            f"temperature outside {TEMPERATURE_MIN_C}..{TEMPERATURE_MAX_C}C: "
            f"{int(invalid_temperature.sum())} row(s)"
        )

    non_negative_columns = ["precipitation", "rain", "wind_speed", "wind_gusts", "cloud_cover"]
    for column in non_negative_columns:
        values = pd.to_numeric(working[column], errors="coerce")
        invalid = values.isna() | (values < 0)
        if invalid.any():
            errors.append(f"{column} has negative or non-numeric values: {int(invalid.sum())} row(s)")

    cloud_cover = pd.to_numeric(working["cloud_cover"], errors="coerce")
    invalid_cloud_cover = cloud_cover.isna() | ~cloud_cover.between(0, 100)
    if invalid_cloud_cover.any():
        errors.append(f"cloud_cover outside 0-100: {int(invalid_cloud_cover.sum())} row(s)")

    if not working["observation_time"].isna().all():
        working["observation_date"] = working["observation_time"].dt.date
        coverage = working.groupby("observation_date")["city"].nunique()
        incomplete_dates = coverage[coverage != EXPECTED_CITY_COUNT]
        if not incomplete_dates.empty:
            formatted = ", ".join(
                f"{date}={count}/{EXPECTED_CITY_COUNT}"
                for date, count in incomplete_dates.items()
            )
            errors.append(f"incomplete city coverage by date: {formatted}")

        hours_per_group = working.groupby(["city", "observation_date"])[
            "observation_time"
        ].apply(lambda times: times.dt.hour.nunique())
        incomplete_hours = hours_per_group[hours_per_group < EXPECTED_HOURS_PER_DAY]
        if not incomplete_hours.empty:
            items = [
                f"{city}@{date}={count}/{EXPECTED_HOURS_PER_DAY}h"
                for (city, date), count in incomplete_hours.items()
            ]
            suffix = "" if len(items) <= 8 else f", ... (+{len(items) - 8} more)"
            errors.append(
                "incomplete hourly coverage (expected "
                f"{EXPECTED_HOURS_PER_DAY} hours/city/day): "
                + ", ".join(items[:8])
                + suffix
            )

    if errors:
        raise ValueError("Data quality check failed: " + "; ".join(errors))

    observation_dates = int(working["observation_time"].dt.date.nunique())
    return DataQualityResult(
        row_count=len(working),
        observation_dates=observation_dates,
        expected_city_count=EXPECTED_CITY_COUNT,
    )
