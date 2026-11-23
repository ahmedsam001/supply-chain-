{{ config(materialized='table') }}

WITH raw AS (
    SELECT * FROM {{ source('live_market', 'STORES') }}
),

-- 1. Deduplicate by store_id
deduped AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY UPPER(TRIM(STORE_ID))
            ORDER BY STORE_ID DESC
        ) AS rn
    FROM raw
),

-- 2. Standardize store keys & categorical metadata
cleaned AS (
    SELECT
        UPPER(TRIM(COALESCE(STORE_ID, 'UNKNOWN')))                      AS store_id,
        TRIM(COALESCE(STORE_NAME, 'UNKNOWN'))                           AS store_name,
        LOWER(TRIM(COALESCE(DOMAIN, 'unknown')))                        AS domain,
        TRIM(OFFICIAL_URL)                                              AS official_url,
        UPPER(TRIM(COALESCE(BUSINESS_TYPE, 'UNKNOWN')))                 AS business_type
    FROM deduped
    WHERE rn = 1
)

SELECT * FROM cleaned
