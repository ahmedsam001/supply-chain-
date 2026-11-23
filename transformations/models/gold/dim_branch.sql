{{ config(materialized='table') }}

WITH silver_branches AS (
    SELECT * FROM {{ ref('slv_branches') }}
),

final AS (
    SELECT
        branch_id,
        store                                                           AS store_id,
        branch_name,
        governorate,
        city,
        address,
        phone,
        latitude,
        longitude,
        last_checked_at
    FROM silver_branches
)

SELECT * FROM final
