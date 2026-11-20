#!/usr/bin/env python3
"""
Local-first Ingestion & Synthetic ERP Engine — main runner
==========================================================
Live scraping  ->  hash-based CDC  ->  local DuckDB  ->  local Bronze Parquet,
plus synthetic ERP event generation tied to the latest live prices.
No Airflow, no cloud connectors.

Modes
    --mode daily    Full catalog + branches scrape, CDC snapshot, baseline/daily ERP sync.
    --mode hourly   Lightweight price/stock pulse (no branch pass, capped catalog),
                    CDC hash filtering, incremental hourly ERP events.

Optional local scheduler (no Airflow needed):
    --loop --interval-minutes 60     repeat the chosen mode until Ctrl-C

Outputs
    DuckDB : dwh/retail_lakehouse_fresh.duckdb   (schemas live_market, supply_chain_stage)
    Bronze : data/local_bronze/<table>/date=YYYY-MM-DD/hour=HH/part-*.parquet  (UTC)

Examples
    python dwh/run_pipeline.py --mode daily
    python dwh/run_pipeline.py --mode hourly
    python dwh/run_pipeline.py --mode hourly --loop --interval-minutes 30
    python dwh/run_pipeline.py --mode daily --offline --limit 50     # fixtures, no network
"""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import os
import signal
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:  # optional: pick up MAX_PRODUCTS_PER_SOURCE etc. from .env
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except Exception:  # pragma: no cover
    pass

from dwh.bronze_writer import (  # noqa: E402
    BRONZE_ROOT, MARKET_CHANGES_SCHEMA, arrow_schema_for_table, write_bronze,
)
from dwh.cdc_snapshot import (  # noqa: E402
    LOCAL_DB_PATH, apply_cdc, ensure_live_market_schema, insert_run_log,
    map_scrape_to_market_rows, replace_branches, seed_stores,
)
from dwh.pipeline import (  # noqa: E402
    SOURCES, enforce_strict_quality_gate, load_all_source_data, load_source_samples,
    run_live_extraction, validate_source_bundle,
)
from dwh.supply_chain_generator import ensure_supply_chain_tables, run_erp_sync  # noqa: E402

LOCK_FILE = Path(tempfile.gettempdir()) / "retail_lakehouse_fresh.lock"
HOURLY_DEFAULT_LIMIT = 300


# ─────────────────────────────────────────────────────────────────────────────
# Scrape (async, bounded concurrency) — no DB access here
# ─────────────────────────────────────────────────────────────────────────────

async def _scrape_one(
    source_id: str, offline: bool, limit: int, with_locations: bool, run_id: str, run_date: str,
) -> dict[str, Any]:
    t0 = time.monotonic()
    started_at = datetime.now(timezone.utc).replace(tzinfo=None)
    out: dict[str, Any] = {"source": source_id, "run_id": run_id, "started_at": started_at,
                           "products": [], "observations": [], "locations": [], "error": None}
    for attempt in (1, 2):
        try:
            live_data = await run_live_extraction(
                source_id, offline=offline, limit=limit, with_locations=with_locations
            )
            if offline:
                if not live_data:
                    live_data = load_source_samples(source_id)
                data = load_all_source_data(source_id=source_id, live_data=live_data, include_raw_snapshots=False)
            else:
                data = live_data or {"products": [], "observations": [], "locations": [],
                                     "quality_issues": [], "extraction_meta": {"mode": "live"}}
            meta = data.get("extraction_meta", {})
            mode = meta.get("run_mode") or meta.get("mode") or ("offline_fixture" if offline else "live")

            products, observations, locations, _qi, qscore = validate_source_bundle(
                source_id=source_id, bundle=data, run_id=run_id, mode=mode,
            )
            products, observations, locations = enforce_strict_quality_gate(
                source_id=source_id, products=products, observations=observations,
                locations=locations, run_date=run_date,
            )
            out.update(products=products, observations=observations, locations=locations,
                       quality_score=qscore)
            meta_errors = meta.get("errors") or data.get("errors") or []
            if any("circuit breaker" in str(e).lower() for e in meta_errors):
                out["circuit_breaker"] = True
        except Exception as exc:  # one broken store must not abort the run
            out["error"] = f"{type(exc).__name__}: {exc}"
            print(f"  ✗ {source_id}: extraction failed — {out['error']}")

        if out.get("circuit_breaker"):
            print(f"  ⛔ {source_id}: circuit breaker tripped — skipping full-store retry.")
            break

        if not offline and attempt == 1 and (out["error"] or len(out["products"]) == 0):
            print(f"  ⚠️  {source_id}: 0 products on attempt 1 ({out['error'] or 'empty result'}) — retrying once...")
            out["error"] = None
            await asyncio.sleep(2.0)
            continue
        break
    out["scrape_seconds"] = time.monotonic() - t0
    return out


async def scrape_all(
    sources: list[str], offline: bool, limit: int, with_locations: bool,
    pipeline_run_id: str, run_date: str, concurrency: int,
) -> list[dict[str, Any]]:
    sem = asyncio.Semaphore(max(1, concurrency))

    async def _guarded(src: str) -> dict[str, Any]:
        async with sem:
            rid = f"{src}_{pipeline_run_id}_{uuid4().hex[:6]}"
            return await _scrape_one(src, offline, limit, with_locations, rid, run_date)

    return await asyncio.gather(*[_guarded(s) for s in sources])


# ─────────────────────────────────────────────────────────────────────────────
# One full run
# ─────────────────────────────────────────────────────────────────────────────

def run_once(
    mode: str,
    sources: list[str],
    limit: int,
    offline: bool = False,
    db_path: Path = LOCAL_DB_PATH,
    bronze_root: Path = BRONZE_ROOT,
    skip_erp: bool = False,
    concurrency: int = 2,
) -> dict[str, Any]:
    run_ts = datetime.now(timezone.utc)
    now = run_ts.replace(tzinfo=None)  # naive UTC for DuckDB TIMESTAMP columns
    pipeline_run_id = f"{mode}_{run_ts:%Y%m%dT%H%M%SZ}"
    t_start = time.monotonic()
    with_locations = mode == "daily"

    print(f"\n{'═'*72}")
    print(f"  LOCAL INGESTION ENGINE   mode={mode.upper()}   {run_ts:%Y-%m-%d %H:%M:%S} UTC")
    print(f"  DB     : {db_path}")
    print(f"  Bronze : {bronze_root}")
    print(f"  Sources: {', '.join(sources)}   limit/source={limit:,}   "
          f"{'OFFLINE fixtures' if offline else 'LIVE scraping'}")
    print(f"{'═'*72}")

    scraped = asyncio.run(scrape_all(
        sources, offline, limit, with_locations, pipeline_run_id, run_ts.date().isoformat(), concurrency,
    ))

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db_path))
    summary: dict[str, Any] = {"mode": mode, "run_id": pipeline_run_id, "stores": {}, "erp": None}
    try:
        ensure_live_market_schema(conn)
        ensure_supply_chain_tables(conn)
        seed_stores(conn)
        branches_schema = arrow_schema_for_table(conn, "live_market.BRANCHES")
        runlog_schema = arrow_schema_for_table(conn, "live_market.RUN_LOGS")

        print(f"\n  {'STORE':<11}{'SCRAPED':>8}{'UNCHANGED':>11}{'INSERT':>8}{'UPDATE':>8}{'BRANCHES':>10}{'SECS':>8}")
        print(f"  {'-'*64}")
        for item in scraped:
            src = item["source"]
            products, branch_rows, rejected = map_scrape_to_market_rows(
                src, item["products"], item["observations"], item["locations"], now,
            )
            res = apply_cdc(conn, src, products, item["run_id"], now)

            n_branches = 0
            if with_locations and branch_rows:
                n_branches = replace_branches(conn, src, branch_rows)
                write_bronze("branches", branch_rows, branches_schema, run_ts, item["run_id"],
                             op="INSERT", suffix=src, root=bronze_root)

            for op in ("INSERT", "UPDATE"):
                rows = [r for r in res.changed_rows if r["CHANGE_TYPE"] == op]
                write_bronze("market_changes", rows, MARKET_CHANGES_SCHEMA, run_ts,
                             item["run_id"], op=op, suffix=src, root=bronze_root)

            finished = datetime.now(timezone.utc).replace(tzinfo=None)
            duration = item["scrape_seconds"]
            log_row = insert_run_log(conn, item["run_id"], src, mode, res, duration,
                                     item["started_at"], finished)
            write_bronze("run_logs", [log_row], runlog_schema, run_ts, item["run_id"],
                         op="INSERT", suffix=src, root=bronze_root)

            summary["stores"][src] = {
                "scraped": res.scraped, "unchanged": res.unchanged, "inserted": res.inserted,
                "updated": res.updated, "rejected": rejected, "branches": n_branches,
                "error": item["error"],
            }
            flag = "  ✗ " + item["error"][:40] if item["error"] else ""
            print(f"  {src:<11}{res.scraped:>8,}{res.unchanged:>11,}{res.inserted:>8,}"
                  f"{res.updated:>8,}{n_branches:>10,}{duration:>8.1f}{flag}")

        if skip_erp:
            print("\n  ERP sync: skipped (--skip-erp)")
        else:
            erp = run_erp_sync(conn, mode, run_ts, pipeline_run_id, bronze_root=bronze_root)
            summary["erp"] = erp
            print(f"\n  ERP sync [{erp['mode']}] appended: " +
                  ", ".join(f"{k.replace('RAW_', '')}={v:,}" for k, v in erp["appended_rows"].items()))
            if erp["status_updates"]:
                print("  status progressions: " +
                      ", ".join(f"{k.replace('RAW_', '')}={v:,}" for k, v in erp["status_updates"].items()))
    finally:
        conn.close()

    summary["seconds"] = round(time.monotonic() - t_start, 1)
    print(f"\n  ✅ run complete in {summary['seconds']}s\n")
    return summary


# ─────────────────────────────────────────────────────────────────────────────
# CLI + local loop
# ─────────────────────────────────────────────────────────────────────────────

def _locked_run(**kwargs: Any) -> Optional[dict[str, Any]]:
    """Single-writer guard: DuckDB allows one writer, so refuse to overlap runs."""
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK_FILE, "w") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("  ⚠️  another run_pipeline.py instance is active (lock held) — skipping this run.")
            return None
        try:
            return run_once(**kwargs)
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Local-first scraping + synthetic ERP engine (DuckDB + Bronze Parquet)")
    ap.add_argument("--mode", choices=["daily", "hourly"], required=True)
    ap.add_argument("--sources", default=",".join(SOURCES), help="comma-separated store ids (default: all 6)")
    ap.add_argument("--limit", type=int, default=None,
                    help="max products per store (default: $MAX_PRODUCTS_PER_SOURCE or 1000; "
                         f"hourly is capped at {HOURLY_DEFAULT_LIMIT} unless --limit is given)")
    ap.add_argument("--offline", action="store_true", help="use bundled fixtures instead of live scraping")
    ap.add_argument("--loop", action="store_true", help="repeat the chosen mode on a local timer")
    ap.add_argument("--interval-minutes", type=float, default=60.0, help="loop interval (default 60)")
    ap.add_argument("--max-iterations", type=int, default=None, help="stop the loop after N runs (testing)")
    ap.add_argument("--db", default=str(LOCAL_DB_PATH))
    ap.add_argument("--bronze-dir", default=str(BRONZE_ROOT))
    ap.add_argument("--skip-erp", action="store_true", help="market scrape + CDC only")
    args = ap.parse_args(argv)

    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    bad = [s for s in sources if s not in SOURCES]
    if bad:
        ap.error(f"unknown sources: {bad}; valid: {SOURCES}")

    if args.limit is not None:
        limit = args.limit
    else:
        env_limit = int(os.getenv("MAX_PRODUCTS_PER_SOURCE", "1000"))
        limit = min(env_limit, HOURLY_DEFAULT_LIMIT) if args.mode == "hourly" else env_limit
    concurrency = int(os.getenv("MAX_CONCURRENT_EXTRACTORS", "6"))

    kwargs = dict(mode=args.mode, sources=sources, limit=limit, offline=args.offline,
                  db_path=Path(args.db), bronze_root=Path(args.bronze_dir),
                  skip_erp=args.skip_erp, concurrency=concurrency)

    if not args.loop:
        _locked_run(**kwargs)
        return 0

    stop = {"flag": False}

    def _stop(*_: Any) -> None:
        stop["flag"] = True
        print("\n  ⏹  stop requested — finishing after the current wait/run...")

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    interval = max(1.0, args.interval_minutes * 60.0)
    n = 0
    print(f"  🔁 loop mode: {args.mode} every {args.interval_minutes:g} min (Ctrl-C to stop)")
    while not stop["flag"]:
        t0 = time.monotonic()
        try:
            _locked_run(**kwargs)
        except Exception:
            print("  ✗ run failed (loop continues):")
            traceback.print_exc()
        n += 1
        if args.max_iterations and n >= args.max_iterations:
            break
        deadline = t0 + interval
        while not stop["flag"] and time.monotonic() < deadline:
            time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
