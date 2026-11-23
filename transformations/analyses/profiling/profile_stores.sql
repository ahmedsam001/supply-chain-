-- Profiling: live_market.STORES
SELECT
    -- 1. Volume and Duplicates
    COUNT(*) AS total_rows,
    COUNT(DISTINCT STORE_ID) AS unique_keys,
    COUNT(*) - COUNT(DISTINCT STORE_ID) AS duplicate_keys,

    -- 2. Null Checks
    SUM(CASE WHEN STORE_ID IS NULL THEN 1 ELSE 0 END) AS null_pk,
    SUM(CASE WHEN STORE_NAME IS NULL THEN 1 ELSE 0 END) AS null_store_name,
    SUM(CASE WHEN DOMAIN IS NULL THEN 1 ELSE 0 END) AS null_domain,
    SUM(CASE WHEN OFFICIAL_URL IS NULL THEN 1 ELSE 0 END) AS null_official_url,
    SUM(CASE WHEN BUSINESS_TYPE IS NULL THEN 1 ELSE 0 END) AS null_business_type

FROM {{ source('live_market', 'STORES') }}
