{{ config(materialized='table') }}

WITH date_spine AS (
    SELECT
        CAST(d AS DATE) AS full_date
    FROM generate_series(
        DATE '2024-01-01',
        DATE '2027-12-31',
        INTERVAL 1 DAY
    ) AS t(d)
),

enriched AS (
    SELECT
        CAST(STRFTIME(full_date, '%Y%m%d') AS INTEGER)                  AS date_key,
        full_date,
        CAST(EXTRACT(YEAR FROM full_date) AS INTEGER)                   AS year,
        CAST(EXTRACT(QUARTER FROM full_date) AS INTEGER)                AS quarter,
        CAST(EXTRACT(MONTH FROM full_date) AS INTEGER)                  AS month,
        UPPER(STRFTIME(full_date, '%B'))                                AS month_name,
        CAST(EXTRACT(WEEK FROM full_date) AS INTEGER)                   AS week_of_year,
        CAST(EXTRACT(DAY FROM full_date) AS INTEGER)                    AS day_of_month,
        CAST(EXTRACT(ISODOW FROM full_date) AS INTEGER)                 AS day_of_week,
        UPPER(STRFTIME(full_date, '%A'))                                AS day_name,
        STRFTIME(full_date, '%Y-%m')                                    AS year_month,
        CONCAT(
            CAST(EXTRACT(YEAR FROM full_date) AS VARCHAR),
            '-Q',
            CAST(EXTRACT(QUARTER FROM full_date) AS VARCHAR)
        )                                                               AS year_quarter,

        -- Egypt weekend: Friday (ISODOW = 5) and Saturday (ISODOW = 6)
        CASE
            WHEN EXTRACT(ISODOW FROM full_date) IN (5, 6) THEN TRUE
            ELSE FALSE
        END                                                             AS is_egypt_weekend,

        CASE
            WHEN EXTRACT(DAY FROM full_date) = 1 THEN TRUE
            ELSE FALSE
        END                                                             AS is_month_start,

        CASE
            WHEN full_date = LAST_DAY(full_date) THEN TRUE
            ELSE FALSE
        END                                                             AS is_month_end
    FROM date_spine
)

SELECT * FROM enriched
ORDER BY date_key
