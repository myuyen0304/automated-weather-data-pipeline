from __future__ import annotations

import pandas as pd
import pytest

from config import CITIES
from data_quality import validate_weather_observations


def _valid_weather_frame() -> pd.DataFrame:
    rows = []
    for city in CITIES:
        rows.append(
            {
                "city": city["city"],
                "country": city["country"],
                "latitude": city["latitude"],
                "longitude": city["longitude"],
                "observation_time": "2026-06-13T08:30",
                "temperature": 30.5,
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
                "is_day": True,
                "inserted_at": "2026-06-13T08:31:00",
            }
        )
    return pd.DataFrame(rows)


def test_validate_weather_observations_accepts_complete_batch() -> None:
    result = validate_weather_observations(_valid_weather_frame())

    assert result.row_count == len(CITIES)
    assert result.observation_dates == 1
    assert result.expected_city_count == len(CITIES)


def test_validate_weather_observations_rejects_missing_city() -> None:
    df = _valid_weather_frame().iloc[:-1].copy()

    with pytest.raises(ValueError, match="missing configured cities"):
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
