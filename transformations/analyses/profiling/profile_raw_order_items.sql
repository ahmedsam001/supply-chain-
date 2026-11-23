-- Profiling: supply_chain_stage.RAW_ORDER_ITEMS
SELECT
    -- 1. Volume and Duplicates
    COUNT(*) AS total_rows,
    COUNT(DISTINCT ORDER_ITEM_ID) AS unique_keys,
    COUNT(*) - COUNT(DISTINCT ORDER_ITEM_ID) AS duplicate_keys,

    -- 2. Null Checks
    SUM(CASE WHEN ORDER_ITEM_ID IS NULL THEN 1 ELSE 0 END) AS null_pk,
    SUM(CASE WHEN ORDER_ID IS NULL THEN 1 ELSE 0 END) AS null_order_id,
    SUM(CASE WHEN PRODUCT_ID IS NULL THEN 1 ELSE 0 END) AS null_product_id,
    SUM(CASE WHEN STORE IS NULL THEN 1 ELSE 0 END) AS null_store,
    SUM(CASE WHEN QUANTITY IS NULL THEN 1 ELSE 0 END) AS null_quantity,
    SUM(CASE WHEN UNIT_PRICE_EGP IS NULL THEN 1 ELSE 0 END) AS null_unit_price_egp,

    -- 3. Outlier/Anomaly Checks
    SUM(CASE WHEN QUANTITY <= 0 THEN 1 ELSE 0 END) AS non_positive_quantity,
    SUM(CASE WHEN UNIT_PRICE_EGP < 0 THEN 1 ELSE 0 END) AS negative_unit_price_egp,
    SUM(CASE WHEN DISCOUNT_AMOUNT_EGP < 0 THEN 1 ELSE 0 END) AS negative_discount_amount_egp,
    SUM(CASE WHEN UNIT_COST_EGP < 0 THEN 1 ELSE 0 END) AS negative_unit_cost_egp,
    SUM(CASE WHEN UNIT_COST_EGP > UNIT_PRICE_EGP THEN 1 ELSE 0 END) AS cost_above_price,
    MIN(QUANTITY) AS min_quantity,
    MAX(QUANTITY) AS max_quantity

FROM {{ source('supply_chain_stage', 'RAW_ORDER_ITEMS') }}
