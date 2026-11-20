"""
PostgreSQL Database Schema — DDL for the Egypt E-Commerce Data Platform

Creates all tables for the canonical data model.
Run with: python -m storage.schema
"""

SCHEMA_DDL = """
-- Egypt E-Commerce Data Platform — Database Schema
-- Generated: 2026-09-26

-- ═══════════════════════════════════════════════════════════════════
-- SOURCES
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS sources (
    source_id       VARCHAR(50)   PRIMARY KEY,
    source_name     VARCHAR(200)  NOT NULL,
    domain          VARCHAR(255)  NOT NULL,
    compliance_status CHAR(1)     NOT NULL CHECK (compliance_status IN ('A','B','C','D')),
    extraction_method VARCHAR(50) NOT NULL,
    last_verified_at TIMESTAMPTZ  DEFAULT NOW(),
    rate_limit_rpm  INTEGER       DEFAULT 30,
    enabled         BOOLEAN       DEFAULT FALSE,
    notes           TEXT,
    created_at      TIMESTAMPTZ   DEFAULT NOW(),
    updated_at      TIMESTAMPTZ   DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════════
-- PRODUCTS
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS products (
    product_id        VARCHAR(50)   PRIMARY KEY,
    source_id         VARCHAR(50)   NOT NULL REFERENCES sources(source_id),
    source_product_id VARCHAR(255)  NOT NULL,
    sku               VARCHAR(255),
    gtin              VARCHAR(32),
    raw_category_path TEXT,
    source_url        TEXT,
    variants          JSONB,
    product_name      TEXT          NOT NULL,
    brand             VARCHAR(200),
    category          VARCHAR(200),
    subcategory       VARCHAR(200),
    product_url       TEXT,
    image_url         TEXT,
    specifications    JSONB,
    first_seen_at     TIMESTAMPTZ   DEFAULT NOW(),
    last_seen_at      TIMESTAMPTZ   DEFAULT NOW(),
    is_active         BOOLEAN       DEFAULT TRUE,

    UNIQUE (source_id, source_product_id)
);

CREATE INDEX IF NOT EXISTS idx_products_source ON products(source_id);
CREATE INDEX IF NOT EXISTS idx_products_brand ON products(brand);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);

-- ═══════════════════════════════════════════════════════════════════
-- LOCATIONS
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS locations (
    location_id     VARCHAR(50)   PRIMARY KEY,
    source_id       VARCHAR(50)   NOT NULL REFERENCES sources(source_id),
    location_type   VARCHAR(50)   NOT NULL,
    branch_name     VARCHAR(255),
    address         TEXT,
    city            VARCHAR(100),
    governorate     VARCHAR(100),
    latitude        DOUBLE PRECISION,
    longitude       DOUBLE PRECISION,
    delivery_zone   VARCHAR(255),
    phone           VARCHAR(50),
    working_hours   VARCHAR(255),
    h3_index        VARCHAR(20),
    created_at      TIMESTAMPTZ   DEFAULT NOW(),
    updated_at      TIMESTAMPTZ   DEFAULT NOW(),

    UNIQUE (source_id, branch_name, city)
);

CREATE INDEX IF NOT EXISTS idx_locations_source ON locations(source_id);
CREATE INDEX IF NOT EXISTS idx_locations_governorate ON locations(governorate);
CREATE INDEX IF NOT EXISTS idx_locations_city ON locations(city);
CREATE INDEX IF NOT EXISTS idx_locations_h3 ON locations(h3_index);

-- ═══════════════════════════════════════════════════════════════════
-- PRODUCT OBSERVATIONS (append-only)
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS product_observations (
    observation_id      VARCHAR(50)   PRIMARY KEY,
    product_id          VARCHAR(50)   NOT NULL REFERENCES products(product_id),
    location_id         VARCHAR(50)   REFERENCES locations(location_id),
    observed_at         TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    price               DECIMAL(12,2),
    old_price           DECIMAL(12,2),
    discount            DECIMAL(5,2),
    currency            CHAR(3)       DEFAULT 'EGP',
    availability_status VARCHAR(30)   DEFAULT 'unknown',
    delivery_status     TEXT,
    rating              DECIMAL(3,2),
    review_count        INTEGER,
    source_url          TEXT,
    seller_name         VARCHAR(255),
    sellers             JSONB,
    stock_status        VARCHAR(50),
    stock_quantity      INTEGER,
    stock_quantity_evidence TEXT,
    raw_availability_text TEXT,
    raw_price_text      TEXT,
    availability_scope  VARCHAR(40) DEFAULT 'UNKNOWN',
    fulfillment_method  VARCHAR(50),
    delivery_available  BOOLEAN,
    delivery_eta        TEXT,
    delivery_fee        DECIMAL(10,2),
    hash_version        INTEGER DEFAULT 2,
    run_id              VARCHAR(100),
    row_hash            CHAR(64),
    created_at          TIMESTAMPTZ   DEFAULT NOW()
);

-- Partition-friendly index on observed_at for time-series queries
CREATE INDEX IF NOT EXISTS idx_observations_product_time
    ON product_observations(product_id, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_observations_observed_at
    ON product_observations(observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_observations_availability
    ON product_observations(availability_status);

CREATE INDEX IF NOT EXISTS idx_observations_row_hash
    ON product_observations(row_hash);

-- ═══════════════════════════════════════════════════════════════════
-- DATA QUALITY ISSUES
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS data_quality_issues (
    issue_id      VARCHAR(50)   PRIMARY KEY,
    run_id        VARCHAR(100),
    source_id     VARCHAR(50)   NOT NULL,
    entity_type   VARCHAR(50)   NOT NULL,
    entity_id     VARCHAR(255)  NOT NULL,
    issue_code    VARCHAR(80)   NOT NULL,
    severity      VARCHAR(20)   NOT NULL,
    message       TEXT          NOT NULL,
    raw_value     TEXT,
    source_url    TEXT,
    detected_at   TIMESTAMPTZ   DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════════
-- EXTRACTION RUNS (metadata)
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS extraction_runs (
    run_id              SERIAL        PRIMARY KEY,
    source_id           VARCHAR(50)   NOT NULL REFERENCES sources(source_id),
    started_at          TIMESTAMPTZ   NOT NULL,
    completed_at        TIMESTAMPTZ,
    products_extracted  INTEGER       DEFAULT 0,
    locations_extracted INTEGER       DEFAULT 0,
    observations_created INTEGER      DEFAULT 0,
    errors_count        INTEGER       DEFAULT 0,
    pages_visited       INTEGER       DEFAULT 0,
    duration_seconds    DECIMAL(10,2),
    status              VARCHAR(20)   DEFAULT 'running',
    error_log           TEXT
);

CREATE INDEX IF NOT EXISTS idx_runs_source_time
    ON extraction_runs(source_id, started_at DESC);

-- ═══════════════════════════════════════════════════════════════════
-- PRICE CHANGES (derived / change detection)
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS price_changes (
    change_id           SERIAL        PRIMARY KEY,
    product_id          VARCHAR(50)   NOT NULL REFERENCES products(product_id),
    location_id         VARCHAR(50)   REFERENCES locations(location_id),
    detected_at         TIMESTAMPTZ   DEFAULT NOW(),
    old_price           DECIMAL(12,2),
    new_price           DECIMAL(12,2),
    price_change_pct    DECIMAL(8,4),
    old_availability    VARCHAR(30),
    new_availability    VARCHAR(30),
    change_type         VARCHAR(30)   NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_price_changes_product
    ON price_changes(product_id, detected_at DESC);

-- ═══════════════════════════════════════════════════════════════════
-- VIEWS
-- ═══════════════════════════════════════════════════════════════════

-- Latest observation per product
CREATE OR REPLACE VIEW v_latest_observations AS
SELECT DISTINCT ON (product_id)
    o.observation_id,
    o.product_id,
    p.product_name,
    p.brand,
    p.category,
    p.source_id,
    s.source_name,
    o.price,
    o.old_price,
    o.discount,
    o.availability_status,
    o.observed_at,
    o.rating,
    o.review_count
FROM product_observations o
JOIN products p ON o.product_id = p.product_id
JOIN sources s ON p.source_id = s.source_id
ORDER BY product_id, observed_at DESC;

-- Products with price drops
CREATE OR REPLACE VIEW v_price_drops AS
SELECT
    pc.product_id,
    p.product_name,
    p.brand,
    s.source_name,
    pc.old_price,
    pc.new_price,
    pc.price_change_pct,
    pc.detected_at
FROM price_changes pc
JOIN products p ON pc.product_id = p.product_id
JOIN sources s ON p.source_id = s.source_id
WHERE pc.change_type = 'price_decrease'
ORDER BY pc.detected_at DESC;
""";


def create_schema():
    """Print DDL to stdout — can be piped to psql."""
    print(SCHEMA_DDL)


if __name__ == "__main__":
    create_schema()
