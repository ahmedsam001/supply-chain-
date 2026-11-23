{{ config(materialized='table') }}

WITH price_events AS (
    SELECT
        stock_status,
        change_type,
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

distinct_price_status AS (
    SELECT DISTINCT
        stock_status,
        change_type,
        price_direction
    FROM price_events
)

SELECT
    ROW_NUMBER() OVER (
        ORDER BY stock_status, change_type, price_direction
    ) AS price_event_status_key,
    stock_status,
    change_type,
    price_direction
FROM distinct_price_status
