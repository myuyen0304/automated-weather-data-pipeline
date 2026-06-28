from __future__ import annotations

from pathlib import Path

import load_postgres


def test_init_database_creates_source_tables_only(monkeypatch) -> None:
    """init chỉ tạo bảng nguồn (fact + dim). Tầng mart (05, 08) đã chuyển sang
    dbt (weather_dbt/, `dbt build`) nên KHÔNG còn chạy trong init_database."""
    calls: list[tuple[str, object | None]] = []
    engine = object()

    def fake_run_sql_file(sql_path: Path, engine_arg: object | None = None) -> None:
        calls.append((Path(sql_path).name, engine_arg))

    monkeypatch.setattr(load_postgres, "run_sql_file", fake_run_sql_file)

    load_postgres.init_database(engine)

    assert calls == [
        ("01_create_staging_table.sql", engine),
        ("02_create_dimensions.sql", engine),
        ("03_create_fact_table.sql", engine),
        ("06_create_agriculture_schema.sql", engine),
    ]
    # Mart không còn được tạo trong init -> dbt sở hữu tầng này.
    assert ("05_create_marts.sql", engine) not in calls
    assert ("08_create_irrigation_need_mart.sql", engine) not in calls


def test_irrigation_need_model_defines_fao56_contract() -> None:
    """Hợp đồng FAO-56 giờ nằm ở dbt model (nguồn sự thật của mart), KHÔNG còn
    sql/08 — file đó đã xoá khi tầng mart chuyển sang dbt (weather_dbt/)."""
    sql_text = Path("weather_dbt/models/marts/mart_irrigation_need.sql").read_text(encoding="utf-8")
    normalized_sql = " ".join(sql_text.split())

    # Materialized thành view (thay CREATE VIEW của sql cũ).
    assert "{{ config(materialized='view') }}" in normalized_sql
    # mart_daily qua ref() -> dbt tự suy thứ tự; dim qua source() (EL nạp ngoài dbt).
    assert "FROM {{ ref('mart_daily_weather_summary') }}" in normalized_sql
    assert "JOIN {{ source('weather_core', 'dim_agri_region') }}" in normalized_sql
    assert "JOIN {{ source('weather_core', 'dim_crop') }}" in normalized_sql
    # ETc = ET0 x Kc, nhu cầu tưới = max(0, ETc - mưa hiệu dụng).
    assert "total_et0_mm * c.kc_mid" in normalized_sql
    assert "AS etc_mm" in normalized_sql
    assert "AS irrigation_need_mm" in normalized_sql
    assert "AS daily_gdd" in normalized_sql
    # Lúa nước: cân bằng nước không áp dụng -> irrigation_need_mm = NULL.
    assert "water_balance_applicable" in normalized_sql


def test_dim_agri_region_supports_multiple_crops_per_city() -> None:
    """Grain (city, crop): bỏ ràng buộc 1 cây/tỉnh, thêm area_share nullable."""
    sql_text = Path("sql/06_create_agriculture_schema.sql").read_text(encoding="utf-8")
    normalized_sql = " ".join(sql_text.split())

    # Khoá duy nhất theo cặp (city, crop), KHÔNG còn UNIQUE chỉ trên city.
    assert "UNIQUE (city, crop)" in normalized_sql
    assert "UNIQUE (city)" not in normalized_sql
    # area_share nullable + CHECK (0,1]; crop_source ghi căn cứ hiện diện cây.
    assert "area_share" in normalized_sql
    assert "crop_source" in normalized_sql
    assert "area_share IS NULL OR (area_share > 0 AND area_share <= 1)" in normalized_sql
    # Migrate DB cũ: đổi tên main_crop_group -> crop.
    assert "RENAME COLUMN main_crop_group TO crop" in normalized_sql


def test_dim_agri_region_has_crop_role_with_one_primary_guard() -> None:
    """crop_role ordinal (primary/secondary) + DB chặn >=2 primary/tỉnh."""
    sql_text = Path("sql/06_create_agriculture_schema.sql").read_text(encoding="utf-8")
    normalized_sql = " ".join(sql_text.split())

    # Cột crop_role + CHECK chỉ cho primary/secondary (hoặc NULL khi migrate).
    assert "crop_role" in normalized_sql
    assert "crop_role IN ('primary', 'secondary')" in normalized_sql
    # Partial unique index: mỗi tỉnh tối đa 1 'primary'.
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_dim_agri_region_one_primary" in normalized_sql
    assert "WHERE crop_role = 'primary'" in normalized_sql
    # Migrate DB cũ: thêm cột crop_role.
    assert "ADD COLUMN IF NOT EXISTS crop_role" in normalized_sql


def test_dim_agri_region_has_flagship_overlay() -> None:
    """is_flagship: cây chủ lực kinh tế, trực giao crop_role, mặc định FALSE."""
    schema_sql = " ".join(
        Path("sql/06_create_agriculture_schema.sql").read_text(encoding="utf-8").split()
    )
    load_sql = " ".join(
        Path("sql/07_load_agriculture_schema.sql").read_text(encoding="utf-8").split()
    )

    # Cột boolean mặc định FALSE (không phải tỉnh nào cũng có cây đặc trưng cần đánh dấu).
    assert "is_flagship BOOLEAN NOT NULL DEFAULT FALSE" in schema_sql
    # Migrate DB cũ: thêm cột is_flagship.
    assert "ADD COLUMN IF NOT EXISTS is_flagship BOOLEAN NOT NULL DEFAULT FALSE" in schema_sql
    # Loader chuyển is_flagship từ staging vào dim (COALESCE FALSE cho dòng cũ).
    assert "is_flagship" in load_sql


def test_irrigation_need_model_joins_multi_crop_dim() -> None:
    """Model join theo ar.crop (đa cây/tỉnh), không còn cột main_crop_group."""
    sql_text = Path("weather_dbt/models/marts/mart_irrigation_need.sql").read_text(encoding="utf-8")
    normalized_sql = " ".join(sql_text.split())

    assert "c.crop = ar.crop" in normalized_sql
    assert "main_crop_group" not in normalized_sql
    # crop_role được expose ở mart để Power BI lọc "cây diện tích lớn nhất".
    assert "crop_role" in normalized_sql
    # is_flagship expose để dashboard lọc cây chủ lực kinh tế (vd cà phê Tây Nguyên).
    assert "is_flagship" in normalized_sql


def test_crop_coefficients_are_sourced_in_dim_crop() -> None:
    """dim_crop phải seed Kc/T_base KÈM nguồn (chống 'số magic không nguồn')."""
    sql_text = Path("sql/06_create_agriculture_schema.sql").read_text(encoding="utf-8")
    normalized_sql = " ".join(sql_text.split())

    assert "CREATE TABLE IF NOT EXISTS dim_crop" in sql_text
    assert "kc_source" in normalized_sql
    assert "t_base_source" in normalized_sql
    assert "FAO-56" in normalized_sql
    # Lúa nước phải được đánh dấu KHÔNG áp dụng cân bằng nước.
    assert "'rice', 1.20, 10.0, FALSE" in normalized_sql
    # Cao su (cây chủ lực Đông Nam Bộ) seed kèm nguồn FAO-56, áp dụng cân bằng nước.
    assert "'rubber', 1.00, NULL, TRUE" in normalized_sql
