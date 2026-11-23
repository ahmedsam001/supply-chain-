{{ config(materialized='table') }}

WITH distinct_order_attrs AS (
    SELECT DISTINCT
        order_channel,
        payment_method,
        order_status
    FROM {{ ref('slv_customer_orders') }}
)

SELECT
    ROW_NUMBER() OVER (
        ORDER BY order_channel, payment_method, order_status
    ) AS order_details_key,
    order_channel,
    payment_method,
    order_status
FROM distinct_order_attrs
