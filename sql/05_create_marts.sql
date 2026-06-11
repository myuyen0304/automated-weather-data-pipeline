-- ============================================================================
-- 05_create_marts.sql
-- Tạo các bảng/view mart phục vụ Power BI và phân tích.
-- View đọc trực tiếp từ fact + dimension nên luôn phản ánh dữ liệu mới nhất.
-- Chạy 1 lần khi khởi tạo (có thể chạy lại nhờ CREATE OR REPLACE).
-- ============================================================================

-- Mart tổng hợp theo NGÀY và thành phố.
CREATE OR REPLACE VIEW mart_daily_weather_summary AS
SELECT
    l.city,
    d.full_date,
    AVG(f.temperature)          AS avg_temperature,
    MAX(f.temperature)          AS max_temperature,
    MIN(f.temperature)          AS min_temperature,
    AVG(f.humidity)             AS avg_humidity,
    AVG(f.apparent_temperature) AS avg_apparent_temperature,
    AVG(f.pressure_msl)         AS avg_pressure_msl,
    AVG(f.surface_pressure)     AS avg_surface_pressure,
    AVG(f.wind_speed)           AS avg_wind_speed,
    MAX(f.wind_gusts)           AS max_wind_gusts,
    SUM(f.precipitation)        AS total_precipitation,
    SUM(f.rain)                 AS total_rain,
    AVG(f.cloud_cover)          AS avg_cloud_cover
FROM fact_weather_observation f
JOIN dim_location l ON f.location_id = l.location_id
JOIN dim_date d     ON f.date_id = d.date_id
GROUP BY l.city, d.full_date;

-- Mart tổng hợp theo TUẦN (year + ISO week) và thành phố.
CREATE OR REPLACE VIEW mart_weekly_weather_summary AS
SELECT
    l.city,
    d.year,
    EXTRACT(WEEK FROM d.full_date)::INT AS iso_week,
    AVG(f.temperature)   AS avg_temperature,
    MAX(f.temperature)   AS max_temperature,
    MIN(f.temperature)   AS min_temperature,
    AVG(f.humidity)      AS avg_humidity,
    AVG(f.wind_speed)    AS avg_wind_speed,
    SUM(f.precipitation) AS total_precipitation,
    SUM(f.rain)          AS total_rain,
    AVG(f.cloud_cover)   AS avg_cloud_cover
FROM fact_weather_observation f
JOIN dim_location l ON f.location_id = l.location_id
JOIN dim_date d     ON f.date_id = d.date_id
GROUP BY l.city, d.year, EXTRACT(WEEK FROM d.full_date);
