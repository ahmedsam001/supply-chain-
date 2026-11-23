{{ config(materialized='table') }}

WITH distinct_market_status AS (
    SELECT DISTINCT
        stock_status,
        change_type
    FROM {{ ref('slv_market_snapshots') }}
)

SELECT
    ROW_NUMBER() OVER (
        ORDER BY stock_status, change_type
    ) AS market_status_key,
    stock_status,
    change_type
FROM distinct_market_status
