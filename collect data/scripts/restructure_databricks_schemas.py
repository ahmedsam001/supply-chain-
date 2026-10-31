"""
Restructure Databricks Lakehouse Schemas
========================================
Creates workspace.live_market, workspace.supply_chain_stage, and workspace.stage.
Moves table definitions to workspace.live_market and drops old tables from workspace.default.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dwh.databricks_client import (
    load_databricks_config,
    get_databricks_connection,
    DEFAULT_STORES,
    _sql_lit,
)

def restructure_schemas():
    cfg = load_databricks_config()
    cfg["schema"] = "live_market"
    conn = get_databricks_connection(cfg)
    cur = conn.cursor()

    print("1. Creating Schemas in workspace catalog...")
    cur.execute("CREATE SCHEMA IF NOT EXISTS workspace.live_market")
    print("   ✓ workspace.live_market ready")
    cur.execute("CREATE SCHEMA IF NOT EXISTS workspace.supply_chain_stage")
    print("   ✓ workspace.supply_chain_stage ready")
    cur.execute("CREATE SCHEMA IF NOT EXISTS workspace.stage")
    print("   ✓ workspace.stage ready")

    print("2. Creating the 5 Lakehouse Tables in workspace.live_market...")
    ddl_statements = [
        """
        CREATE TABLE IF NOT EXISTS workspace.live_market.PRODUCTS (
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
        ) USING DELTA
        """,
        """
        CREATE TABLE IF NOT EXISTS workspace.live_market.PRICE_HISTORY (
            OBSERVATION_ID      STRING,
            COLLECTED_DATE      DATE,
            STORE               STRING,
            PRODUCT_ID          STRING,
            PRICE               DOUBLE,
            OLD_PRICE           DOUBLE,
            STOCK_STATUS        STRING,
            COLLECTED_AT        TIMESTAMP
        ) USING DELTA
        """,
        """
        CREATE TABLE IF NOT EXISTS workspace.live_market.STORES (
            STORE_ID            STRING,
            STORE_NAME          STRING,
            DOMAIN              STRING,
            OFFICIAL_URL        STRING,
            BUSINESS_TYPE       STRING
        ) USING DELTA
        """,
        """
        CREATE TABLE IF NOT EXISTS workspace.live_market.BRANCHES (
            BRANCH_ID           STRING,
            STORE               STRING,
            BRANCH_NAME         STRING,
            GOVERNORATE         STRING,
            CITY                STRING,
            ADDRESS             STRING,
            PHONE               STRING,
            LATITUDE            DOUBLE,
            LONGITUDE           DOUBLE
        ) USING DELTA
        """,
        """
        CREATE TABLE IF NOT EXISTS workspace.live_market.RUN_LOGS (
            RUN_ID                  STRING,
            STORE                   STRING,
            RUN_DATE                DATE,
            PRODUCTS_COLLECTED      INT,
            OBSERVATIONS_COLLECTED  INT,
            DURATION_SECONDS        DOUBLE,
            STARTED_AT              TIMESTAMP,
            FINISHED_AT             TIMESTAMP
        ) USING DELTA
        """,
    ]

    for ddl in ddl_statements:
        cur.execute(ddl)
    print("   ✓ All 5 tables created in workspace.live_market")

    print("3. Seeding STORES in workspace.live_market...")
    values_clauses = []
    for s in DEFAULT_STORES:
        values_clauses.append(
            f"({_sql_lit(s['store_id'])}, {_sql_lit(s['store_name'])}, "
            f"{_sql_lit(s['domain'])}, {_sql_lit(s['official_url'])}, {_sql_lit(s['business_type'])})"
        )
    values_sql = ",\n            ".join(values_clauses)
    cur.execute(
        f"""
        MERGE INTO workspace.live_market.STORES t
        USING (
            SELECT * FROM VALUES
            {values_sql}
            AS s(STORE_ID, STORE_NAME, DOMAIN, OFFICIAL_URL, BUSINESS_TYPE)
        ) s
        ON t.STORE_ID = s.STORE_ID
        WHEN MATCHED THEN UPDATE SET
            t.STORE_NAME = s.STORE_NAME,
            t.DOMAIN = s.DOMAIN,
            t.OFFICIAL_URL = s.OFFICIAL_URL,
            t.BUSINESS_TYPE = s.BUSINESS_TYPE
        WHEN NOT MATCHED THEN INSERT
            (STORE_ID, STORE_NAME, DOMAIN, OFFICIAL_URL, BUSINESS_TYPE)
            VALUES (s.STORE_ID, s.STORE_NAME, s.DOMAIN, s.OFFICIAL_URL, s.BUSINESS_TYPE)
        """
    )
    print("   ✓ workspace.live_market.STORES seeded")

    print("4. Dropping old tables from workspace.default...")
    for tbl in ["PRODUCTS", "PRICE_HISTORY", "STORES", "BRANCHES", "RUN_LOGS"]:
        cur.execute(f"DROP TABLE IF EXISTS workspace.default.{tbl}")
        print(f"   ✓ Dropped workspace.default.{tbl}")

    print("5. Verifying schemas and tables...")
    cur.execute("SHOW SCHEMAS IN workspace")
    schemas = [r[0] for r in cur.fetchall()]
    print(f"   Schemas in workspace: {schemas}")

    cur.execute("SHOW TABLES IN workspace.live_market")
    live_tables = [r[1] for r in cur.fetchall()]
    print(f"   Tables in workspace.live_market: {live_tables}")

    cur.execute("SHOW TABLES IN workspace.default")
    default_tables = [r[1] for r in cur.fetchall()]
    print(f"   Tables in workspace.default: {default_tables}")

    cur.close()
    conn.close()
    print("=== Restructuring Complete ===")

if __name__ == "__main__":
    restructure_schemas()
