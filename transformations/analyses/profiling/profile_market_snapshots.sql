-- Profiling: live_market.MARKET_SNAPSHOTS
SELECT
    -- 1. Volume and Duplicates
    COUNT(*) AS total_rows,
    COUNT(DISTINCT SNAPSHOT_ID) AS unique_keys,
    COUNT(*) - COUNT(DISTINCT SNAPSHOT_ID) AS duplicate_keys,

    -- 2. Null Checks
    SUM(CASE WHEN SNAPSHOT_ID IS NULL THEN 1 ELSE 0 END) AS null_pk,
    SUM(CASE WHEN PRODUCT_ID IS NULL THEN 1 ELSE 0 END) AS null_product_id,
    SUM(CASE WHEN STORE IS NULL THEN 1 ELSE 0 END) AS null_store,
    SUM(CASE WHEN PRICE IS NULL THEN 1 ELSE 0 END) AS null_price,
    SUM(CASE WHEN STATE_HASH IS NULL THEN 1 ELSE 0 END) AS null_state_hash,
    SUM(CASE WHEN CHANGE_TYPE IS NULL THEN 1 ELSE 0 END) AS null_change_type,
    SUM(CASE WHEN COLLECTED_AT IS NULL THEN 1 ELSE 0 END) AS null_collected_at,

    -- 3. Outlier/Anomaly Checks
    SUM(CASE WHEN PRICE <= 0 THEN 1 ELSE 0 END) AS non_positive_prices,
    SUM(CASE WHEN OLD_PRICE < 0 THEN 1 ELSE 0 END) AS negative_old_price,
    MIN(COLLECTED_AT) AS oldest_record,
    MAX(COLLECTED_AT) AS newest_record

FROM {{ source('live_market', 'MARKET_SNAPSHOTS') }}
