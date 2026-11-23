{{ config(materialized='table') }}

WITH raw AS (
    SELECT * FROM {{ source('supply_chain_stage', 'RAW_PO_LINES') }}
),

-- 1. Deduplicate by po_line_id
deduped AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY TRIM(PO_LINE_ID)
            ORDER BY PO_LINE_ID DESC
        ) AS rn
    FROM raw
),

-- 2. Standardize strings, enforce qty caps, cast financials to DECIMAL(12, 2)
cleaned AS (
    SELECT
        TRIM(PO_LINE_ID)                                                AS po_line_id,
        TRIM(PO_ID)                                                     AS po_id,
        TRIM(PRODUCT_ID)                                                AS product_id,
        UPPER(TRIM(COALESCE(STORE, 'UNKNOWN')))                         AS store,
        UPPER(TRIM(COALESCE(CATEGORY, 'UNKNOWN')))                      AS category,

        -- Safe non-negative integer quantities (received capped at ordered)
        CAST(ABS(COALESCE(ORDERED_QTY, 0)) AS INTEGER)                  AS ordered_qty,
        CAST(
            LEAST(ABS(COALESCE(RECEIVED_QTY, 0)), ABS(COALESCE(ORDERED_QTY, 0)))
            AS INTEGER
        )                                                               AS received_qty,

        -- Safe DECIMAL(12, 2) unit cost & reconciled line total
        CAST(ABS(COALESCE(UNIT_COST_EGP, 0)) AS DECIMAL(12, 2))         AS unit_cost_egp,
        CAST(
            CASE
                WHEN LINE_TOTAL_EGP IS NULL
                  OR ABS(
                        ABS(LINE_TOTAL_EGP)
                        - (ABS(COALESCE(ORDERED_QTY, 0)) * ABS(COALESCE(UNIT_COST_EGP, 0)))
                     ) > 0.01
                THEN ABS(COALESCE(ORDERED_QTY, 0)) * ABS(COALESCE(UNIT_COST_EGP, 0))
                ELSE ABS(LINE_TOTAL_EGP)
            END
            AS DECIMAL(12, 2)
        )                                                               AS line_total_egp,

        -- Data quality flags
        CASE
            WHEN RECEIVED_QTY > ABS(COALESCE(ORDERED_QTY, 0))
            THEN TRUE ELSE FALSE
        END                                                             AS had_over_received,
        CASE
            WHEN LINE_TOTAL_EGP IS NOT NULL
             AND ABS(
                    ABS(LINE_TOTAL_EGP)
                    - (ABS(COALESCE(ORDERED_QTY, 0)) * ABS(COALESCE(UNIT_COST_EGP, 0)))
                 ) > 0.01
            THEN TRUE ELSE FALSE
        END                                                             AS had_line_total_mismatch

    FROM deduped
    WHERE rn = 1
)

SELECT * FROM cleaned
