-- ============================================================================
-- 02_create_dimensions.sql
-- Tạo các bảng dimension cho star schema:
--   - dim_location: thông tin địa điểm (thành phố, quốc gia, tọa độ)
--   - dim_date:     thuộc tính ngày tháng để phân tích theo thời gian
-- Chạy 1 lần khi khởi tạo database.
-- ============================================================================

CREATE TABLE IF NOT EXISTS dim_location (
    location_id SERIAL PRIMARY KEY,
    city        VARCHAR(100),
    country     VARCHAR(100),
    latitude    NUMERIC(9, 6),
    longitude   NUMERIC(9, 6),
    -- Ràng buộc UNIQUE giúp bước load (script 04) không tạo trùng địa điểm.
    CONSTRAINT uq_dim_location_city UNIQUE (city)
);

CREATE TABLE IF NOT EXISTS dim_date (
    date_id     INT PRIMARY KEY,   -- dạng YYYYMMDD, ví dụ 20260611
    full_date   DATE,
    day         INT,
    month       INT,
    quarter     INT,
    year        INT,
    day_of_week VARCHAR(20),
    is_weekend  BOOLEAN
);
