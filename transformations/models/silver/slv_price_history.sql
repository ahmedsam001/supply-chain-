{{ config(materialized='table') }}

WITH raw AS (
    SELECT * FROM {{ source('live_market', 'PRICE_HISTORY') }}
),

-- 1. Deduplicate chronologically by snapshot_id
deduped AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY TRIM(SNAPSHOT_ID)
            ORDER BY COLLECTED_AT DESC NULLS LAST
        ) AS rn
    FROM raw
),

-- 2. Standardize strings, cast financials to DECIMAL(12, 2), and add DQ flags
cleaned AS (
    SELECT
        TRIM(SNAPSHOT_ID)                                               AS snapshot_id,
        CAST(COLLECTED_DATE AS DATE)                                    AS collected_date,
        UPPER(TRIM(COALESCE(STORE, 'UNKNOWN')))                         AS store,
        TRIM(PRODUCT_ID)                                                AS product_id,

        -- Non-positive or extreme placeholder price (>= 1,000,000 EGP) -> NULL; otherwise DECIMAL(12, 2)
        CAST(
            CASE
                WHEN PRICE <= 0 OR PRICE >= 1000000 THEN NULL
                ELSE COALESCE(PRICE, 0)
            END
            AS DECIMAL(12, 2)
        )                                                               AS price,

        -- Keep NULL when no previous price exists or outlier; otherwise positive DECIMAL(12, 2)
        CAST(
            CASE
                WHEN OLD_PRICE IS NOT NULL AND OLD_PRICE > 0 AND OLD_PRICE < 1000000 THEN ABS(OLD_PRICE)
                ELSE NULL
            END
            AS DECIMAL(12, 2)
        )                                                               AS old_price,

        -- Discount bounded to [0, 100], default 0.00 when absent
        CAST(
            CASE
                WHEN DISCOUNT IS NULL OR DISCOUNT < 0 OR DISCOUNT > 100 THEN 0
                ELSE DISCOUNT
            END
            AS DECIMAL(12, 2)
        )                                                               AS discount_pct,

        UPPER(TRIM(COALESCE(STOCK_STATUS, 'UNKNOWN')))                  AS stock_status,
        TRIM(STATE_HASH)                                                AS state_hash,

        -- Validate CHANGE_TYPE against known CDC values
        CASE
            WHEN UPPER(TRIM(CHANGE_TYPE)) IN ('INSERT', 'UPDATE', 'NO_CHANGE')
            THEN UPPER(TRIM(CHANGE_TYPE))
            ELSE 'UNKNOWN'
        END                                                             AS change_type,

        CAST(COLLECTED_AT AS TIMESTAMP)                                 AS collected_at,
        TRIM(RUN_ID)                                                    AS run_id,

        -- Data quality flags
        CASE WHEN PRICE <= 0 THEN TRUE ELSE FALSE END                   AS had_non_positive_price,
        CASE WHEN PRICE >= 1000000 THEN TRUE ELSE FALSE END             AS is_price_outlier,
        CASE
            WHEN UPPER(TRIM(COALESCE(CHANGE_TYPE, ''))) NOT IN ('INSERT', 'UPDATE', 'NO_CHANGE')
            THEN TRUE ELSE FALSE
        END                                                             AS had_invalid_change_type

    FROM deduped
    WHERE rn = 1
)

SELECT * FROM cleaned
