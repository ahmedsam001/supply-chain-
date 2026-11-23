{{ config(materialized='table') }}

WITH po_lines AS (
    SELECT * FROM {{ ref('slv_po_lines') }}
),

purchase_orders AS (
    SELECT * FROM {{ ref('slv_purchase_orders') }}
),

current_products AS (
    SELECT
        product_sk,
        product_id
    FROM {{ ref('dim_product') }}
    WHERE is_current = TRUE
),

po_details AS (
    SELECT * FROM {{ ref('dim_po_details') }}
),

procurement_fact AS (
    SELECT
        -- Grain: 1 row per purchase order line item
        l.po_line_id,
        l.po_id,

        -- Conformed Dimension Foreign Keys
        CAST(STRFTIME(CAST(po.order_date AS DATE), '%Y%m%d') AS INTEGER)                AS order_date_key,
        CASE
            WHEN po.expected_delivery_clean IS NOT NULL
            THEN CAST(STRFTIME(CAST(po.expected_delivery_clean AS DATE), '%Y%m%d') AS INTEGER)
            ELSE NULL
        END                                                                             AS expected_delivery_date_key,
        p.product_sk,
        l.product_id,
        COALESCE(l.store, po.store)                                                     AS store_id,
        po.supplier_id,
        po.warehouse_id,
        pd.po_details_key,

        -- Procurement Dates
        po.order_date,
        po.expected_delivery_clean,

        -- Procurement Quantities & Financial Measures
        l.ordered_qty,
        l.received_qty,
        CAST(GREATEST(l.ordered_qty - l.received_qty, 0) AS INTEGER)                    AS open_qty,
        CAST(
            CASE
                WHEN l.ordered_qty > 0
                THEN (CAST(l.received_qty AS DOUBLE) / l.ordered_qty) * 100
                ELSE 0
            END
            AS DECIMAL(12, 2)
        )                                                                               AS fill_rate_pct,

        l.unit_cost_egp,
        l.line_total_egp,
        CAST(l.received_qty * l.unit_cost_egp AS DECIMAL(12, 2))                        AS received_value_egp,
        CAST(
            DATEDIFF('day', CAST(po.order_date AS DATE), CAST(po.expected_delivery_clean AS DATE))
            AS INTEGER
        )                                                                               AS expected_lead_days

    FROM po_lines l
    INNER JOIN purchase_orders po
        ON l.po_id = po.po_id
    LEFT JOIN current_products p
        ON l.product_id = p.product_id
    LEFT JOIN po_details pd
        ON po.po_status = pd.po_status
       AND po.currency = pd.currency
)

SELECT * FROM procurement_fact
