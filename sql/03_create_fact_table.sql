-- ============================================================================
-- 03_create_fact_table.sql
-- Tạo bảng fact: lưu các chỉ số đo lường thời tiết, tham chiếu tới dimension.
-- Chạy 1 lần khi khởi tạo database (sau script 02 vì có khóa ngoại).
-- ============================================================================

CREATE TABLE IF NOT EXISTS fact_weather_observation (
    observation_id       BIGSERIAL PRIMARY KEY,
    location_id          INT REFERENCES dim_location(location_id),
    date_id              INT REFERENCES dim_date(date_id),
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
    inserted_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Mỗi địa điểm chỉ có 1 bản ghi cho mỗi mốc thời gian quan sát.
    -- Nhờ vậy script 04 chạy lại nhiều lần (mỗi ngày) không tạo dữ liệu trùng.
    CONSTRAINT uq_fact_location_time UNIQUE (location_id, observation_time)
);
