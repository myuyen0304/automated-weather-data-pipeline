-- Port của sql/05 (mart_weekly_weather_summary). Tổng hợp theo year + ISO week.
{{ config(materialized='view') }}

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
FROM {{ source('weather_core', 'fact_weather_observation') }} f
JOIN {{ source('weather_core', 'dim_location') }} l ON f.location_id = l.location_id
JOIN {{ source('weather_core', 'dim_date') }}     d ON f.date_id = d.date_id
GROUP BY l.city, d.year, EXTRACT(WEEK FROM d.full_date)
