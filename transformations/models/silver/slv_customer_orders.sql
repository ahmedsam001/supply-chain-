{{ config(materialized='table') }}

WITH raw AS (
    SELECT * FROM {{ source('supply_chain_stage', 'RAW_CUSTOMER_ORDERS') }}
),

-- Parse mixed raw timestamp formats (ISO-8601, space-separated, DD/MM/YYYY HH:MM, YYYY/MM/DD HH:MM:SS)
-- before deduplicating so ROW_NUMBER() orders chronologically instead of lexicographically.
parsed AS (
    SELECT
        *,
        COALESCE(
            TRY_CAST(TRIM(ORDER_TS_RAW) AS TIMESTAMP),
            TRY_STRPTIME(TRIM(ORDER_TS_RAW), '%d/%m/%Y %H:%M'),
            TRY_STRPTIME(TRIM(ORDER_TS_RAW), '%d/%m/%Y %H:%M:%S'),
            TRY_STRPTIME(TRIM(ORDER_TS_RAW), '%Y/%m/%d %H:%M:%S'),
            TRY_STRPTIME(TRIM(ORDER_TS_RAW), '%Y/%m/%d %H:%M')
        ) AS parsed_order_ts
    FROM raw
),

deduped AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY TRIM(ORDER_ID)
            ORDER BY parsed_order_ts DESC NULLS LAST, ORDER_TS_RAW DESC
        ) AS rn
    FROM parsed
),

branches AS (
    SELECT
        branch_id,
        governorate
    FROM {{ ref('slv_branches') }}
),

gov_mapping AS (
    SELECT DISTINCT
        LOWER(TRIM(raw_value))          AS raw_value_key,
        UPPER(TRIM(standard_value))     AS standard_value
    FROM {{ ref('locations_mapping') }}
),

-- Aggregate shipment timestamps to 1 row per ORDER_ID to guarantee zero join fan-out
shipments AS (
    SELECT
        TRIM(ORDER_ID)                                              AS order_id,
        MIN(COALESCE(dispatched_ts, delivered_ts))                  AS shipment_fallback_ts
    FROM {{ ref('slv_shipments') }}
    GROUP BY 1
),

-- Aggregate cleaned line-item totals per order to sanitize any order containing a >=1M EGP outlier item
order_item_totals AS (
    SELECT
        order_id,
        CAST(SUM((quantity * unit_price_egp) - discount_amount_egp) AS DECIMAL(12, 2)) AS clean_items_subtotal_egp,
        BOOL_OR(is_price_outlier)                                                      AS has_price_outlier
    FROM {{ ref('slv_order_items') }}
    GROUP BY 1
),

cleaned AS (
    SELECT
        TRIM(d.ORDER_ID)                                            AS order_id,
        TRIM(d.CUSTOMER_ID)                                         AS customer_id,
        UPPER(TRIM(d.STORE))                                        AS store,
        TRIM(d.FULFILLMENT_BRANCH_ID)                               AS fulfillment_branch_id,

        -- Standardize categorical text fields
        UPPER(TRIM(COALESCE(d.ORDER_CHANNEL_RAW, 'UNKNOWN')))       AS order_channel,
        UPPER(TRIM(COALESCE(d.PAYMENT_METHOD_RAW, 'UNKNOWN')))      AS payment_method,
        COALESCE(
            NULLIF(m.standard_value, 'UNKNOWN'),
            NULLIF(UPPER(TRIM(b.governorate)), 'UNKNOWN'),
            'UNKNOWN'
        )                                                           AS customer_governorate,
        UPPER(TRIM(COALESCE(d.ORDER_STATUS_RAW, 'UNKNOWN')))        AS order_status,

        -- Multi-tier order timestamp:
        -- 1. Parsed ORDER_TS_RAW (handles all mixed formats)
        -- 2. Fallback to related shipment timestamp from slv_shipments
        -- 3. Safe sentinel timestamp so downstream date functions & not_null tests never break
        COALESCE(
            d.parsed_order_ts,
            s.shipment_fallback_ts,
            CAST('1970-01-01 00:00:00' AS TIMESTAMP)
        )                                                           AS order_ts,

        -- Safe, non-negative, fixed-precision financial columns (outlier-adjusted when order contains >=1M EGP item)
        CAST(
            CASE
                WHEN COALESCE(oi.has_price_outlier, FALSE) THEN oi.clean_items_subtotal_egp
                ELSE ABS(COALESCE(d.SUBTOTAL_EGP, 0))
            END
            AS DECIMAL(12, 2)
        )                                                           AS subtotal_egp,
        CAST(ABS(COALESCE(d.SHIPPING_FEE_EGP, 0)) AS DECIMAL(12, 2)) AS shipping_fee_egp,

        -- Reconciled total: if outlier-adjusted, NULL, or mismatched beyond 0.01 EGP tolerance, compute clean subtotal + shipping
        CAST(
            CASE
                WHEN COALESCE(oi.has_price_outlier, FALSE)
                THEN oi.clean_items_subtotal_egp + ABS(COALESCE(d.SHIPPING_FEE_EGP, 0))
                WHEN d.TOTAL_ORDER_EGP IS NULL
                  OR ABS(
                        ABS(d.TOTAL_ORDER_EGP)
                        - (ABS(COALESCE(d.SUBTOTAL_EGP, 0)) + ABS(COALESCE(d.SHIPPING_FEE_EGP, 0)))
                     ) > 0.01
                THEN ABS(COALESCE(d.SUBTOTAL_EGP, 0)) + ABS(COALESCE(d.SHIPPING_FEE_EGP, 0))
                ELSE ABS(d.TOTAL_ORDER_EGP)
            END
            AS DECIMAL(12, 2)
        )                                                           AS total_order_egp,

        -- Data quality flags
        CASE
            WHEN d.TOTAL_ORDER_EGP IS NOT NULL
             AND ABS(
                    ABS(d.TOTAL_ORDER_EGP)
                    - (ABS(COALESCE(d.SUBTOTAL_EGP, 0)) + ABS(COALESCE(d.SHIPPING_FEE_EGP, 0)))
                 ) > 0.01
            THEN TRUE ELSE FALSE
        END                                                         AS is_total_mismatch,
        CASE
            WHEN d.SUBTOTAL_EGP < 0 OR d.SHIPPING_FEE_EGP < 0 OR d.TOTAL_ORDER_EGP < 0
            THEN TRUE ELSE FALSE
        END                                                         AS had_negative_amounts,
        CASE
            WHEN d.parsed_order_ts IS NULL AND d.ORDER_TS_RAW IS NOT NULL
            THEN TRUE ELSE FALSE
        END                                                         AS is_ts_unparseable,
        CASE
            WHEN d.parsed_order_ts IS NULL
            THEN TRUE ELSE FALSE
        END                                                         AS is_ts_imputed,
        COALESCE(oi.has_price_outlier, FALSE)                       AS has_price_outlier

    FROM deduped d
    LEFT JOIN gov_mapping m
        ON LOWER(TRIM(d.CUSTOMER_GOVERNORATE_RAW)) = m.raw_value_key
    LEFT JOIN branches b
        ON TRIM(d.FULFILLMENT_BRANCH_ID) = b.branch_id
    LEFT JOIN shipments s
        ON TRIM(d.ORDER_ID) = s.order_id
    LEFT JOIN order_item_totals oi
        ON TRIM(d.ORDER_ID) = oi.order_id
    WHERE d.rn = 1
)

SELECT * FROM cleaned
