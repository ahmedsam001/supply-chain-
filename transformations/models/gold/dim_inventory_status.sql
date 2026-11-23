{{ config(materialized='table') }}

WITH distinct_inventory_status AS (
    SELECT DISTINCT
        location_type,
        stock_status
    FROM {{ ref('slv_inventory_logs') }}
)

SELECT
    ROW_NUMBER() OVER (
        ORDER BY location_type, stock_status
    ) AS inventory_status_key,
    location_type,
    stock_status
FROM distinct_inventory_status
