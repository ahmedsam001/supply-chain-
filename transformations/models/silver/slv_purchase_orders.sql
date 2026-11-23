{{ config(materialized='table') }}

WITH raw AS (
    SELECT * FROM {{ source('supply_chain_stage', 'RAW_PURCHASE_ORDERS') }}
),

-- 1. Parse mixed raw date/timestamp formats before deduplicating
parsed_dates AS (
    SELECT
        *,
        COALESCE(
            TRY_CAST(TRIM(ORDER_DATE_RAW) AS TIMESTAMP),
            TRY_STRPTIME(TRIM(ORDER_DATE_RAW), '%d/%m/%Y %H:%M'),
            TRY_STRPTIME(TRIM(ORDER_DATE_RAW), '%d/%m/%Y %H:%M:%S'),
            TRY_STRPTIME(TRIM(ORDER_DATE_RAW), '%Y/%m/%d %H:%M:%S'),
            TRY_STRPTIME(TRIM(ORDER_DATE_RAW), '%Y/%m/%d %H:%M')
        ) AS parsed_order_date,
        COALESCE(
            TRY_CAST(TRIM(EXPECTED_DELIVERY_RAW) AS TIMESTAMP),
            TRY_STRPTIME(TRIM(EXPECTED_DELIVERY_RAW), '%d/%m/%Y %H:%M'),
            TRY_STRPTIME(TRIM(EXPECTED_DELIVERY_RAW), '%d/%m/%Y %H:%M:%S'),
            TRY_STRPTIME(TRIM(EXPECTED_DELIVERY_RAW), '%Y/%m/%d %H:%M:%S'),
            TRY_STRPTIME(TRIM(EXPECTED_DELIVERY_RAW), '%Y/%m/%d %H:%M')
        ) AS parsed_expected_delivery
    FROM raw
),

-- 2. Deduplicate chronologically by po_id
deduped AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY TRIM(PO_ID)
            ORDER BY parsed_order_date DESC NULLS LAST, ORDER_DATE_RAW DESC
        ) AS rn
    FROM parsed_dates
),

-- 3. Standardize strings, validate dates, cast financials to DECIMAL(12, 2)
cleaned AS (
    SELECT
        TRIM(PO_ID)                                                     AS po_id,
        TRIM(SUPPLIER_ID)                                               AS supplier_id,
        TRIM(WAREHOUSE_ID)                                              AS warehouse_id,
        UPPER(TRIM(COALESCE(STORE, 'UNKNOWN')))                         AS store,
        UPPER(TRIM(COALESCE(PO_STATUS_RAW, 'UNKNOWN')))                 AS po_status,

        -- Parsed order date with safe sentinel fallback
        COALESCE(
            parsed_order_date,
            CAST('1970-01-01 00:00:00' AS TIMESTAMP)
        )                                                               AS order_date,

        -- Raw parsed expected delivery & chronologically validated clean expected delivery
        parsed_expected_delivery                                        AS expected_delivery,
        CASE
            WHEN parsed_expected_delivery < parsed_order_date THEN NULL
            ELSE parsed_expected_delivery
        END                                                             AS expected_delivery_clean,

        -- Safe non-negative DECIMAL(12, 2) PO amount
        CAST(ABS(COALESCE(TOTAL_AMOUNT_EGP, 0)) AS DECIMAL(12, 2))      AS total_amount_egp,
        UPPER(TRIM(COALESCE(CURRENCY, 'EGP')))                          AS currency,

        -- Data quality flags
        CASE
            WHEN parsed_expected_delivery < parsed_order_date
            THEN TRUE ELSE FALSE
        END                                                             AS had_delivery_before_order,
        CASE WHEN TOTAL_AMOUNT_EGP < 0 THEN TRUE ELSE FALSE END         AS had_negative_amount,
        CASE
            WHEN parsed_order_date IS NULL AND ORDER_DATE_RAW IS NOT NULL
            THEN TRUE ELSE FALSE
        END                                                             AS is_order_date_unparseable,
        CASE
            WHEN parsed_expected_delivery IS NULL AND EXPECTED_DELIVERY_RAW IS NOT NULL
            THEN TRUE ELSE FALSE
        END                                                             AS is_delivery_date_unparseable

    FROM deduped
    WHERE rn = 1
)

SELECT * FROM cleaned
