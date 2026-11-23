-- Profiling: live_market.BRANCHES
SELECT
    
    -- 1. Volume and Duplicates
    COUNT(*) AS total_rows,
    COUNT(DISTINCT BRANCH_ID) AS unique_keys,
    COUNT(*) - COUNT(DISTINCT BRANCH_ID) AS duplicate_keys,

    -- 2. Null Checks
    SUM(CASE WHEN BRANCH_ID IS NULL THEN 1 ELSE 0 END) AS null_pk,
    SUM(CASE WHEN STORE IS NULL THEN 1 ELSE 0 END) AS null_store,
    SUM(CASE WHEN BRANCH_NAME IS NULL THEN 1 ELSE 0 END) AS null_branch_name,
    SUM(CASE WHEN GOVERNORATE IS NULL THEN 1 ELSE 0 END) AS null_governorate,
    SUM(CASE WHEN LATITUDE IS NULL THEN 1 ELSE 0 END) AS null_latitude,
    SUM(CASE WHEN LONGITUDE IS NULL THEN 1 ELSE 0 END) AS null_longitude,

    -- 3. Outlier/Anomaly Checks
    SUM(CASE WHEN LATITUDE NOT BETWEEN 21 AND 32 OR LONGITUDE NOT BETWEEN 24 AND 37 THEN 1 ELSE 0 END) AS coords_outside_egypt,
    MIN(LAST_CHECKED_AT) AS oldest_check,
    MAX(LAST_CHECKED_AT) AS newest_check

FROM {{ source('live_market', 'BRANCHES') }}
