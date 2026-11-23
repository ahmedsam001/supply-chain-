{{ config(materialized='table') }}

WITH silver_suppliers AS (
    SELECT * FROM {{ ref('slv_suppliers') }}
),

final AS (
    SELECT
        supplier_id,
        supplier_name,
        supplier_type,
        archetype_code,
        country,
        city,
        currency,
        payment_terms,
        rating,
        contact_email,
        active_flag,
        created_at
    FROM silver_suppliers
)

SELECT * FROM final
