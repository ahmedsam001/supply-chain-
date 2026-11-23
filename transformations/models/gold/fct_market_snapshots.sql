{{ config(materialized='table') }}

WITH market_snapshots AS (
    SELECT * FROM {{ ref('slv_market_snapshots') }}
),

current_products AS (
    SELECT
        product_sk,
        product_id
    FROM {{ ref('dim_product') }}
    WHERE is_current = TRUE
),

market_status AS (
    SELECT * FROM {{ ref('dim_market_status') }}
),

snapshot_fact AS (
    SELECT
        -- Grain: 1 row per product market snapshot (Periodic Snapshot of Full Market State)
        m.snapshot_id,

        -- Conformed Dimension Foreign Keys
        CAST(STRFTIME(m.collected_date, '%Y%m%d') AS INTEGER)               AS date_key,
        p.product_sk,
        m.product_id,
        m.store                                                             AS store_id,
        m.run_id,
        ms.market_status_key,

        -- Snapshot Timestamps
        m.collected_date,
        m.collected_at,

        -- Pricing & Availability Measures
        m.price,
        m.old_price,
        m.discount_pct,
        m.is_price_outlier,
        CAST(
            CASE
                WHEN m.old_price IS NOT NULL AND m.old_price > m.price
                THEN m.old_price - m.price
                ELSE 0
            END
            AS DECIMAL(12, 2)
        )                                                                   AS discount_amount_egp,
        CASE WHEN m.discount_pct > 0 THEN TRUE ELSE FALSE END               AS is_discounted,
        CASE WHEN m.stock_status = 'IN_STOCK' THEN TRUE ELSE FALSE END      AS is_in_stock

    FROM market_snapshots m
    LEFT JOIN current_products p
        ON m.product_id = p.product_id
    LEFT JOIN market_status ms
        ON m.stock_status = ms.stock_status
       AND m.change_type = ms.change_type
)

SELECT * FROM snapshot_fact
