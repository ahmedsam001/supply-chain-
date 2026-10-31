-- =============================================================
-- Egypt E-Commerce Databricks Lakehouse Schema (Delta Lake)
-- =============================================================
-- 5 Simple Flat Tables (Clean Architecture - No Star Schema, No Views):
--   1. PRODUCTS        : Current product catalog with latest price & stock
--   2. PRICE_HISTORY   : Daily price & stock snapshot observations
--   3. STORES          : Platform / retailer directory
--   4. BRANCHES        : Physical retail stores & branches in Egypt
--   5. RUN_LOGS        : Scraping execution logs & performance audit
-- =============================================================

CREATE TABLE IF NOT EXISTS PRODUCTS (
    STORE               STRING,
    PRODUCT_ID          STRING,
    PRODUCT_NAME        STRING,
    CATEGORY            STRING,
    BRAND               STRING,
    CURRENT_PRICE       DOUBLE,
    OLD_PRICE           DOUBLE,
    DISCOUNT            DOUBLE,
    STOCK_STATUS        STRING,
    PRODUCT_URL         STRING,
    IMAGE_URL           STRING,
    LAST_UPDATED_AT     TIMESTAMP
) USING DELTA;

CREATE TABLE IF NOT EXISTS PRICE_HISTORY (
    OBSERVATION_ID      STRING,
    COLLECTED_DATE      DATE,
    STORE               STRING,
    PRODUCT_ID          STRING,
    PRICE               DOUBLE,
    OLD_PRICE           DOUBLE,
    STOCK_STATUS        STRING,
    COLLECTED_AT        TIMESTAMP
) USING DELTA;

CREATE TABLE IF NOT EXISTS STORES (
    STORE_ID            STRING,
    STORE_NAME          STRING,
    DOMAIN              STRING,
    OFFICIAL_URL        STRING,
    BUSINESS_TYPE       STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS BRANCHES (
    BRANCH_ID           STRING,
    STORE               STRING,
    BRANCH_NAME         STRING,
    GOVERNORATE         STRING,
    CITY                STRING,
    ADDRESS             STRING,
    PHONE               STRING,
    LATITUDE            DOUBLE,
    LONGITUDE           DOUBLE
) USING DELTA;

CREATE TABLE IF NOT EXISTS RUN_LOGS (
    RUN_ID                  STRING,
    STORE                   STRING,
    RUN_DATE                DATE,
    PRODUCTS_COLLECTED      INT,
    OBSERVATIONS_COLLECTED  INT,
    DURATION_SECONDS        DOUBLE,
    STARTED_AT              TIMESTAMP,
    FINISHED_AT             TIMESTAMP
) USING DELTA;

