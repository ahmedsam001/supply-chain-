#!/usr/bin/env python3
"""
Local Bronze Parquet writer
===========================
Writes each run's delta rows as typed, zstd-compressed Parquet files into a
Hive-style partitioned folder, ready for a future ADLS Gen2 upload:

    data/local_bronze/<table_name>/date=YYYY-MM-DD/hour=HH/part-<run_id>[-<suffix>].parquet

Partition date/hour are the UTC start time of the run. Every file carries three
lineage columns: `_run_id`, `_ingested_at`, `_change_op` (INSERT | UPDATE).
Append-only: status updates to existing ERP rows are emitted again with
`_change_op = 'UPDATE'` (latest ingested row per business key wins downstream).
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BRONZE_ROOT = PROJECT_ROOT / "data" / "local_bronze"

_DUCK_TO_ARROW = {
    "VARCHAR": pa.string(),
    "DOUBLE": pa.float64(),
    "INTEGER": pa.int32(),
    "BIGINT": pa.int64(),
    "DATE": pa.date32(),
    "TIMESTAMP": pa.timestamp("us"),
}

# Explicit schema for the denormalised CDC change feed (no backing DuckDB table).
MARKET_CHANGES_SCHEMA = pa.schema([
    ("SNAPSHOT_ID", pa.string()), ("COLLECTED_DATE", pa.date32()), ("STORE", pa.string()),
    ("PRODUCT_ID", pa.string()), ("PRODUCT_NAME", pa.string()), ("CATEGORY", pa.string()),
    ("BRAND", pa.string()), ("PRICE", pa.float64()), ("OLD_PRICE", pa.float64()),
    ("DISCOUNT", pa.float64()), ("STOCK_STATUS", pa.string()), ("PRODUCT_URL", pa.string()),
    ("IMAGE_URL", pa.string()), ("STATE_HASH", pa.string()), ("CHANGE_TYPE", pa.string()),
    ("COLLECTED_AT", pa.timestamp("us")), ("RUN_ID", pa.string()),
])


def arrow_schema_for_table(conn: duckdb.DuckDBPyConnection, qualified_table: str) -> pa.Schema:
    """Derive an Arrow schema from a DuckDB table so all-NULL columns keep their type."""
    fields = []
    for name, dtype, *_ in conn.execute(f"DESCRIBE {qualified_table}").fetchall():
        fields.append((name, _DUCK_TO_ARROW.get(str(dtype).upper(), pa.string())))
    return pa.schema(fields)


def partition_dir(table: str, run_ts: datetime, root: Optional[Path] = None) -> Path:
    return (root or BRONZE_ROOT) / table / f"date={run_ts:%Y-%m-%d}" / f"hour={run_ts:%H}"


def write_bronze(
    table: str,
    rows: list[dict[str, Any]],
    schema: pa.Schema,
    run_ts: datetime,
    run_id: str,
    op: str = "INSERT",
    suffix: str = "",
    root: Optional[Path] = None,
) -> Optional[Path]:
    """Write `rows` to the partitioned bronze folder. Returns the file path (None if empty)."""
    if not rows:
        return None
    names = schema.names
    columns = {n: [r.get(n) for r in rows] for n in names}
    tbl = pa.Table.from_pydict(columns, schema=schema)
    n = tbl.num_rows
    tbl = tbl.append_column("_run_id", pa.array([run_id] * n, pa.string()))
    tbl = tbl.append_column("_ingested_at", pa.array([run_ts.replace(tzinfo=None)] * n, pa.timestamp("us")))
    tbl = tbl.append_column("_change_op", pa.array([op] * n, pa.string()))

    out_dir = partition_dir(table, run_ts, root)
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"part-{run_id}{('-' + suffix) if suffix else ''}-{op.lower()}.parquet"
    out = out_dir / fname
    pq.write_table(tbl, out, compression="zstd")
    return out
