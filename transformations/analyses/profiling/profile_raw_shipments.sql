SELECT * ,  FROM {{ source('supply_chain_stage', 'RAW_SHIPMENTS') }} 

{# 
SELECT
    -- 1. Volume and Duplicates
    COUNT(*) AS total_rows,
    COUNT(DISTINCT SHIPMENT_ID) AS unique_keys,
    COUNT(*) - COUNT(DISTINCT SHIPMENT_ID) AS duplicate_keys,

    -- 2. Null Checks
    SUM(CASE WHEN SHIPMENT_ID IS NULL THEN 1 ELSE 0 END) AS null_pk,
    SUM(CASE WHEN ORDER_ID IS NULL THEN 1 ELSE 0 END) AS null_order_id,
    SUM(CASE WHEN STORE IS NULL THEN 1 ELSE 0 END) AS null_store,
    SUM(CASE WHEN CARRIER_NAME IS NULL THEN 1 ELSE 0 END) AS null_carrier_name,
    SUM(CASE WHEN SHIPMENT_STATUS_RAW IS NULL THEN 1 ELSE 0 END) AS null_shipment_status_raw,
    SUM(CASE WHEN DISPATCHED_TS_RAW IS NULL THEN 1 ELSE 0 END) AS null_dispatched_ts_raw,

    -- 3. Outlier/Anomaly Checks
    SUM(CASE WHEN SHIPPING_COST_EGP < 0 THEN 1 ELSE 0 END) AS negative_shipping_cost_egp,
    SUM(CASE WHEN DISPATCHED_TS_RAW IS NOT NULL AND TRY_CAST(DISPATCHED_TS_RAW AS TIMESTAMP) IS NULL THEN 1 ELSE 0 END) AS unparseable_dispatched_ts_raw,
    SUM(CASE WHEN DELIVERED_TS_RAW IS NOT NULL AND TRY_CAST(DELIVERED_TS_RAW AS TIMESTAMP) IS NULL THEN 1 ELSE 0 END) AS unparseable_delivered_ts_raw,
    MIN(DISPATCHED_TS_RAW) AS oldest_dispatch_raw,
    MAX(DISPATCHED_TS_RAW) AS newest_dispatch_raw,
    SUM(CASE WHEN TRY_CAST(DELIVERED_TS_RAW AS TIMESTAMP) < TRY_CAST(DISPATCHED_TS_RAW AS TIMESTAMP) THEN 1 ELSE 0 END) AS delivered_before_dispatch

FROM {{ source('supply_chain_stage', 'RAW_SHIPMENTS') }} #}
