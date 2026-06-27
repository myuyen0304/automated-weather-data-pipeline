from __future__ import annotations

"""Load agriculture mapping (city -> region/crop) into PostgreSQL.

Flow:
    data/agriculture/agri_region_mapping.csv -> stg_agri_region_mapping
    staging -> dim_agri_region via sql/07_load_agriculture_schema.sql

Lưu ý: hằng số nông học (Kc, T_base) nằm trong dim_crop, được SEED ngay trong
sql/06 (DDL) với nguồn FAO-56 trích trong từng dòng — KHÔNG nạp từ CSV ở đây, để
không tái lập kiểu "số magic không nguồn".

Chạy sau khi base weather schema tồn tại. Nếu gộp với --load, main.py chạy
weather load trước để mart_daily_weather_summary có dữ liệu.
"""

from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from config import AGRICULTURE_DATA_DIR, SQL_DIR
from data_quality import validate_agri_region_mapping
from load_postgres import get_engine, run_sql_file


AGRI_MAPPING_COLUMNS = [
    "city", "agri_region", "crop", "crop_role", "area_share", "crop_source", "is_flagship",
]


def _read_required_csv(csv_path: Path, columns: list[str]) -> pd.DataFrame:
    if not csv_path.exists():
        raise FileNotFoundError(f"Khong tim thay {csv_path}. Tao file agriculture CSV truoc.")

    df = pd.read_csv(csv_path)
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise ValueError(f"{csv_path.name} thieu cot: {', '.join(missing)}")
    if df.empty:
        raise ValueError(f"{csv_path.name} khong co dong nao.")
    return df[columns]


def _load_dataframe_to_staging(
    df: pd.DataFrame,
    table: str,
    engine: Engine,
) -> int:
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {table}"))
    df.to_sql(table, engine, if_exists="append", index=False)
    print(f"Loaded {len(df)} rows into {table}")
    return len(df)


def load_agriculture_to_postgres(engine: Engine | None = None) -> None:
    """Validate + nạp mapping city->region/crop, refresh dim_agri_region."""
    engine = engine or get_engine()
    mapping_df = _read_required_csv(
        AGRICULTURE_DATA_DIR / "agri_region_mapping.csv",
        AGRI_MAPPING_COLUMNS,
    )
    validate_agri_region_mapping(mapping_df)
    print(
        f"Agriculture data quality checks passed: {len(mapping_df)} city mappings"
    )

    _load_dataframe_to_staging(mapping_df, "stg_agri_region_mapping", engine)
    run_sql_file(SQL_DIR / "07_load_agriculture_schema.sql", engine)


if __name__ == "__main__":
    load_agriculture_to_postgres()
