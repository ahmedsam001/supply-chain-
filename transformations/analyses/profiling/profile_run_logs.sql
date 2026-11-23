-- Profiling: live_market.RUN_LOGS
SELECT
    -- 1. Volume and Duplicates
    COUNT(*) AS total_rows,
    COUNT(DISTINCT RUN_ID) AS unique_keys,
    COUNT(*) - COUNT(DISTINCT RUN_ID) AS duplicate_keys,

    -- 2. Null Checks
    SUM(CASE WHEN RUN_ID IS NULL THEN 1 ELSE 0 END) AS null_pk,
    SUM(CASE WHEN STORE IS NULL THEN 1 ELSE 0 END) AS null_store,
    SUM(CASE WHEN RUN_MODE IS NULL THEN 1 ELSE 0 END) AS null_run_mode,
    SUM(CASE WHEN RUN_DATE IS NULL THEN 1 ELSE 0 END) AS null_run_date,
    SUM(CASE WHEN PRODUCTS_COLLECTED IS NULL THEN 1 ELSE 0 END) AS null_products_collected,
    SUM(CASE WHEN FINISHED_AT IS NULL THEN 1 ELSE 0 END) AS null_finished_at,

    -- 3. Outlier/Anomaly Checks
    SUM(CASE WHEN PRODUCTS_COLLECTED = 0 THEN 1 ELSE 0 END) AS zero_product_runs,
    SUM(CASE WHEN PRODUCTS_COLLECTED < 0 THEN 1 ELSE 0 END) AS negative_products_collected,
    SUM(CASE WHEN DURATION_SECONDS < 0 THEN 1 ELSE 0 END) AS negative_duration_seconds,
    SUM(CASE WHEN FINISHED_AT < STARTED_AT THEN 1 ELSE 0 END) AS finished_before_started,
    MIN(RUN_DATE) AS oldest_run,
    MAX(RUN_DATE) AS newest_run

FROM {{ source('live_market', 'RUN_LOGS') }}
