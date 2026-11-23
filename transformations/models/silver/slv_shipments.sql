{{ config(materialized='table') }}

WITH raw AS (
    SELECT * FROM {{ source('supply_chain_stage', 'RAW_SHIPMENTS') }}
),

-- 1. Parse mixed timestamp formats (ISO-8601, space-separated, DD/MM/YYYY HH:MM, YYYY/MM/DD HH:MM:SS)
parsed_dates AS (
    SELECT
        *,
        COALESCE(
            TRY_CAST(TRIM(DISPATCHED_TS_RAW) AS TIMESTAMP),
            TRY_STRPTIME(TRIM(DISPATCHED_TS_RAW), '%d/%m/%Y %H:%M'),
            TRY_STRPTIME(TRIM(DISPATCHED_TS_RAW), '%d/%m/%Y %H:%M:%S'),
            TRY_STRPTIME(TRIM(DISPATCHED_TS_RAW), '%Y/%m/%d %H:%M:%S'),
            TRY_STRPTIME(TRIM(DISPATCHED_TS_RAW), '%Y/%m/%d %H:%M')
        ) AS parsed_dispatched_ts,
        COALESCE(
            TRY_CAST(TRIM(DELIVERED_TS_RAW) AS TIMESTAMP),
            TRY_STRPTIME(TRIM(DELIVERED_TS_RAW), '%d/%m/%Y %H:%M'),
            TRY_STRPTIME(TRIM(DELIVERED_TS_RAW), '%d/%m/%Y %H:%M:%S'),
            TRY_STRPTIME(TRIM(DELIVERED_TS_RAW), '%Y/%m/%d %H:%M:%S'),
            TRY_STRPTIME(TRIM(DELIVERED_TS_RAW), '%Y/%m/%d %H:%M')
        ) AS parsed_delivered_ts
    FROM raw
),

-- 2. Deduplicate chronologically by shipment_id
deduped AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY TRIM(SHIPMENT_ID)
            ORDER BY parsed_dispatched_ts DESC NULLS LAST, DISPATCHED_TS_RAW DESC
        ) AS rn
    FROM parsed_dates
),

-- 3. Lookup tables for governorate standardization & branch fallback
gov_mapping AS (
    SELECT DISTINCT
        LOWER(TRIM(raw_value))      AS raw_value_key,
        UPPER(TRIM(standard_value)) AS standard_value
    FROM {{ ref('locations_mapping') }}
),

branches AS (
    SELECT
        branch_id,
        governorate
    FROM {{ ref('slv_branches') }}
),

-- 4. Clean strings, timestamps, numeric costs, and DQ flags
cleaned AS (
    SELECT
        TRIM(d.SHIPMENT_ID)                                             AS shipment_id,
        TRIM(d.ORDER_ID)                                                AS order_id,
        UPPER(TRIM(COALESCE(d.STORE, 'UNKNOWN')))                       AS store,
        TRIM(d.ORIGIN_WAREHOUSE_ID)                                     AS origin_warehouse_id,
        TRIM(d.DESTINATION_BRANCH_ID)                                   AS destination_branch_id,

        -- Standardize destination governorate with branch fallback
        COALESCE(
            NULLIF(m.standard_value, 'UNKNOWN'),
            NULLIF(UPPER(TRIM(b.governorate)), 'UNKNOWN'),
            'UNKNOWN'
        )                                                               AS destination_gov,

        -- Standardize categorical strings
        UPPER(TRIM(COALESCE(d.CARRIER_NAME, 'UNKNOWN')))                AS carrier_name,
        UPPER(TRIM(COALESCE(d.SHIPMENT_TYPE, 'UNKNOWN')))               AS shipment_type,
        UPPER(TRIM(COALESCE(d.SHIPMENT_STATUS_RAW, 'UNKNOWN')))         AS shipment_status,

        -- Clean timestamps (NULL only when legitimately not yet dispatched/delivered)
        d.parsed_dispatched_ts                                          AS dispatched_ts,
        CASE
            WHEN d.parsed_delivered_ts < d.parsed_dispatched_ts THEN NULL
            ELSE d.parsed_delivered_ts
        END                                                             AS delivered_ts,

        -- Safe, non-negative shipping cost in DECIMAL(12, 2)
        CAST(ABS(COALESCE(d.SHIPPING_COST_EGP, 0)) AS DECIMAL(12, 2))   AS shipping_cost_egp,

        -- Data quality flags
        CASE
            WHEN d.parsed_delivered_ts < d.parsed_dispatched_ts
            THEN TRUE ELSE FALSE
        END                                                             AS had_delivered_before_dispatched,
        CASE
            WHEN d.SHIPPING_COST_EGP < 0
            THEN TRUE ELSE FALSE
        END                                                             AS had_negative_cost,
        CASE
            WHEN d.parsed_dispatched_ts IS NULL AND d.DISPATCHED_TS_RAW IS NOT NULL
            THEN TRUE ELSE FALSE
        END                                                             AS is_dispatched_ts_unparseable,
        CASE
            WHEN d.parsed_delivered_ts IS NULL AND d.DELIVERED_TS_RAW IS NOT NULL
            THEN TRUE ELSE FALSE
        END                                                             AS is_delivered_ts_unparseable,
        CASE
            WHEN d.parsed_delivered_ts > CURRENT_TIMESTAMP
            THEN TRUE ELSE FALSE
        END                                                             AS is_future_delivery_ts

    FROM deduped d
    LEFT JOIN gov_mapping m
        ON LOWER(TRIM(d.DESTINATION_GOV_RAW)) = m.raw_value_key
    LEFT JOIN branches b
        ON TRIM(d.DESTINATION_BRANCH_ID) = b.branch_id
    WHERE d.rn = 1
)

SELECT * FROM cleaned
