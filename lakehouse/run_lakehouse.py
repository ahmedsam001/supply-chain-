#!/usr/bin/env python3
"""
Azure Lakehouse Compute Runner (designed for Azure Container Apps Jobs)
=======================================================================
Decoupled from GitHub Actions scraping. Runs on a schedule (hourly or daily):
  1. Pulls latest DuckDB state from Azure ADLS Gen2 (`state/` container)
  2. Executes dbt transformations + data quality tests:
       - hourly: refreshes live market Silver & Gold models only (< 5 seconds)
       - daily:  full dbt seed + dbt run (33 models) + dbt test (364 tests)
  3. Exports & uploads Silver (14 tables) and Gold (19 tables) Parquet to
     Azure ADLS Gen2 (`silver/` and `gold/` containers).

Usage:
    python lakehouse/run_lakehouse.py --mode daily
    python lakehouse/run_lakehouse.py --mode hourly
    python lakehouse/run_lakehouse.py --mode daily --local   # local test, no Azure I/O
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TRANS_DIR = REPO_ROOT / "transformations"
AZURE_SYNC = REPO_ROOT / "data_collection" / "azure_sync.py"

HOURLY_MODELS = [
    "dim_date",
    "slv_stores",
    "dim_store",
    "slv_products",
    "slv_price_history",
    "slv_market_snapshots",
    "slv_run_logs",
    "dim_product",
    "dim_market_status",
    "dim_price_event_status",
    "fct_market_snapshots",
    "fct_price_changes",
]


def _resolve_dbt() -> str:
    venv_dbt = REPO_ROOT / ".venv" / "bin" / "dbt"
    if venv_dbt.exists():
        return str(venv_dbt)
    found = shutil.which("dbt")
    if found:
        return found
    sys.exit("dbt executable not found on PATH or in .venv/bin/dbt")


def _run(cmd: list[str], cwd: Path = REPO_ROOT) -> None:
    print(f"\n>>> {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, cwd=str(cwd), check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Azure Lakehouse dbt transformations & ADLS Gen2 publish.")
    parser.add_argument("--mode", choices=["hourly", "daily"], default="daily")
    parser.add_argument("--local", action="store_true", help="Skip Azure pull/push; export Parquet locally only.")
    args = parser.parse_args()

    dbt_bin = _resolve_dbt()
    py_bin = sys.executable

    # 1. Pull latest state from Azure ADLS Gen2
    if not args.local:
        _run([py_bin, str(AZURE_SYNC), "--action", "pull-state"])

    # 2. Run dbt transformations & tests
    if args.mode == "daily":
        _run([dbt_bin, "seed", "--profiles-dir", "."], cwd=TRANS_DIR)
        _run([dbt_bin, "run", "--profiles-dir", "."], cwd=TRANS_DIR)
        _run([dbt_bin, "test", "--profiles-dir", "."], cwd=TRANS_DIR)
    else:
        select_args = ["--select", *HOURLY_MODELS]
        _run([dbt_bin, "run", "--profiles-dir", ".", *select_args], cwd=TRANS_DIR)
        _run([dbt_bin, "test", "--profiles-dir", ".", "--indirect-selection=cautious", *select_args], cwd=TRANS_DIR)

    # 3. Export & upload Silver + Gold Parquet to Azure ADLS Gen2
    extra = ["--local-only"] if args.local else []
    _run([py_bin, str(AZURE_SYNC), "--action", "push-silver", *extra])
    _run([py_bin, str(AZURE_SYNC), "--action", "push-gold", *extra])

    print(f"\nLakehouse run ({args.mode}, local={args.local}) completed successfully!", flush=True)


if __name__ == "__main__":
    main()
