from __future__ import annotations

import pandas as pd
import pytest

from config import CITIES
from data_quality import (
    validate_agri_region_mapping,
    validate_weather_observations,
)


def _valid_weather_frame() -> pd.DataFrame:
    """One day of 24 hourly observations for every city (the hourly grain).

    Hourly grain is the rule the validator now enforces: each (city, day) must
    have all 24 hours, otherwise the daily/delivery-risk marts are skewed.
    """
    rows = []
    for city in CITIES:
        for hour in range(24):
            rows.append(
                {
                    "city": city["city"],
                    "country": city["country"],
                    "latitude": city["latitude"],
                    "longitude": city["longitude"],
                    "observation_time": f"2026-06-13T{hour:02d}:00",
                    "temperature": 24.0 + hour * 0.4,
                    "humidity": 75,
                    "apparent_temperature": 34.0,
                    "pressure_msl": 1008.0,
                    "surface_pressure": 1005.0,
                    "wind_speed": 8.5,
                    "wind_direction": 180,
                    "wind_gusts": 18.0,
                    "precipitation": 0.0,
                    "rain": 0.0,
                    "cloud_cover": 65,
                    "weather_code": 3,
                    "weather_condition": "Overcast",
                    "is_day": 6 <= hour < 18,
                    "inserted_at": "2026-06-13T23:59:00",
                }
            )
    return pd.DataFrame(rows)


def test_validate_weather_observations_accepts_complete_batch() -> None:
    result = validate_weather_observations(_valid_weather_frame())

    # 24 distinct hours per city, one date -> no duplicate, full coverage.
    assert result.row_count == len(CITIES) * 24
    assert result.observation_dates == 1
    assert result.expected_city_count == len(CITIES)


def test_validate_weather_observations_rejects_missing_city() -> None:
    # Drop every row of one city so it is genuinely absent (not just short hours).
    last_city = CITIES[-1]["city"]
    df = _valid_weather_frame()
    df = df[df["city"] != last_city].copy()

    with pytest.raises(ValueError, match="missing configured cities"):
        validate_weather_observations(df)


def test_validate_weather_observations_rejects_incomplete_hours() -> None:
    # Keep only 20 of the 24 hours for a single city -> incomplete hourly coverage.
    target_city = CITIES[0]["city"]
    df = _valid_weather_frame()
    drop_mask = (df["city"] == target_city) & (
        df["observation_time"] >= "2026-06-13T20:00"
    )
    df = df[~drop_mask].copy()

    with pytest.raises(ValueError, match="incomplete hourly coverage"):
        validate_weather_observations(df)


def test_validate_weather_observations_rejects_invalid_humidity() -> None:
    df = _valid_weather_frame()
    df.loc[0, "humidity"] = 140

    with pytest.raises(ValueError, match="humidity outside 0-100"):
        validate_weather_observations(df)


def test_validate_weather_observations_rejects_duplicate_city_time() -> None:
    df = pd.concat([_valid_weather_frame(), _valid_weather_frame().head(1)], ignore_index=True)

    with pytest.raises(ValueError, match="duplicate city/observation_time"):
        validate_weather_observations(df)


# --- Agriculture city -> crop mapping ----------------------------------------

def _valid_agri_mapping_frame() -> pd.DataFrame:
    """Mỗi city 1 cây (coffee, primary), area_share NULL — hợp lệ tối thiểu."""
    return pd.DataFrame(
        {
            "city": [city["city"] for city in CITIES],
            "agri_region": ["Test Region"] * len(CITIES),
            "crop": ["coffee"] * len(CITIES),
            "crop_role": ["primary"] * len(CITIES),
            "area_share": [pd.NA] * len(CITIES),
            "crop_source": ["test source"] * len(CITIES),
        }
    )


def test_validate_agri_region_mapping_accepts_complete_city_mapping() -> None:
    assert validate_agri_region_mapping(_valid_agri_mapping_frame()) == len(CITIES)


def test_validate_agri_region_mapping_accepts_multiple_crops_per_city() -> None:
    """Đa cây/tỉnh: thêm dòng (city, crop) khác cây -> hợp lệ, không phải trùng."""
    base = _valid_agri_mapping_frame()
    extra = base.head(1).copy()
    extra["crop"] = "vegetable"
    extra["crop_role"] = "secondary"  # cây phụ -> city đầu vẫn đúng 1 primary
    df = pd.concat([base, extra], ignore_index=True)

    assert validate_agri_region_mapping(df) == len(CITIES) + 1


def test_validate_agri_region_mapping_rejects_missing_city() -> None:
    df = _valid_agri_mapping_frame().iloc[:-1].copy()

    with pytest.raises(ValueError, match="missing configured cities"):
        validate_agri_region_mapping(df)


def test_validate_agri_region_mapping_rejects_duplicate_city_crop_pair() -> None:
    df = pd.concat(
        [_valid_agri_mapping_frame(), _valid_agri_mapping_frame().head(1)],
        ignore_index=True,
    )

    with pytest.raises(ValueError, match=r"duplicate \(city, crop\)"):
        validate_agri_region_mapping(df)


def test_validate_agri_region_mapping_rejects_unknown_crop() -> None:
    df = _valid_agri_mapping_frame()
    df.loc[0, "crop"] = "dragonfruit"  # not seeded in dim_crop

    with pytest.raises(ValueError, match="unknown crops"):
        validate_agri_region_mapping(df)


def test_validate_agri_region_mapping_rejects_area_share_out_of_range() -> None:
    df = _valid_agri_mapping_frame()
    df.loc[0, "area_share"] = 1.5  # tỷ trọng phải trong (0, 1]

    with pytest.raises(ValueError, match="area_share out of range"):
        validate_agri_region_mapping(df)


def test_validate_agri_region_mapping_rejects_blank_crop_source() -> None:
    """crop_source là căn cứ hiện diện cây -> không được để trống nếu có cột."""
    df = _valid_agri_mapping_frame()
    df.loc[0, "crop_source"] = ""

    with pytest.raises(ValueError, match="crop_source"):
        validate_agri_region_mapping(df)


def test_validate_agri_region_mapping_rejects_incomplete_share_sum() -> None:
    """Khi MỌI dòng của một city có share thì tổng phải ~1 (config đầy đủ)."""
    base = _valid_agri_mapping_frame()
    first_city = base.loc[0, "city"]
    # city đầu: 2 cây, share 0.5 + 0.2 = 0.7 != 1.0
    base.loc[0, "area_share"] = 0.5
    extra = base.head(1).copy()
    extra["crop"] = "vegetable"
    extra["crop_role"] = "secondary"  # giữ đúng 1 primary -> test fail vì tổng share, không phải role
    extra["area_share"] = 0.2
    df = pd.concat([base, extra], ignore_index=True)

    with pytest.raises(ValueError, match="sums to"):
        validate_agri_region_mapping(df)
    assert first_city  # giữ tham chiếu cho rõ ý định test


def test_validate_agri_region_mapping_rejects_invalid_crop_role() -> None:
    df = _valid_agri_mapping_frame()
    df.loc[0, "crop_role"] = "dominant"  # phải là primary/secondary

    with pytest.raises(ValueError, match="invalid crop_role"):
        validate_agri_region_mapping(df)


def test_validate_agri_region_mapping_rejects_blank_crop_role() -> None:
    df = _valid_agri_mapping_frame()
    df.loc[0, "crop_role"] = ""

    with pytest.raises(ValueError, match="crop_role"):
        validate_agri_region_mapping(df)


def test_validate_agri_region_mapping_rejects_two_primary_crops() -> None:
    """Đa cây nhưng 2 dòng cùng primary -> sai (mỗi tỉnh đúng 1 cây chủ lực)."""
    base = _valid_agri_mapping_frame()
    extra = base.head(1).copy()
    extra["crop"] = "vegetable"
    extra["crop_role"] = "primary"  # city đầu giờ có 2 primary
    df = pd.concat([base, extra], ignore_index=True)

    with pytest.raises(ValueError, match="exactly 1 primary"):
        validate_agri_region_mapping(df)


def test_validate_agri_region_mapping_rejects_zero_primary_crops() -> None:
    """Tỉnh có cây nhưng không cây nào primary -> sai (index không bắt được case này)."""
    df = _valid_agri_mapping_frame()
    df.loc[0, "crop_role"] = "secondary"  # city đầu giờ 0 primary

    with pytest.raises(ValueError, match="exactly 1 primary"):
        validate_agri_region_mapping(df)
