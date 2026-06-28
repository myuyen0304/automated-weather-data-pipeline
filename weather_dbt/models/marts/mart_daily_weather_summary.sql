-- Port của sql/05 (mart_daily_weather_summary). Tên bảng fact/dim -> source().
-- Logic tổng hợp giữ NGUYÊN: ET0 cộng 24 giờ = ET0 ngày (mm); soil_* lấy TB.
{{ config(materialized='view') }}

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
    AVG(f.cloud_cover)          AS avg_cloud_cover,
    SUM(f.et0_fao)              AS total_et0_mm,
    AVG(f.soil_moisture)        AS avg_soil_moisture,
    AVG(f.soil_temperature)     AS avg_soil_temperature,
    AVG(f.shortwave_radiation)  AS avg_shortwave_radiation
FROM {{ source('weather_core', 'fact_weather_observation') }} f
JOIN {{ source('weather_core', 'dim_location') }} l ON f.location_id = l.location_id
JOIN {{ source('weather_core', 'dim_date') }}     d ON f.date_id = d.date_id
GROUP BY l.city, d.full_date
