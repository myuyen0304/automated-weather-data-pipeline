-- ============================================================================
-- 06_create_agriculture_schema.sql
-- Schema cho mart tưới FAO-56 (irrigation advisory).
--
-- Hai loại dữ liệu, tách bạch để KHÔNG lặp lại bẫy "số magic không nguồn":
--   1. dim_agri_region  -- map city -> vùng nông nghiệp -> cây trồng. Đây là
--      CONFIG triển khai (deployment config), nạp từ data/agriculture/*.csv.
--   2. dim_crop         -- HẰNG SỐ NÔNG HỌC (Kc, nhiệt độ gốc GDD). Mọi giá trị
--      đều TRÍCH NGUỒN công bố (FAO-56) ngay trong INSERT bên dưới. Seed thẳng
--      trong DDL để hằng số luôn đi kèm nguồn, không nằm rải rác trong CSV.
-- ============================================================================

-- Staging cho mapping city -> region/crop (nạp từ CSV mỗi lần --load-agriculture).
CREATE TABLE IF NOT EXISTS stg_agri_region_mapping (
    city            VARCHAR(100),
    agri_region     VARCHAR(100),
    main_crop_group VARCHAR(50)
);

-- Dimension mapping: mỗi city thuộc 1 vùng và 1 nhóm cây chính.
CREATE TABLE IF NOT EXISTS dim_agri_region (
    agri_region_id  SERIAL PRIMARY KEY,
    city            VARCHAR(100) NOT NULL,
    agri_region     VARCHAR(100) NOT NULL,
    main_crop_group VARCHAR(50) NOT NULL,
    CONSTRAINT uq_dim_agri_region_city UNIQUE (city)
);

-- Hằng số nông học theo cây trồng. NGUỒN ghi ngay trong cột source.
--   kc_mid                   : hệ số cây trồng giữa mùa (FAO-56 Table 12).
--   t_base_c                 : nhiệt độ gốc tính GDD (°C).
--   water_balance_applicable : cân bằng nước ET0xKc - mưa CÓ áp dụng được không.
--                              Lúa nước (ruộng ngập) KHÔNG theo mô hình này
--                              (có ponding/thấm/làm đất) -> FALSE, chỉ tính GDD.
CREATE TABLE IF NOT EXISTS dim_crop (
    crop                     VARCHAR(50) PRIMARY KEY,
    kc_mid                   NUMERIC(4, 2) NOT NULL,
    t_base_c                 NUMERIC(4, 1) NOT NULL,
    water_balance_applicable BOOLEAN NOT NULL,
    kc_source                TEXT NOT NULL,
    t_base_source            TEXT NOT NULL
);

-- Seed hằng số nông học (idempotent). Mọi số đều trích nguồn FAO-56 / tài liệu cây trồng.
INSERT INTO dim_crop (crop, kc_mid, t_base_c, water_balance_applicable, kc_source, t_base_source)
VALUES
    ('coffee', 0.95, 10.0, TRUE,
     'FAO-56 Table 12: coffee Kc_mid 0.90-1.05 (chọn 0.95, cà phê có ground cover); cây lâu năm nên Kc ~ ổn định.',
     'Nhiệt độ gốc cà phê ~10°C (literature phổ biến cho cà phê chè/vối).'),
    ('vegetable', 1.05, 10.0, TRUE,
     'FAO-56 Table 12: nhóm "small vegetables" Kc_mid ~1.05 (GENERIC - cần tinh chỉnh theo cây rau cụ thể).',
     'T_base rau ~10°C (xấp xỉ chung, nên tinh chỉnh theo loại rau).'),
    ('rice', 1.20, 10.0, FALSE,
     'FAO-56 Table 12: rice Kc_mid ~1.20 (tham khảo; KHÔNG dùng cho cân bằng nước vì ruộng ngập).',
     'T_base lúa ~10°C (IRRI/FAO thường dùng cho GDD lúa).')
ON CONFLICT (crop) DO UPDATE SET
    kc_mid = EXCLUDED.kc_mid,
    t_base_c = EXCLUDED.t_base_c,
    water_balance_applicable = EXCLUDED.water_balance_applicable,
    kc_source = EXCLUDED.kc_source,
    t_base_source = EXCLUDED.t_base_source;
