-- ============================================================================
-- 04_load_star_schema.sql
-- Nạp dữ liệu từ bảng staging vào star schema (dim + fact).
-- KHÁC với 01-03: script này CHẠY MỖI LẦN pipeline (sau khi staging có data).
-- Được viết idempotent: chạy lại nhiều lần không tạo bản ghi trùng.
-- Nếu staging chứa dữ liệu Archive cho cùng city + observation_time đã từng được
-- load bằng forecast, fact sẽ được cập nhật để ưu tiên batch mới nhất.
-- ============================================================================

-- 1) dim_location: thêm các thành phố mới xuất hiện trong staging.
INSERT INTO dim_location (city, country, latitude, longitude)
SELECT DISTINCT s.city, s.country, s.latitude, s.longitude
FROM stg_weather_observations s
ON CONFLICT (city) DO NOTHING;

-- 2) dim_date: sinh thuộc tính ngày từ observation_time trong staging.
INSERT INTO dim_date (date_id, full_date, day, month, quarter, year, day_of_week, is_weekend)
SELECT DISTINCT
    CAST(TO_CHAR(s.observation_time, 'YYYYMMDD') AS INT) AS date_id,
    CAST(s.observation_time AS DATE)                     AS full_date,
    EXTRACT(DAY     FROM s.observation_time)::INT         AS day,
    EXTRACT(MONTH   FROM s.observation_time)::INT         AS month,
    EXTRACT(QUARTER FROM s.observation_time)::INT         AS quarter,
    EXTRACT(YEAR    FROM s.observation_time)::INT         AS year,
    TRIM(TO_CHAR(s.observation_time, 'Day'))             AS day_of_week,
    EXTRACT(ISODOW FROM s.observation_time) IN (6, 7)     AS is_weekend
FROM stg_weather_observations s
ON CONFLICT (date_id) DO NOTHING;

-- 3) fact_weather_observation: join staging với dimension và nạp số liệu.
INSERT INTO fact_weather_observation (
    location_id, date_id, observation_time,
    temperature, humidity, apparent_temperature,
    pressure_msl, surface_pressure,
    wind_speed, wind_direction, wind_gusts,
    precipitation, rain, cloud_cover,
    weather_code, weather_condition, is_day
)
SELECT
    l.location_id,
    CAST(TO_CHAR(s.observation_time, 'YYYYMMDD') AS INT) AS date_id,
    s.observation_time,
    s.temperature, s.humidity, s.apparent_temperature,
    s.pressure_msl, s.surface_pressure,
    s.wind_speed, s.wind_direction, s.wind_gusts,
    s.precipitation, s.rain, s.cloud_cover,
    s.weather_code, s.weather_condition, s.is_day
FROM stg_weather_observations s
JOIN dim_location l ON l.city = s.city
ON CONFLICT (location_id, observation_time) DO UPDATE SET
    date_id = EXCLUDED.date_id,
    temperature = EXCLUDED.temperature,
    humidity = EXCLUDED.humidity,
    apparent_temperature = EXCLUDED.apparent_temperature,
    pressure_msl = EXCLUDED.pressure_msl,
    surface_pressure = EXCLUDED.surface_pressure,
    wind_speed = EXCLUDED.wind_speed,
    wind_direction = EXCLUDED.wind_direction,
    wind_gusts = EXCLUDED.wind_gusts,
    precipitation = EXCLUDED.precipitation,
    rain = EXCLUDED.rain,
    cloud_cover = EXCLUDED.cloud_cover,
    weather_code = EXCLUDED.weather_code,
    weather_condition = EXCLUDED.weather_condition,
    is_day = EXCLUDED.is_day,
    inserted_at = CURRENT_TIMESTAMP;
