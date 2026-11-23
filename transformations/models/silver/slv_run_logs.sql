{{ config(materialized='table') }}

WITH raw AS (
    SELECT * FROM {{ source('live_market', 'RUN_LOGS') }}
),

-- 1. Deduplicate chronologically by run_id
deduped AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY TRIM(RUN_ID)
            ORDER BY FINISHED_AT DESC NULLS LAST, STARTED_AT DESC NULLS LAST
        ) AS rn
    FROM raw
),

-- 2. Standardize strings, enforce non-negative metrics, and validate timestamps
cleaned AS (
    SELECT
        TRIM(RUN_ID)                                                    AS run_id,
        UPPER(TRIM(COALESCE(STORE, 'UNKNOWN')))                         AS store,
        UPPER(TRIM(COALESCE(RUN_MODE, 'UNKNOWN')))                      AS run_mode,
        CAST(RUN_DATE AS DATE)                                          AS run_date,

        -- Safe non-negative integer counts & DECIMAL(12, 2) duration
        CAST(ABS(COALESCE(PRODUCTS_COLLECTED, 0)) AS INTEGER)           AS products_collected,
        CAST(ABS(COALESCE(SNAPSHOTS_WRITTEN, 0)) AS INTEGER)            AS snapshots_written,
        CAST(ABS(COALESCE(PRODUCTS_UNCHANGED, 0)) AS INTEGER)           AS products_unchanged,
        CAST(ABS(COALESCE(DURATION_SECONDS, 0)) AS DECIMAL(12, 2))      AS duration_seconds,

        CAST(STARTED_AT AS TIMESTAMP)                                   AS started_at,

        -- Transactional event timestamp: keep NULL if FINISHED_AT predates STARTED_AT or unfinished
        CASE
            WHEN FINISHED_AT < STARTED_AT THEN NULL
            ELSE CAST(FINISHED_AT AS TIMESTAMP)
        END                                                             AS finished_at,

        -- Derived & data quality flags
        CASE WHEN ABS(COALESCE(PRODUCTS_COLLECTED, 0)) = 0 THEN TRUE ELSE FALSE END AS is_zero_product_run,
        CASE WHEN FINISHED_AT < STARTED_AT THEN TRUE ELSE FALSE END                 AS had_finished_before_started,
        CASE
            WHEN PRODUCTS_COLLECTED < 0 OR DURATION_SECONDS < 0
            THEN TRUE ELSE FALSE
        END                                                                         AS had_negative_counts

    FROM deduped
    WHERE rn = 1
)

SELECT * FROM cleaned
