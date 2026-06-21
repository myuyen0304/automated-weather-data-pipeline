-- ============================================================================
-- 08_create_irrigation_need_mart.sql
-- Mart tưới theo chuẩn FAO-56 (Allen et al. 1998, Irrigation & Drainage Paper 56).
--
-- Grain = city + full_date + crop.
-- Mô hình: ETc = ET0 x Kc ; nhu cầu tưới = max(0, ETc - mưa hiệu dụng).
--   - ET0 (total_et0_mm): ET tham chiếu ngày = tổng 24 giờ et0_fao (Open-Meteo).
--   - Kc (kc_mid): hệ số cây trồng, trích FAO-56 Table 12 (xem dim_crop.kc_source).
--   - Mưa hiệu dụng: dùng total_rain ngày làm xấp xỉ ĐƠN GIẢN (chưa trừ dòng chảy
--     mặt/thấm sâu) -> ngày mưa to nhu cầu tưới là CẬN DƯỚI.
--   - soil_moisture (avg_soil_moisture): chỉ là CHỈ BÁO trạng thái đất, KHÔNG trừ
--     vào mm (tránh cần hằng số field-capacity chưa có nguồn).
--   - GDD ngày = max(0, (Tmax+Tmin)/2 - T_base).
--
-- Lúa nước (water_balance_applicable = FALSE): KHÔNG tính irrigation_need_mm
-- (ruộng ngập không theo ET0xKc - mưa); chỉ trả GDD/timing.
--
-- Đây là decision-support cấp VÙNG, CHƯA validate với năng suất/đo nước thực địa.
-- ============================================================================

CREATE OR REPLACE VIEW mart_irrigation_need AS
WITH base AS (
    SELECT
        w.city,
        ar.agri_region,
        ar.main_crop_group AS crop,
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
    FROM mart_daily_weather_summary w
    JOIN dim_agri_region ar ON ar.city = w.city
    JOIN dim_crop c         ON c.crop = ar.main_crop_group
)
SELECT
    city,
    agri_region,
    crop,
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
    ROUND(GREATEST(0, (max_temperature + min_temperature) / 2 - t_base_c), 2) AS daily_gdd,
    water_balance_applicable,
    CASE
        WHEN NOT water_balance_applicable
            THEN 'Lua nuoc: khong dung can bang nuoc ET0xKc; chi theo doi GDD/lich mua vu.'
        WHEN GREATEST(0, etc_mm - COALESCE(total_rain, 0)) > 0
            THEN 'Can tuoi ~' || ROUND(etc_mm - COALESCE(total_rain, 0), 1)
                 || ' mm: ETc vuot mua hieu dung hom nay.'
        ELSE 'Mua du bu ETc hom nay, chua can tuoi.'
    END AS advisory_message
FROM base;
