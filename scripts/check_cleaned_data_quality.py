from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from config import CLEANED_DATA_DIR  # noqa: E402
from data_quality import validate_weather_observations  # noqa: E402


def main() -> None:
    cleaned_path = CLEANED_DATA_DIR / "weather_observations.csv"
    df = pd.read_csv(cleaned_path)
    result = validate_weather_observations(df)
    print(
        "Data quality checks passed: "
        f"{result.row_count} rows, "
        f"{result.observation_dates} observation date(s), "
        f"{result.expected_city_count} expected cities"
    )


if __name__ == "__main__":
    main()
