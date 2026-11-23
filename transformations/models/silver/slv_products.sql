{{ config(materialized='table') }}

WITH raw AS (
    SELECT * FROM {{ source('live_market', 'PRODUCTS') }}
),

-- 1. Deduplicate on composite key (store, product_id) by latest update
deduped AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY UPPER(TRIM(STORE)), TRIM(PRODUCT_ID)
            ORDER BY LAST_UPDATED_AT DESC NULLS LAST
        ) AS rn
    FROM raw
),

-- 2. Standardize strings, cast financials to DECIMAL(12, 2), and apply Infinity Date validity
cleaned AS (
    SELECT
        UPPER(TRIM(COALESCE(STORE, 'UNKNOWN')))                         AS store,
        TRIM(PRODUCT_ID)                                                AS product_id,
        TRIM(COALESCE(PRODUCT_NAME, 'UNKNOWN'))                         AS product_name,
        CASE
            WHEN TRIM(CATEGORY) = 'بليس بوند' THEN 'SMARTWATCHES'
            ELSE UPPER(TRIM(COALESCE(CATEGORY, 'UNKNOWN')))
        END                                                             AS category,
        UPPER(TRIM(COALESCE(BRAND, 'UNKNOWN')))                         AS brand,

        -- Non-positive or extreme placeholder price (>= 1,000,000 EGP) -> NULL; otherwise DECIMAL(12, 2)
        CAST(
            CASE
                WHEN CURRENT_PRICE <= 0 OR CURRENT_PRICE >= 1000000 THEN NULL
                ELSE COALESCE(CURRENT_PRICE, 0)
            END
            AS DECIMAL(12, 2)
        )                                                               AS current_price,

        -- Keep NULL when no valid higher old price exists (or >= 1,000,000 EGP outlier)
        CAST(
            CASE
                WHEN OLD_PRICE IS NULL OR OLD_PRICE <= 0 OR OLD_PRICE >= 1000000 OR OLD_PRICE < CURRENT_PRICE THEN NULL
                ELSE OLD_PRICE
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
        TRIM(PRODUCT_URL)                                               AS product_url,
        TRIM(IMAGE_URL)                                                 AS image_url,
        TRIM(STATE_HASH)                                                AS state_hash,

        CAST(FIRST_SEEN_AT AS TIMESTAMP)                                AS first_seen_at,
        CAST(LAST_UPDATED_AT AS TIMESTAMP)                              AS last_updated_at,
        CAST(LAST_CHECKED_AT AS TIMESTAMP)                              AS last_checked_at,

        -- Dimension Infinity Date rule: active catalog products remain valid until 9999-12-31
        CAST('9999-12-31 23:59:59' AS TIMESTAMP)                        AS valid_to,

        -- Data quality flags
        CASE WHEN CURRENT_PRICE <= 0 THEN TRUE ELSE FALSE END           AS had_non_positive_price,
        CASE WHEN CURRENT_PRICE >= 1000000 THEN TRUE ELSE FALSE END     AS is_price_outlier,
        CASE
            WHEN OLD_PRICE IS NOT NULL AND OLD_PRICE < CURRENT_PRICE
            THEN TRUE ELSE FALSE
        END                                                             AS had_old_price_lt_current,
        CASE
            WHEN DISCOUNT < 0 OR DISCOUNT > 100
            THEN TRUE ELSE FALSE
        END                                                             AS had_invalid_discount

    FROM deduped
    WHERE rn = 1
)

SELECT * FROM cleaned
