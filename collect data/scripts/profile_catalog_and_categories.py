#!/usr/bin/env python3
"""
Catalog & Category Profile Report Generator
Queries Databricks workspace.live_market and local DuckDB dwh/egypt_ecommerce.duckdb.
"""

from __future__ import annotations

import json
from pathlib import Path
import duckdb
from dwh.databricks_client import get_databricks_connection

DUCKDB_PATH = Path("dwh/egypt_ecommerce.duckdb")


def profile():
    print("Connecting to Databricks...")
    with get_databricks_connection() as conn:
        dbx_cursor = conn.cursor()

        # 1. Parity Check
        print("\n--- 1. PARITY CHECK ---")
        dbx_cursor.execute("""
            SELECT STORE, COUNT(*) as cnt
            FROM workspace.live_market.PRODUCTS
            GROUP BY STORE
            ORDER BY STORE
        """)
        dbx_prod_counts = {r[0]: r[1] for r in dbx_cursor.fetchall()}

        dbx_cursor.execute("""
            SELECT STORE, COUNT(*) as cnt
            FROM workspace.live_market.PRICE_HISTORY
            GROUP BY STORE
            ORDER BY STORE
        """)
        dbx_ph_counts = {r[0]: r[1] for r in dbx_cursor.fetchall()}

        dbx_cursor.execute("""
            SELECT STORE, COUNT(*) as cnt
            FROM workspace.live_market.BRANCHES
            GROUP BY STORE
            ORDER BY STORE
        """)
        dbx_branch_counts = {r[0]: r[1] for r in dbx_cursor.fetchall()}

        dbx_cursor.execute("SELECT COUNT(*) FROM workspace.live_market.STORES")
        dbx_stores_count = dbx_cursor.fetchone()[0]

        # Query DuckDB
        duck = duckdb.connect(str(DUCKDB_PATH), read_only=True)
        duck_prod_counts = {
            r[0]: r[1]
            for r in duck.execute("SELECT source_id, COUNT(*) FROM dim_product GROUP BY source_id ORDER BY source_id").fetchall()
        }
        duck_obs_counts = {
            r[0]: r[1]
            for r in duck.execute("SELECT source_id, COUNT(*) FROM fact_observation GROUP BY source_id ORDER BY source_id").fetchall()
        }
        duck_branch_counts = {
            r[0]: r[1]
            for r in duck.execute("SELECT source_id, COUNT(*) FROM dim_location WHERE location_type = 'STORE' GROUP BY source_id ORDER BY source_id").fetchall()
        }

        # 2. Category Breakdown in Databricks
        print("\n--- 2. CATEGORY BREAKDOWN ---")
        dbx_cursor.execute("""
            SELECT 
                STORE,
                COALESCE(CATEGORY, 'Uncategorized') as cat,
                COUNT(*) as product_count,
                ROUND(MIN(CURRENT_PRICE), 2) as min_price,
                ROUND(AVG(CURRENT_PRICE), 2) as avg_price,
                ROUND(MAX(CURRENT_PRICE), 2) as max_price,
                ROUND(SUM(CASE WHEN DISCOUNT IS NOT NULL AND DISCOUNT > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) as sale_pct,
                ROUND(AVG(CASE WHEN DISCOUNT IS NOT NULL AND DISCOUNT > 0 THEN DISCOUNT ELSE NULL END), 1) as avg_discount_pct
            FROM workspace.live_market.PRODUCTS
            GROUP BY STORE, COALESCE(CATEGORY, 'Uncategorized')
            ORDER BY STORE, product_count DESC
        """)
        cat_rows = dbx_cursor.fetchall()

        # 3. Governorate Distribution
        print("\n--- 3. GOVERNORATE DISTRIBUTION ---")
        dbx_cursor.execute("""
            SELECT 
                COALESCE(GOVERNORATE, 'Unknown') as gov,
                STORE,
                COUNT(*) as branch_count
            FROM workspace.live_market.BRANCHES
            GROUP BY COALESCE(GOVERNORATE, 'Unknown'), STORE
            ORDER BY gov, STORE
        """)
        gov_rows = dbx_cursor.fetchall()

        # 4. Data Quality & Completeness
        print("\n--- 4. DATA QUALITY AUDIT ---")
        dbx_cursor.execute("""
            SELECT 
                STORE,
                COUNT(*) as total_prods,
                SUM(CASE WHEN PRODUCT_ID IS NULL THEN 1 ELSE 0 END) as null_pid,
                SUM(CASE WHEN PRODUCT_NAME IS NULL OR TRIM(PRODUCT_NAME) = '' THEN 1 ELSE 0 END) as null_name,
                SUM(CASE WHEN CURRENT_PRICE IS NULL OR CURRENT_PRICE <= 0 THEN 1 ELSE 0 END) as invalid_price,
                SUM(CASE WHEN IMAGE_URL IS NOT NULL AND TRIM(IMAGE_URL) != '' THEN 1 ELSE 0 END) as with_image,
                SUM(CASE WHEN BRAND IS NOT NULL AND TRIM(BRAND) != '' THEN 1 ELSE 0 END) as with_brand,
                SUM(CASE WHEN STOCK_STATUS IS NOT NULL THEN 1 ELSE 0 END) as with_stock
            FROM workspace.live_market.PRODUCTS
            GROUP BY STORE
            ORDER BY STORE
        """)
        quality_rows = dbx_cursor.fetchall()

        return {
            "dbx_prod_counts": dbx_prod_counts,
            "dbx_ph_counts": dbx_ph_counts,
            "dbx_branch_counts": dbx_branch_counts,
            "dbx_stores_count": dbx_stores_count,
            "duck_prod_counts": duck_prod_counts,
            "duck_obs_counts": duck_obs_counts,
            "duck_branch_counts": duck_branch_counts,
            "cat_rows": cat_rows,
            "gov_rows": gov_rows,
            "quality_rows": quality_rows,
        }


if __name__ == "__main__":
    res = profile()
    print("\n" + "=" * 60)
    print("PROFILING RESULTS JSON:")
    print("=" * 60)
    # Serialize tuples/lists safely
    clean_res = {
        "dbx_prod_counts": res["dbx_prod_counts"],
        "dbx_ph_counts": res["dbx_ph_counts"],
        "dbx_branch_counts": res["dbx_branch_counts"],
        "dbx_stores_count": res["dbx_stores_count"],
        "duck_prod_counts": res["duck_prod_counts"],
        "duck_obs_counts": res["duck_obs_counts"],
        "duck_branch_counts": res["duck_branch_counts"],
        "cat_rows": [list(r) for r in res["cat_rows"]],
        "gov_rows": [list(r) for r in res["gov_rows"]],
        "quality_rows": [list(r) for r in res["quality_rows"]],
    }
    print(json.dumps(clean_res, indent=2, default=str))
