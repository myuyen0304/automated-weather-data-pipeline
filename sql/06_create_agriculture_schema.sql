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
-- Buffer thuần, không dữ liệu bền -> DROP+CREATE để luôn khớp schema CSV hiện tại.
DROP TABLE IF EXISTS stg_agri_region_mapping;
CREATE TABLE stg_agri_region_mapping (
    city        VARCHAR(100),
    agri_region VARCHAR(100),
    crop        VARCHAR(50),
    crop_role   VARCHAR(20),
    area_share  NUMERIC(4, 3),
    crop_source TEXT,
    is_flagship BOOLEAN
);

-- Dimension mapping: grain = (city, crop). Một tỉnh có THỂ trồng nhiều cây
-- (đặc biệt sau sáp nhập 2025, mỗi tỉnh rộng và đa cây), nên KHÔNG còn ràng buộc
-- 1 cây/tỉnh. area_share = tỷ trọng diện tích cây trong tỉnh, NULLABLE vì hiện
-- CHƯA có nguồn tỷ trọng theo ranh giới 34 tỉnh mới (Niên giám TK trễ ~1 năm và
-- publish theo ranh giới cũ) -> để NULL, KHÔNG bịa/chia đều. crop_source ghi căn
-- cứ cho sự HIỆN DIỆN của cây (định tính, có thể trích nguồn).
--   crop_role : xếp hạng ĐỊNH TÍNH cây trong tỉnh ('primary' = cây có diện tích gieo trồng lớn nhất tỉnh,
--               'secondary' = cây phụ). Là ordinal nên trích nguồn được mà KHÔNG
--               cần số (khác area_share). Mỗi tỉnh đúng 1 'primary' (xem partial
--               unique index bên dưới). Khi có area_share thật -> primary = cây
--               share cao nhất, lúc đó crop_role suy lại từ số.
CREATE TABLE IF NOT EXISTS dim_agri_region (
    agri_region_id  SERIAL PRIMARY KEY,
    city            VARCHAR(100) NOT NULL,
    agri_region     VARCHAR(100) NOT NULL,
    crop            VARCHAR(50) NOT NULL,
    crop_role       VARCHAR(20),
    area_share      NUMERIC(4, 3),
    crop_source     TEXT,
    -- Cây chủ lực KINH TẾ tỉnh (định tính), TRỰC GIAO với crop_role: crop_role xếp
    -- theo diện tích gieo trồng (NGTK), còn is_flagship đánh dấu cây đặc trưng/kinh
    -- tế (vd cà phê Tây Nguyên) mà NGTK quốc gia KHÔNG có DT theo tỉnh. Mặc định
    -- FALSE; chỉ TRUE khi có căn cứ ghi trong crop_source. Dùng để dashboard chọn
    -- cây nổi bật, KHÔNG thay crop_role và KHÔNG suy ra area_share.
    is_flagship     BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT uq_dim_agri_region_city_crop UNIQUE (city, crop),
    CONSTRAINT chk_dim_agri_region_area_share
        CHECK (area_share IS NULL OR (area_share > 0 AND area_share <= 1)),
    CONSTRAINT chk_dim_agri_region_crop_role
        CHECK (crop_role IS NULL OR crop_role IN ('primary', 'secondary'))
);

-- Migrate DB cũ (schema 1 cây/tỉnh: cột main_crop_group + UNIQUE(city)) sang đa
-- cây/tỉnh, KHÔNG mất dữ liệu config. Idempotent; với DB mới các lệnh này no-op.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'dim_agri_region' AND column_name = 'main_crop_group'
    ) THEN
        ALTER TABLE dim_agri_region RENAME COLUMN main_crop_group TO crop;
    END IF;
END $$;

ALTER TABLE dim_agri_region ADD COLUMN IF NOT EXISTS area_share NUMERIC(4, 3);
ALTER TABLE dim_agri_region ADD COLUMN IF NOT EXISTS crop_source TEXT;
ALTER TABLE dim_agri_region ADD COLUMN IF NOT EXISTS crop_role VARCHAR(20);
ALTER TABLE dim_agri_region ADD COLUMN IF NOT EXISTS is_flagship BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE dim_agri_region DROP CONSTRAINT IF EXISTS uq_dim_agri_region_city;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_dim_agri_region_city_crop'
    ) THEN
        ALTER TABLE dim_agri_region
            ADD CONSTRAINT uq_dim_agri_region_city_crop UNIQUE (city, crop);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_dim_agri_region_area_share'
    ) THEN
        ALTER TABLE dim_agri_region
            ADD CONSTRAINT chk_dim_agri_region_area_share
            CHECK (area_share IS NULL OR (area_share > 0 AND area_share <= 1));
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_dim_agri_region_crop_role'
    ) THEN
        ALTER TABLE dim_agri_region
            ADD CONSTRAINT chk_dim_agri_region_crop_role
            CHECK (crop_role IS NULL OR crop_role IN ('primary', 'secondary'));
    END IF;
END $$;

-- Đúng 1 'primary' (cây diện tích lớn nhất)/tỉnh: partial unique index chặn tỉnh có >=2 'primary'.
-- (Trường hợp 0 primary do DQ gate ở data_quality.py bắt — index không bắt được.)
-- Đặt SAU migration ADD COLUMN crop_role để cột chắc chắn tồn tại trên cả DB cũ.
-- Old rows crop_role NULL -> index rỗng -> apply an toan.
CREATE UNIQUE INDEX IF NOT EXISTS uq_dim_agri_region_one_primary
    ON dim_agri_region (city)
    WHERE crop_role = 'primary';

-- Hằng số nông học theo cây trồng. NGUỒN ghi ngay trong cột source.
--   kc_mid                   : hệ số cây trồng giữa mùa (FAO-56 Table 12).
--   t_base_c                 : nhiệt độ gốc tính GDD (°C).
--   water_balance_applicable : cân bằng nước ET0xKc - mưa CÓ áp dụng được không.
--                              Lúa nước (ruộng ngập) KHÔNG theo mô hình này
--                              (có ponding/thấm/làm đất) -> FALSE, chỉ tính GDD.
--   t_base_c là NULLABLE: FAO-56 chỉ cho Kc (mô hình ET), KHÔNG cho nhiệt độ gốc
--   GDD. T_base chỉ điền khi có nguồn chắc (ngô/đậu tương/lạc ~10°C là chuẩn phổ
--   biến); cây lâu năm nhiệt đới (mía/sắn/chuối/cây có múi/chè) T_base không thống
--   nhất -> để NULL, KHÔNG đoán (đúng kỷ luật NULL như area_share). NULL t_base_c
--   chỉ làm daily_gdd = NULL; irrigation_need (ETc-mưa) vẫn đủ nguồn từ Kc.
CREATE TABLE IF NOT EXISTS dim_crop (
    crop                     VARCHAR(50) PRIMARY KEY,
    kc_mid                   NUMERIC(4, 2) NOT NULL,
    t_base_c                 NUMERIC(4, 1),
    water_balance_applicable BOOLEAN NOT NULL,
    kc_source                TEXT NOT NULL,
    t_base_source            TEXT NOT NULL
);

-- Migrate DB cũ (t_base_c từng NOT NULL) -> nullable. Idempotent; DB mới no-op.
ALTER TABLE dim_crop ALTER COLUMN t_base_c DROP NOT NULL;

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
     'T_base lúa ~10°C (IRRI/FAO thường dùng cho GDD lúa).'),
    -- Cây cạn (water_balance_applicable=TRUE). Kc TRA TỪ FAO-56 Table 12, đã đối
    -- chiếu nguồn fao.org. T_base chỉ điền khi có chuẩn phổ biến, còn lại để NULL.
    ('maize', 1.20, 10.0, TRUE,
     'FAO-56 Table 12: field maize (grain) Kc_mid 1.20.',
     'Nhiệt độ gốc GDD ngô ~10°C (chuẩn phổ biến, McMaster & Wilhelm 1997 / USDA).'),
    ('soybean', 1.15, 10.0, TRUE,
     'FAO-56 Table 12: soybeans Kc_mid 1.15.',
     'Nhiệt độ gốc GDD đậu tương ~10°C (giá trị phổ biến).'),
    ('groundnut', 1.15, 10.0, TRUE,
     'FAO-56 Table 12: groundnut (peanut) Kc_mid 1.15.',
     'Nhiệt độ gốc GDD lạc ~10°C (giá trị phổ biến).'),
    ('sugarcane', 1.25, NULL, TRUE,
     'FAO-56 Table 12: sugar cane Kc_mid 1.25.',
     'T_base GDD mía không thống nhất trong tài liệu -> để NULL, KHÔNG đoán (chỉ ảnh hưởng daily_gdd, không ảnh hưởng irrigation_need).'),
    ('cassava', 1.10, NULL, TRUE,
     'FAO-56 Table 12: cassava năm 2 (cây đã trưởng thành) Kc_mid 1.10 (năm 1 = 0.80).',
     'T_base GDD sắn không thống nhất -> để NULL, KHÔNG đoán.'),
    ('sweet_potato', 1.15, NULL, TRUE,
     'FAO-56 Table 12: sweet potato Kc_mid 1.15.',
     'T_base GDD khoai lang không thống nhất -> để NULL, KHÔNG đoán.'),
    ('banana', 1.10, NULL, TRUE,
     'FAO-56 Table 12: banana năm 1 Kc_mid 1.10 (chọn năm 1 thận trọng; năm 2 = 1.20).',
     'T_base GDD chuối không thống nhất -> để NULL, KHÔNG đoán.'),
    ('citrus', 0.70, NULL, TRUE,
     'FAO-56 Table 12: citrus CÓ thảm phủ đất (active ground cover), tán 70% -> Kc_mid 0.70 (giả định có thảm phủ, phổ biến ở VN; không thảm phủ = 0.65).',
     'T_base GDD cây có múi không thống nhất -> để NULL, KHÔNG đoán.'),
    ('tea', 1.00, NULL, TRUE,
     'FAO-56 Table 12: tea non-shaded Kc_mid 1.00 (chè không che bóng; có che bóng = 1.15).',
     'T_base GDD chè không thống nhất -> để NULL, KHÔNG đoán.'),
    ('rubber', 1.00, NULL, TRUE,
     'FAO-56 Table 12: rubber trees Kc_mid 1.00 (Kc_ini 0.95, Kc_end 1.00); cây công nghiệp lâu năm.',
     'T_base GDD cao su không thống nhất trong tài liệu -> để NULL, KHÔNG đoán (chỉ ảnh hưởng daily_gdd, không ảnh hưởng irrigation_need).')
ON CONFLICT (crop) DO UPDATE SET
    kc_mid = EXCLUDED.kc_mid,
    t_base_c = EXCLUDED.t_base_c,
    water_balance_applicable = EXCLUDED.water_balance_applicable,
    kc_source = EXCLUDED.kc_source,
    t_base_source = EXCLUDED.t_base_source;
