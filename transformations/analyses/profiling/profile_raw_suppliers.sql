-- Profiling: supply_chain_stage.RAW_SUPPLIERS
SELECT
    -- 1. Volume and Duplicates
    COUNT(*) AS total_rows,
    COUNT(DISTINCT SUPPLIER_ID) AS unique_keys,
    COUNT(*) - COUNT(DISTINCT SUPPLIER_ID) AS duplicate_keys,

    -- 2. Null Checks
    SUM(CASE WHEN SUPPLIER_ID IS NULL THEN 1 ELSE 0 END) AS null_pk,
    SUM(CASE WHEN SUPPLIER_NAME IS NULL THEN 1 ELSE 0 END) AS null_supplier_name,
    SUM(CASE WHEN SUPPLIER_TYPE IS NULL THEN 1 ELSE 0 END) AS null_supplier_type,
    SUM(CASE WHEN COUNTRY IS NULL THEN 1 ELSE 0 END) AS null_country,
    SUM(CASE WHEN ACTIVE_FLAG IS NULL THEN 1 ELSE 0 END) AS null_active_flag,
    SUM(CASE WHEN CREATED_AT_RAW IS NULL THEN 1 ELSE 0 END) AS null_created_at_raw,

    -- 3. Outlier/Anomaly Checks
    SUM(CASE WHEN RATING < 0 OR RATING > 5 THEN 1 ELSE 0 END) AS rating_out_of_range,
    MIN(RATING) AS min_rating,
    MAX(RATING) AS max_rating,
    SUM(CASE WHEN CREATED_AT_RAW IS NOT NULL AND TRY_CAST(CREATED_AT_RAW AS TIMESTAMP) IS NULL THEN 1 ELSE 0 END) AS unparseable_created_at_raw,
    MIN(CREATED_AT_RAW) AS oldest_created_raw,
    MAX(CREATED_AT_RAW) AS newest_created_raw,
    SUM(CASE WHEN CONTACT_EMAIL IS NOT NULL AND CONTACT_EMAIL NOT LIKE '%@%' THEN 1 ELSE 0 END) AS invalid_emails

FROM {{ source('supply_chain_stage', 'RAW_SUPPLIERS') }}
