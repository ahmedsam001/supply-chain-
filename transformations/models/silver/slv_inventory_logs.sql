{{ config(materialized='table') }}

WITH raw AS (
    SELECT * FROM {{ source('supply_chain_stage', 'RAW_INVENTORY_LOGS') }}
),

-- 1. Parse mixed snapshot timestamp formats before deduplicating
parsed_dates AS (
    SELECT
        *,
        COALESCE(
            TRY_CAST(TRIM(SNAPSHOT_TS_RAW) AS TIMESTAMP),
            TRY_STRPTIME(TRIM(SNAPSHOT_TS_RAW), '%d/%m/%Y %H:%M'),
            TRY_STRPTIME(TRIM(SNAPSHOT_TS_RAW), '%d/%m/%Y %H:%M:%S'),
            TRY_STRPTIME(TRIM(SNAPSHOT_TS_RAW), '%Y/%m/%d %H:%M:%S'),
            TRY_STRPTIME(TRIM(SNAPSHOT_TS_RAW), '%Y/%m/%d %H:%M')
        ) AS parsed_snapshot_ts
    FROM raw
),

-- 2. Deduplicate chronologically by inv_log_id
deduped AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY TRIM(INV_LOG_ID)
            ORDER BY parsed_snapshot_ts DESC NULLS LAST, SNAPSHOT_TS_RAW DESC
        ) AS rn
    FROM parsed_dates
),

-- 3. Standardize strings, enforce non-negative quantities, and set DQ flags
cleaned AS (
    SELECT
        TRIM(INV_LOG_ID)                                                AS inv_log_id,
        TRIM(PRODUCT_ID)                                                AS product_id,
        UPPER(TRIM(COALESCE(STORE, 'UNKNOWN')))                         AS store,
        UPPER(TRIM(COALESCE(LOCATION_TYPE, 'UNKNOWN')))                 AS location_type,
        TRIM(WAREHOUSE_ID)                                              AS warehouse_id,
        TRIM(BRANCH_ID)                                                 AS branch_id,

        -- Safe non-negative integer inventory counts
        CAST(ABS(COALESCE(QTY_ON_HAND, 0)) AS INTEGER)                  AS qty_on_hand,
        CAST(
            LEAST(ABS(COALESCE(RESERVED_QTY, 0)), ABS(COALESCE(QTY_ON_HAND, 0)))
            AS INTEGER
        )                                                               AS reserved_qty,
        CAST(ABS(COALESCE(REORDER_POINT, 0)) AS INTEGER)                AS reorder_point,

        -- Standardize stock status (unify 'OK' ERP alias into 'IN_STOCK')
        CASE
            WHEN UPPER(TRIM(STOCK_STATUS_RAW)) = 'OK' THEN 'IN_STOCK'
            ELSE UPPER(TRIM(COALESCE(STOCK_STATUS_RAW, 'UNKNOWN')))
        END                                                             AS stock_status,

        -- Parsed snapshot timestamp with safe sentinel fallback
        COALESCE(
            parsed_snapshot_ts,
            CAST('1970-01-01 00:00:00' AS TIMESTAMP)
        )                                                               AS snapshot_ts,

        -- Data quality flags
        CASE WHEN QTY_ON_HAND < 0 THEN TRUE ELSE FALSE END              AS had_negative_qty,
        CASE
            WHEN RESERVED_QTY > ABS(COALESCE(QTY_ON_HAND, 0))
            THEN TRUE ELSE FALSE
        END                                                             AS had_reserved_gt_onhand,
        CASE
            WHEN parsed_snapshot_ts IS NULL AND SNAPSHOT_TS_RAW IS NOT NULL
            THEN TRUE ELSE FALSE
        END                                                             AS is_ts_unparseable

    FROM deduped
    WHERE rn = 1
)

SELECT * FROM cleaned
