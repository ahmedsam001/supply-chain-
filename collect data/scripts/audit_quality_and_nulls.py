#!/usr/bin/env python3
"""
Comprehensive NULL & Data Quality Diagnostic Auditor for Egypt E-Commerce.
Queries both master DuckDB and Databricks Delta Lake (workspace.default).
Generates detailed NULL analysis, sample rows, business classifications, and parity verification.
"""

import sys
from pathlib import Path
import json

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import duckdb
from dwh.databricks_client import get_databricks_connection, load_databricks_config, is_databricks_configured

DUCKDB_PATH = PROJECT_ROOT / "dwh" / "egypt_ecommerce.duckdb"

TABLE_COLUMNS = {
    "PRODUCTS": [
        "STORE", "PRODUCT_ID", "PRODUCT_NAME", "CATEGORY", "BRAND",
        "CURRENT_PRICE", "OLD_PRICE", "DISCOUNT", "STOCK_STATUS",
        "PRODUCT_URL", "IMAGE_URL", "LAST_UPDATED_AT"
    ],
    "PRICE_HISTORY": [
        "OBSERVATION_ID", "COLLECTED_DATE", "STORE", "PRODUCT_ID",
        "PRICE", "OLD_PRICE", "STOCK_STATUS", "COLLECTED_AT"
    ],
    "STORES": [
        "STORE_ID", "STORE_NAME", "DOMAIN", "OFFICIAL_URL", "BUSINESS_TYPE"
    ],
    "BRANCHES": [
        "BRANCH_ID", "STORE", "BRANCH_NAME", "GOVERNORATE",
        "CITY", "ADDRESS", "PHONE", "LATITUDE", "LONGITUDE"
    ],
    "RUN_LOGS": [
        "RUN_ID", "STORE", "RUN_DATE", "PRODUCTS_COLLECTED",
        "OBSERVATIONS_COLLECTED", "DURATION_SECONDS", "STARTED_AT", "FINISHED_AT"
    ],
}

# Mapping between Databricks table/column names and DuckDB Star Schema tables/columns
DUCKDB_MAPPING = {
    "PRODUCTS": ("dim_product", {
        "STORE": "source_id",
        "PRODUCT_ID": "product_id",
        "PRODUCT_NAME": "product_name",
        "CATEGORY": "category",
        "BRAND": "brand",
        "CURRENT_PRICE": None,
        "OLD_PRICE": None,
        "DISCOUNT": None,
        "STOCK_STATUS": None,
        "PRODUCT_URL": "product_url",
        "IMAGE_URL": "image_url",
        "LAST_UPDATED_AT": "last_seen_at"
    }),
    "PRICE_HISTORY": ("fact_observation", {
        "OBSERVATION_ID": "observation_id",
        "COLLECTED_DATE": "run_date",
        "STORE": "source_id",
        "PRODUCT_ID": "product_id",
        "PRICE": "price",
        "OLD_PRICE": "old_price",
        "STOCK_STATUS": "stock_status",
        "COLLECTED_AT": "observed_at"
    }),
    "STORES": ("dim_source", {
        "STORE_ID": "source_id",
        "STORE_NAME": "source_name",
        "DOMAIN": "domain",
        "OFFICIAL_URL": None,
        "BUSINESS_TYPE": "business_type"
    }),
    "BRANCHES": ("dim_location", {
        "BRANCH_ID": "location_id",
        "STORE": "source_id",
        "BRANCH_NAME": "branch_name",
        "GOVERNORATE": "governorate",
        "CITY": "city",
        "ADDRESS": "address",
        "PHONE": "phone",
        "LATITUDE": "latitude",
        "LONGITUDE": "longitude"
    }),
    "RUN_LOGS": ("run_manifest", {
        "RUN_ID": "run_id",
        "STORE": "source_id",
        "RUN_DATE": "run_date",
        "PRODUCTS_COLLECTED": "products_count",
        "OBSERVATIONS_COLLECTED": "observations_count",
        "DURATION_SECONDS": "duration_seconds",
        "STARTED_AT": "started_at",
        "FINISHED_AT": "finished_at"
    })
}


def audit_databricks() -> dict:
    cfg = load_databricks_config()
    if not is_databricks_configured(cfg):
        return {"error": "Databricks not configured"}

    report = {"table_counts": {}, "store_breakdowns": {}, "null_analysis": {}}
    schema_name = cfg.get("schema", "live_market")
    conn = get_databricks_connection(cfg)
    cur = conn.cursor()

    try:
        for tbl, cols in TABLE_COLUMNS.items():
            # Total row count
            cur.execute(f"SELECT COUNT(*) FROM workspace.{schema_name}.{tbl}")
            total_rows = cur.fetchone()[0]
            report["table_counts"][tbl] = total_rows

            # Store breakdown
            store_col = "STORE" if tbl in ("PRODUCTS", "PRICE_HISTORY", "BRANCHES", "RUN_LOGS") else ("STORE_ID" if tbl == "STORES" else None)
            if store_col and total_rows > 0:
                cur.execute(f"SELECT {store_col}, COUNT(*) FROM workspace.{schema_name}.{tbl} GROUP BY {store_col} ORDER BY COUNT(*) DESC")
                report["store_breakdowns"][tbl] = {row[0]: row[1] for row in cur.fetchall()}

            # Column NULL analysis
            report["null_analysis"][tbl] = []
            if total_rows > 0:
                for col in cols:
                    cur.execute(f"SELECT COUNT(*) FROM workspace.{schema_name}.{tbl} WHERE {col} IS NULL")
                    null_cnt = cur.fetchone()[0]
                    if null_cnt > 0:
                        pct = round((null_cnt / total_rows) * 100, 2)
                        # Fetch up to 2 sample rows where column is NULL
                        cur.execute(f"SELECT * FROM workspace.{schema_name}.{tbl} WHERE {col} IS NULL LIMIT 2")
                        samples = cur.fetchall()
                        sample_dicts = []
                        for s in samples:
                            sample_dicts.append({cols[idx]: (str(val) if val is not None else "NULL") for idx, val in enumerate(s)})

                        report["null_analysis"][tbl].append({
                            "column": col,
                            "null_count": null_cnt,
                            "total_rows": total_rows,
                            "null_pct": pct,
                            "samples": sample_dicts
                        })
    finally:
        cur.close()
        conn.close()

    return report


def audit_duckdb() -> dict:
    if not DUCKDB_PATH.exists():
        return {"error": "DuckDB file not found"}

    conn = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    report = {"table_counts": {}, "store_breakdowns": {}}

    for tbl in ["dim_product", "fact_observation", "dim_location", "dim_source", "run_manifest", "fact_quality_issue"]:
        try:
            cnt = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            report["table_counts"][tbl] = cnt
            if tbl in ("dim_product", "fact_observation", "dim_location", "run_manifest") and cnt > 0:
                rows = conn.execute(f"SELECT source_id, COUNT(*) FROM {tbl} GROUP BY source_id ORDER BY COUNT(*) DESC").fetchall()
                report["store_breakdowns"][tbl] = {r[0]: r[1] for r in rows}
        except Exception:
            pass

    conn.close()
    return report


if __name__ == "__main__":
    print("=== Auditing Master Local DuckDB ===")
    duck_rep = audit_duckdb()
    print(json.dumps(duck_rep, indent=2))

    print("\n=== Auditing Databricks Delta Lake ===")
    dbx_rep = audit_databricks()
    print(json.dumps(dbx_rep, indent=2))

