-- =============================================================
-- Egypt E-Commerce DWH — PostgreSQL / DuckDB Compatible Schema
-- =============================================================
-- Tables follow a star schema partitioned by canonical Department:
--   dim_department, dim_source, dim_product, dim_location → fact_observation
-- Each department also has its own dedicated SQL View (v_dept_*)
-- so electronics, meats, mobiles, grocery, etc. can be queried independently.
-- =============================================================

-- ── Department / Sector dimension (الأقسام الرئيسية) ──────────
CREATE TABLE IF NOT EXISTS dim_department (
    department_id   TEXT PRIMARY KEY,
    name_en         TEXT NOT NULL,
    name_ar         TEXT NOT NULL,
    sector          TEXT NOT NULL,
    view_name       TEXT
);

-- ── Source dimension ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dim_source (
    source_id        TEXT PRIMARY KEY,
    source_name      TEXT,
    domain           TEXT,
    business_type    TEXT,
    collection_mode  TEXT   -- 'offline_fixture' | 'live'
);

-- ── Product dimension ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dim_product (
    product_id          TEXT PRIMARY KEY,
    source_id           TEXT,
    source_product_id   TEXT,
    department          TEXT,   -- FK → dim_department(department_id)
    product_name        TEXT NOT NULL,
    brand               TEXT,
    category            TEXT,
    subcategory         TEXT,
    sku                 TEXT,
    gtin                TEXT,
    product_url         TEXT,
    image_url           TEXT,
    first_seen_at       TIMESTAMP,
    last_seen_at        TIMESTAMP
);

-- ── Location dimension ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dim_location (
    location_id     TEXT PRIMARY KEY,
    source_id       TEXT,
    location_type   TEXT,   -- 'branch' | 'presence' | 'delivery_zone'
    location_name   TEXT,
    branch_name     TEXT,
    address         TEXT,
    city            TEXT,
    governorate     TEXT,
    latitude        DOUBLE PRECISION,
    longitude       DOUBLE PRECISION,
    phone           TEXT,
    working_hours   TEXT,
    first_seen_at   TIMESTAMP
);

-- ── Daily price / availability observation fact ───────────────
CREATE TABLE IF NOT EXISTS fact_observation (
    observation_id      TEXT PRIMARY KEY,
    product_id          TEXT,
    source_id           TEXT,
    source_product_id   TEXT,
    department          TEXT,   -- FK → dim_department(department_id)

    -- Time
    run_date            DATE NOT NULL,
    run_id              TEXT,
    observed_at         TIMESTAMP,
    collection_mode     TEXT,   -- 'offline_fixture' | 'live'

    -- Price
    price               DOUBLE PRECISION,
    old_price           DOUBLE PRECISION,
    discount            DOUBLE PRECISION,
    currency            TEXT DEFAULT 'EGP',
    raw_price_text      TEXT,

    -- Availability
    availability_status TEXT,
    availability_scope  TEXT,
    stock_status        TEXT,
    raw_availability_text TEXT,

    -- Delivery
    delivery_available  BOOLEAN,
    delivery_eta        TEXT,
    delivery_fee        DOUBLE PRECISION,
    delivery_status     TEXT,

    -- Seller
    seller_name         TEXT,
    fulfillment_method  TEXT,

    -- Quality
    quality_score       DOUBLE PRECISION,
    row_hash            TEXT
);

-- ── Quality issues log ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fact_quality_issue (
    issue_id        TEXT PRIMARY KEY,
    run_date        DATE,
    run_id          TEXT,
    source_id       TEXT,
    entity_type     TEXT,
    entity_id       TEXT,
    issue_code      TEXT,
    severity        TEXT,
    message         TEXT,
    raw_value       TEXT,
    detected_at     TIMESTAMP
);

-- ── Daily run manifest ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS run_manifest (
    run_id              TEXT PRIMARY KEY,
    run_date            DATE,
    source_id           TEXT,
    collection_mode     TEXT,
    products_count      INTEGER,
    observations_count  INTEGER,
    locations_count     INTEGER,
    quality_issues_count INTEGER,
    quality_score       DOUBLE PRECISION,
    duration_seconds    DOUBLE PRECISION,
    errors_count        INTEGER,
    started_at          TIMESTAMP,
    finished_at         TIMESTAMP
);

-- ── Indexes ───────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_obs_product   ON fact_observation(product_id);
CREATE INDEX IF NOT EXISTS idx_obs_source    ON fact_observation(source_id);
CREATE INDEX IF NOT EXISTS idx_obs_dept      ON fact_observation(department);
CREATE INDEX IF NOT EXISTS idx_obs_run_date  ON fact_observation(run_date);
CREATE INDEX IF NOT EXISTS idx_obs_price     ON fact_observation(price);
CREATE INDEX IF NOT EXISTS idx_prod_source   ON dim_product(source_id);
CREATE INDEX IF NOT EXISTS idx_prod_dept     ON dim_product(department);
CREATE INDEX IF NOT EXISTS idx_loc_gov       ON dim_location(governorate);
CREATE INDEX IF NOT EXISTS idx_loc_source    ON dim_location(source_id);

-- ── Department Summary View (ملخص كل قسم مستقل) ───────────────
CREATE OR REPLACE VIEW v_department_summary AS
SELECT
    d.department_id,
    d.name_ar AS department_ar,
    d.name_en AS department_en,
    d.sector,
    COUNT(DISTINCT p.product_id) AS products_count,
    COUNT(o.observation_id) AS observations_count,
    ROUND(AVG(CASE WHEN o.price > 0 AND o.price <= 500000 THEN o.price END), 2) AS avg_price_egp,
    MIN(CASE WHEN o.price > 0 THEN o.price END) AS min_price_egp,
    MAX(CASE WHEN o.price <= 500000 THEN o.price END) AS max_price_egp,
    SUM(CASE WHEN o.availability_status = 'in_stock' THEN 1 ELSE 0 END) AS in_stock_count
FROM dim_department d
LEFT JOIN dim_product p ON p.department = d.department_id
LEFT JOIN fact_observation o ON o.product_id = p.product_id
GROUP BY d.department_id, d.name_ar, d.name_en, d.sector;

-- ── Isolated Department Views (جداول عرض منفصلة لكل قسم) ───────
CREATE OR REPLACE VIEW v_dept_mobiles_tablets AS
SELECT p.*, o.price, o.old_price, o.discount, o.availability_status, o.availability_scope, o.run_date, o.collection_mode
FROM dim_product p LEFT JOIN fact_observation o ON o.product_id = p.product_id
WHERE p.department = 'mobiles_tablets';

CREATE OR REPLACE VIEW v_dept_computing AS
SELECT p.*, o.price, o.old_price, o.discount, o.availability_status, o.availability_scope, o.run_date, o.collection_mode
FROM dim_product p LEFT JOIN fact_observation o ON o.product_id = p.product_id
WHERE p.department = 'computing';

CREATE OR REPLACE VIEW v_dept_electronics_tv AS
SELECT p.*, o.price, o.old_price, o.discount, o.availability_status, o.availability_scope, o.run_date, o.collection_mode
FROM dim_product p LEFT JOIN fact_observation o ON o.product_id = p.product_id
WHERE p.department = 'electronics_tv';

CREATE OR REPLACE VIEW v_dept_home_appliances AS
SELECT p.*, o.price, o.old_price, o.discount, o.availability_status, o.availability_scope, o.run_date, o.collection_mode
FROM dim_product p LEFT JOIN fact_observation o ON o.product_id = p.product_id
WHERE p.department = 'home_appliances';

CREATE OR REPLACE VIEW v_dept_fresh_meats_poultry AS
SELECT p.*, o.price, o.old_price, o.discount, o.availability_status, o.availability_scope, o.run_date, o.collection_mode
FROM dim_product p LEFT JOIN fact_observation o ON o.product_id = p.product_id
WHERE p.department = 'fresh_meats_poultry';

CREATE OR REPLACE VIEW v_dept_dairy_cheese_eggs AS
SELECT p.*, o.price, o.old_price, o.discount, o.availability_status, o.availability_scope, o.run_date, o.collection_mode
FROM dim_product p LEFT JOIN fact_observation o ON o.product_id = p.product_id
WHERE p.department = 'dairy_cheese_eggs';

CREATE OR REPLACE VIEW v_dept_fruits_vegetables AS
SELECT p.*, o.price, o.old_price, o.discount, o.availability_status, o.availability_scope, o.run_date, o.collection_mode
FROM dim_product p LEFT JOIN fact_observation o ON o.product_id = p.product_id
WHERE p.department = 'fruits_vegetables';

CREATE OR REPLACE VIEW v_dept_grocery_pantry AS
SELECT p.*, o.price, o.old_price, o.discount, o.availability_status, o.availability_scope, o.run_date, o.collection_mode
FROM dim_product p LEFT JOIN fact_observation o ON o.product_id = p.product_id
WHERE p.department = 'grocery_pantry';

CREATE OR REPLACE VIEW v_dept_beverages AS
SELECT p.*, o.price, o.old_price, o.discount, o.availability_status, o.availability_scope, o.run_date, o.collection_mode
FROM dim_product p LEFT JOIN fact_observation o ON o.product_id = p.product_id
WHERE p.department = 'beverages';

CREATE OR REPLACE VIEW v_dept_bakery_snacks AS
SELECT p.*, o.price, o.old_price, o.discount, o.availability_status, o.availability_scope, o.run_date, o.collection_mode
FROM dim_product p LEFT JOIN fact_observation o ON o.product_id = p.product_id
WHERE p.department = 'bakery_snacks';

CREATE OR REPLACE VIEW v_dept_frozen_foods AS
SELECT p.*, o.price, o.old_price, o.discount, o.availability_status, o.availability_scope, o.run_date, o.collection_mode
FROM dim_product p LEFT JOIN fact_observation o ON o.product_id = p.product_id
WHERE p.department = 'frozen_foods';

CREATE OR REPLACE VIEW v_dept_household_cleaning AS
SELECT p.*, o.price, o.old_price, o.discount, o.availability_status, o.availability_scope, o.run_date, o.collection_mode
FROM dim_product p LEFT JOIN fact_observation o ON o.product_id = p.product_id
WHERE p.department = 'household_cleaning';

CREATE OR REPLACE VIEW v_dept_personal_care_beauty AS
SELECT p.*, o.price, o.old_price, o.discount, o.availability_status, o.availability_scope, o.run_date, o.collection_mode
FROM dim_product p LEFT JOIN fact_observation o ON o.product_id = p.product_id
WHERE p.department = 'personal_care_beauty';

-- ── Complete Flat Denormalized View (كل البيانات مجمعة في صف واحد بدون JOIN) ──
CREATE OR REPLACE VIEW v_raw_products_data AS
SELECT
    o.observation_id,
    o.run_date,
    o.observed_at,
    s.source_name,
    o.source_id,
    p.product_id,
    p.source_product_id,
    p.product_name,
    p.brand,
    d.name_ar AS department_ar,
    d.name_en AS department_en,
    p.department,
    p.category,
    p.subcategory,
    o.price,
    o.old_price,
    o.discount,
    o.currency,
    o.availability_status,
    o.availability_scope,
    o.stock_status,
    o.raw_price_text,
    p.product_url,
    p.image_url,
    p.sku,
    p.gtin,
    o.delivery_available,
    o.delivery_fee,
    o.delivery_eta,
    o.seller_name,
    o.collection_mode,
    o.quality_score,
    p.first_seen_at,
    p.last_seen_at
FROM fact_observation o
LEFT JOIN dim_product p ON p.product_id = o.product_id
LEFT JOIN dim_source s ON s.source_id = o.source_id
LEFT JOIN dim_department d ON d.department_id = p.department;
