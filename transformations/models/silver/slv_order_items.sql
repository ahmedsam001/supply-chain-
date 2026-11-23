{{ config(materialized='table') }}

WITH raw AS (
    SELECT * FROM {{ source('supply_chain_stage', 'RAW_ORDER_ITEMS') }}
),

-- 1. Deduplicate by order_item_id
deduped AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY TRIM(ORDER_ITEM_ID)
            ORDER BY ORDER_ITEM_ID DESC
        ) AS rn
    FROM raw
),

-- 2. Standardize strings, apply >=1M EGP outlier guard, cast financials to DECIMAL(12, 2), and set DQ flags
cleaned AS (
    SELECT
        TRIM(ORDER_ITEM_ID)                                             AS order_item_id,
        TRIM(ORDER_ID)                                                  AS order_id,
        TRIM(PRODUCT_ID)                                                AS product_id,
        UPPER(TRIM(COALESCE(STORE, 'UNKNOWN')))                         AS store,
        CASE
            WHEN TRIM(CATEGORY) = 'بليس بوند' THEN 'SMARTWATCHES'
            ELSE UPPER(TRIM(COALESCE(CATEGORY, 'UNKNOWN')))
        END                                                             AS category,

        -- Non-positive quantities -> NULL (business-invalid)
        CAST(
            CASE WHEN QUANTITY <= 0 THEN NULL ELSE QUANTITY END
            AS INTEGER
        )                                                               AS quantity,

        -- Safe, non-negative DECIMAL(12, 2) financials (zeroed if >= 1,000,000 EGP placeholder outlier)
        CAST(
            CASE
                WHEN ABS(COALESCE(UNIT_PRICE_EGP, 0)) >= 1000000 THEN 0
                ELSE ABS(COALESCE(UNIT_PRICE_EGP, 0))
            END
            AS DECIMAL(12, 2)
        )                                                               AS unit_price_egp,

        -- DISCOUNT_AMOUNT_EGP is a line-level total discount (not per-unit)
        CAST(
            CASE
                WHEN ABS(COALESCE(UNIT_PRICE_EGP, 0)) >= 1000000 THEN 0
                ELSE ABS(COALESCE(DISCOUNT_AMOUNT_EGP, 0))
            END
            AS DECIMAL(12, 2)
        )                                                               AS discount_amount_egp,

        -- Cost > price is anomalous -> NULL; outlier line cost zeroed
        CAST(
            CASE
                WHEN ABS(COALESCE(UNIT_PRICE_EGP, 0)) >= 1000000 THEN 0
                WHEN UNIT_COST_EGP > ABS(COALESCE(UNIT_PRICE_EGP, 0)) THEN NULL
                ELSE ABS(COALESCE(UNIT_COST_EGP, 0))
            END
            AS DECIMAL(12, 2)
        )                                                               AS unit_cost_egp,

        -- Derived net unit price: divide line-level discount by quantity before subtracting from unit_price
        CAST(
            CASE
                WHEN ABS(COALESCE(UNIT_PRICE_EGP, 0)) >= 1000000 THEN 0
                WHEN QUANTITY > 0
                THEN GREATEST(
                    ABS(COALESCE(UNIT_PRICE_EGP, 0)) - (ABS(COALESCE(DISCOUNT_AMOUNT_EGP, 0)) / QUANTITY),
                    0
                )
                ELSE ABS(COALESCE(UNIT_PRICE_EGP, 0))
            END
            AS DECIMAL(12, 2)
        )                                                               AS net_unit_price_egp,

        -- Data quality flags
        CASE WHEN QUANTITY <= 0 THEN TRUE ELSE FALSE END                AS had_non_positive_qty,
        CASE
            WHEN UNIT_COST_EGP > ABS(COALESCE(UNIT_PRICE_EGP, 0))
            THEN TRUE ELSE FALSE
        END                                                             AS had_cost_gt_price,
        CASE
            WHEN ABS(COALESCE(UNIT_PRICE_EGP, 0)) >= 1000000
            THEN TRUE ELSE FALSE
        END                                                             AS is_price_outlier

    FROM deduped
    WHERE rn = 1
)

SELECT * FROM cleaned
