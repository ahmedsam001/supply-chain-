-- Profiling: live_market.PRODUCTS
SELECT
    -- 1. Volume and Duplicates
    COUNT(*) AS total_rows,
    COUNT(DISTINCT STORE || '|' || PRODUCT_ID) AS unique_keys,
    COUNT(*) - COUNT(DISTINCT STORE || '|' || PRODUCT_ID) AS duplicate_keys,

    -- 2. Null Checks
    SUM(CASE WHEN STORE || '|' || PRODUCT_ID IS NULL THEN 1 ELSE 0 END) AS null_pk,
    SUM(CASE WHEN STORE IS NULL THEN 1 ELSE 0 END) AS null_store,
    SUM(CASE WHEN PRODUCT_ID IS NULL THEN 1 ELSE 0 END) AS null_product_id,
    SUM(CASE WHEN PRODUCT_NAME IS NULL THEN 1 ELSE 0 END) AS null_product_name,
    SUM(CASE WHEN CURRENT_PRICE IS NULL THEN 1 ELSE 0 END) AS null_current_price,
    SUM(CASE WHEN STOCK_STATUS IS NULL THEN 1 ELSE 0 END) AS null_stock_status,
    SUM(CASE WHEN STATE_HASH IS NULL THEN 1 ELSE 0 END) AS null_state_hash,

    -- 3. Outlier/Anomaly Checks
    SUM(CASE WHEN CURRENT_PRICE <= 0 THEN 1 ELSE 0 END) AS non_positive_prices,
    SUM(CASE WHEN OLD_PRICE IS NOT NULL AND OLD_PRICE < CURRENT_PRICE THEN 1 ELSE 0 END) AS old_price_below_current,
    SUM(CASE WHEN DISCOUNT < 0 OR DISCOUNT > 100 THEN 1 ELSE 0 END) AS discount_out_of_range,
    MIN(CURRENT_PRICE) AS min_price,
    MAX(CURRENT_PRICE) AS max_price,
    MIN(FIRST_SEEN_AT) AS oldest_first_seen,
    MAX(FIRST_SEEN_AT) AS newest_first_seen,
    MAX(LAST_CHECKED_AT) AS newest_check

FROM {{ source('live_market', 'PRODUCTS') }}
