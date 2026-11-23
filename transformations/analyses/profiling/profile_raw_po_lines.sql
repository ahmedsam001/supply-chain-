-- Profiling: supply_chain_stage.RAW_PO_LINES
SELECT
    -- 1. Volume and Duplicates
    COUNT(*) AS total_rows,
    COUNT(DISTINCT PO_LINE_ID) AS unique_keys,
    COUNT(*) - COUNT(DISTINCT PO_LINE_ID) AS duplicate_keys,

    -- 2. Null Checks
    SUM(CASE WHEN PO_LINE_ID IS NULL THEN 1 ELSE 0 END) AS null_pk,
    SUM(CASE WHEN PO_ID IS NULL THEN 1 ELSE 0 END) AS null_po_id,
    SUM(CASE WHEN PRODUCT_ID IS NULL THEN 1 ELSE 0 END) AS null_product_id,
    SUM(CASE WHEN STORE IS NULL THEN 1 ELSE 0 END) AS null_store,
    SUM(CASE WHEN ORDERED_QTY IS NULL THEN 1 ELSE 0 END) AS null_ordered_qty,
    SUM(CASE WHEN UNIT_COST_EGP IS NULL THEN 1 ELSE 0 END) AS null_unit_cost_egp,

    -- 3. Outlier/Anomaly Checks
    SUM(CASE WHEN ORDERED_QTY <= 0 THEN 1 ELSE 0 END) AS non_positive_ordered_qty,
    SUM(CASE WHEN RECEIVED_QTY < 0 THEN 1 ELSE 0 END) AS negative_received_qty,
    SUM(CASE WHEN UNIT_COST_EGP < 0 THEN 1 ELSE 0 END) AS negative_unit_cost_egp,
    SUM(CASE WHEN LINE_TOTAL_EGP < 0 THEN 1 ELSE 0 END) AS negative_line_total_egp,
    SUM(CASE WHEN RECEIVED_QTY > ORDERED_QTY THEN 1 ELSE 0 END) AS over_received_rows,
    SUM(CASE WHEN ABS(ORDERED_QTY * UNIT_COST_EGP - LINE_TOTAL_EGP) > 0.01 THEN 1 ELSE 0 END) AS line_total_mismatch_rows

FROM {{ source('supply_chain_stage', 'RAW_PO_LINES') }}
