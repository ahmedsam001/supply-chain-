{{ config(materialized='table') }}

WITH orders AS (
    SELECT * FROM {{ ref('slv_customer_orders') }}
),

customer_profile AS (
    SELECT
        customer_id,
        ARG_MAX(customer_governorate, order_ts)                         AS primary_governorate,
        ARG_MAX(order_channel, order_ts)                                AS preferred_channel,
        ARG_MAX(payment_method, order_ts)                               AS preferred_payment_method,
        MIN(CAST(order_ts AS DATE))                                     AS first_order_date,
        MAX(CAST(order_ts AS DATE))                                     AS last_order_date,
        CAST(COUNT(*) AS INTEGER)                                       AS lifetime_orders,
        CAST(SUM(total_order_egp) AS DECIMAL(12, 2))                    AS lifetime_spend_egp
    FROM orders
    GROUP BY customer_id
)

SELECT * FROM customer_profile
