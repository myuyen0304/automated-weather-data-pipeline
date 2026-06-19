-- ============================================================================
-- 06_create_delivery_risk_mart.sql
-- Mart hỗ trợ quyết định logistics: chấm mức rủi ro giao hàng theo (city, ngày)
-- dựa trên MƯA và GIÓ GIẬT — 2 yếu tố cản trở giao hàng (đặc biệt xe máy ở VN).
--
-- LƯU Ý (không overclaim): đây là RULE-BASED RISK INDICATOR / decision-support
-- mart suy ra từ dữ liệu thời tiết public (forecast + ERA5 archive). KHÔNG phải
-- model dự báo delay đã kiểm chứng bằng dữ liệu đơn hàng/giao hàng thực tế.
--
-- View-trên-view: đọc thẳng mart_daily_weather_summary (đã gộp hourly -> ngày)
-- nên luôn phản ánh fact mới nhất, không cần job refresh. Phụ thuộc view daily
-- nên phải chạy SAU 05_create_marts.sql. CREATE OR REPLACE -> chạy lại an toàn.
-- ============================================================================

CREATE OR REPLACE VIEW mart_delivery_risk AS
SELECT
    city,
    full_date,
    total_rain,
    total_precipitation,
    max_wind_gusts,
    avg_wind_speed,
    -- Điểm rủi ro heuristic (0-100) để dashboard tô màu / sắp xếp; KHÔNG phải
    -- xác suất delay. Trọng số mưa*2 + gió giật chỉ là quy ước khởi đầu.
    LEAST(100, COALESCE(total_rain, 0) * 2 + COALESCE(max_wind_gusts, 0))::NUMERIC(6, 2)
        AS risk_score,
    -- Ngưỡng (mưa 30/10 mm, gió giật 50/35 km/h — đơn vị Open-Meteo mặc định) là
    -- đề xuất khởi đầu, CONFIGURABLE: chỉnh tại đây khi hiệu chỉnh theo thực tế.
    CASE
        WHEN total_rain > 30 OR max_wind_gusts > 50 THEN 'High'
        WHEN total_rain > 10 OR max_wind_gusts > 35 THEN 'Medium'
        ELSE 'Low'
    END AS delivery_risk_level
FROM mart_daily_weather_summary;
