{{ config(materialized='table') }}

WITH order_items AS (
    SELECT * FROM {{ ref('slv_order_items') }}
),

orders AS (
    SELECT * FROM {{ ref('slv_customer_orders') }}
),

current_products AS (
    SELECT
        product_sk,
        product_id
    FROM {{ ref('dim_product') }}
    WHERE is_current = TRUE
),

order_details AS (
    SELECT * FROM {{ ref('dim_order_details') }}
),

sales_fact AS (
    SELECT
        -- Grain: 1 row per order line item
        i.order_item_id,
        i.order_id,

        -- Conformed Dimension Foreign Keys
        CAST(STRFTIME(CAST(o.order_ts AS DATE), '%Y%m%d') AS INTEGER)   AS date_key,
        p.product_sk,
        i.product_id,
        COALESCE(i.store, o.store)                                      AS store_id,
        o.fulfillment_branch_id                                         AS branch_id,
        o.customer_id,
        od.order_details_key,

        -- Transaction Timestamp
        o.order_ts,

        -- Line-Item Measures (DECIMAL(12, 2))
        i.quantity,
        i.unit_price_egp,
        i.discount_amount_egp,
        i.net_unit_price_egp,
        i.unit_cost_egp,
        i.is_price_outlier,

        CAST(
            i.quantity * i.unit_price_egp
            AS DECIMAL(12, 2)
        )                                                               AS gross_sales_egp,

        CAST(
            i.discount_amount_egp
            AS DECIMAL(12, 2)
        )                                                               AS total_discount_egp,

        CAST(
            GREATEST((i.quantity * i.unit_price_egp) - i.discount_amount_egp, 0)
            AS DECIMAL(12, 2)
        )                                                               AS net_revenue_egp,

        CAST(
            i.quantity * i.unit_cost_egp
            AS DECIMAL(12, 2)
        )                                                               AS total_cost_egp,

        CAST(
            GREATEST((i.quantity * i.unit_price_egp) - i.discount_amount_egp, 0)
            - (i.quantity * i.unit_cost_egp)
            AS DECIMAL(12, 2)
        )                                                               AS gross_profit_egp,

        CAST(
            CASE
                WHEN GREATEST((i.quantity * i.unit_price_egp) - i.discount_amount_egp, 0) > 0
                THEN (
                    (
                        GREATEST((i.quantity * i.unit_price_egp) - i.discount_amount_egp, 0)
                        - (i.quantity * i.unit_cost_egp)
                    )
                    / GREATEST((i.quantity * i.unit_price_egp) - i.discount_amount_egp, 0)
                ) * 100
                ELSE 0
            END
            AS DECIMAL(12, 2)
        )                                                               AS gross_margin_pct

    FROM order_items i
    INNER JOIN orders o
        ON i.order_id = o.order_id
    LEFT JOIN current_products p
        ON i.product_id = p.product_id
    LEFT JOIN order_details od
        ON o.order_channel = od.order_channel
       AND o.payment_method = od.payment_method
       AND o.order_status = od.order_status
)

SELECT * FROM sales_fact
