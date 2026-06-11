-- ============================================================================
-- 01_create_staging_table.sql
-- Tạo bảng staging: nơi chứa dữ liệu ĐÃ làm sạch nhưng CHƯA mô hình hóa.
-- Đây là lớp trung gian giữa file cleaned (CSV) và star schema phân tích.
-- Chạy 1 lần khi khởi tạo database.
-- ============================================================================

CREATE TABLE IF NOT EXISTS stg_weather_observations (
    city                 VARCHAR(100),
    country              VARCHAR(100),
    latitude             NUMERIC(9, 6),
    longitude            NUMERIC(9, 6),
    observation_time     TIMESTAMP,
    temperature          NUMERIC(5, 2),
    humidity             NUMERIC(5, 2),
    apparent_temperature NUMERIC(5, 2),
    pressure_msl         NUMERIC(7, 2),
    surface_pressure     NUMERIC(7, 2),
    wind_speed           NUMERIC(6, 2),
    wind_direction       NUMERIC(6, 2),
    wind_gusts           NUMERIC(6, 2),
    precipitation        NUMERIC(6, 2),
    rain                 NUMERIC(6, 2),
    cloud_cover          INT,
    weather_code         INT,
    weather_condition    VARCHAR(100),
    is_day               BOOLEAN,
    inserted_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
