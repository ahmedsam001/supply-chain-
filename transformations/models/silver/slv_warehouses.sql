{{ config(materialized='table') }}

WITH raw AS (
    SELECT * FROM {{ source('supply_chain_stage', 'RAW_WAREHOUSES') }}
),

-- 1. Parse mixed audit timestamps before deduplicating
parsed_dates AS (
    SELECT
        *,
        COALESCE(
            TRY_CAST(TRIM(LAST_AUDIT_RAW) AS TIMESTAMP),
            TRY_STRPTIME(TRIM(LAST_AUDIT_RAW), '%d/%m/%Y %H:%M'),
            TRY_STRPTIME(TRIM(LAST_AUDIT_RAW), '%d/%m/%Y %H:%M:%S'),
            TRY_STRPTIME(TRIM(LAST_AUDIT_RAW), '%Y/%m/%d %H:%M:%S'),
            TRY_STRPTIME(TRIM(LAST_AUDIT_RAW), '%Y/%m/%d %H:%M')
        ) AS parsed_audit_ts
    FROM raw
),

-- 2. Deduplicate chronologically by warehouse_id
deduped AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY TRIM(WAREHOUSE_ID)
            ORDER BY parsed_audit_ts DESC NULLS LAST, LAST_AUDIT_RAW DESC
        ) AS rn
    FROM parsed_dates
),

-- 3. Centralized governorate lookup (normalizes e.g. 'Al Qahirah' -> 'CAIRO')
gov_mapping AS (
    SELECT DISTINCT
        LOWER(TRIM(raw_value))      AS raw_value_key,
        UPPER(TRIM(standard_value)) AS standard_value
    FROM {{ ref('locations_mapping') }}
),

-- 4. Standardize strings, validate coordinates, and apply Infinity Date validity
cleaned AS (
    SELECT
        TRIM(d.WAREHOUSE_ID)                                            AS warehouse_id,
        TRIM(COALESCE(d.WAREHOUSE_NAME, 'UNKNOWN'))                     AS warehouse_name,
        UPPER(TRIM(COALESCE(d.WAREHOUSE_TYPE, 'UNKNOWN')))              AS warehouse_type,
        COALESCE(
            NULLIF(m.standard_value, 'UNKNOWN'),
            UPPER(TRIM(NULLIF(d.GOVERNORATE_RAW, ''))),
            'UNKNOWN'
        )                                                               AS governorate,
        UPPER(TRIM(COALESCE(d.CITY_RAW, 'UNKNOWN')))                    AS city,

        -- Non-positive capacity -> NULL; otherwise positive integer
        CAST(
            CASE
                WHEN d.CAPACITY_PALLETS <= 0 THEN NULL
                ELSE ABS(COALESCE(d.CAPACITY_PALLETS, 0))
            END
            AS INTEGER
        )                                                               AS capacity_pallets,

        UPPER(TRIM(COALESCE(d.COLD_CHAIN_ENABLED, 'N')))                AS cold_chain_enabled,

        -- Egypt bounding box: Latitude 21-32 N, Longitude 24-37 E
        CASE
            WHEN d.LATITUDE BETWEEN 21 AND 32 AND d.LONGITUDE BETWEEN 24 AND 37
            THEN CAST(d.LATITUDE AS DECIMAL(12, 6))
            ELSE NULL
        END                                                             AS latitude,
        CASE
            WHEN d.LATITUDE BETWEEN 21 AND 32 AND d.LONGITUDE BETWEEN 24 AND 37
            THEN CAST(d.LONGITUDE AS DECIMAL(12, 6))
            ELSE NULL
        END                                                             AS longitude,

        UPPER(TRIM(COALESCE(d.OPERATIONAL_STATUS, 'UNKNOWN')))          AS operational_status,

        -- Parsed last audit timestamp with safe fallback
        COALESCE(
            d.parsed_audit_ts,
            CAST('1970-01-01 00:00:00' AS TIMESTAMP)
        )                                                               AS last_audit_ts,

        -- Data quality flags
        CASE WHEN d.CAPACITY_PALLETS <= 0 THEN TRUE ELSE FALSE END      AS had_non_positive_capacity,
        CASE
            WHEN NOT (d.LATITUDE BETWEEN 21 AND 32 AND d.LONGITUDE BETWEEN 24 AND 37)
            THEN TRUE ELSE FALSE
        END                                                             AS had_coords_outside_egypt,
        CASE
            WHEN d.parsed_audit_ts IS NULL AND d.LAST_AUDIT_RAW IS NOT NULL
            THEN TRUE ELSE FALSE
        END                                                             AS is_audit_ts_unparseable

    FROM deduped d
    LEFT JOIN gov_mapping m
        ON LOWER(TRIM(d.GOVERNORATE_RAW)) = m.raw_value_key
    WHERE d.rn = 1
)

SELECT * FROM cleaned
