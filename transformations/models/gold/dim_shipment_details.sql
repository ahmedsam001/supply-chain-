{{ config(materialized='table') }}

WITH distinct_shipment_attrs AS (
    SELECT DISTINCT
        carrier_name,
        shipment_type,
        shipment_status,
        destination_gov
    FROM {{ ref('slv_shipments') }}
)

SELECT
    ROW_NUMBER() OVER (
        ORDER BY carrier_name, shipment_type, shipment_status, destination_gov
    ) AS shipment_details_key,
    carrier_name,
    shipment_type,
    shipment_status,
    destination_gov
FROM distinct_shipment_attrs
