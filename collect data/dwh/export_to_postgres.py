#!/usr/bin/env python3
"""
Export from DuckDB → PostgreSQL (one-time or daily sync)

Usage:
    python dwh/export_to_postgres.py --pg-url "postgresql://user:pass@localhost/egypt_dwh"

Setup PostgreSQL first (run once as admin):
    sudo -u postgres psql -c "CREATE USER egypt_user WITH PASSWORD 'egypt2024';"
    sudo -u postgres psql -c "CREATE DATABASE egypt_ecommerce_dwh OWNER egypt_user;"
"""

from __future__ import annotations

import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = PROJECT_ROOT / "dwh" / "egypt_ecommerce.duckdb"


def export_to_postgres(pg_url: str, duck_db: Path) -> None:
    import duckdb
    import psycopg2
    from psycopg2.extras import execute_batch

    duck = duckdb.connect(str(duck_db), read_only=True)
    pg = psycopg2.connect(pg_url)
    pg_cur = pg.cursor()

    # Create schema in PostgreSQL
    schema_sql = (PROJECT_ROOT / "dwh" / "schema.sql").read_text()
    for stmt in schema_sql.split(";"):
        stmt = stmt.strip()
        if stmt:
            try:
                pg_cur.execute(stmt)
            except Exception:
                pg.rollback()

    tables = [
        "dim_department", "dim_source", "dim_product", "dim_location",
        "fact_observation", "fact_quality_issue", "run_manifest",
    ]

    for tbl in tables:
        rows = duck.execute(f"SELECT * FROM {tbl}").fetchall()
        if not rows:
            continue
        cols = [d[0] for d in duck.execute(f"DESCRIBE {tbl}").fetchall()]
        placeholders = ",".join(["%s"] * len(cols))
        col_str = ",".join(cols)
        upsert = f"""
            INSERT INTO {tbl} ({col_str})
            VALUES ({placeholders})
            ON CONFLICT DO NOTHING
        """
        execute_batch(pg_cur, upsert, rows, page_size=200)
        print(f"  ✓ {tbl}: {len(rows):,} rows exported")

    pg.commit()
    pg_cur.close()
    pg.close()
    duck.close()
    print("\nExport complete → PostgreSQL")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-url", required=True,
                        help="PostgreSQL connection URL")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    args = parser.parse_args()
    export_to_postgres(args.pg_url, Path(args.db))
