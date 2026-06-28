-- mart_irrigation_need - Mart tưới chuẩn FAO-56 (Allen et al. 1998, Irrigation &
-- Drainage Paper 56). Model thể hiện rõ NHẤT giá trị dbt: phụ thuộc
-- mart_daily_weather_summary qua ref() -> dbt TỰ suy thứ tự (mart_daily chạy
-- TRƯỚC), thay đoạn hardcode thứ tự build mart trong load_postgres.py.
--   - mart_daily_weather_summary : ref() -> model dbt khác (dbt suy thứ tự).
--   - dim_agri_region / dim_crop : source() -> bảng EL nạp ngoài dbt.
--
-- Grain = city + full_date + crop. Một tỉnh nhiều cây -> nhiều dòng/ngày; KHÔNG
-- rollup trọng số cấp tỉnh vì area_share hiện NULL. crop_role ('primary'/'secondary')
-- để Power BI lọc nhanh "cây diện tích lớn nhất"; is_flagship đánh dấu cây chủ lực
-- KINH TẾ (vd cà phê Tây Nguyên) - trực giao crop_role.
--
-- Mô hình: ETc = ET0 x Kc ; nhu cầu tưới = max(0, ETc - mưa hiệu dụng).
--   - ET0 (total_et0_mm): ET tham chiếu ngày = tổng 24 giờ et0_fao (Open-Meteo).
--   - Kc (kc_mid): hệ số cây trồng, FAO-56 Table 12 (xem dim_crop.kc_source).
--   - Mưa hiệu dụng: dùng total_rain ngày làm xấp xỉ ĐƠN GIẢN (chưa trừ dòng chảy
--     mặt/thấm sâu) -> ngày mưa to nhu cầu tưới là CẬN DƯỚI.
--   - soil_moisture (avg_soil_moisture): chỉ là CHỈ BÁO trạng thái đất, KHÔNG trừ
--     vào mm (tránh hằng số field-capacity chưa có nguồn).
--   - GDD ngày = max(0, (Tmax+Tmin)/2 - T_base), chỉ khi cây có T_base trích nguồn.
--
-- Lúa nước (water_balance_applicable = FALSE): KHÔNG tính irrigation_need_mm (ruộng
-- ngập không theo ET0xKc - mưa); chỉ trả GDD/timing. Decision-support cấp VÙNG,
-- CHƯA validate với năng suất/đo nước thực địa.
{{ config(materialized='view') }}

WITH base AS (
    SELECT
        w.city,
        ar.agri_region,
        ar.crop AS crop,
        ar.crop_role,
        ar.is_flagship,
        ar.area_share,
        w.full_date,
        w.max_temperature,
        w.min_temperature,
        w.total_rain,
        w.avg_soil_moisture,
        w.avg_shortwave_radiation,
        w.total_et0_mm,
        c.kc_mid,
        c.t_base_c,
        c.water_balance_applicable,
        ROUND(w.total_et0_mm * c.kc_mid, 2) AS etc_mm
    FROM {{ ref('mart_daily_weather_summary') }} w
    JOIN {{ source('weather_core', 'dim_agri_region') }} ar ON ar.city = w.city
    JOIN {{ source('weather_core', 'dim_crop') }} c         ON c.crop = ar.crop
)
SELECT
    city,
    agri_region,
    crop,
    crop_role,
    is_flagship,
    area_share,
    full_date,
    total_et0_mm,
    kc_mid,
    etc_mm,
    ROUND(COALESCE(total_rain, 0), 2) AS effective_rain_mm,
    CASE
        WHEN water_balance_applicable
            THEN GREATEST(0, ROUND(etc_mm - COALESCE(total_rain, 0), 2))
        ELSE NULL
    END AS irrigation_need_mm,
    avg_soil_moisture,
    -- GDD chỉ tính khi cây có T_base trích nguồn. T_base NULL -> GDD NULL (KHÔNG
    -- để GREATEST(0, ... - NULL) vì Postgres bỏ qua NULL -> ra 0 GDD giả).
    CASE
        WHEN t_base_c IS NULL THEN NULL
        ELSE ROUND(GREATEST(0, (max_temperature + min_temperature) / 2 - t_base_c), 2)
    END AS daily_gdd,
    water_balance_applicable,
    CASE
        WHEN NOT water_balance_applicable
            THEN 'Lua nuoc: khong dung can bang nuoc ET0xKc; chi theo doi GDD/lich mua vu.'
        WHEN GREATEST(0, etc_mm - COALESCE(total_rain, 0)) > 0
            THEN 'Can tuoi ~' || ROUND(etc_mm - COALESCE(total_rain, 0), 1)
                 || ' mm: ETc vuot mua hieu dung hom nay.'
        ELSE 'Mua du bu ETc hom nay, chua can tuoi.'
    END AS advisory_message
FROM base
