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

REQUIRED_AGRI_MAPPING_COLUMNS = [
    "city",
    "agri_region",
    "main_crop_group",
]

# Cây trồng hợp lệ = đúng các crop được seed trong dim_crop (sql/12). Mapping trỏ
# tới crop ngoài tập này sẽ bị JOIN rỗng ở mart -> chặn sớm tại DQ gate.
KNOWN_CROPS = {"coffee", "vegetable", "rice"}

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

    # Biến nông học (FAO-56): chỉ kiểm range trên giá trị NON-NULL. Null được dung
    # thứ ở đây (vd ô lưới ven biển hiếm khi thiếu soil) để không chặn oan load
    # weather lõi; mart tưới tự bỏ dòng thiếu khi JOIN. Đây là DQ trên INPUT.
    if "et0_fao" in working.columns:
        et0 = pd.to_numeric(working["et0_fao"], errors="coerce")
        invalid_et0 = et0.notna() & (et0 < 0)
        if invalid_et0.any():
            errors.append(f"et0_fao negative: {int(invalid_et0.sum())} row(s)")
    if "soil_moisture" in working.columns:
        soil_moisture = pd.to_numeric(working["soil_moisture"], errors="coerce")
        invalid_sm = soil_moisture.notna() & ~soil_moisture.between(0, 1)
        if invalid_sm.any():
            errors.append(f"soil_moisture outside 0-1 m3/m3: {int(invalid_sm.sum())} row(s)")
    if "soil_temperature" in working.columns:
        soil_temp = pd.to_numeric(working["soil_temperature"], errors="coerce")
        invalid_st = soil_temp.notna() & ~soil_temp.between(TEMPERATURE_MIN_C, TEMPERATURE_MAX_C)
        if invalid_st.any():
            errors.append(
                f"soil_temperature outside {TEMPERATURE_MIN_C}..{TEMPERATURE_MAX_C}C: "
                f"{int(invalid_st.sum())} row(s)"
            )
    if "shortwave_radiation" in working.columns:
        shortwave = pd.to_numeric(working["shortwave_radiation"], errors="coerce")
        invalid_sw = shortwave.notna() & (shortwave < 0)
        if invalid_sw.any():
            errors.append(f"shortwave_radiation negative: {int(invalid_sw.sum())} row(s)")

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


def _require_columns(df: pd.DataFrame, required_columns: list[str], label: str) -> None:
    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        raise ValueError(
            f"{label} data quality check failed: "
            f"missing required columns: {', '.join(missing_columns)}"
        )


def _blank_string_mask(series: pd.Series) -> pd.Series:
    return series.isna() | series.astype(str).str.strip().eq("")


def validate_agri_region_mapping(df: pd.DataFrame) -> int:
    """Validate city -> agriculture region/crop mapping before loading it."""
    _require_columns(df, REQUIRED_AGRI_MAPPING_COLUMNS, "Agriculture mapping")
    errors: list[str] = []

    if df.empty:
        errors.append("mapping batch has no rows")

    working = df[REQUIRED_AGRI_MAPPING_COLUMNS].copy()
    for column in REQUIRED_AGRI_MAPPING_COLUMNS:
        blank = _blank_string_mask(working[column])
        if blank.any():
            errors.append(f"blank values in {column}: {int(blank.sum())}")

    duplicate_cities = working.duplicated(subset=["city"], keep=False)
    if duplicate_cities.any():
        errors.append(f"duplicate city mapping rows: {int(duplicate_cities.sum())}")

    observed_cities = set(working["city"].dropna().astype(str).str.strip())
    missing_cities = EXPECTED_CITIES - observed_cities
    unknown_cities = observed_cities - EXPECTED_CITIES
    if missing_cities:
        errors.append(f"missing configured cities: {_format_values(missing_cities)}")
    if unknown_cities:
        errors.append(f"unknown cities: {_format_values(unknown_cities)}")

    # Crop phải nằm trong dim_crop (KNOWN_CROPS) — nếu không, JOIN ở mart sẽ rỗng.
    observed_crops = set(working["main_crop_group"].dropna().astype(str).str.strip())
    unknown_crops = observed_crops - KNOWN_CROPS
    if unknown_crops:
        errors.append(f"unknown crops (not in dim_crop): {_format_values(unknown_crops)}")

    if errors:
        raise ValueError("Agriculture mapping data quality check failed: " + "; ".join(errors))

    return len(working)
