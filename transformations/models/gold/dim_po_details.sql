{{ config(materialized='table') }}

WITH distinct_po_attrs AS (
    SELECT DISTINCT
        po_status,
        currency
    FROM {{ ref('slv_purchase_orders') }}
)

SELECT
    ROW_NUMBER() OVER (
        ORDER BY po_status, currency
    ) AS po_details_key,
    po_status,
    currency
FROM distinct_po_attrs
