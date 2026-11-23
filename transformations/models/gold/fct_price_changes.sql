{{ config(materialized='table') }}

WITH price_deltas AS (
    -- Transaction Fact: capture ONLY changed/inserted market records for volatility & alert analysis
    SELECT
        *,
        CASE
            WHEN is_price_outlier THEN 'OUTLIER_FLAGGED'
            WHEN old_price IS NULL THEN 'NEW_LISTING'
            WHEN price < old_price THEN 'PRICE_DROP'
            WHEN price > old_price THEN 'PRICE_INCREASE'
            ELSE 'UNCHANGED'
        END AS price_direction
    FROM {{ ref('slv_price_history') }}
    WHERE change_type IN ('INSERT', 'UPDATE')
),

current_products AS (
    SELECT
        product_sk,
        product_id
    FROM {{ ref('dim_product') }}
    WHERE is_current = TRUE
),

price_event_status AS (
    SELECT * FROM {{ ref('dim_price_event_status') }}
),

price_changes_fact AS (
    SELECT
        -- Grain: 1 row per price change / listing event (Transaction Fact)
        h.snapshot_id,

        -- Conformed Dimension Foreign Keys
        CAST(STRFTIME(h.collected_date, '%Y%m%d') AS INTEGER)               AS date_key,
        p.product_sk,
        h.product_id,
        h.store                                                             AS store_id,
        h.run_id,
        pes.price_event_status_key,

        -- Event Timestamps
        h.collected_date,
        h.collected_at,

        -- Price Volatility & Alert Measures
        h.price,
        h.old_price,
        h.discount_pct,
        h.is_price_outlier,

        CAST(
            CASE
                WHEN h.price IS NOT NULL AND h.old_price IS NOT NULL THEN h.price - h.old_price
                ELSE 0
            END
            AS DECIMAL(12, 2)
        )                                                                   AS price_delta_egp,

        CAST(
            CASE
                WHEN h.price IS NOT NULL AND h.old_price IS NOT NULL AND h.old_price > 0
                THEN ((h.price - h.old_price) / h.old_price) * 100
                ELSE 0
            END
            AS DECIMAL(12, 2)
        )                                                                   AS price_delta_pct

    FROM price_deltas h
    LEFT JOIN current_products p
        ON h.product_id = p.product_id
    LEFT JOIN price_event_status pes
        ON h.stock_status = pes.stock_status
       AND h.change_type = pes.change_type
       AND h.price_direction = pes.price_direction
)

SELECT * FROM price_changes_fact
