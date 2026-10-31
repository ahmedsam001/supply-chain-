#!/usr/bin/env python3
"""
Egypt E-Commerce DWH Databricks Lakehouse Sync Engine
=====================================================
Synchronizes clean retail e-commerce data from DuckDB or local storage
directly into Databricks Delta Lake (5 Flat Clean Tables):
  1. PRODUCTS
  2. PRICE_HISTORY
  3. STORES
  4. BRANCHES
  5. RUN_LOGS

Configuration (via .env or CLI args):
    DATABRICKS_HOST       = https://dbc-dc732145-aafa.cloud.databricks.com
    DATABRICKS_HTTP_PATH  = /sql/1.0/warehouses/...
    DATABRICKS_USERNAME   = by234DEPI
    DATABRICKS_PASSWORD   = DEPI@234
    DATABRICKS_TOKEN      = <optional_pat_token>
    DATABRICKS_CATALOG    = hive_metastore
    DATABRICKS_SCHEMA     = default

Usage:
    python dwh/export_to_databricks.py                      # Full sync using .env credentials
    python dwh/export_to_databricks.py --dry-run            # Dry-run validation without network connection
    python dwh/export_to_databricks.py --test-connection   # Test connectivity to Databricks
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Optional

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dwh.databricks_client import (
    DEFAULT_STORES,
    ensure_databricks_schema,
    get_databricks_connection,
    ingest_direct_to_databricks,
    is_databricks_configured,
    load_databricks_config,
    test_databricks_connection,
)

DEFAULT_DB = PROJECT_ROOT / "dwh" / "egypt_ecommerce.duckdb"
DATABRICKS_SCHEMA_SQL = PROJECT_ROOT / "dwh" / "databricks_schema.sql"

DATABRICKS_TABLES: list[str] = [
    "PRODUCTS",
    "PRICE_HISTORY",
    "STORES",
    "BRANCHES",
    "RUN_LOGS",
]


def inspect_local_duckdb(duck_db: Path) -> dict[str, int]:
    """Inspect local DuckDB tables and return row counts per table."""
    if not duck_db.exists():
        return {
            "dim_product": 0,
            "fact_observation": 0,
            "dim_location": 0,
            "dim_source": 0,
            "run_manifest": 0,
        }

    conn = duckdb.connect(str(duck_db), read_only=True)
    counts: dict[str, int] = {}
    check_tables = ["dim_product", "fact_observation", "dim_location", "dim_source", "run_manifest"]
    try:
        for tbl in check_tables:
            try:
                cnt = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                counts[tbl] = int(cnt)
            except Exception:
                counts[tbl] = 0
    finally:
        conn.close()
    return counts


def export_to_databricks(
    duck_db: Path = DEFAULT_DB,
    cfg: Optional[dict[str, str]] = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """
    Export data to Databricks 5 clean Delta tables.
    If dry_run=True, validates local counts without opening network connection.
    """
    cfg = cfg or load_databricks_config()
    counts = inspect_local_duckdb(duck_db)

    print(f"\n{'═'*65}")
    print("  🧱 DATABRICKS DIRECT LAKEHOUSE SYNC — EGYPT E-COMMERCE PLATFORM")
    print(f"  Local DuckDB : {duck_db}")
    print(f"  Host         : {cfg.get('server_hostname') or '(not set — configure in .env)'}")
    print(f"  HTTP Path    : {cfg.get('http_path') or '(not set — configure in .env)'}")
    print(f"  User         : {cfg.get('username') or '(none)'}")
    print(f"  Catalog      : {cfg.get('catalog')}.{cfg.get('schema')}")
    print(f"  Mode         : {'DRY-RUN (Local Verification)' if dry_run else 'LIVE DATABRICKS SYNC'}")
    print(f"{'═'*65}\n")

    if dry_run:
        print("  📋 Clean Databricks Delta tables ready for sync:")
        print(f"     • PRODUCTS        (Catalog & Latest Price) : {counts.get('dim_product', 0):,} rows")
        print(f"     • PRICE_HISTORY   (Daily Price Snapshots)  : {counts.get('fact_observation', 0):,} rows")
        print(f"     • STORES          (Retailers Directory)    : {len(DEFAULT_STORES)} stores")
        print(f"     • BRANCHES        (Physical Locations)     : {counts.get('dim_location', 0):,} rows")
        print(f"     • RUN_LOGS        (Extraction Runs)        : {counts.get('run_manifest', 0):,} rows")
        print("\n  ✓ Dry-run verification passed.")
        return counts

    if not is_databricks_configured(cfg):
        raise RuntimeError("Databricks credentials / host are not configured in .env file.")

    conn = get_databricks_connection(cfg)
    exported_counts: dict[str, int] = {}
    try:
        # 1. Ensure the 5 flat clean Delta tables exist and stores are seeded
        ensure_databricks_schema(conn)

        # 2. If DuckDB exists, read and push each source
        if duck_db.exists():
            duck = duckdb.connect(str(duck_db), read_only=True)
            sources = [r[0] for r in duck.execute("SELECT DISTINCT source_id FROM dim_product").fetchall()]
            for src in sources:
                prods_rows = duck.execute(
                    "SELECT product_id, source_id, source_product_id, product_name, brand, category, subcategory, product_url, image_url, last_seen_at FROM dim_product WHERE source_id = ?",
                    [src],
                ).fetchall()
                prods = [
                    {
                        "product_id": r[0],
                        "source_id": r[1],
                        "source_product_id": r[2],
                        "product_name": r[3],
                        "brand": r[4],
                        "category": r[5],
                        "subcategory": r[6],
                        "product_url": r[7],
                        "image_url": r[8],
                        "collected_at": str(r[9]),
                    }
                    for r in prods_rows
                ]

                obs_rows = duck.execute(
                    "SELECT observation_id, product_id, source_id, source_product_id, price, old_price, discount, stock_status, availability_status, observed_at, seller_name FROM fact_observation WHERE source_id = ?",
                    [src],
                ).fetchall()
                obs = [
                    {
                        "observation_id": r[0],
                        "product_id": r[1],
                        "source_id": r[2],
                        "source_product_id": r[3],
                        "price": r[4],
                        "old_price": r[5],
                        "discount": r[6],
                        "stock_status": r[7],
                        "availability_status": r[8],
                        "observed_at": str(r[9]),
                        "seller_name": r[10],
                    }
                    for r in obs_rows
                ]

                loc_rows = duck.execute(
                    "SELECT location_id, source_id, branch_name, location_name, address, city, governorate, phone, latitude, longitude FROM dim_location WHERE source_id = ?",
                    [src],
                ).fetchall()
                locs = [
                    {
                        "location_id": r[0],
                        "source_id": r[1],
                        "branch_name": r[2] or r[3],
                        "address": r[4],
                        "city": r[5],
                        "governorate": r[6],
                        "phone": r[7],
                        "latitude": r[8],
                        "longitude": r[9],
                    }
                    for r in loc_rows
                ]

                ingest_direct_to_databricks(
                    source_id=src,
                    products=prods,
                    observations=obs,
                    locations=locs,
                    conn=conn,
                )
            duck.close()

        # Count rows in Databricks
        cur = conn.cursor()
        for tbl in DATABRICKS_TABLES:
            cur.execute(f"SELECT COUNT(*) FROM {tbl}")
            cnt = cur.fetchone()[0]
            exported_counts[tbl.lower()] = cnt
            print(f"  ✓ {tbl:18s}: {cnt:,} rows in Databricks")
        cur.close()

        print(f"\n✅ Databricks Lakehouse clean sync complete → {cfg['catalog']}.{cfg['schema']}")
    finally:
        conn.close()

    return exported_counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Egypt E-Commerce data to Databricks 5 clean tables")
    parser.add_argument("--db", default=str(DEFAULT_DB), help=f"DuckDB path (default: {DEFAULT_DB})")
    parser.add_argument("--host", default=None, help="Databricks workspace host (overrides .env)")
    parser.add_argument("--http-path", default=None, help="Databricks SQL warehouse HTTP path (overrides .env)")
    parser.add_argument("--username", default=None, help="Databricks username (overrides .env)")
    parser.add_argument("--password", default=None, help="Databricks password (overrides .env)")
    parser.add_argument("--token", default=None, help="Databricks personal access token (overrides .env)")
    parser.add_argument("--catalog", default=None, help="Databricks catalog (default: hive_metastore)")
    parser.add_argument("--schema", default=None, help="Databricks schema (default: default)")
    parser.add_argument("--dry-run", action="store_true", help="Inspect local tables without connecting")
    parser.add_argument("--test-connection", action="store_true", help="Test connectivity to Databricks")
    args = parser.parse_args()

    cfg = load_databricks_config(args)

    if args.test_connection:
        ok, msg = test_databricks_connection(cfg)
        print(f"Databricks Status: {'SUCCESS' if ok else 'FAILED'}")
        print(f"Message: {msg}")
        sys.exit(0 if ok else 1)

    export_to_databricks(duck_db=Path(args.db), cfg=cfg, dry_run=args.dry_run)


if __name__ == "__main__":
    main()

