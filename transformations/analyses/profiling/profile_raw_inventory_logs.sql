-- Profiling: supply_chain_stage.RAW_INVENTORY_LOGS
SELECT
    -- 1. Volume and Duplicates
    COUNT(*) AS total_rows,
    COUNT(DISTINCT INV_LOG_ID) AS unique_keys,
    COUNT(*) - COUNT(DISTINCT INV_LOG_ID) AS duplicate_keys,

    -- 2. Null Checks
    SUM(CASE WHEN INV_LOG_ID IS NULL THEN 1 ELSE 0 END) AS null_pk,
    SUM(CASE WHEN PRODUCT_ID IS NULL THEN 1 ELSE 0 END) AS null_product_id,
    SUM(CASE WHEN STORE IS NULL THEN 1 ELSE 0 END) AS null_store,
    SUM(CASE WHEN WAREHOUSE_ID IS NULL THEN 1 ELSE 0 END) AS null_warehouse_id,
    SUM(CASE WHEN BRANCH_ID IS NULL THEN 1 ELSE 0 END) AS null_branch_id,
    SUM(CASE WHEN QTY_ON_HAND IS NULL THEN 1 ELSE 0 END) AS null_qty_on_hand,
    SUM(CASE WHEN SNAPSHOT_TS_RAW IS NULL THEN 1 ELSE 0 END) AS null_snapshot_ts_raw,

    -- 3. Outlier/Anomaly Checks
    SUM(CASE WHEN QTY_ON_HAND < 0 THEN 1 ELSE 0 END) AS negative_qty_on_hand,
    SUM(CASE WHEN RESERVED_QTY < 0 THEN 1 ELSE 0 END) AS negative_reserved_qty,
    SUM(CASE WHEN REORDER_POINT < 0 THEN 1 ELSE 0 END) AS negative_reorder_point,
    SUM(CASE WHEN RESERVED_QTY > QTY_ON_HAND THEN 1 ELSE 0 END) AS reserved_exceeds_on_hand,
    SUM(CASE WHEN SNAPSHOT_TS_RAW IS NOT NULL AND TRY_CAST(SNAPSHOT_TS_RAW AS TIMESTAMP) IS NULL THEN 1 ELSE 0 END) AS unparseable_snapshot_ts_raw,
    MIN(SNAPSHOT_TS_RAW) AS oldest_snapshot_raw,
    MAX(SNAPSHOT_TS_RAW) AS newest_snapshot_raw

FROM {{ source('supply_chain_stage', 'RAW_INVENTORY_LOGS') }}
