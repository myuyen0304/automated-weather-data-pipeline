from __future__ import annotations

from pathlib import Path

import load_postgres


def test_init_database_runs_irrigation_mart_after_base_marts(monkeypatch) -> None:
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
        ("05_create_marts.sql", engine),
        ("08_create_irrigation_need_mart.sql", engine),
    ]


def test_irrigation_need_mart_defines_fao56_contract() -> None:
    sql_text = Path("sql/08_create_irrigation_need_mart.sql").read_text(encoding="utf-8")
    normalized_sql = " ".join(sql_text.split())

    assert "CREATE OR REPLACE VIEW mart_irrigation_need AS" in sql_text
    assert "FROM mart_daily_weather_summary" in normalized_sql
    assert "JOIN dim_agri_region" in normalized_sql
    assert "JOIN dim_crop" in normalized_sql
    # ETc = ET0 x Kc, nhu cầu tưới = max(0, ETc - mưa hiệu dụng).
    assert "total_et0_mm * c.kc_mid" in normalized_sql
    assert "AS etc_mm" in normalized_sql
    assert "AS irrigation_need_mm" in normalized_sql
    assert "AS daily_gdd" in normalized_sql
    # Lúa nước: cân bằng nước không áp dụng -> irrigation_need_mm = NULL.
    assert "water_balance_applicable" in normalized_sql


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
