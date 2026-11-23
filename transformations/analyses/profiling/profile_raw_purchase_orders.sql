-- Profiling: supply_chain_stage.RAW_PURCHASE_ORDERS
SELECT
    -- 1. Volume and Duplicates
    COUNT(*) AS total_rows,
    COUNT(DISTINCT PO_ID) AS unique_keys,
    COUNT(*) - COUNT(DISTINCT PO_ID) AS duplicate_keys,

    -- 2. Null Checks
    SUM(CASE WHEN PO_ID IS NULL THEN 1 ELSE 0 END) AS null_pk,
    SUM(CASE WHEN SUPPLIER_ID IS NULL THEN 1 ELSE 0 END) AS null_supplier_id,
    SUM(CASE WHEN WAREHOUSE_ID IS NULL THEN 1 ELSE 0 END) AS null_warehouse_id,
    SUM(CASE WHEN PO_STATUS_RAW IS NULL THEN 1 ELSE 0 END) AS null_po_status_raw,
    SUM(CASE WHEN ORDER_DATE_RAW IS NULL THEN 1 ELSE 0 END) AS null_order_date_raw,
    SUM(CASE WHEN TOTAL_AMOUNT_EGP IS NULL THEN 1 ELSE 0 END) AS null_total_amount_egp,

    -- 3. Outlier/Anomaly Checks
    SUM(CASE WHEN TOTAL_AMOUNT_EGP < 0 THEN 1 ELSE 0 END) AS negative_total_amount_egp,
    SUM(CASE WHEN ORDER_DATE_RAW IS NOT NULL AND TRY_CAST(ORDER_DATE_RAW AS TIMESTAMP) IS NULL THEN 1 ELSE 0 END) AS unparseable_order_date_raw,
    SUM(CASE WHEN EXPECTED_DELIVERY_RAW IS NOT NULL AND TRY_CAST(EXPECTED_DELIVERY_RAW AS TIMESTAMP) IS NULL THEN 1 ELSE 0 END) AS unparseable_expected_delivery_raw,
    MIN(ORDER_DATE_RAW) AS oldest_order_date_raw,
    MAX(ORDER_DATE_RAW) AS newest_order_date_raw,
    SUM(CASE WHEN TRY_CAST(EXPECTED_DELIVERY_RAW AS TIMESTAMP) < TRY_CAST(ORDER_DATE_RAW AS TIMESTAMP) THEN 1 ELSE 0 END) AS delivery_before_order

FROM {{ source('supply_chain_stage', 'RAW_PURCHASE_ORDERS') }}
