from __future__ import annotations

import csv
import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CITIES_FILE= PROJECT_ROOT / "data" / "cities.csv"
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw" / "open-meteo"
CLEANED_DATA_DIR = PROJECT_ROOT / "data" / "cleaned"
SQL_DIR = PROJECT_ROOT / "sql"

load_dotenv(PROJECT_ROOT / ".env")

OPEN_METEO_BASE_URL = os.getenv(
    "OPEN_METEO_BASE_URL",
    "https://api.open-meteo.com/v1/forecast",
)
WEATHER_TIMEZONE = os.getenv("WEATHER_TIMEZONE", "Asia/Ho_Chi_Minh")

# --- PostgreSQL connection (khớp với docker-compose.yml và .env.example) ---
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "weather_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")


def get_db_url() -> str:
    """Chuỗi kết nối SQLAlchemy cho PostgreSQL (dùng driver psycopg2).

    Ví dụ: postgresql+psycopg2://postgres:postgres@localhost:5432/weather_db
    """
    return (
        f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )

CURRENT_WEATHER_FIELDS = [
    "temperature_2m",
    "relative_humidity_2m",
    "apparent_temperature",
    "precipitation",
    "rain",
    "weather_code",
    "cloud_cover",
    "pressure_msl",
    "surface_pressure",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "is_day",
]

def load_cities(path: Path) -> list[dict[str, object]]:
    """Load city coordinates from CSV for API extraction."""
    cities: list[dict[str, object]] = []
    with path.open(encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file, skipinitialspace=True)
        for row in reader:
            clean_row = {key.strip(): value.strip() for key, value in row.items()}
            cities.append(
                {
                    "city": clean_row["city"],
                    "country": clean_row["country"],
                    "latitude": float(clean_row["latitude"]),
                    "longitude": float(clean_row["longitude"]),
                }
            )
    return cities


CITIES = load_cities(CITIES_FILE)

CITY_BY_SLUG = {
    city["city"].strip().lower().replace(" ", "_"): city
    for city in CITIES
}
