{# -- Profiling: supply_chain_stage.RAW_CUSTOMER_ORDERS
SELECT
    -- 1. Volume and Duplicates
    COUNT(*) AS total_rows,
    COUNT(DISTINCT ORDER_ID) AS unique_keys,
    COUNT(*) - COUNT(DISTINCT ORDER_ID) AS duplicate_keys,

    -- 2. Null Checks
    SUM(CASE WHEN ORDER_ID IS NULL THEN 1 ELSE 0 END) AS null_pk,
    SUM(CASE WHEN CUSTOMER_ID IS NULL THEN 1 ELSE 0 END) AS null_customer_id,
    SUM(CASE WHEN STORE IS NULL THEN 1 ELSE 0 END) AS null_store,
    SUM(CASE WHEN ORDER_STATUS_RAW IS NULL THEN 1 ELSE 0 END) AS null_order_status_raw,
    SUM(CASE WHEN ORDER_TS_RAW IS NULL THEN 1 ELSE 0 END) AS null_order_ts_raw,
    SUM(CASE WHEN TOTAL_ORDER_EGP IS NULL THEN 1 ELSE 0 END) AS null_total_order_egp,

    -- 3. Outlier/Anomaly Checks
    SUM(CASE WHEN SUBTOTAL_EGP < 0 THEN 1 ELSE 0 END) AS negative_subtotal_egp,
    SUM(CASE WHEN SHIPPING_FEE_EGP < 0 THEN 1 ELSE 0 END) AS negative_shipping_fee_egp,
    SUM(CASE WHEN TOTAL_ORDER_EGP < 0 THEN 1 ELSE 0 END) AS negative_total_order_egp,
    SUM(CASE WHEN ABS(SUBTOTAL_EGP + SHIPPING_FEE_EGP - TOTAL_ORDER_EGP) > 0.01 THEN 1 ELSE 0 END) AS total_mismatch_rows,
    SUM(CASE WHEN ORDER_TS_RAW IS NOT NULL AND TRY_CAST(ORDER_TS_RAW AS TIMESTAMP) IS NULL THEN 1 ELSE 0 END) AS unparseable_order_ts_raw,
    MIN(ORDER_TS_RAW) AS oldest_order_raw,
    MAX(ORDER_TS_RAW) AS newest_order_raw

FROM {{ source('supply_chain_stage', 'RAW_CUSTOMER_ORDERS') }} #}


select *  FROM {{ source('supply_chain_stage', 'RAW_CUSTOMER_ORDERS') }}

