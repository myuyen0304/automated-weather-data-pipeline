from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from data_quality import validate_weather_observations  # noqa: E402
from transform_weather import read_cleaned_dataframe  # noqa: E402


def main() -> None:
    # read_cleaned_dataframe tự fallback sang MinIO khi cleaned không ghi local.
    df = read_cleaned_dataframe()
    result = validate_weather_observations(df)
    print(
        "Data quality checks passed: "
        f"{result.row_count} rows, "
        f"{result.observation_dates} observation date(s), "
        f"{result.expected_city_count} expected cities"
    )


if __name__ == "__main__":
    main()
