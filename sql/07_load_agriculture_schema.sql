-- ============================================================================
-- 07_load_agriculture_schema.sql
-- Nạp mapping (city, crop) từ staging vào dim_agri_region.
-- Grain đa cây/tỉnh -> TRUNCATE + INSERT lại toàn bộ cho idempotent và tránh dòng
-- cũ sót lại khi cơ cấu cây của một tỉnh thay đổi (ON CONFLICT theo (city) cũ sẽ
-- để lại rác). Không bảng nào tham chiếu agri_region_id (mart là VIEW) nên TRUNCATE
-- an toàn.
-- Lưu ý: dim_crop (hằng số nông học) được seed trong 06 (DDL), KHÔNG nạp ở đây.
-- ============================================================================

TRUNCATE TABLE dim_agri_region RESTART IDENTITY;

INSERT INTO dim_agri_region (city, agri_region, crop, crop_role, area_share, crop_source, is_flagship)
SELECT
    TRIM(city)        AS city,
    TRIM(agri_region) AS agri_region,
    TRIM(crop)        AS crop,
    TRIM(crop_role)   AS crop_role,
    area_share,
    crop_source,
    COALESCE(is_flagship, FALSE) AS is_flagship
FROM stg_agri_region_mapping;
