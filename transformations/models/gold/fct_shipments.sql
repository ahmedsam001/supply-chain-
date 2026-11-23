{{ config(materialized='table') }}

WITH shipments AS (
    SELECT * FROM {{ ref('slv_shipments') }}
),

orders AS (
    SELECT
        order_id,
        customer_id,
        order_ts
    FROM {{ ref('slv_customer_orders') }}
),

shipment_details AS (
    SELECT * FROM {{ ref('dim_shipment_details') }}
),

shipment_fact AS (
    SELECT
        -- Grain: 1 row per outbound shipment
        s.shipment_id,
        s.order_id,

        -- Conformed Dimension Foreign Keys (role-playing date keys)
        CAST(STRFTIME(CAST(o.order_ts AS DATE), '%Y%m%d') AS INTEGER)       AS order_date_key,
        CASE
            WHEN s.dispatched_ts IS NOT NULL
            THEN CAST(STRFTIME(CAST(s.dispatched_ts AS DATE), '%Y%m%d') AS INTEGER)
            ELSE NULL
        END                                                                 AS dispatched_date_key,
        CASE
            WHEN s.delivered_ts IS NOT NULL
            THEN CAST(STRFTIME(CAST(s.delivered_ts AS DATE), '%Y%m%d') AS INTEGER)
            ELSE NULL
        END                                                                 AS delivered_date_key,

        s.store                                                             AS store_id,
        s.origin_warehouse_id                                               AS warehouse_id,
        s.destination_branch_id                                             AS branch_id,
        o.customer_id,
        sd.shipment_details_key,

        -- Lifecycle Timestamps (NULL preserved when event has not yet occurred)
        o.order_ts,
        s.dispatched_ts,
        s.delivered_ts,

        -- Logistics Measures & SLA KPIs
        s.shipping_cost_egp,

        CASE
            WHEN s.dispatched_ts IS NOT NULL
            THEN CAST(DATEDIFF('minute', o.order_ts, s.dispatched_ts) / 60.0 AS DECIMAL(12, 2))
            ELSE NULL
        END                                                                 AS dispatch_lead_hours,

        CASE
            WHEN s.dispatched_ts IS NOT NULL AND s.delivered_ts IS NOT NULL
            THEN CAST(DATEDIFF('minute', s.dispatched_ts, s.delivered_ts) / 60.0 AS DECIMAL(12, 2))
            ELSE NULL
        END                                                                 AS transit_hours,

        CASE
            WHEN s.delivered_ts IS NOT NULL
            THEN CAST(DATEDIFF('minute', o.order_ts, s.delivered_ts) / 60.0 AS DECIMAL(12, 2))
            ELSE NULL
        END                                                                 AS total_fulfillment_hours,

        CASE WHEN s.shipment_status = 'DELIVERED' THEN TRUE ELSE FALSE END  AS is_delivered,

        -- Standard 96-hour (4-day) national delivery SLA for delivered shipments
        CASE
            WHEN s.shipment_status = 'DELIVERED'
             AND DATEDIFF('hour', o.order_ts, s.delivered_ts) <= 96
            THEN TRUE
            WHEN s.shipment_status = 'DELIVERED'
            THEN FALSE
            ELSE NULL
        END                                                                 AS is_on_time

    FROM shipments s
    INNER JOIN orders o
        ON s.order_id = o.order_id
    LEFT JOIN shipment_details sd
        ON s.carrier_name = sd.carrier_name
       AND s.shipment_type = sd.shipment_type
       AND s.shipment_status = sd.shipment_status
       AND s.destination_gov = sd.destination_gov
)

SELECT * FROM shipment_fact
