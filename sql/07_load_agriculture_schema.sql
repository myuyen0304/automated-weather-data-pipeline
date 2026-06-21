-- ============================================================================
-- 07_load_agriculture_schema.sql
-- Nạp mapping city -> region/crop từ staging vào dim_agri_region.
-- Idempotent: chạy lại sẽ cập nhật giá trị mapping thay đổi.
-- Lưu ý: dim_crop (hằng số nông học) được seed trong 06 (DDL), KHÔNG nạp ở đây.
-- ============================================================================

INSERT INTO dim_agri_region (city, agri_region, main_crop_group)
SELECT
    TRIM(city)            AS city,
    TRIM(agri_region)     AS agri_region,
    TRIM(main_crop_group) AS main_crop_group
FROM stg_agri_region_mapping
ON CONFLICT (city) DO UPDATE SET
    agri_region = EXCLUDED.agri_region,
    main_crop_group = EXCLUDED.main_crop_group;
