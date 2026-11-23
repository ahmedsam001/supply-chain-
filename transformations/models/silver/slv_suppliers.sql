{{ config(materialized='table') }}

WITH raw AS (
    SELECT * FROM {{ source('supply_chain_stage', 'RAW_SUPPLIERS') }}
),

-- 1. Parse mixed creation timestamps before deduplicating
parsed_dates AS (
    SELECT
        *,
        COALESCE(
            TRY_CAST(TRIM(CREATED_AT_RAW) AS TIMESTAMP),
            TRY_STRPTIME(TRIM(CREATED_AT_RAW), '%d/%m/%Y %H:%M'),
            TRY_STRPTIME(TRIM(CREATED_AT_RAW), '%d/%m/%Y %H:%M:%S'),
            TRY_STRPTIME(TRIM(CREATED_AT_RAW), '%Y/%m/%d %H:%M:%S'),
            TRY_STRPTIME(TRIM(CREATED_AT_RAW), '%Y/%m/%d %H:%M')
        ) AS parsed_created_at
    FROM raw
),

-- 2. Deduplicate chronologically by supplier_id
deduped AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY TRIM(SUPPLIER_ID)
            ORDER BY parsed_created_at DESC NULLS LAST, CREATED_AT_RAW DESC
        ) AS rn
    FROM parsed_dates
),

-- 3. Standardize strings, normalize active_flag, cast rating, and apply Infinity Date validity
cleaned AS (
    SELECT
        TRIM(SUPPLIER_ID)                                               AS supplier_id,
        TRIM(COALESCE(SUPPLIER_NAME, 'UNKNOWN'))                        AS supplier_name,
        UPPER(TRIM(COALESCE(SUPPLIER_TYPE, 'UNKNOWN')))                 AS supplier_type,
        UPPER(TRIM(COALESCE(ARCHETYPE_CODE, 'UNKNOWN')))                AS archetype_code,
        UPPER(TRIM(COALESCE(COUNTRY, 'UNKNOWN')))                       AS country,
        CASE UPPER(TRIM(COALESCE(CITY, 'UNKNOWN')))
            WHEN '6TH OCTOBERGIZA'              THEN '6TH OF OCTOBER'
            WHEN 'AL QAHIRAH'                   THEN 'CAIRO'
            WHEN 'NASR CITY, CAIRO'             THEN 'CAIRO'
            WHEN 'BADR CITY - CAIRO'            THEN 'BADR CITY'
            WHEN '10TH OF RAMADAN - SHARQIA'    THEN '10TH OF RAMADAN'
            ELSE UPPER(TRIM(COALESCE(CITY, 'UNKNOWN')))
        END                                                             AS city,
        UPPER(TRIM(COALESCE(CURRENCY, 'EGP')))                          AS currency,
        UPPER(TRIM(COALESCE(PAYMENT_TERMS, 'UNKNOWN')))                 AS payment_terms,

        -- Rating bounded to [0, 5] as DECIMAL(12, 2)
        CAST(
            CASE
                WHEN RATING < 0 OR RATING > 5 THEN NULL
                ELSE COALESCE(RATING, 0)
            END
            AS DECIMAL(12, 2)
        )                                                               AS rating,

        -- Validated lowercase email
        CASE
            WHEN CONTACT_EMAIL NOT LIKE '%@%' THEN NULL
            ELSE LOWER(TRIM(CONTACT_EMAIL))
        END                                                             AS contact_email,

        -- Unify messy boolean/status strings ('1', 'Y', 'true', 'ACTIVE') -> 'ACTIVE' / 'INACTIVE'
        CASE
            WHEN UPPER(TRIM(ACTIVE_FLAG)) IN ('1', 'Y', 'YES', 'TRUE', 'ACTIVE')
            THEN 'ACTIVE'
            ELSE 'INACTIVE'
        END                                                             AS active_flag,

        -- Parsed creation timestamp with safe fallback
        COALESCE(
            parsed_created_at,
            CAST('1970-01-01 00:00:00' AS TIMESTAMP)
        )                                                               AS created_at,

        -- Data quality flags
        CASE WHEN RATING < 0 OR RATING > 5 THEN TRUE ELSE FALSE END     AS had_invalid_rating,
        CASE WHEN CONTACT_EMAIL NOT LIKE '%@%' THEN TRUE ELSE FALSE END AS had_invalid_email,
        CASE
            WHEN parsed_created_at IS NULL AND CREATED_AT_RAW IS NOT NULL
            THEN TRUE ELSE FALSE
        END                                                             AS is_created_at_unparseable

    FROM deduped
    WHERE rn = 1
)

SELECT * FROM cleaned
