{{ config(materialized='table') }}

WITH raw AS (
    SELECT * FROM {{ source('live_market', 'BRANCHES') }}
),

deduped AS (
    SELECT *,
        ROW_NUMBER() OVER (
            PARTITION BY BRANCH_ID
            ORDER BY LAST_CHECKED_AT DESC
        ) AS rn
    FROM raw
),

with_mapping AS (
    SELECT
        d.*,
        m.governorate AS mapped_governorate,
        bn.branch_name_en AS mapped_branch_name_en
    FROM deduped d
    LEFT JOIN {{ ref('branch_to_gov') }} m
        ON TRIM(d.BRANCH_NAME) = TRIM(m.branch_name)
    LEFT JOIN {{ ref('branch_name_mapping') }} bn
        ON TRIM(d.BRANCH_NAME) = TRIM(bn.raw_branch_name)
),

cleaned AS (
    SELECT
        TRIM(BRANCH_ID)                                             AS branch_id,
        UPPER(TRIM(STORE))                                          AS store,
        COALESCE(
            NULLIF(TRIM(mapped_branch_name_en), ''),
            TRIM(BRANCH_NAME)
        )                                                           AS branch_name,
        UPPER(TRIM(COALESCE(
            NULLIF(mapped_governorate, ''),
            NULLIF(GOVERNORATE, ''),
            'unknown'
        )))                                                         AS governorate,
        CASE
            WHEN TRIM(CITY) = TRIM(BRANCH_NAME)
              OR LOWER(TRIM(CITY)) IN ('unknown', 'undefined', '')
            THEN NULL
            ELSE TRIM(CITY)
        END                                                         AS city,
        TRIM(ADDRESS)                                               AS address,
        TRIM(PHONE)                                                 AS phone,

        -- Egypt bounding box: Latitude 21–32 N, Longitude 24–37 E
        CASE
            WHEN LATITUDE BETWEEN 21 AND 32
             AND LONGITUDE BETWEEN 24 AND 37
            THEN CAST(LATITUDE AS DECIMAL(12, 6))
            ELSE NULL
        END                                                         AS latitude,

        CASE
            WHEN LATITUDE BETWEEN 21 AND 32
             AND LONGITUDE BETWEEN 24 AND 37
            THEN CAST(LONGITUDE AS DECIMAL(12, 6))
            ELSE NULL
        END                                                         AS longitude,

        CAST(LAST_CHECKED_AT AS TIMESTAMP)                          AS last_checked_at,

        -- Data quality flag
        CASE
            WHEN NOT (LATITUDE BETWEEN 21 AND 32
                      AND LONGITUDE BETWEEN 24 AND 37)
            THEN TRUE ELSE FALSE
        END                                                         AS had_coords_outside_egypt

    FROM with_mapping
    WHERE rn = 1
)

SELECT * FROM cleaned
