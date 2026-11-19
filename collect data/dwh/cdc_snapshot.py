#!/usr/bin/env python3
"""
Hash-based CDC snapshots for the local `live_market` schema
===========================================================
Local-first, zero-redundancy change capture for scraped market data.

Every scraped product gets a deterministic SHA-256 `STATE_HASH` computed over
    (PRODUCT_ID, CURRENT_PRICE, OLD_PRICE, DISCOUNT, STOCK_STATUS)
and is compared with the latest stored state in `live_market.PRODUCTS`:

    unchanged hash -> NO new PRICE_HISTORY row; only PRODUCTS.LAST_CHECKED_AT moves
    new product    -> PRODUCTS insert + PRICE_HISTORY row, CHANGE_TYPE = 'INSERT'
    changed hash   -> PRODUCTS update + PRICE_HISTORY row, CHANGE_TYPE = 'UPDATE'

Only the INSERT/UPDATE rows are returned to the caller so they can be written to
`data/local_bronze/market_changes/`. No cloud connectors live here.
"""

from __future__ import annotations

import hashlib
import math
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional
from uuid import NAMESPACE_DNS, uuid5

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from normalization.normalizers import normalize_image_url, normalize_stock_status  # noqa: E402
from normalization.taxonomy import classify_product  # noqa: E402

LOCAL_DB_PATH = PROJECT_ROOT / "dwh" / "retail_lakehouse_fresh.duckdb"

DEFAULT_STORES = [
    {"store_id": "jumia", "store_name": "Jumia Egypt", "domain": "jumia.com.eg",
     "official_url": "https://www.jumia.com.eg", "business_type": "General Marketplace"},
    {"store_id": "two_b", "store_name": "2B Egypt", "domain": "2b.com.eg",
     "official_url": "https://2b.com.eg", "business_type": "Electronics & Tech Retailer"},
    {"store_id": "carrefour", "store_name": "Carrefour Egypt", "domain": "carrefouregypt.com",
     "official_url": "https://www.carrefouregypt.com", "business_type": "Hypermarket & Supermarket"},
    {"store_id": "tradeline", "store_name": "Tradeline", "domain": "tradeline-stores.com",
     "official_url": "https://tradeline-stores.com", "business_type": "Apple Authorised Reseller"},
    {"store_id": "dream2000", "store_name": "Dream 2000", "domain": "dream2000.com",
     "official_url": "https://dream2000.com", "business_type": "Mobile & Electronics Retailer"},
    {"store_id": "raya", "store_name": "Raya Shop", "domain": "rayashop.com",
     "official_url": "https://www.rayashop.com", "business_type": "Consumer Electronics Retailer"},
]

# ─────────────────────────────────────────────────────────────────────────────
# Schema (live_market). No PK constraints: uniqueness is enforced by the CDC logic
# (DuckDB ART indexes make bulk UPDATE-by-key slow and add little here).
# ─────────────────────────────────────────────────────────────────────────────

LIVE_MARKET_DDL: list[str] = [
    "CREATE SCHEMA IF NOT EXISTS live_market",
    """CREATE TABLE IF NOT EXISTS live_market.STORES (
        STORE_ID VARCHAR, STORE_NAME VARCHAR, DOMAIN VARCHAR,
        OFFICIAL_URL VARCHAR, BUSINESS_TYPE VARCHAR)""",
    """CREATE TABLE IF NOT EXISTS live_market.BRANCHES (
        BRANCH_ID VARCHAR, STORE VARCHAR, BRANCH_NAME VARCHAR, GOVERNORATE VARCHAR,
        CITY VARCHAR, ADDRESS VARCHAR, PHONE VARCHAR, LATITUDE DOUBLE, LONGITUDE DOUBLE,
        LAST_CHECKED_AT TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS live_market.PRODUCTS (
        STORE VARCHAR, PRODUCT_ID VARCHAR, PRODUCT_NAME VARCHAR, CATEGORY VARCHAR,
        BRAND VARCHAR, CURRENT_PRICE DOUBLE, OLD_PRICE DOUBLE, DISCOUNT DOUBLE,
        STOCK_STATUS VARCHAR, PRODUCT_URL VARCHAR, IMAGE_URL VARCHAR,
        STATE_HASH VARCHAR, FIRST_SEEN_AT TIMESTAMP, LAST_UPDATED_AT TIMESTAMP,
        LAST_CHECKED_AT TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS live_market.PRICE_HISTORY (
        SNAPSHOT_ID VARCHAR, COLLECTED_DATE DATE, STORE VARCHAR, PRODUCT_ID VARCHAR,
        PRICE DOUBLE, OLD_PRICE DOUBLE, DISCOUNT DOUBLE, STOCK_STATUS VARCHAR,
        STATE_HASH VARCHAR, CHANGE_TYPE VARCHAR, COLLECTED_AT TIMESTAMP, RUN_ID VARCHAR)""",
    """CREATE TABLE IF NOT EXISTS live_market.RUN_LOGS (
        RUN_ID VARCHAR, STORE VARCHAR, RUN_MODE VARCHAR, RUN_DATE DATE,
        PRODUCTS_COLLECTED INTEGER, SNAPSHOTS_WRITTEN INTEGER, PRODUCTS_UNCHANGED INTEGER,
        DURATION_SECONDS DOUBLE, STARTED_AT TIMESTAMP, FINISHED_AT TIMESTAMP)""",
    "CREATE OR REPLACE VIEW live_market.MARKET_SNAPSHOTS AS SELECT * FROM live_market.PRICE_HISTORY",
]


def ensure_live_market_schema(conn: duckdb.DuckDBPyConnection) -> None:
    for stmt in LIVE_MARKET_DDL:
        conn.execute(stmt)


def seed_stores(conn: duckdb.DuckDBPyConnection) -> None:
    """Idempotently load the 6 retailers into live_market.STORES."""
    conn.execute("DELETE FROM live_market.STORES")
    conn.executemany(
        "INSERT INTO live_market.STORES VALUES (?, ?, ?, ?, ?)",
        [(s["store_id"], s["store_name"], s["domain"], s["official_url"], s["business_type"])
         for s in DEFAULT_STORES],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic state hash
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_num(v: Any) -> str:
    if v is None:
        return ""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return ""
    if math.isnan(f) or math.isinf(f):
        return ""
    return f"{f:.2f}"


def compute_state_hash(
    product_id: Any,
    current_price: Any,
    old_price: Any,
    discount: Any,
    stock_status: Any,
) -> str:
    """SHA-256 over (PRODUCT_ID, CURRENT_PRICE, OLD_PRICE, DISCOUNT, STOCK_STATUS).

    Numbers are rendered with fixed 2-decimals, NULL as '', stock upper-cased, so the
    hash is stable across runs, Python versions and float representation noise.
    """
    payload = "|".join([
        str(product_id or "").strip(),
        _fmt_num(current_price),
        _fmt_num(old_price),
        _fmt_num(discount),
        str(stock_status or "").strip().upper(),
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# Scrape -> live_market row mapping (post validation + quality gate)
# ─────────────────────────────────────────────────────────────────────────────

def map_scrape_to_market_rows(
    source_id: str,
    products: list[dict],
    observations: list[dict],
    locations: Optional[list[dict]],
    now: datetime,
) -> tuple[list[dict], list[dict], int]:
    """Map validated scrape output to PRODUCTS-shaped rows and BRANCHES rows.

    Returns (product_rows, branch_rows, rejected_count). Rows failing the critical
    NULL gate (price/name/url/stock) are rejected, never stored.
    """
    locations = locations or []

    obs_map: dict[str, dict] = {}
    for o in observations:
        spid = str(o.get("source_product_id") or "").strip()
        pid = str(o.get("product_id") or "").strip()
        if not spid and ":" in pid:
            spid = pid.split(":", 1)[1]
        canonical = f"{source_id}:{spid}" if spid else pid
        if not canonical:
            continue
        try:
            price = float(o["price"]) if o.get("price") is not None else None
        except (ValueError, TypeError):
            price = None
        if price is None or price <= 0:
            continue
        stock = normalize_stock_status(o.get("stock_status"), o.get("availability_status"))
        if not stock or stock == "UNKNOWN":
            continue
        clean = dict(o)
        clean["price"] = price
        clean["stock_status"] = stock
        obs_map[canonical] = clean
        if spid:
            obs_map[spid] = clean
        if pid:
            obs_map[pid] = clean

    product_rows: list[dict] = []
    seen: set[str] = set()
    rejected = 0
    for p in products:
        spid = str(p.get("source_product_id") or "").strip()
        rpid = str(p.get("product_id") or "").strip()
        if not spid and ":" in rpid:
            spid = rpid.split(":", 1)[1]
        canonical = f"{source_id}:{spid}" if spid else rpid
        if not canonical or canonical in seen:
            continue

        o = obs_map.get(canonical) or obs_map.get(spid) or obs_map.get(rpid) or {}
        pname = str(p.get("product_name") or "").strip()[:2000]
        purl = str(p.get("product_url") or "").strip()[:2000] if p.get("product_url") else None
        price = float(o["price"]) if o.get("price") is not None else None
        stock = o.get("stock_status")

        if (not pname or pname == "Unknown Product" or not purl
                or price is None or price <= 0 or not stock or stock == "UNKNOWN"):
            rejected += 1
            continue
        seen.add(canonical)

        brand = str(p.get("brand") or "").strip()[:255] or None
        raw_cat = str(p.get("category") or p.get("raw_category_path") or "").strip()[:500]
        if not raw_cat or raw_cat == "Uncategorized":
            raw_cat = classify_product(pname, brand, raw_cat).get("category") or raw_cat or "General"

        old_price = float(o["old_price"]) if o.get("old_price") is not None else None
        if old_price is not None and old_price <= price:
            old_price = None
        discount = float(o["discount"]) if o.get("discount") is not None else None
        if old_price is None:
            discount = None
        elif discount is None:
            discount = round((1.0 - price / old_price) * 100.0, 1)

        iurl = normalize_image_url(p.get("image_url"))
        product_rows.append({
            "STORE": source_id,
            "PRODUCT_ID": canonical,
            "PRODUCT_NAME": pname,
            "CATEGORY": raw_cat,
            "BRAND": brand,
            "CURRENT_PRICE": price,
            "OLD_PRICE": old_price,
            "DISCOUNT": discount,
            "STOCK_STATUS": stock,
            "PRODUCT_URL": purl,
            "IMAGE_URL": str(iurl)[:2000] if iurl else None,
        })

    branch_rows: list[dict] = []
    seen_b: set[str] = set()
    for loc in locations:
        bname = str(loc.get("branch_name") or loc.get("location_name") or "").strip()[:255]
        if not bname:
            continue
        bid = str(loc.get("location_id") or uuid5(NAMESPACE_DNS, f"{source_id}|{bname}"))
        if bid in seen_b:
            continue
        seen_b.add(bid)

        def _coord(v, lo, hi):
            try:
                f = float(v) if v is not None else None
            except (ValueError, TypeError):
                return None
            return f if f is not None and lo <= f <= hi else None

        def _txt(v, n):
            return str(v).strip()[:n] if v else None

        branch_rows.append({
            "BRANCH_ID": bid, "STORE": source_id, "BRANCH_NAME": bname,
            "GOVERNORATE": _txt(loc.get("governorate"), 255),
            "CITY": _txt(loc.get("city"), 255),
            "ADDRESS": _txt(loc.get("address") or loc.get("delivery_zone"), 2000),
            "PHONE": _txt(loc.get("phone"), 255),
            "LATITUDE": _coord(loc.get("latitude"), 21.5, 32.5),
            "LONGITUDE": _coord(loc.get("longitude"), 24.0, 37.5),
            "LAST_CHECKED_AT": now,
        })
    return product_rows, branch_rows, rejected


# ─────────────────────────────────────────────────────────────────────────────
# CDC apply
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CDCResult:
    store: str
    scraped: int = 0
    unchanged: int = 0
    inserted: int = 0
    updated: int = 0
    changed_rows: list[dict] = field(default_factory=list)  # rows destined for bronze market_changes

    @property
    def changed(self) -> int:
        return self.inserted + self.updated


_PRODUCT_COLS = [
    "STORE", "PRODUCT_ID", "PRODUCT_NAME", "CATEGORY", "BRAND", "CURRENT_PRICE",
    "OLD_PRICE", "DISCOUNT", "STOCK_STATUS", "PRODUCT_URL", "IMAGE_URL", "STATE_HASH",
]


def apply_cdc(
    conn: duckdb.DuckDBPyConnection,
    store: str,
    product_rows: list[dict],
    run_id: str,
    now: datetime,
) -> CDCResult:
    """Compare incoming rows with stored state and apply INSERT/UPDATE/no-op."""
    res = CDCResult(store=store, scraped=len(product_rows))
    if not product_rows:
        return res

    existing: dict[str, str] = dict(conn.execute(
        "SELECT PRODUCT_ID, STATE_HASH FROM live_market.PRODUCTS WHERE STORE = ?", [store]
    ).fetchall())

    unchanged_ids: list[str] = []
    new_rows: list[dict] = []
    upd_rows: list[dict] = []
    for r in product_rows:
        r["STATE_HASH"] = compute_state_hash(
            r["PRODUCT_ID"], r["CURRENT_PRICE"], r["OLD_PRICE"], r["DISCOUNT"], r["STOCK_STATUS"]
        )
        prev = existing.get(r["PRODUCT_ID"])
        if prev is None:
            r["CHANGE_TYPE"] = "INSERT"
            new_rows.append(r)
        elif prev != r["STATE_HASH"]:
            r["CHANGE_TYPE"] = "UPDATE"
            upd_rows.append(r)
        else:
            unchanged_ids.append(r["PRODUCT_ID"])

    res.unchanged, res.inserted, res.updated = len(unchanged_ids), len(new_rows), len(upd_rows)

    conn.execute("BEGIN TRANSACTION")
    try:
        if unchanged_ids:
            conn.register("cdc_unchanged", pd.DataFrame({"pid": unchanged_ids}))
            conn.execute(
                "UPDATE live_market.PRODUCTS SET LAST_CHECKED_AT = ? "
                "WHERE STORE = ? AND PRODUCT_ID IN (SELECT pid FROM cdc_unchanged)",
                [now, store],
            )
            conn.unregister("cdc_unchanged")

        if upd_rows:
            conn.register("cdc_upd", pd.DataFrame(upd_rows)[_PRODUCT_COLS])
            conn.execute(
                """UPDATE live_market.PRODUCTS AS p SET
                       PRODUCT_NAME = u.PRODUCT_NAME, CATEGORY = u.CATEGORY, BRAND = u.BRAND,
                       CURRENT_PRICE = CAST(u.CURRENT_PRICE AS DOUBLE),
                       OLD_PRICE = CAST(u.OLD_PRICE AS DOUBLE),
                       DISCOUNT = CAST(u.DISCOUNT AS DOUBLE),
                       STOCK_STATUS = u.STOCK_STATUS, PRODUCT_URL = u.PRODUCT_URL,
                       IMAGE_URL = u.IMAGE_URL, STATE_HASH = u.STATE_HASH,
                       LAST_UPDATED_AT = ?, LAST_CHECKED_AT = ?
                   FROM cdc_upd u WHERE p.STORE = u.STORE AND p.PRODUCT_ID = u.PRODUCT_ID""",
                [now, now],
            )
            conn.unregister("cdc_upd")

        if new_rows:
            conn.register("cdc_new", pd.DataFrame(new_rows)[_PRODUCT_COLS])
            conn.execute(
                """INSERT INTO live_market.PRODUCTS
                   SELECT STORE, PRODUCT_ID, PRODUCT_NAME, CATEGORY, BRAND,
                          CAST(CURRENT_PRICE AS DOUBLE), CAST(OLD_PRICE AS DOUBLE),
                          CAST(DISCOUNT AS DOUBLE), STOCK_STATUS, PRODUCT_URL, IMAGE_URL,
                          STATE_HASH, ?, ?, ?
                   FROM cdc_new""",
                [now, now, now],
            )
            conn.unregister("cdc_new")

        changed = new_rows + upd_rows
        if changed:
            snap_rows = [
                (
                    str(uuid5(NAMESPACE_DNS, f"{r['PRODUCT_ID']}|{r['STATE_HASH']}|{now.isoformat()}")),
                    now.date(), store, r["PRODUCT_ID"], r["CURRENT_PRICE"], r["OLD_PRICE"],
                    r["DISCOUNT"], r["STOCK_STATUS"], r["STATE_HASH"], r["CHANGE_TYPE"], now, run_id,
                )
                for r in changed
            ]
            conn.executemany(
                "INSERT INTO live_market.PRICE_HISTORY VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", snap_rows
            )
            for r, snap in zip(changed, snap_rows):
                res.changed_rows.append({
                    "SNAPSHOT_ID": snap[0], "COLLECTED_DATE": snap[1], "STORE": store,
                    "PRODUCT_ID": r["PRODUCT_ID"], "PRODUCT_NAME": r["PRODUCT_NAME"],
                    "CATEGORY": r["CATEGORY"], "BRAND": r["BRAND"],
                    "PRICE": r["CURRENT_PRICE"], "OLD_PRICE": r["OLD_PRICE"],
                    "DISCOUNT": r["DISCOUNT"], "STOCK_STATUS": r["STOCK_STATUS"],
                    "PRODUCT_URL": r["PRODUCT_URL"], "IMAGE_URL": r["IMAGE_URL"],
                    "STATE_HASH": r["STATE_HASH"], "CHANGE_TYPE": r["CHANGE_TYPE"],
                    "COLLECTED_AT": now, "RUN_ID": run_id,
                })
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return res


def replace_branches(
    conn: duckdb.DuckDBPyConnection, store: str, branch_rows: list[dict]
) -> int:
    """Refresh a store's branch list (small dimension; full replace per store)."""
    if not branch_rows:
        return 0
    cols = ["BRANCH_ID", "STORE", "BRANCH_NAME", "GOVERNORATE", "CITY", "ADDRESS",
            "PHONE", "LATITUDE", "LONGITUDE", "LAST_CHECKED_AT"]
    conn.execute("BEGIN TRANSACTION")
    try:
        conn.execute("DELETE FROM live_market.BRANCHES WHERE STORE = ?", [store])
        conn.executemany(
            f"INSERT INTO live_market.BRANCHES VALUES ({','.join(['?'] * len(cols))})",
            [tuple(r[c] for c in cols) for r in branch_rows],
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return len(branch_rows)


def insert_run_log(
    conn: duckdb.DuckDBPyConnection, run_id: str, store: str, mode: str,
    res: CDCResult, duration: float, started_at: datetime, finished_at: datetime,
) -> dict:
    row = {
        "RUN_ID": run_id, "STORE": store, "RUN_MODE": mode, "RUN_DATE": started_at.date(),
        "PRODUCTS_COLLECTED": res.scraped, "SNAPSHOTS_WRITTEN": res.changed,
        "PRODUCTS_UNCHANGED": res.unchanged, "DURATION_SECONDS": round(duration, 2),
        "STARTED_AT": started_at, "FINISHED_AT": finished_at,
    }
    conn.execute("INSERT INTO live_market.RUN_LOGS VALUES (?,?,?,?,?,?,?,?,?,?)", list(row.values()))
    return row
