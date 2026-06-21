from __future__ import annotations

import csv
import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CITIES_FILE= PROJECT_ROOT / "data" / "cities.csv"
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw" / "open-meteo"
CLEANED_DATA_DIR = PROJECT_ROOT / "data" / "cleaned"
AGRICULTURE_DATA_DIR = PROJECT_ROOT / "data" / "agriculture"
SQL_DIR = PROJECT_ROOT / "sql"

load_dotenv(PROJECT_ROOT / ".env")

OPEN_METEO_BASE_URL = os.getenv(
    "OPEN_METEO_BASE_URL",
    "https://api.open-meteo.com/v1/forecast",
)
WEATHER_TIMEZONE = os.getenv("WEATHER_TIMEZONE", "Asia/Ho_Chi_Minh")

# Độ trễ ERA5 reanalysis (Archive API): dữ liệu thường trễ ~5 ngày so với hiện tại.
# Đây là nguồn runtime chung: backfill clamp end_date và Airflow DAG tính target date
# đều suy từ giá trị này. Lưu ý: DAG KHÔNG import config được lúc parse (src chỉ vào
# PYTHONPATH ở subprocess), nên DAG đọc lại cùng env ERA5_DELAY_DAYS thay vì import.
ERA5_DELAY_DAYS = int(os.getenv("ERA5_DELAY_DAYS", "5"))

# --- PostgreSQL connection (khớp với docker-compose.yml và .env.example) ---
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "weather_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")


def _env_flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


OBJECT_STORAGE_ENABLED = _env_flag("OBJECT_STORAGE_ENABLED")
RAW_LOCAL_WRITE_ENABLED = _env_flag("RAW_LOCAL_WRITE_ENABLED", "true")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "http://127.0.0.1:9000")
S3_BUCKET = os.getenv("S3_BUCKET", "weather-pipeline")
S3_REGION = os.getenv("S3_REGION", "us-east-1")
S3_RAW_PREFIX = os.getenv("S3_RAW_PREFIX", "raw/open-meteo").strip("/")
S3_CLEANED_PREFIX = os.getenv("S3_CLEANED_PREFIX", "cleaned").strip("/")


def get_db_url() -> str:
    """Chuỗi kết nối SQLAlchemy cho PostgreSQL (dùng driver psycopg2).

    Ví dụ: postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/weather_db
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
    # Biến nông học cho mart tưới FAO-56 (ETc = ET0 x Kc - mưa hiệu dụng, GDD).
    # Cả Forecast lẫn Archive API đều trả 4 biến này non-null cho toạ độ VN
    # (đã verify curl). et0 = mm/giờ (cộng 24 giờ = ET0 ngày), soil_moisture = m3/m3.
    "et0_fao_evapotranspiration",
    "soil_moisture_0_to_7cm",
    "soil_temperature_0_to_7cm",
    "shortwave_radiation",
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
