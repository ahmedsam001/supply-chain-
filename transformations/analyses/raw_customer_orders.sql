SELECT 
    -- 1. فحص الحجم الأساسي والتكرار
    COUNT(*) AS total_rows,
    COUNT(DISTINCT order_id) AS unique_orders,
    COUNT(DISTINCT customer_id) AS total_unique_customers,
    COUNT(DISTINCT store) AS distinct_stores,
    
    -- 2. فحص القيم الفاضية (Nulls) لأهم العواميد
    SUM(CASE WHEN order_id IS NULL THEN 1 ELSE 0 END) AS null_order_ids,
    SUM(CASE WHEN customer_id IS NULL THEN 1 ELSE 0 END) AS null_customers,
    SUM(CASE WHEN store IS NULL THEN 1 ELSE 0 END) AS null_stores,
    SUM(CASE WHEN order_status_raw IS NULL THEN 1 ELSE 0 END) AS null_statuses,
    SUM(CASE WHEN order_ts_raw IS NULL THEN 1 ELSE 0 END) AS null_order_dates,
    SUM(CASE WHEN payment_method_raw IS NULL THEN 1 ELSE 0 END) AS null_payment_methods,
    
    -- 3. فحص الأرقام (الفلوس) لاكتشاف أي قيم شاذة (سوالب أو أصفار)
    MIN(total_order_egp) AS min_order_value,
    MAX(total_order_egp) AS max_order_value,
    AVG(total_order_egp) AS avg_order_value,
    SUM(CASE WHEN total_order_egp < 0 THEN 1 ELSE 0 END) AS negative_totals,
    SUM(CASE WHEN shipping_fee_egp < 0 THEN 1 ELSE 0 END) AS negative_shipping
    
FROM {{ source('supply_chain_stage', 'RAW_CUSTOMER_ORDERS') }}