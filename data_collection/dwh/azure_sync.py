#!/usr/bin/env python3
"""
Azure ADLS Gen2 sync helper (decoupled from run_pipeline.py).

Reads AZURE_STORAGE_CONNECTION_STRING from the environment or .env.
Never prints keys or the connection string.

    python dwh/azure_sync.py --action pull-state
    python dwh/azure_sync.py --action push-bronze
    python dwh/azure_sync.py --action push-silver
    python dwh/azure_sync.py --action push-gold
    python dwh/azure_sync.py --action push-state
    python dwh/azure_sync.py --action verify
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "dwh" / "retail_lakehouse_fresh.duckdb"
BRONZE_ROOT = PROJECT_ROOT / "data" / "local_bronze"
SILVER_ROOT = PROJECT_ROOT / "data" / "local_silver"
GOLD_ROOT = PROJECT_ROOT / "data" / "local_gold"
DB_BLOB = "retail_lakehouse_fresh.duckdb"
HASH_BLOB = "latest_market_hashes.parquet"

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv(PROJECT_ROOT.parent / ".env")
except Exception:  # pragma: no cover
    pass


def _service():
    from azure.storage.blob import BlobServiceClient

    conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "").strip()
    if not conn:
        sys.exit("AZURE_STORAGE_CONNECTION_STRING is not set (env or .env).")
    return BlobServiceClient.from_connection_string(conn)


def _container(svc, name: str):
    cc = svc.get_container_client(name)
    try:
        if not cc.exists():
            cc.create_container()
    except Exception as exc:  # container may be pre-provisioned; surface class only
        print(f"  ! container '{name}' check failed: {type(exc).__name__}")
    return cc


def _upload(cc, local: Path, blob_name: str) -> None:
    with open(local, "rb") as fh:
        cc.upload_blob(name=blob_name, data=fh, overwrite=True)


def pull_state() -> None:
    from azure.core.exceptions import ResourceNotFoundError

    cc = _container(_service(), "state")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = cc.get_blob_client(DB_BLOB).download_blob()
    except ResourceNotFoundError:
        print(f"state/{DB_BLOB} not found yet — starting fresh.")
        return
    tmp = DB_PATH.with_suffix(".duckdb.part")
    with open(tmp, "wb") as fh:
        data.readinto(fh)
    tmp.replace(DB_PATH)
    print(f"pulled state/{DB_BLOB} ({DB_PATH.stat().st_size / 1e6:.2f} MB)")


def push_bronze() -> None:
    files = sorted(BRONZE_ROOT.rglob("*.parquet")) if BRONZE_ROOT.exists() else []
    if not files:
        print("no Parquet files under data/local_bronze/ — nothing to upload.")
        return
    cc = _container(_service(), "bronze")
    total = 0
    for f in files:
        _upload(cc, f, f.relative_to(BRONZE_ROOT).as_posix())
        total += f.stat().st_size
    print(f"uploaded {len(files)} parquet files ({total / 1e6:.2f} MB) to bronze")


def push_state() -> None:
    import duckdb

    if not DB_PATH.exists():
        sys.exit(f"missing {DB_PATH}")
    hashes = Path(tempfile.gettempdir()) / HASH_BLOB
    conn = duckdb.connect(str(DB_PATH))
    try:
        conn.execute("CHECKPOINT;")
        conn.execute(
            f"""COPY (SELECT PRODUCT_ID, STORE, STATE_HASH, LAST_UPDATED_AT, LAST_CHECKED_AT
                      FROM live_market.PRODUCTS)
                TO '{hashes.as_posix()}' (FORMAT PARQUET)"""
        )
    finally:
        conn.close()
    cc = _container(_service(), "state")
    _upload(cc, DB_PATH, DB_BLOB)
    _upload(cc, hashes, HASH_BLOB)
    print(f"uploaded state/{DB_BLOB} ({DB_PATH.stat().st_size / 1e6:.2f} MB) and state/{HASH_BLOB}")


def _export_layer_parquet(prefixes: tuple[str, ...], out_root: Path) -> list[Path]:
    """Export DuckDB main.* tables matching prefixes to zstd-compressed Parquet."""
    import duckdb

    if not DB_PATH.exists():
        sys.exit(f"missing {DB_PATH}")

    out_root.mkdir(parents=True, exist_ok=True)
    exported: list[Path] = []
    conn = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'main' ORDER BY table_name"
            ).fetchall()
            if r[0].startswith(prefixes)
        ]
        for tbl in tables:
            tbl_dir = out_root / tbl
            tbl_dir.mkdir(parents=True, exist_ok=True)
            out_file = tbl_dir / f"{tbl}.parquet"
            conn.execute(
                f"COPY (SELECT * FROM main.\"{tbl}\") "
                f"TO '{out_file.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)"
            )
            exported.append(out_file)
    finally:
        conn.close()
    return exported


def push_silver(local_only: bool = False) -> None:
    files = _export_layer_parquet(("slv_",), SILVER_ROOT)
    total = sum(f.stat().st_size for f in files)
    if local_only:
        print(f"exported {len(files)} silver parquet tables ({total / 1e6:.2f} MB) locally under {SILVER_ROOT}")
        return
    cc = _container(_service(), "silver")
    for f in files:
        _upload(cc, f, f.relative_to(SILVER_ROOT).as_posix())
    print(f"uploaded {len(files)} silver parquet tables ({total / 1e6:.2f} MB) to silver")


def push_gold(local_only: bool = False) -> None:
    files = _export_layer_parquet(("dim_", "fct_"), GOLD_ROOT)
    total = sum(f.stat().st_size for f in files)
    if local_only:
        print(f"exported {len(files)} gold parquet tables ({total / 1e6:.2f} MB) locally under {GOLD_ROOT}")
        return
    cc = _container(_service(), "gold")
    for f in files:
        _upload(cc, f, f.relative_to(GOLD_ROOT).as_posix())
    print(f"uploaded {len(files)} gold parquet tables ({total / 1e6:.2f} MB) to gold")


def verify() -> None:
    svc = _service()
    for name in ("bronze", "silver", "gold", "state"):
        cc = svc.get_container_client(name)
        try:
            blobs = list(cc.list_blobs())
        except Exception as exc:
            print(f"{name}: ERROR {type(exc).__name__}")
            continue
        size = sum(b.size or 0 for b in blobs) / 1e6
        latest = max((b.last_modified for b in blobs), default=None)
        print(f"container={name} blobs={len(blobs)} size_mb={size:.2f} latest_modified={latest}")
        for b in sorted(blobs, key=lambda x: x.last_modified, reverse=True)[:3]:
            print(f"   {b.last_modified}  {b.name}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--action",
        required=True,
        choices=["pull-state", "push-bronze", "push-silver", "push-gold", "push-state", "verify"],
    )
    p.add_argument("--local-only", action="store_true", help="Export Parquet locally without uploading to Azure.")
    a = p.parse_args()
    if a.action == "push-silver":
        push_silver(local_only=a.local_only)
    elif a.action == "push-gold":
        push_gold(local_only=a.local_only)
    else:
        {"pull-state": pull_state, "push-bronze": push_bronze,
         "push-state": push_state, "verify": verify}[a.action]()


if __name__ == "__main__":
    main()
