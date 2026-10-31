"""
Direct Databricks Lakehouse Ingestion Client for Egypt E-Commerce Platform.
==========================================================================
Handles direct, high-throughput batch ingestion of scraped data
straight into Databricks Delta Lake clean tables (5 clean tables):
  1. PRODUCTS
  2. PRICE_HISTORY
  3. STORES
  4. BRANCHES
  5. RUN_LOGS
"""

from __future__ import annotations

import base64
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import NAMESPACE_DNS, uuid4, uuid5

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from normalization.normalizers import (
    normalize_availability_status,
    normalize_image_url,
    normalize_stock_status,
)
from normalization.taxonomy import classify_product

DEFAULT_STORES = [
    {
        "store_id": "jumia",
        "store_name": "Jumia Egypt",
        "domain": "jumia.com.eg",
        "official_url": "https://www.jumia.com.eg",
        "business_type": "General Marketplace",
    },
    {
        "store_id": "two_b",
        "store_name": "2B Egypt",
        "domain": "2b.com.eg",
        "official_url": "https://2b.com.eg",
        "business_type": "Electronics & Tech Retailer",
    },
    {
        "store_id": "carrefour",
        "store_name": "Carrefour Egypt",
        "domain": "carrefouregypt.com",
        "official_url": "https://www.carrefouregypt.com",
        "business_type": "Hypermarket & Supermarket",
    },
    {
        "store_id": "tradeline",
        "store_name": "Tradeline",
        "domain": "tradeline-stores.com",
        "official_url": "https://tradeline-stores.com",
        "business_type": "Apple Authorised Reseller",
    },
    {
        "store_id": "dream2000",
        "store_name": "Dream 2000",
        "domain": "dream2000.com",
        "official_url": "https://dream2000.com",
        "business_type": "Mobile & Electronics Retailer",
    },
    {
        "store_id": "raya",
        "store_name": "Raya Shop",
        "domain": "rayashop.com",
        "official_url": "https://www.rayashop.com",
        "business_type": "Electronics & Home Appliances Retailer",
    },
]


def load_databricks_config(args: Optional[Any] = None) -> dict[str, str]:
    """Load Databricks connection settings from .env, environment, or args."""
    load_dotenv(PROJECT_ROOT / ".env")
    raw_host = (
        getattr(args, "host", None)
        or os.getenv("DATABRICKS_HOST", "")
    ).strip()

    # Normalize host name for server_hostname
    server_hostname = raw_host
    if "://" in server_hostname:
        server_hostname = server_hostname.split("://", 1)[1]
    server_hostname = server_hostname.rstrip("/")

    return {
        "raw_host": raw_host,
        "server_hostname": server_hostname,
        "http_path": (
            getattr(args, "http_path", None)
            or os.getenv("DATABRICKS_HTTP_PATH", "")
        ).strip(),
        "username": (
            getattr(args, "username", None)
            or os.getenv("DATABRICKS_USERNAME", "by234DEPI")
        ).strip(),
        "password": (
            getattr(args, "password", None)
            or os.getenv("DATABRICKS_PASSWORD", "DEPI@234")
        ).strip(),
        "token": (
            getattr(args, "token", None)
            or os.getenv("DATABRICKS_TOKEN", "")
        ).strip(),
        "catalog": (
            getattr(args, "catalog", None)
            or os.getenv("DATABRICKS_CATALOG", "hive_metastore")
        ).strip(),
        "schema": (
            getattr(args, "schema", None)
            or os.getenv("DATABRICKS_SCHEMA", "live_market")
        ).strip(),
    }


def is_databricks_configured(cfg: Optional[dict[str, str]] = None) -> bool:
    """Return True if Databricks host and valid credentials exist."""
    cfg = cfg or load_databricks_config()
    placeholders = {
        "",
        "your_host",
        "your_workspace_url",
        "<databricks_host>",
        "your_http_path",
        "<databricks_http_path>",
        "none",
    }
    has_host = bool(cfg.get("server_hostname")) and cfg["server_hostname"].lower() not in placeholders
    has_http_path = bool(cfg.get("http_path")) and cfg["http_path"].lower() not in placeholders
    has_token = bool(cfg.get("token")) and cfg["token"].lower() not in placeholders
    has_user_pass = bool(cfg.get("username")) and bool(cfg.get("password"))
    return has_host and (has_token or has_user_pass)


def get_databricks_connection(cfg: Optional[dict[str, str]] = None):
    """Establish DB-API connection to Databricks Lakehouse."""
    from databricks import sql

    cfg = cfg or load_databricks_config()
    if not is_databricks_configured(cfg):
        raise RuntimeError(
            "Databricks is not configured in .env. "
            "Please provide DATABRICKS_HOST, DATABRICKS_HTTP_PATH, and credentials (DATABRICKS_TOKEN or DATABRICKS_USERNAME/DATABRICKS_PASSWORD)."
        )

    server_hostname = cfg["server_hostname"]
    http_path = cfg["http_path"]
    token = cfg.get("token")
    username = cfg.get("username")
    password = cfg.get("password")
    catalog = cfg.get("catalog") or None
    schema = cfg.get("schema") or None

    conn_kwargs: dict[str, Any] = {
        "server_hostname": server_hostname,
        "http_path": http_path,
        "_socket_timeout": 30,
        "_retry_stop_after_attempts_count": 20,
        "_retry_stop_after_attempts_duration": 60,
    }
    if catalog:
        conn_kwargs["catalog"] = catalog
    if schema:
        conn_kwargs["schema"] = schema

    if token:
        conn_kwargs["access_token"] = token
    elif username and password:
        # Standard HTTP Basic Auth header provider for Databricks endpoint
        def basic_credentials_provider():
            creds = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("utf-8")
            return lambda: {"Authorization": f"Basic {creds}"}

        conn_kwargs["credentials_provider"] = basic_credentials_provider
    else:
        # If no credentials provided, default token to empty to prevent interactive OAuth browser popup
        conn_kwargs["access_token"] = ""

    return sql.connect(**conn_kwargs)


def test_databricks_connection(cfg: Optional[dict[str, str]] = None) -> tuple[bool, str]:
    """Test connectivity to Databricks endpoint and verify basic query."""
    cfg = cfg or load_databricks_config()
    if not is_databricks_configured(cfg):
        missing = []
        if not cfg.get("server_hostname"):
            missing.append("DATABRICKS_HOST")
        if not cfg.get("http_path"):
            missing.append("DATABRICKS_HTTP_PATH")
        if not cfg.get("token") and not (cfg.get("username") and cfg.get("password")):
            missing.append("DATABRICKS_TOKEN or DATABRICKS_USERNAME/DATABRICKS_PASSWORD")
        return False, f"Missing Databricks configuration: {', '.join(missing)}"

    try:
        conn = get_databricks_connection(cfg)
        with conn.cursor() as cur:
            cur.execute("SELECT 1 AS status")
            row = cur.fetchone()
            if row and row[0] == 1:
                return True, "Successfully connected to Databricks and executed test query."
        conn.close()
        return True, "Connection successful."
    except Exception as exc:
        return False, f"Connection failed: {str(exc)}"


def ensure_databricks_schema(conn=None) -> None:
    """Apply DDL to ensure the 5 clean Delta tables exist and seed default stores."""
    close_after = False
    cfg = load_databricks_config()
    if conn is None:
        conn = get_databricks_connection(cfg)
        close_after = True

    schema_sql_path = PROJECT_ROOT / "dwh" / "databricks_schema.sql"
    if not schema_sql_path.exists():
        return

    cur = conn.cursor()
    try:
        sql_content = schema_sql_path.read_text(encoding="utf-8")
        for stmt in sql_content.split(";"):
            stmt = stmt.strip()
            if stmt:
                cur.execute(stmt)
        seed_stores(cur)
    finally:
        cur.close()
        if close_after:
            conn.close()


def _sql_lit(val: Any) -> str:
    """Safely format a Python value as a Spark SQL literal for vectorized batch statements."""
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    if isinstance(val, (int, float)):
        import math
        if math.isnan(val) or math.isinf(val):
            return "NULL"
        return str(val)
    s = str(val).replace("\x00", "").replace("\\", "\\\\").replace("'", "''")
    return f"'{s}'"


def seed_stores(cur) -> None:
    """Vectorized upsert of default retailers into STORES Delta table."""
    values_clauses = []
    for s in DEFAULT_STORES:
        values_clauses.append(
            f"({_sql_lit(s['store_id'])}, {_sql_lit(s['store_name'])}, "
            f"{_sql_lit(s['domain'])}, {_sql_lit(s['official_url'])}, {_sql_lit(s['business_type'])})"
        )
    values_sql = ",\n            ".join(values_clauses)
    cur.execute(
        f"""
        MERGE INTO STORES t
        USING (
            SELECT * FROM VALUES
            {values_sql}
            AS s(STORE_ID, STORE_NAME, DOMAIN, OFFICIAL_URL, BUSINESS_TYPE)
        ) s
        ON t.STORE_ID = s.STORE_ID
        WHEN MATCHED THEN UPDATE SET
            t.STORE_NAME = s.STORE_NAME,
            t.DOMAIN = s.DOMAIN,
            t.OFFICIAL_URL = s.OFFICIAL_URL,
            t.BUSINESS_TYPE = s.BUSINESS_TYPE
        WHEN NOT MATCHED THEN INSERT (STORE_ID, STORE_NAME, DOMAIN, OFFICIAL_URL, BUSINESS_TYPE)
            VALUES (s.STORE_ID, s.STORE_NAME, s.DOMAIN, s.OFFICIAL_URL, s.BUSINESS_TYPE)
        """
    )


def ingest_direct_to_databricks(
    source_id: str,
    products: list[dict],
    observations: list[dict],
    locations: Optional[list[dict]] = None,
    run_meta: Optional[dict] = None,
    conn=None,
    batch_size: int = 1000,
) -> dict[str, int]:
    """
    Directly ingest scraped products, observations, branches and run logs into Databricks.
    Enforces strict deduplication and critical-NULL quality gate before executing
    vectorized multi-row batch MERGE statements (chunks of 1,000 rows).
    """
    locations = locations or []
    run_meta = run_meta or {}
    close_after = False

    if conn is None:
        conn = get_databricks_connection()
        close_after = True

    cur = conn.cursor()
    stats = {"products": 0, "price_history": 0, "branches": 0, "run_logs": 0}

    try:
        # Ensure STORES dimension is seeded
        seed_stores(cur)

        now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        today = date.today().isoformat()
        run_id = run_meta.get("run_id") or f"{source_id}_{today}_{str(uuid4())[:8]}"

        # ── 1. Deduplicate & Map Observations by (source_id, product_id, collected_date) ──
        obs_map: dict[str, dict] = {}
        deduped_obs_by_pid: dict[str, dict] = {}
        for o in observations:
            spid = str(o.get("source_product_id") or "").strip()
            pid = str(o.get("product_id") or "").strip()
            if not spid and ":" in pid:
                spid = pid.split(":", 1)[1]
            canonical_pid = f"{source_id}:{spid}" if spid else pid
            if not canonical_pid:
                continue

            raw_price = o.get("price")
            try:
                price_val = float(raw_price) if raw_price is not None else None
            except (ValueError, TypeError):
                price_val = None

            raw_price_text = str(o.get("raw_price_text") or "").lower()
            is_call_for_price = "call for price" in raw_price_text
            if (price_val is None or price_val <= 0) and not is_call_for_price:
                continue

            stock = normalize_stock_status(o.get("stock_status"), o.get("availability_status"))
            if not stock or stock == "UNKNOWN":
                continue

            obs_clean = dict(o)
            obs_clean["price"] = price_val
            obs_clean["stock_status"] = stock
            obs_clean["canonical_pid"] = canonical_pid

            deduped_obs_by_pid[canonical_pid] = obs_clean
            obs_map[canonical_pid] = obs_clean
            if spid:
                obs_map[spid] = obs_clean
            if pid:
                obs_map[pid] = obs_clean

        # ── 2. Validate & Deduplicate PRODUCTS by (source_id, product_id) ─────────
        product_rows = []
        valid_canonical_pids: set[str] = set()
        seen_product_keys: set[tuple[str, str]] = set()
        rejected_nulls = 0

        for p in products:
            spid = str(p.get("source_product_id") or "").strip()
            rpid = str(p.get("product_id") or "").strip()
            if not spid and ":" in rpid:
                spid = rpid.split(":", 1)[1]
            canonical_pid = f"{source_id}:{spid}" if spid else rpid

            dedup_key = (source_id, canonical_pid)
            if not canonical_pid or dedup_key in seen_product_keys:
                continue

            o = obs_map.get(canonical_pid) or obs_map.get(spid) or obs_map.get(rpid) or {}

            pname = str(p.get("product_name") or "").strip()[:2000]
            purl = str(p.get("product_url") or "").strip()[:2000] if p.get("product_url") else None
            price = float(o.get("price")) if o.get("price") is not None else None
            raw_price_text = str(o.get("raw_price_text") or "").lower()
            is_call_for_price = "call for price" in raw_price_text
            stock = normalize_stock_status(o.get("stock_status"), o.get("availability_status"))

            # HARD STOP ON CRITICAL NULLS:
            # Reject if CURRENT_PRICE is NULL (unless Call for Price), or if PRODUCT_ID,
            # PRODUCT_NAME, STORE, PRODUCT_URL, or STOCK_STATUS is NULL or 'UNKNOWN'
            if (
                not source_id
                or not canonical_pid
                or not pname
                or pname == "Unknown Product"
                or not purl
                or ((price is None or price <= 0) and not is_call_for_price)
                or not stock
                or stock == "UNKNOWN"
            ):
                rejected_nulls += 1
                continue

            seen_product_keys.add(dedup_key)
            valid_canonical_pids.add(canonical_pid)

            brand = str(p.get("brand") or "").strip()[:255] if p.get("brand") else None
            raw_cat = str(p.get("category") or p.get("raw_category_path") or "").strip()[:500] if (p.get("category") or p.get("raw_category_path")) else None

            if not raw_cat or raw_cat == "Uncategorized":
                tax = classify_product(pname, brand, raw_cat)
                category = tax.get("category") or raw_cat or "General"
            else:
                category = raw_cat

            old_price = float(o.get("old_price")) if o.get("old_price") is not None else None
            if old_price is not None and price is not None and old_price <= price:
                old_price = None

            discount = float(o.get("discount")) if o.get("discount") is not None else None
            if discount is None and price and old_price and old_price > price:
                discount = round((1.0 - price / old_price) * 100.0, 1)
            elif old_price is None:
                discount = None

            iurl = normalize_image_url(p.get("image_url"))
            img_url = str(iurl)[:2000] if iurl else None
            last_updated = str(o.get("observed_at") or p.get("collected_at") or now_ts)[:19].replace("T", " ")

            product_rows.append((
                source_id,
                canonical_pid,
                pname,
                category,
                brand,
                price,
                old_price,
                discount,
                stock,
                purl,
                img_url,
                last_updated,
            ))

        if rejected_nulls > 0:
            print(f"    🛡️  Quality Gate rejected {rejected_nulls:,} invalid/NULL-price product records for {source_id}")

        if product_rows:
            for i in range(0, len(product_rows), batch_size):
                chunk = product_rows[i : i + batch_size]
                values_str = ",\n                    ".join(
                    f"({_sql_lit(r[0])}, {_sql_lit(r[1])}, {_sql_lit(r[2])}, {_sql_lit(r[3])}, "
                    f"{_sql_lit(r[4])}, CAST({_sql_lit(r[5])} AS DOUBLE), CAST({_sql_lit(r[6])} AS DOUBLE), "
                    f"CAST({_sql_lit(r[7])} AS DOUBLE), {_sql_lit(r[8])}, {_sql_lit(r[9])}, "
                    f"{_sql_lit(r[10])}, CAST({_sql_lit(r[11])} AS TIMESTAMP))"
                    for r in chunk
                )
                merge_product_sql = f"""
                MERGE INTO PRODUCTS t
                USING (
                    SELECT * FROM VALUES
                    {values_str}
                    AS s(STORE, PRODUCT_ID, PRODUCT_NAME, CATEGORY, BRAND,
                         CURRENT_PRICE, OLD_PRICE, DISCOUNT, STOCK_STATUS,
                         PRODUCT_URL, IMAGE_URL, LAST_UPDATED_AT)
                ) s
                ON t.STORE = s.STORE AND t.PRODUCT_ID = s.PRODUCT_ID
                WHEN MATCHED THEN UPDATE SET
                    t.PRODUCT_NAME = s.PRODUCT_NAME,
                    t.CATEGORY = s.CATEGORY,
                    t.BRAND = s.BRAND,
                    t.CURRENT_PRICE = s.CURRENT_PRICE,
                    t.OLD_PRICE = s.OLD_PRICE,
                    t.DISCOUNT = s.DISCOUNT,
                    t.STOCK_STATUS = s.STOCK_STATUS,
                    t.PRODUCT_URL = s.PRODUCT_URL,
                    t.IMAGE_URL = s.IMAGE_URL,
                    t.LAST_UPDATED_AT = s.LAST_UPDATED_AT
                WHEN NOT MATCHED THEN INSERT (
                    STORE, PRODUCT_ID, PRODUCT_NAME, CATEGORY, BRAND,
                    CURRENT_PRICE, OLD_PRICE, DISCOUNT, STOCK_STATUS,
                    PRODUCT_URL, IMAGE_URL, LAST_UPDATED_AT
                ) VALUES (
                    s.STORE, s.PRODUCT_ID, s.PRODUCT_NAME, s.CATEGORY, s.BRAND,
                    s.CURRENT_PRICE, s.OLD_PRICE, s.DISCOUNT, s.STOCK_STATUS,
                    s.PRODUCT_URL, s.IMAGE_URL, s.LAST_UPDATED_AT
                )
                """
                cur.execute(merge_product_sql)
            stats["products"] = len(product_rows)
            print(f"    🧱 Databricks PRODUCTS: {len(product_rows):,} rows vectorized-upserted")

        # ── 3. Vectorized Ingest PRICE_HISTORY (Deduplicated by store, product_id, collected_date) ──
        history_rows = []
        seen_obs_keys: set[tuple[str, str, str]] = set()
        for canonical_pid, o in deduped_obs_by_pid.items():
            if canonical_pid not in valid_canonical_pids:
                continue

            obs_date = str(o.get("observed_at") or o.get("collected_at") or today)[:10]
            if len(obs_date) != 10:
                obs_date = today

            dedup_obs_key = (source_id, canonical_pid, obs_date)
            if dedup_obs_key in seen_obs_keys:
                continue
            seen_obs_keys.add(dedup_obs_key)

            obs_id = str(uuid5(NAMESPACE_DNS, f"{source_id}|{canonical_pid}|{obs_date}"))
            price = float(o.get("price")) if o.get("price") is not None else None
            old_price = float(o.get("old_price")) if o.get("old_price") is not None else None
            if old_price is not None and price is not None and old_price <= price:
                old_price = None
            stock = o["stock_status"]
            collected_at = str(o.get("observed_at") or o.get("collected_at") or now_ts)[:19].replace("T", " ")

            history_rows.append((
                obs_id,
                obs_date,
                source_id,
                canonical_pid,
                price,
                old_price,
                stock,
                collected_at,
            ))

        if history_rows:
            for i in range(0, len(history_rows), batch_size):
                chunk = history_rows[i : i + batch_size]
                values_str = ",\n                    ".join(
                    f"({_sql_lit(r[0])}, CAST({_sql_lit(r[1])} AS DATE), {_sql_lit(r[2])}, {_sql_lit(r[3])}, "
                    f"CAST({_sql_lit(r[4])} AS DOUBLE), CAST({_sql_lit(r[5])} AS DOUBLE), "
                    f"{_sql_lit(r[6])}, CAST({_sql_lit(r[7])} AS TIMESTAMP))"
                    for r in chunk
                )
                merge_history_sql = f"""
                MERGE INTO PRICE_HISTORY t
                USING (
                    SELECT * FROM VALUES
                    {values_str}
                    AS s(OBSERVATION_ID, COLLECTED_DATE, STORE, PRODUCT_ID,
                         PRICE, OLD_PRICE, STOCK_STATUS, COLLECTED_AT)
                ) s
                ON t.STORE = s.STORE AND t.PRODUCT_ID = s.PRODUCT_ID AND t.COLLECTED_DATE = s.COLLECTED_DATE
                WHEN MATCHED THEN UPDATE SET
                    t.OBSERVATION_ID = s.OBSERVATION_ID,
                    t.PRICE = s.PRICE,
                    t.OLD_PRICE = s.OLD_PRICE,
                    t.STOCK_STATUS = s.STOCK_STATUS,
                    t.COLLECTED_AT = s.COLLECTED_AT
                WHEN NOT MATCHED THEN INSERT (
                    OBSERVATION_ID, COLLECTED_DATE, STORE, PRODUCT_ID,
                    PRICE, OLD_PRICE, STOCK_STATUS, COLLECTED_AT
                ) VALUES (
                    s.OBSERVATION_ID, s.COLLECTED_DATE, s.STORE, s.PRODUCT_ID,
                    s.PRICE, s.OLD_PRICE, s.STOCK_STATUS, s.COLLECTED_AT
                )
                """
                cur.execute(merge_history_sql)
            stats["price_history"] = len(history_rows)
            print(f"    🧱 Databricks PRICE_HISTORY: {len(history_rows):,} rows vectorized-upserted")

        # ── 4. Vectorized Ingest BRANCHES ─────────────────────────────────────────
        branch_rows = []
        seen_branches: set[tuple[str, str]] = set()
        for loc in locations:
            bname = str(loc.get("branch_name") or loc.get("location_name") or "").strip()[:255]
            if not bname:
                continue
            bid = str(loc.get("location_id") or uuid5(NAMESPACE_DNS, f"{source_id}|{bname}"))
            bkey = (source_id, bid)
            if bkey in seen_branches:
                continue
            seen_branches.add(bkey)

            lat = loc.get("latitude")
            lon = loc.get("longitude")
            try:
                lat_f = float(lat) if lat is not None else None
                lon_f = float(lon) if lon is not None else None
                if lat_f is not None and not (21.5 <= lat_f <= 32.5):
                    lat_f = None
                if lon_f is not None and not (24.0 <= lon_f <= 37.5):
                    lon_f = None
            except (ValueError, TypeError):
                lat_f, lon_f = None, None

            gov = str(loc.get("governorate") or "").strip()[:255] if loc.get("governorate") else None
            city = str(loc.get("city") or "").strip()[:255] if loc.get("city") else None
            addr = str(loc.get("address") or loc.get("delivery_zone") or "").strip()[:2000] if (loc.get("address") or loc.get("delivery_zone")) else None
            phone = str(loc.get("phone") or "").strip()[:255] if loc.get("phone") else None

            branch_rows.append((
                bid,
                source_id,
                bname,
                gov,
                city,
                addr,
                phone,
                lat_f,
                lon_f,
            ))

        if branch_rows:
            for i in range(0, len(branch_rows), batch_size):
                chunk = branch_rows[i : i + batch_size]
                values_str = ",\n                    ".join(
                    f"({_sql_lit(r[0])}, {_sql_lit(r[1])}, {_sql_lit(r[2])}, {_sql_lit(r[3])}, "
                    f"{_sql_lit(r[4])}, {_sql_lit(r[5])}, {_sql_lit(r[6])}, "
                    f"CAST({_sql_lit(r[7])} AS DOUBLE), CAST({_sql_lit(r[8])} AS DOUBLE))"
                    for r in chunk
                )
                merge_branch_sql = f"""
                MERGE INTO BRANCHES t
                USING (
                    SELECT * FROM VALUES
                    {values_str}
                    AS s(BRANCH_ID, STORE, BRANCH_NAME, GOVERNORATE,
                         CITY, ADDRESS, PHONE, LATITUDE, LONGITUDE)
                ) s
                ON t.STORE = s.STORE AND t.BRANCH_ID = s.BRANCH_ID
                WHEN MATCHED THEN UPDATE SET
                    t.BRANCH_NAME = s.BRANCH_NAME,
                    t.GOVERNORATE = s.GOVERNORATE,
                    t.CITY = s.CITY,
                    t.ADDRESS = s.ADDRESS,
                    t.PHONE = s.PHONE,
                    t.LATITUDE = s.LATITUDE,
                    t.LONGITUDE = s.LONGITUDE
                WHEN NOT MATCHED THEN INSERT (
                    BRANCH_ID, STORE, BRANCH_NAME, GOVERNORATE,
                    CITY, ADDRESS, PHONE, LATITUDE, LONGITUDE
                ) VALUES (
                    s.BRANCH_ID, s.STORE, s.BRANCH_NAME, s.GOVERNORATE,
                    s.CITY, s.ADDRESS, s.PHONE, s.LATITUDE, s.LONGITUDE
                )
                """
                cur.execute(merge_branch_sql)
            stats["branches"] = len(branch_rows)
            print(f"    🧱 Databricks BRANCHES: {len(branch_rows):,} rows vectorized-upserted")

        # ── 5. Ingest RUN_LOGS ─────────────────────────────────────────
        duration = float(run_meta.get("duration_seconds") or 0.0)
        started_at = str(run_meta.get("started_at") or now_ts)[:19].replace("T", " ")
        finished_at = str(run_meta.get("finished_at") or now_ts)[:19].replace("T", " ")
        cur.execute(
            f"""
            MERGE INTO RUN_LOGS t
            USING (
                SELECT
                    {_sql_lit(run_id)} AS RUN_ID,
                    {_sql_lit(source_id)} AS STORE,
                    CAST({_sql_lit(today)} AS DATE) AS RUN_DATE,
                    CAST({len(product_rows)} AS INT) AS PRODUCTS_COLLECTED,
                    CAST({len(history_rows)} AS INT) AS OBSERVATIONS_COLLECTED,
                    CAST({round(duration, 2)} AS DOUBLE) AS DURATION_SECONDS,
                    CAST({_sql_lit(started_at)} AS TIMESTAMP) AS STARTED_AT,
                    CAST({_sql_lit(finished_at)} AS TIMESTAMP) AS FINISHED_AT
            ) s
            ON t.RUN_ID = s.RUN_ID
            WHEN MATCHED THEN UPDATE SET
                t.PRODUCTS_COLLECTED = s.PRODUCTS_COLLECTED,
                t.OBSERVATIONS_COLLECTED = s.OBSERVATIONS_COLLECTED,
                t.DURATION_SECONDS = s.DURATION_SECONDS,
                t.FINISHED_AT = s.FINISHED_AT
            WHEN NOT MATCHED THEN INSERT (
                RUN_ID, STORE, RUN_DATE, PRODUCTS_COLLECTED,
                OBSERVATIONS_COLLECTED, DURATION_SECONDS, STARTED_AT, FINISHED_AT
            ) VALUES (
                s.RUN_ID, s.STORE, s.RUN_DATE, s.PRODUCTS_COLLECTED,
                s.OBSERVATIONS_COLLECTED, s.DURATION_SECONDS, s.STARTED_AT, s.FINISHED_AT
            )
            """
        )
        stats["run_logs"] = 1

    finally:
        cur.close()
        if close_after:
            conn.close()

    return stats


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Databricks connection and status utility")
    parser.add_argument("--test-connection", action="store_true", help="Test Databricks connection")
    parser.add_argument("--host", default=None, help="Databricks workspace host")
    parser.add_argument("--http-path", default=None, help="Databricks SQL warehouse / cluster HTTP path")
    parser.add_argument("--username", default=None, help="Databricks username")
    parser.add_argument("--password", default=None, help="Databricks password")
    parser.add_argument("--token", default=None, help="Databricks personal access token")
    args = parser.parse_args()

    cfg = load_databricks_config(args)
    ok, msg = test_databricks_connection(cfg)
    print(f"Databricks Status: {'SUCCESS' if ok else 'FAILED'}")
    print(f"Message: {msg}")
    sys.exit(0 if ok else 1)
