#!/usr/bin/env python3
"""
Post-upload Data Quality Guard (Silent Failure Detection).

Inspects the latest pipeline run in `live_market.RUN_LOGS` inside
`dwh/retail_lakehouse_fresh.duckdb` and exits non-zero (1) if:
  - No RUN_LOGS entries exist
  - Any row reports a failure/error status (when a STATUS column is present)
  - Total scraped products across the run == 0
  - Any active/expected store returned 0 products or is missing from the run

Designed to run AFTER Azure sync (`push-bronze` / `push-state`) in GitHub Actions
so valid data from healthy stores is safely persisted before GitHub marks the
workflow run as Failed and sends native failure email notifications.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Optional

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "dwh" / "retail_lakehouse_fresh.duckdb"
DEFAULT_EXPECTED_STORES = (
    "jumia",
    "two_b",
    "carrefour",
    "tradeline",
    "dream2000",
    "raya",
)

_PIPELINE_TOKEN_RE = re.compile(r"(?:daily|hourly)_\d{8}T\d{6}Z")
_HEALTHY_STATUSES = {"", "OK", "SUCCESS", "SUCCEEDED", "COMPLETED", "HEALTHY"}


@dataclass
class HealthReport:
    ok: bool
    run_label: str
    run_mode: str
    total_products: int
    total_snapshots: int
    total_unchanged: int
    per_store: dict[str, dict] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def _extract_pipeline_token(run_id: str) -> Optional[str]:
    m = _PIPELINE_TOKEN_RE.search(run_id or "")
    return m.group(0) if m else None


def evaluate_run_health(
    db_path: Path = DEFAULT_DB_PATH,
    expected_stores: Optional[list[str]] = None,
) -> HealthReport:
    if not db_path.exists():
        return HealthReport(
            ok=False,
            run_label="missing-db",
            run_mode="unknown",
            total_products=0,
            total_snapshots=0,
            total_unchanged=0,
            errors=[f"DuckDB file not found at {db_path}"],
        )

    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        tables = {
            (r[0], r[1])
            for r in conn.execute(
                "SELECT table_schema, table_name FROM information_schema.tables"
            ).fetchall()
        }
        if ("live_market", "RUN_LOGS") not in tables:
            return HealthReport(
                ok=False,
                run_label="missing-table",
                run_mode="unknown",
                total_products=0,
                total_snapshots=0,
                total_unchanged=0,
                errors=["Table live_market.RUN_LOGS does not exist."],
            )

        cols = [
            r[0].upper()
            for r in conn.execute("DESCRIBE live_market.RUN_LOGS").fetchall()
        ]
        has_status = "STATUS" in cols

        # Determine expected active stores
        if expected_stores is None:
            stores_from_db: list[str] = []
            if ("live_market", "STORES") in tables:
                stores_from_db = [
                    r[0]
                    for r in conn.execute(
                        "SELECT STORE_ID FROM live_market.STORES WHERE STORE_ID IS NOT NULL"
                    ).fetchall()
                ]
            active_stores = stores_from_db or list(DEFAULT_EXPECTED_STORES)
        else:
            active_stores = [s.strip() for s in expected_stores if s.strip()]

        status_expr = "STATUS" if has_status else "NULL AS STATUS"
        latest = conn.execute(
            f"""SELECT RUN_ID, STORE, RUN_MODE, PRODUCTS_COLLECTED,
                       SNAPSHOTS_WRITTEN, PRODUCTS_UNCHANGED,
                       DURATION_SECONDS, FINISHED_AT, {status_expr}
                FROM live_market.RUN_LOGS
                ORDER BY FINISHED_AT DESC NULLS LAST
                LIMIT 1"""
        ).fetchone()

        if latest is None:
            return HealthReport(
                ok=False,
                run_label="empty",
                run_mode="unknown",
                total_products=0,
                total_snapshots=0,
                total_unchanged=0,
                errors=["No rows found in live_market.RUN_LOGS."],
            )

        latest_run_id = latest[0] or ""
        latest_mode = latest[2] or "unknown"
        latest_finished = latest[7]
        token = _extract_pipeline_token(latest_run_id)

        if token:
            run_label = token
            rows = conn.execute(
                f"""SELECT RUN_ID, STORE, RUN_MODE, PRODUCTS_COLLECTED,
                           SNAPSHOTS_WRITTEN, PRODUCTS_UNCHANGED,
                           DURATION_SECONDS, FINISHED_AT, {status_expr}
                    FROM live_market.RUN_LOGS
                    WHERE RUN_ID LIKE ?
                    ORDER BY STORE""",
                (f"%{token}%",),
            ).fetchall()
        elif latest_finished is not None:
            run_label = latest_run_id or str(latest_finished)
            window_start = latest_finished - timedelta(minutes=15)
            rows = conn.execute(
                f"""SELECT RUN_ID, STORE, RUN_MODE, PRODUCTS_COLLECTED,
                           SNAPSHOTS_WRITTEN, PRODUCTS_UNCHANGED,
                           DURATION_SECONDS, FINISHED_AT, {status_expr}
                    FROM live_market.RUN_LOGS
                    WHERE FINISHED_AT >= ?
                    ORDER BY FINISHED_AT DESC""",
                (window_start,),
            ).fetchall()
        else:
            run_label = latest_run_id or "latest"
            rows = conn.execute(
                f"""SELECT RUN_ID, STORE, RUN_MODE, PRODUCTS_COLLECTED,
                           SNAPSHOTS_WRITTEN, PRODUCTS_UNCHANGED,
                           DURATION_SECONDS, FINISHED_AT, {status_expr}
                    FROM live_market.RUN_LOGS
                    WHERE RUN_ID = ?""",
                (latest_run_id,),
            ).fetchall()
    finally:
        conn.close()

    per_store: dict[str, dict] = {}
    errors: list[str] = []

    for r in rows:
        store = (r[1] or "").strip()
        if store in per_store:
            continue  # keep latest row per store when using time-window fallback
        collected = int(r[3] or 0)
        written = int(r[4] or 0)
        unchanged = int(r[5] or 0)
        duration = float(r[6] or 0.0)
        status = (str(r[8]).strip() if r[8] is not None else "")
        per_store[store] = {
            "run_id": r[0],
            "products_collected": collected,
            "snapshots_written": written,
            "products_unchanged": unchanged,
            "duration_seconds": duration,
            "status": status,
        }
        if status and status.upper() not in _HEALTHY_STATUSES:
            errors.append(
                f"Store '{store}' reported non-healthy status '{status}'."
            )

    total_products = sum(v["products_collected"] for v in per_store.values())
    total_snapshots = sum(v["snapshots_written"] for v in per_store.values())
    total_unchanged = sum(v["products_unchanged"] for v in per_store.values())

    if total_products == 0:
        errors.append("Total scraped products across the latest run is 0.")

    for store, stats in sorted(per_store.items()):
        if stats["products_collected"] <= 0:
            errors.append(
                f"Store '{store}' returned 0 products (possible anti-bot block or selector change)."
            )

    for store in active_stores:
        if store not in per_store:
            errors.append(
                f"Expected store '{store}' is missing from latest RUN_LOGS ({run_label})."
            )

    return HealthReport(
        ok=len(errors) == 0,
        run_label=run_label,
        run_mode=latest_mode,
        total_products=total_products,
        total_snapshots=total_snapshots,
        total_unchanged=total_unchanged,
        per_store=per_store,
        errors=errors,
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Post-upload data quality guard for live_market.RUN_LOGS."
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="Path to DuckDB database (default: dwh/retail_lakehouse_fresh.duckdb).",
    )
    parser.add_argument(
        "--expected-stores",
        type=str,
        default=None,
        help="Optional comma-separated list of expected stores (defaults to live_market.STORES).",
    )
    args = parser.parse_args(argv)

    expected = (
        [s.strip() for s in args.expected_stores.split(",") if s.strip()]
        if args.expected_stores
        else None
    )
    report = evaluate_run_health(db_path=args.db_path, expected_stores=expected)

    print(f"Run Health Check [{report.run_mode}] — {report.run_label}")
    if report.per_store:
        print(f"  {'STORE':<12}{'SCRAPED':>9}{'CHANGED':>9}{'UNCHANGED':>11}{'SECS':>8}")
        print(f"  {'-' * 49}")
        for store, s in sorted(report.per_store.items()):
            print(
                f"  {store:<12}{s['products_collected']:>9,}"
                f"{s['snapshots_written']:>9,}{s['products_unchanged']:>11,}"
                f"{s['duration_seconds']:>8.1f}"
            )

    if not report.ok:
        print("\n❌ HEALTH CHECK FAILED:")
        for err in report.errors:
            print(f"  - {err}")
        return 1

    print(
        f"\n✅ HEALTH CHECK PASSED: {len(report.per_store)} stores healthy, "
        f"{report.total_products:,} products scraped "
        f"({report.total_snapshots:,} changed, {report.total_unchanged:,} unchanged)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
