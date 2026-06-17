from __future__ import annotations

from extract_weather import build_hourly_payloads, derive_is_day


def _archive_response() -> dict[str, object]:
    """Fake Open-Meteo response with an hourly block spanning two days.

    Archive hourly has no is_day field, so build_hourly_payloads must derive it.
    """
    return {
        "latitude": 21.0245,
        "longitude": 105.8412,
        "hourly": {
            "time": [
                "2026-05-10T00:00",
                "2026-05-10T12:00",
                "2026-05-11T00:00",
            ],
            "temperature_2m": [24.0, 33.0, None],
            "relative_humidity_2m": [90, 60, 80],
        },
    }


def test_build_hourly_payloads_emits_one_payload_per_valid_hour() -> None:
    payloads, skipped = build_hourly_payloads(
        _archive_response(),
        ["temperature_2m", "relative_humidity_2m"],
        start_date="2026-05-10",
        end_date="2026-05-11",
    )

    # Two valid hours; the null-temperature hour is skipped.
    assert len(payloads) == 2
    assert skipped == ["2026-05-11T00:00"]

    days_hours = [(day, hour) for day, hour, _ in payloads]
    assert days_hours == [("2026-05-10", "00"), ("2026-05-10", "12")]

    times = [payload["current"]["time"] for _, _, payload in payloads]
    assert len(set(times)) == len(times)  # observation_time is distinct per hour


def test_build_hourly_payloads_derives_is_day_without_api_field() -> None:
    payloads, _ = build_hourly_payloads(
        _archive_response(),
        ["temperature_2m"],
        start_date="2026-05-10",
        end_date="2026-05-10",
    )

    by_hour = {hour: payload["current"]["is_day"] for _, hour, payload in payloads}
    assert by_hour["00"] == 0  # midnight -> night
    assert by_hour["12"] == 1  # noon -> day


def test_build_hourly_payloads_respects_date_window() -> None:
    payloads, skipped = build_hourly_payloads(
        _archive_response(),
        ["temperature_2m"],
        start_date="2026-05-10",
        end_date="2026-05-10",
    )

    # 2026-05-11 hour is outside the window, so it is neither emitted nor skipped.
    assert all(day == "2026-05-10" for day, _, _ in payloads)
    assert skipped == []


def test_derive_is_day_prefers_api_value() -> None:
    assert derive_is_day(0) == 0
    assert derive_is_day(12) == 1
    assert derive_is_day(0, api_value=1) == 1  # API value overrides the heuristic
    assert derive_is_day(12, api_value=0) == 0


def test_derive_is_day_uses_sunrise_sunset_window() -> None:
    window = ("2026-05-10T05:24", "2026-05-10T18:30")

    # Within the real solar window -> day, even for an hour the 06-18h heuristic
    # would call night.
    assert derive_is_day(5, time_str="2026-05-10T05:30", sun_window=window) == 1
    assert derive_is_day(18, time_str="2026-05-10T18:00", sun_window=window) == 1
    # Outside the window -> night, including an hour the heuristic would call day.
    assert derive_is_day(5, time_str="2026-05-10T05:00", sun_window=window) == 0
    assert derive_is_day(18, time_str="2026-05-10T18:45", sun_window=window) == 0


def test_build_hourly_payloads_uses_daily_sun_window() -> None:
    response = _archive_response()
    response["daily"] = {
        "time": ["2026-05-10"],
        "sunrise": ["2026-05-10T05:24"],
        "sunset": ["2026-05-10T18:30"],
    }

    payloads, _ = build_hourly_payloads(
        response,
        ["temperature_2m"],
        start_date="2026-05-10",
        end_date="2026-05-10",
    )

    by_hour = {hour: payload["current"]["is_day"] for _, hour, payload in payloads}
    assert by_hour["00"] == 0  # before sunrise
    assert by_hour["12"] == 1  # between sunrise and sunset
