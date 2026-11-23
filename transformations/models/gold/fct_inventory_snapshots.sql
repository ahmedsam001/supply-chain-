{{ config(materialized='table') }}

WITH inventory_logs AS (
    SELECT * FROM {{ ref('slv_inventory_logs') }}
),

current_products AS (
    SELECT
        product_sk,
        product_id
    FROM {{ ref('dim_product') }}
    WHERE is_current = TRUE
),

inventory_status AS (
    SELECT * FROM {{ ref('dim_inventory_status') }}
),

inventory_fact AS (
    SELECT
        -- Grain: 1 row per product x location x inventory snapshot (Semi-Additive)
        inv.inv_log_id,

        -- Conformed Dimension Foreign Keys
        CAST(STRFTIME(CAST(inv.snapshot_ts AS DATE), '%Y%m%d') AS INTEGER)  AS date_key,
        p.product_sk,
        inv.product_id,
        inv.store                                                           AS store_id,
        inv.warehouse_id,
        inv.branch_id,
        ist.inventory_status_key,

        -- Snapshot Timestamp
        inv.snapshot_ts,

        -- Semi-Additive Inventory Measures
        inv.qty_on_hand,
        inv.reserved_qty,
        CAST(GREATEST(inv.qty_on_hand - inv.reserved_qty, 0) AS INTEGER)    AS available_qty,
        inv.reorder_point,

        -- Operational Alert Flags
        CASE WHEN inv.qty_on_hand = 0 THEN TRUE ELSE FALSE END              AS is_stockout,
        CASE WHEN inv.qty_on_hand <= inv.reorder_point THEN TRUE ELSE FALSE END AS is_below_reorder

    FROM inventory_logs inv
    LEFT JOIN current_products p
        ON inv.product_id = p.product_id
    LEFT JOIN inventory_status ist
        ON inv.location_type = ist.location_type
       AND inv.stock_status = ist.stock_status
)

SELECT * FROM inventory_fact
