
SELECT * ,  FROM {{ source('supply_chain_stage', 'RAW_WAREHOUSES') }} 

{# -- Profiling: supply_chain_stage.RAW_WAREHOUSES
SELECT
    -- 1. Volume and Duplicates
    COUNT(*) AS total_rows,
    COUNT(DISTINCT WAREHOUSE_ID) AS unique_keys,
    COUNT(*) - COUNT(DISTINCT WAREHOUSE_ID) AS duplicate_keys,

    -- 2. Null Checks
    SUM(CASE WHEN WAREHOUSE_ID IS NULL THEN 1 ELSE 0 END) AS null_pk,
    SUM(CASE WHEN WAREHOUSE_NAME IS NULL THEN 1 ELSE 0 END) AS null_warehouse_name,
    SUM(CASE WHEN WAREHOUSE_TYPE IS NULL THEN 1 ELSE 0 END) AS null_warehouse_type,
    SUM(CASE WHEN GOVERNORATE_RAW IS NULL THEN 1 ELSE 0 END) AS null_governorate_raw,
    SUM(CASE WHEN CAPACITY_PALLETS IS NULL THEN 1 ELSE 0 END) AS null_capacity_pallets,
    SUM(CASE WHEN OPERATIONAL_STATUS IS NULL THEN 1 ELSE 0 END) AS null_operational_status,

    -- 3. Outlier/Anomaly Checks
    SUM(CASE WHEN CAPACITY_PALLETS <= 0 THEN 1 ELSE 0 END) AS non_positive_capacity,
    SUM(CASE WHEN LATITUDE NOT BETWEEN 21 AND 32 OR LONGITUDE NOT BETWEEN 24 AND 37 THEN 1 ELSE 0 END) AS coords_outside_egypt,
    SUM(CASE WHEN LAST_AUDIT_RAW IS NOT NULL AND TRY_CAST(LAST_AUDIT_RAW AS TIMESTAMP) IS NULL THEN 1 ELSE 0 END) AS unparseable_last_audit_raw,
    MIN(LAST_AUDIT_RAW) AS oldest_audit_raw,
    MAX(LAST_AUDIT_RAW) AS newest_audit_raw

FROM {{ source('supply_chain_stage', 'RAW_WAREHOUSES') }} #}
