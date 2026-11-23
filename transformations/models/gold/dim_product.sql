{{ config(materialized='table') }}

WITH silver_products AS (
    SELECT * FROM {{ ref('slv_products') }}
),

scd2_dimension AS (
    SELECT
        -- Deterministic surrogate key for SCD Type 2 versioning
        MD5(
            product_id || '|' || CAST(first_seen_at AS VARCHAR)
        )                                                               AS product_sk,

        -- Natural & conformed foreign keys
        product_id,
        store                                                           AS store_id,

        -- Conformed product attributes
        product_name,
        category,
        CASE
            WHEN category LIKE '%WATCH%' OR category LIKE '%WEARABLE%'
                THEN 'WEARABLES & SMARTWATCHES'
            WHEN category LIKE '%CASE%' OR category LIKE '%CABLE%' OR category LIKE '%CORD%'
              OR category LIKE '%CHARG%' OR category LIKE '%POWER%' OR category LIKE '%ACCESSOR%'
              OR category LIKE '%STRAP%' OR category LIKE '%LENS%' OR category LIKE '%PROTECTOR%'
              OR category LIKE '%BAND%' OR category LIKE '%AIRTAG%' OR category LIKE '%PENCIL%'
              OR category LIKE '%CARD HOLDER%' OR category LIKE '%POLISHING%' OR category LIKE '%EXTENDER%'
                THEN 'ACCESSORIES & CHARGING'
            WHEN category LIKE '%PHONE%' OR category LIKE '%MOBILE%' OR category LIKE '%TABLET%'
              OR category LIKE '%IPAD%'
                THEN 'SMARTPHONES & TABLETS'
            WHEN category LIKE '%LAPTOP%' OR category LIKE '%COMPUT%' OR category LIKE '%MAC%'
              OR category LIKE '%DESKTOP%' OR category LIKE '%MONITOR%' OR category LIKE '%DISPLAY%'
              OR category LIKE '%PRINTER%' OR category LIKE '%STORAGE%' OR category LIKE '%NETWORK%'
              OR category LIKE '%KEYBOARD%' OR category LIKE '%MICE%' OR category LIKE '%SOFTWARE%'
                THEN 'LAPTOPS & COMPUTING'
            WHEN category LIKE '%APPLIANCE%' OR category LIKE '%WATER TREATMENT%' OR category LIKE '%AIR CARE%'
                THEN 'HOME & KITCHEN APPLIANCES'
            WHEN category LIKE '%TV%' OR category LIKE '%TELEVISION%' OR category LIKE '%AUDIO%'
              OR category LIKE '%SPEAKER%' OR category LIKE '%HEADPHONE%' OR category LIKE '%AIRPODS%'
              OR category LIKE '%MICROPHONE%' OR category LIKE '%PROJECTOR%' OR category LIKE '%MUSICAL%'
              OR category = 'ELECTRONICS'
                THEN 'TV, AUDIO & ELECTRONICS'
            WHEN category LIKE '%GAMING%' OR category LIKE '%CAMERA%' OR category LIKE '%TOYS%'
                THEN 'GAMING & CAMERAS'
            WHEN category LIKE '%GROCERY%' OR category LIKE '%FOOD%' OR category LIKE '%BEVERAGE%'
              OR category LIKE '%COFFEE%' OR category LIKE '%MEAT%' OR category LIKE '%DAIRY%'
              OR category LIKE '%MILK%' OR category LIKE '%FRUIT%' OR category LIKE '%SNACK%'
              OR category LIKE '%BAKERY%' OR category LIKE '%PANTRY%' OR category LIKE '%COOKING%'
              OR category LIKE '%ORGANIC%' OR category LIKE '%PET%'
                THEN 'GROCERY & FOOD'
            WHEN category LIKE '%HEALTH%' OR category LIKE '%BEAUTY%' OR category LIKE '%HAIR%'
              OR category LIKE '%PERSONAL%' OR category LIKE '%BABY%' OR category LIKE '%TISSUE%'
              OR category LIKE '%LAUNDRY%' OR category LIKE '%HOUSEHOLD%' OR category LIKE '%DIFFUSER%'
              OR category LIKE '%CONSUMABLE%'
                THEN 'HEALTH, BEAUTY & HOME CARE'
            ELSE 'HOME, OFFICE & LIFESTYLE'
        END                                                             AS category_group,
        brand,
        current_price,
        old_price,
        discount_pct,
        is_price_outlier,
        stock_status,
        product_url,
        image_url,
        state_hash,

        -- SCD Type 2 validity window (Infinity Date = 9999-12-31 23:59:59 for active rows)
        first_seen_at                                                   AS valid_from,
        valid_to,
        CASE
            WHEN valid_to = CAST('9999-12-31 23:59:59' AS TIMESTAMP)
            THEN TRUE
            ELSE FALSE
        END                                                             AS is_current,

        -- Operational audit timestamps
        last_updated_at,
        last_checked_at

    FROM silver_products
)

SELECT * FROM scd2_dimension
