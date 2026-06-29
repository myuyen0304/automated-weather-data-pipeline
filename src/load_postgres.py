from __future__ import annotations

"""Load lớp: nạp dữ liệu cleaned vào PostgreSQL và chạy SQL mô hình hóa.

Luồng:
    file cleaned CSV  ->  bảng staging (stg_weather_observations)
    bảng staging      ->  star schema (dim_location, dim_date, fact_weather_observation)
                          thông qua script sql/04_load_star_schema.sql

Cần PostgreSQL đang chạy (xem docker-compose.yml). Nếu chưa bật DB, bước này
sẽ báo lỗi kết nối — extract/transform vẫn chạy độc lập được mà không cần DB.
"""

from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from config import CLEANED_DATA_DIR, SQL_DIR, get_db_url
from data_quality import validate_weather_observations
from transform_weather import read_cleaned_dataframe


STAGING_TABLE = "stg_weather_observations"

# Các cột khớp đúng với bảng staging (bỏ cột source_file vốn chỉ dùng để truy vết).
STAGING_COLUMNS = [
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
    "et0_fao",
    "soil_moisture",
    "soil_temperature",
    "shortwave_radiation",
    "weather_code",
    "weather_condition",
    "is_day",
    "inserted_at",
]


def get_engine() -> Engine:
    """Tạo SQLAlchemy engine từ thông tin trong .env / config."""
    return create_engine(get_db_url(), future=True)


def run_sql_file(sql_path: Path, engine: Engine | None = None) -> None:
    """Chạy toàn bộ một file .sql (dùng cho DDL và script mô hình hóa)."""
    engine = engine or get_engine()
    sql_text = Path(sql_path).read_text(encoding="utf-8")
    with engine.begin() as conn:
        conn.execute(text(sql_text))
    print(f"Executed SQL file: {sql_path}")


def init_database(engine: Engine | None = None) -> None:
    """Tạo schema (chạy 1 lần): staging, dimensions, fact, agri dims.

    Lưu ý: KHÔNG chạy 04_load_star_schema.sql ở đây vì script đó nạp dữ liệu
    từ staging và nên chạy mỗi lần pipeline (xem load_to_postgres).

    Tầng MART (mart_daily/weekly_weather_summary từ sql/05, mart_irrigation_need
    từ sql/08) KHÔNG còn tạo ở đây — đã chuyển sang dbt (weather_dbt/), dựng bằng
    `dbt build`. sql/05 và sql/08 giữ lại làm tham chiếu nhưng không nằm trong
    init nữa. Vì thế init chỉ cần tạo bảng nguồn (fact + dim) mà dbt sẽ đọc qua
    source(); 06 vẫn cần để seed dim_crop + tạo dim_agri_region.
    """
    engine = engine or get_engine()
    for name in (
        "01_create_staging_table.sql",
        "02_create_dimensions.sql",
        "03_create_fact_table.sql",
        "06_create_agriculture_schema.sql",    # agri mapping + dim_crop (FAO-56 hằng số có nguồn)
    ):
        run_sql_file(SQL_DIR / name, engine)


def load_cleaned_to_staging(
    cleaned_path: Path | None = None,
    engine: Engine | None = None,
) -> int:
    """Đọc file cleaned CSV và append vào bảng staging. Trả về số dòng đã nạp."""
    cleaned_path = cleaned_path or (CLEANED_DATA_DIR / "weather_observations.csv")
    engine = engine or get_engine()

    # Đọc qua helper để có fallback MinIO khi cleaned không ghi local
    # (CLEANED_LOCAL_WRITE_ENABLED=false).
    df = read_cleaned_dataframe(cleaned_path)
    missing_columns = [column for column in STAGING_COLUMNS if column not in df.columns]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"Cleaned CSV is missing required staging columns: {missing}")

    if df.empty:
        raise ValueError(f"Cleaned CSV has no rows: {cleaned_path}")

    # Chỉ giữ các cột thuộc bảng staging, theo đúng thứ tự.
    df = df[STAGING_COLUMNS]
    quality_result = validate_weather_observations(df)
    print(
        "Data quality checks passed: "
        f"{quality_result.row_count} rows, "
        f"{quality_result.observation_dates} observation date(s), "
        f"{quality_result.expected_city_count} expected cities"
    )

    # Staging là buffer cho batch HIỆN TẠI: xóa sạch trước khi nạp để không
    # tích lũy dữ liệu cũ qua nhiều lần chạy. Star schema vẫn an toàn vì script
    # 04 upsert theo (location_id, observation_time) để không tạo trùng và để
    # Archive data có thể thay thế forecast data cũ nếu cùng mốc giờ.
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {STAGING_TABLE}"))

    df.to_sql(STAGING_TABLE, engine, if_exists="append", index=False)
    print(f"Loaded {len(df)} rows into {STAGING_TABLE}")
    return len(df)


def populate_star_schema(engine: Engine | None = None) -> None:
    """Chạy 04_load_star_schema.sql để nạp dim + fact từ staging."""
    run_sql_file(SQL_DIR / "04_load_star_schema.sql", engine)


def load_to_postgres(
    cleaned_path: Path | None = None,
    engine: Engine | None = None,
) -> None:
    """Bước load đầy đủ trong pipeline: staging -> star schema.

    Giả định schema đã được tạo trước bằng init_database() (chạy 1 lần).
    """
    engine = engine or get_engine()
    load_cleaned_to_staging(cleaned_path, engine)
    populate_star_schema(engine)


if __name__ == "__main__":
    # Chạy trực tiếp file này để init schema rồi load dữ liệu hiện có.
    eng = get_engine()
    init_database(eng)
    load_to_postgres(engine=eng)
