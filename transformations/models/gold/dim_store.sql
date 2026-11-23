{{ config(materialized='table') }}

WITH silver_stores AS (
    SELECT * FROM {{ ref('slv_stores') }}
),

final AS (
    SELECT
        store_id,
        store_name,
        domain,
        official_url,
        business_type
    FROM silver_stores
)

SELECT * FROM final
