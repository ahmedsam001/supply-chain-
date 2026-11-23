{{ config(materialized='table') }}

WITH silver_warehouses AS (
    SELECT * FROM {{ ref('slv_warehouses') }}
),

final AS (
    SELECT
        warehouse_id,
        warehouse_name,
        warehouse_type,
        governorate,
        city,
        capacity_pallets,
        cold_chain_enabled,
        latitude,
        longitude,
        operational_status,
        last_audit_ts
    FROM silver_warehouses
)

SELECT * FROM final
