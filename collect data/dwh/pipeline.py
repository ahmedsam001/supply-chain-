#!/usr/bin/env python3
"""
Egypt E-Commerce Extraction/Validation Library + Legacy Star-Schema Loader
==========================================================================
NOTE: The active, local-first pipeline entrypoint is `dwh/run_pipeline.py`
(hash-based CDC into `dwh/retail_lakehouse_fresh.duckdb` + local Bronze Parquet).
This module remains the shared extraction / validation / quality-gate library
(`run_live_extraction`, `validate_source_bundle`, `enforce_strict_quality_gate`)
and the legacy star-schema loader kept for tests and ad-hoc analysis.
It has NO cloud/warehouse connectors.

Orchestrates data ingestion from configured retail sources, classifies every product
into its canonical department taxonomy, populates an analytical Star Schema in DuckDB,
and writes per-department JSON partitions.

Architectural Highlights:
    1. Dimensional Modeling (Star Schema):
       - Dimensions: `dim_department`, `dim_source`, `dim_product`, `dim_location`
       - Facts: `fact_observation` (price, availability, stock), `fact_quality_issue`
       - Audit: `run_manifest` (reconciliation, field coverage, validation scores)
    2. Canonical Taxonomy (14 Departments):
       - Mobiles & Tablets, Computing, Electronics & TVs, Home Appliances,
         Fresh Meats & Poultry, Dairy & Eggs, Fruits & Vegetables, Grocery & Pantry,
         Beverages, Bakery & Snacks, Frozen Foods, Household Cleaning, Beauty & Personal Care, Other.
       - Supported by 14 isolated department SQL views (`v_dept_<id>`).
    3. Idempotent Ingestion & Deduplication:
       - Products use deterministic canonical IDs (`<source_id>:<source_product_id>`).
       - Observations use deterministic UUID5 keys (`<product_id>|<run_date>|<seller_name>`),
         guaranteeing zero duplicate rows across multi-day or repeated same-day runs.
       - Quality issues use deterministic UUID5 hashes (`<run_id>|<issue_code>|<entity_id>|<field_name>`).
    4. Real-Time Dynamic Views:
       - `RAW_PRODUCTS_DATA`: Real-time view joining fact observations with product dimensions.

Usage:
    python dwh/pipeline.py                                    # offline fixture (all departments)
    python dwh/pipeline.py --live                             # live scraping (all departments)
    python dwh/pipeline.py --live --department mobiles        # live scraping: Mobiles & Tablets only
    python dwh/pipeline.py --live --department electronics    # live scraping: Electronics & TVs only
    python dwh/pipeline.py --live --department meats          # live scraping: Fresh Meats & Poultry only
    python dwh/pipeline.py --live --department grocery        # live scraping: Grocery & Pantry only
    python dwh/pipeline.py --list-departments                 # list all 14 departments & SQL views
    python dwh/pipeline.py --query                            # print DWH & department summary
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import NAMESPACE_DNS, uuid4, uuid5

import duckdb

# ── Project root on sys.path ──────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from normalization.normalizers import (
    normalize_availability_status,
    normalize_image_url,
    normalize_stock_status,
)
from normalization.taxonomy import (
    DEPARTMENT_CATALOG,
    classify_product,
    resolve_department_alias,
)

DEFAULT_DB = PROJECT_ROOT / "dwh" / "egypt_ecommerce.duckdb"
SCHEMA_SQL = PROJECT_ROOT / "dwh" / "schema.sql"

SOURCES = ["jumia", "two_b", "carrefour", "tradeline", "dream2000", "raya"]


# ═══════════════════════════════════════════════════════════════════════════════
# DB Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def get_db(db_path: Path) -> duckdb.DuckDBPyConnection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db_path))
    try:
        os.chmod(db_path, 0o666)
    except OSError:
        pass
    _apply_schema(conn)
    _seed_departments(conn)
    return conn


def _apply_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create tables and department views if they don't exist."""
    for tbl in ("dim_product", "fact_observation"):
        try:
            conn.execute(f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS department TEXT")
        except Exception:
            pass

    sql = SCHEMA_SQL.read_text()
    statements = [s.strip() for s in sql.split(";") if s.strip()]
    for stmt in statements:
        try:
            conn.execute(stmt)
        except Exception:
            pass


def _seed_departments(conn: duckdb.DuckDBPyConnection) -> None:
    """Populate dim_department with all canonical departments."""
    for dept_id, meta in DEPARTMENT_CATALOG.items():
        conn.execute("""
            INSERT INTO dim_department (department_id, name_en, name_ar, sector, view_name)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (department_id) DO UPDATE SET
                name_en   = excluded.name_en,
                name_ar   = excluded.name_ar,
                sector    = excluded.sector,
                view_name = excluded.view_name
        """, [
            dept_id,
            meta["name_en"],
            meta["name_ar"],
            meta["sector"],
            meta["view_name"],
        ])


def _ensure_product_department(p: dict) -> str:
    tax = classify_product(
        product_name=p.get("product_name"),
        category=p.get("category"),
        subcategory=p.get("subcategory"),
        raw_category_path=p.get("raw_category_path"),
    )
    dept = tax["department"]
    p["department"] = dept
    if not p.get("category") or p.get("category") == "Uncategorized":
        p["category"] = tax["category"]
    if not p.get("subcategory"):
        p["subcategory"] = tax["subcategory"]
    return dept


def upsert_source(conn, source_id: str, meta: dict) -> None:
    from dwh.cdc_snapshot import DEFAULT_STORES
    store_defaults = {s["store_id"]: s for s in DEFAULT_STORES}.get(source_id, {})
    conn.execute("""
        INSERT INTO dim_source (source_id, source_name, domain, business_type, collection_mode)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (source_id) DO UPDATE SET
            source_name     = excluded.source_name,
            domain          = excluded.domain,
            business_type   = excluded.business_type,
            collection_mode = excluded.collection_mode
    """, [
        source_id,
        meta.get("source_name") or store_defaults.get("store_name", source_id),
        meta.get("domain") or store_defaults.get("domain", ""),
        meta.get("business_type") or store_defaults.get("business_type", ""),
        meta.get("mode", "live"),
    ])


def upsert_products(
    conn, products: list, source_id: str, now_ts: str
) -> tuple[dict[str, str], dict[str, str]]:
    """
    Upsert products into dim_product using a deterministic product_id
    (`{source_id}:{source_product_id}`) so multi-day runs update the same
    dimension row rather than duplicating products.

    Returns (prod_dept_map, pid_lookup_map).
    """
    prod_dept_map: dict[str, str] = {}
    pid_lookup: dict[str, str] = {}
    for p in products:
        raw_pid = p.get("product_id")
        spid = p.get("source_product_id")
        canonical_pid = f"{source_id}:{spid}" if spid else (raw_pid or str(uuid4()))
        p["product_id"] = canonical_pid

        dept = _ensure_product_department(p)
        prod_dept_map[canonical_pid] = dept
        if raw_pid:
            prod_dept_map[str(raw_pid)] = dept
            pid_lookup[str(raw_pid)] = canonical_pid
        if spid:
            prod_dept_map[str(spid)] = dept
            pid_lookup[str(spid)] = canonical_pid
        pid_lookup[canonical_pid] = canonical_pid

        img_url = normalize_image_url(p.get("image_url"))

        conn.execute("""
            INSERT INTO dim_product
                (product_id, source_id, source_product_id, department, product_name, brand,
                 category, subcategory, sku, gtin, product_url, image_url,
                 first_seen_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (product_id) DO UPDATE SET
                last_seen_at  = excluded.last_seen_at,
                department    = excluded.department,
                brand         = COALESCE(excluded.brand, dim_product.brand),
                category      = COALESCE(excluded.category, dim_product.category),
                subcategory   = COALESCE(excluded.subcategory, dim_product.subcategory),
                sku           = COALESCE(excluded.sku, dim_product.sku),
                gtin          = COALESCE(excluded.gtin, dim_product.gtin),
                product_url   = COALESCE(excluded.product_url, dim_product.product_url),
                image_url     = COALESCE(excluded.image_url, dim_product.image_url)
        """, [
            canonical_pid,
            source_id,
            spid,
            dept,
            p.get("product_name", ""),
            p.get("brand"),
            p.get("category"),
            p.get("subcategory"),
            p.get("sku"),
            p.get("gtin"),
            p.get("product_url"),
            img_url,
            p.get("collected_at") or now_ts,
            now_ts,
        ])
    return prod_dept_map, pid_lookup


def upsert_locations(conn, locations: list, source_id: str, now_ts: str) -> None:
    seen_loc_ids: set[str] = set()
    for loc in locations:
        bname = str(loc.get("branch_name") or loc.get("location_name") or "").strip()
        if not bname:
            continue
        loc_id = str(loc.get("location_id") or uuid5(NAMESPACE_DNS, f"{source_id}|{bname}"))
        if loc_id in seen_loc_ids:
            continue
        seen_loc_ids.add(loc_id)

        lat = loc.get("latitude")
        lon = loc.get("longitude")
        # Validate Egypt bounding box: 21.5 <= lat <= 32.5, 24.0 <= lon <= 37.5
        if lat is not None and lon is not None:
            try:
                lat_f = float(lat)
                lon_f = float(lon)
                if 21.5 <= lat_f <= 32.5 and 24.0 <= lon_f <= 37.5:
                    lat = lat_f
                    lon = lon_f
                else:
                    lat = None
                    lon = None
            except (ValueError, TypeError):
                lat = None
                lon = None
        else:
            lat = None
            lon = None

        conn.execute("""
            INSERT INTO dim_location
                (location_id, source_id, location_type, location_name, branch_name,
                 address, city, governorate, latitude, longitude, phone,
                 working_hours, first_seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (location_id) DO UPDATE SET
                branch_name = excluded.branch_name,
                location_name = excluded.location_name,
                latitude = excluded.latitude,
                longitude = excluded.longitude,
                address = COALESCE(excluded.address, dim_location.address),
                phone = COALESCE(excluded.phone, dim_location.phone),
                working_hours = COALESCE(excluded.working_hours, dim_location.working_hours)
        """, [
            loc_id,
            source_id,
            loc.get("location_type") or "store",
            loc.get("location_name") or bname,
            bname,
            loc.get("address") or loc.get("delivery_zone"),
            loc.get("city"),
            loc.get("governorate"),
            lat,
            lon,
            loc.get("phone"),
            loc.get("working_hours"),
            now_ts,
        ])


def insert_observations(
    conn,
    observations: list,
    source_id: str,
    run_id: str,
    run_date: str,
    mode: str,
    quality_score: float,
    prod_dept_map: Optional[dict[str, str]] = None,
    pid_lookup: Optional[dict[str, str]] = None,
) -> None:
    prod_dept_map = prod_dept_map or {}
    pid_lookup = pid_lookup or {}

    # Strict deduplication by (source_id, product_id, collected_date)
    deduped_observations: dict[str, dict] = {}
    for obs in observations:
        raw_pid = str(obs.get("product_id") or "")
        spid = str(obs.get("source_product_id") or "")
        canonical_pid = (
            pid_lookup.get(raw_pid)
            or pid_lookup.get(spid)
            or (f"{source_id}:{spid}" if spid else raw_pid)
        )
        obs["product_id"] = canonical_pid
        obs_date = str(obs.get("observed_at") or obs.get("collected_at") or run_date)[:10]
        if len(obs_date) != 10:
            obs_date = run_date

        # Deterministic observation ID by (source_id, canonical_pid, obs_date)
        obs_key = f"{source_id}|{canonical_pid}|{obs_date}"
        obs_id = str(uuid5(NAMESPACE_DNS, obs_key))
        obs["observation_id"] = obs_id
        deduped_observations[obs_id] = obs

    for obs_id, obs in deduped_observations.items():
        canonical_pid = obs["product_id"]
        raw_pid = str(obs.get("product_id") or "")
        spid = str(obs.get("source_product_id") or "")
        dept = (
            prod_dept_map.get(canonical_pid)
            or prod_dept_map.get(raw_pid)
            or prod_dept_map.get(spid)
            or obs.get("department")
            or "other"
        )
        obs["department"] = dept

        # Normalize stock status & availability status to canonical enums
        clean_stock = normalize_stock_status(obs.get("stock_status"), obs.get("availability_status"))
        clean_avail = normalize_availability_status(obs.get("availability_status"), clean_stock)

        conn.execute("""
            INSERT INTO fact_observation
                (observation_id, product_id, source_id, source_product_id, department,
                 run_date, run_id, observed_at, collection_mode,
                 price, old_price, discount, currency, raw_price_text,
                 availability_status, availability_scope, stock_status,
                 raw_availability_text, delivery_available, delivery_eta,
                 delivery_fee, delivery_status, seller_name,
                 fulfillment_method, quality_score, row_hash)
            VALUES (?, ?, ?, ?, ?,  ?, ?, ?, ?,  ?, ?, ?, ?, ?,
                    ?, ?, ?,  ?, ?, ?, ?, ?, ?,  ?, ?, ?)
            ON CONFLICT (observation_id) DO UPDATE SET
                product_id            = excluded.product_id,
                department            = excluded.department,
                observed_at           = excluded.observed_at,
                price                 = excluded.price,
                old_price             = excluded.old_price,
                discount              = excluded.discount,
                availability_status   = excluded.availability_status,
                availability_scope    = excluded.availability_scope,
                stock_status          = excluded.stock_status,
                raw_availability_text = excluded.raw_availability_text,
                delivery_available    = excluded.delivery_available,
                delivery_eta          = excluded.delivery_eta,
                delivery_fee          = excluded.delivery_fee,
                delivery_status       = excluded.delivery_status,
                seller_name           = excluded.seller_name,
                fulfillment_method    = excluded.fulfillment_method,
                quality_score         = excluded.quality_score,
                row_hash              = excluded.row_hash
        """, [
            obs_id,
            canonical_pid,
            source_id,
            obs.get("source_product_id") or (canonical_pid.split(":", 1)[1] if ":" in canonical_pid else None),
            dept,
            run_date,
            run_id,
            obs.get("observed_at") or obs.get("collected_at"),
            mode,
            obs.get("price"),
            obs.get("old_price"),
            obs.get("discount"),
            obs.get("currency", "EGP"),
            obs.get("raw_price_text"),
            clean_avail,
            obs.get("availability_scope"),
            clean_stock,
            obs.get("raw_availability_text"),
            obs.get("delivery_available"),
            obs.get("delivery_eta"),
            obs.get("delivery_fee"),
            obs.get("delivery_status"),
            obs.get("seller_name"),
            obs.get("fulfillment_method"),
            quality_score,
            obs.get("row_hash"),
        ])


def insert_quality_issues(conn, issues: list, run_id: str, run_date: str,
                           source_id: str) -> None:
    for qi in issues:
        conn.execute("""
            INSERT INTO fact_quality_issue
                (issue_id, run_date, run_id, source_id, entity_type,
                 entity_id, issue_code, severity, message, raw_value, detected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (issue_id) DO NOTHING
        """, [
            qi.get("issue_id") or str(uuid4()),
            run_date,
            run_id,
            source_id,
            qi.get("entity_type"),
            qi.get("entity_id"),
            qi.get("issue_code"),
            qi.get("severity"),
            qi.get("message"),
            qi.get("raw_value"),
            qi.get("detected_at"),
        ])


def insert_manifest(conn, run_id: str, run_date: str, source_id: str,
                    mode: str, counts: dict, quality_score: float,
                    duration: float, started_at: str, finished_at: str) -> None:
    conn.execute("""
        INSERT INTO run_manifest
            (run_id, run_date, source_id, collection_mode,
             products_count, observations_count, locations_count,
             quality_issues_count, quality_score, duration_seconds,
             errors_count, started_at, finished_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (run_id) DO NOTHING
    """, [
        run_id, run_date, source_id, mode,
        counts.get("products", 0),
        counts.get("observations", 0),
        counts.get("locations", 0),
        counts.get("quality_issues", 0),
        quality_score,
        round(duration, 2),
        counts.get("errors", 0),
        started_at, finished_at,
    ])


def save_department_partitions(
    products: list[dict],
    observations: list[dict],
    run_date: str,
) -> dict[str, int]:
    """
    Save products and observations into isolated folders per department:
        data/departments/<department>/<run_date>/products.json
        data/departments/<department>/<run_date>/observations.json
    """
    by_dept_prods: dict[str, list[dict]] = {}
    by_dept_obs: dict[str, list[dict]] = {}

    for p in products:
        dept = _ensure_product_department(p)
        by_dept_prods.setdefault(dept, []).append(p)

    for o in observations:
        dept = o.get("department") or "other"
        by_dept_obs.setdefault(dept, []).append(o)

    counts: dict[str, int] = {}
    base_dir = PROJECT_ROOT / "data" / "departments"

    for dept, dept_prods in by_dept_prods.items():
        dept_dir = base_dir / dept / run_date
        dept_dir.mkdir(parents=True, exist_ok=True)

        prods_path = dept_dir / "products.json"
        existing_prods: list[dict] = []
        if prods_path.exists():
            try:
                existing_prods = json.loads(prods_path.read_text(encoding="utf-8"))
            except Exception:
                existing_prods = []
        seen = {(x.get("source_id"), x.get("source_product_id")) for x in existing_prods}
        for dp in dept_prods:
            key = (dp.get("source_id"), dp.get("source_product_id"))
            if key not in seen:
                seen.add(key)
                existing_prods.append(dp)
        prods_path.write_text(json.dumps(existing_prods, indent=2, ensure_ascii=False), encoding="utf-8")

        obs_path = dept_dir / "observations.json"
        existing_obs: list[dict] = []
        if obs_path.exists():
            try:
                existing_obs = json.loads(obs_path.read_text(encoding="utf-8"))
            except Exception:
                existing_obs = []
        seen_obs = {x.get("observation_id") for x in existing_obs if x.get("observation_id")}
        for dobs in by_dept_obs.get(dept, []):
            oid = dobs.get("observation_id")
            if not oid or oid not in seen_obs:
                if oid:
                    seen_obs.add(oid)
                existing_obs.append(dobs)
        obs_path.write_text(json.dumps(existing_obs, indent=2, ensure_ascii=False), encoding="utf-8")

        counts[dept] = len(existing_prods)

    return counts


# ═══════════════════════════════════════════════════════════════════════════════
# Load & Merge All Website Data + Validate via Canonical Schema & DataValidator
# ═══════════════════════════════════════════════════════════════════════════════

def load_source_samples(source_id: str) -> dict:
    """Load the existing samples/<source>/ bundle from disk."""
    base = PROJECT_ROOT / "samples" / source_id
    result = {}
    for key in ("products", "observations", "locations", "quality_issues", "extraction_meta"):
        path = base / f"{key}.json"
        if path.exists():
            result[key] = json.loads(path.read_text(encoding="utf-8"))
        else:
            result[key] = [] if key != "extraction_meta" else {}
    return result


def load_all_source_data(
    source_id: str,
    live_data: Optional[dict] = None,
    include_raw_snapshots: bool = True,
) -> dict:
    """
    Collect and merge ALL data for a source across:
      1. All chronological snapshots in data/raw/<source_id>/*/
      2. Golden sample bundles in samples/<source_id>/
      3. Fresh extraction output in `live_data`
    Deduplicates products by source_product_id while preserving all raw_product_id -> source_product_id
    foreign-key mappings so every observation links cleanly to its canonical product.
    """
    bundles: list[dict] = []
    if include_raw_snapshots:
        raw_root = PROJECT_ROOT / "data" / "raw" / source_id
        if raw_root.exists():
            for date_dir in sorted([d for d in raw_root.iterdir() if d.is_dir()]):
                b: dict = {}
                for key in ("products", "observations", "locations", "quality_issues", "extraction_meta"):
                    f = date_dir / f"{key}.json"
                    if f.exists():
                        try:
                            b[key] = json.loads(f.read_text(encoding="utf-8"))
                        except Exception:
                            b[key] = [] if key != "extraction_meta" else {}
                    else:
                        b[key] = [] if key != "extraction_meta" else {}
                bundles.append(b)
        bundles.append(load_source_samples(source_id))

    if live_data:
        bundles.append(live_data)

    prods_by_spid: dict[str, dict] = {}
    raw_pid_to_spid: dict[str, str] = {}
    locs_by_key: dict[str, dict] = {}
    obs_by_id: dict[str, dict] = {}
    latest_meta: dict = {}

    for b in bundles:
        meta = b.get("extraction_meta") or {}
        if meta:
            latest_meta.update({k: v for k, v in meta.items() if v is not None})

        for p in b.get("products", []):
            spid = str(p.get("source_product_id") or p.get("product_id") or "")
            if not spid:
                continue
            rpid = str(p.get("product_id") or "")
            if rpid:
                raw_pid_to_spid[rpid] = spid
            raw_pid_to_spid[spid] = spid

            if spid not in prods_by_spid:
                prods_by_spid[spid] = dict(p)
            else:
                existing = prods_by_spid[spid]
                for k, v in p.items():
                    if v is not None and (existing.get(k) is None or k in ("product_name", "department", "collected_at")):
                        existing[k] = v

        for loc in b.get("locations", []):
            lkey = str(loc.get("branch_name") or loc.get("location_name") or loc.get("location_id") or uuid4())
            locs_by_key[lkey] = dict(loc)

        for obs in b.get("observations", []):
            ocopy = dict(obs)
            opid = str(ocopy.get("product_id") or "")
            ospid = str(ocopy.get("source_product_id") or "")
            resolved_spid = (
                ospid
                or raw_pid_to_spid.get(opid)
                or (opid.split(":", 1)[1] if ":" in opid else opid)
            )
            ocopy["source_product_id"] = resolved_spid
            ocopy["product_id"] = f"{source_id}:{resolved_spid}" if resolved_spid else opid
            oid = str(ocopy.get("observation_id") or f"{ocopy['product_id']}_{ocopy.get('row_hash')}")
            ocopy["observation_id"] = oid
            obs_by_id[oid] = ocopy

    return {
        "products": list(prods_by_spid.values()),
        "observations": list(obs_by_id.values()),
        "locations": list(locs_by_key.values()),
        "quality_issues": [],
        "extraction_meta": latest_meta,
    }


def validate_source_bundle(
    source_id: str,
    bundle: dict,
    run_id: str,
    mode: str,
) -> tuple[list[dict], list[dict], list[dict], list[dict], float]:
    """
    Validate all products, observations, and locations for a source using:
      1. Canonical Pydantic schema models (Product, ProductObservation, Location)
      2. Department taxonomy classification (classify_product)
      3. DataValidator().validate(ExtractionResult(...))
    Returns (valid_products, valid_observations, valid_locations, quality_issues, quality_score).
    """
    from normalization.schema import (
        AvailabilityScope,
        AvailabilityStatus,
        Currency,
        ExtractionResult,
        Location,
        LocationType,
        Product,
        ProductObservation,
    )
    from validation.data_validator import DataValidator

    valid_prods: list[Product] = []
    valid_obs: list[ProductObservation] = []
    valid_locs: list[Location] = []
    prod_dept_by_pid: dict[str, str] = {}

    for p in bundle.get("products", []):
        dept = _ensure_product_department(p)
        tax = classify_product(
            product_name=p.get("product_name"),
            category=p.get("category"),
            subcategory=p.get("subcategory"),
            raw_category_path=p.get("raw_category_path"),
        )
        if not p.get("category") or p.get("category") == "Uncategorized":
            p["category"] = tax["category"]
        if not p.get("subcategory"):
            p["subcategory"] = tax["subcategory"]
        spid = str(p.get("source_product_id") or p.get("product_id"))
        canonical_pid = f"{source_id}:{spid}"
        p["product_id"] = canonical_pid
        prod_dept_by_pid[canonical_pid] = dept
        prod_dept_by_pid[spid] = dept

        try:
            prod_obj = Product(
                product_id=canonical_pid,
                source_id=source_id,
                source_product_id=spid,
                sku=p.get("sku"),
                gtin=p.get("gtin"),
                product_name=p.get("product_name") or "Unknown Product",
                brand=p.get("brand"),
                category=p.get("category"),
                subcategory=p.get("subcategory"),
                raw_category_path=p.get("raw_category_path"),
                product_url=p.get("product_url") or f"https://{source_id}.eg/p/{spid}",
                source_url=p.get("source_url") or p.get("product_url") or f"https://{source_id}.eg/p/{spid}",
                image_url=p.get("image_url"),
                specifications=p.get("specifications"),
                variants=p.get("variants"),
                run_id=run_id,
            )
            valid_prods.append(prod_obj)
        except Exception:
            continue

    for loc in bundle.get("locations", []):
        try:
            ltype_raw = loc.get("location_type") or "store"
            try:
                ltype = LocationType(ltype_raw)
            except ValueError:
                ltype = LocationType.STORE
            loc_obj = Location(
                location_id=str(loc.get("location_id") or uuid4()),
                source_id=source_id,
                location_type=ltype,
                location_name=loc.get("location_name") or loc.get("branch_name"),
                branch_name=loc.get("branch_name"),
                raw_location_name=loc.get("raw_location_name") or loc.get("branch_name") or loc.get("location_name"),
                address=loc.get("address"),
                city=loc.get("city"),
                governorate=loc.get("governorate"),
                latitude=loc.get("latitude"),
                longitude=loc.get("longitude"),
                phone=loc.get("phone"),
                working_hours=loc.get("working_hours"),
                delivery_zone=loc.get("delivery_zone"),
                run_id=run_id,
            )
            valid_locs.append(loc_obj)
        except Exception:
            continue

    for obs in bundle.get("observations", []):
        spid = str(obs.get("source_product_id") or "")
        raw_pid = str(obs.get("product_id") or "")
        canonical_pid = f"{source_id}:{spid}" if spid else raw_pid
        if not spid and ":" in canonical_pid:
            spid = canonical_pid.split(":", 1)[1]
        try:
            avail_raw = obs.get("availability_status") or "unknown"
            try:
                avail_status = AvailabilityStatus(avail_raw)
            except ValueError:
                avail_status = AvailabilityStatus.UNKNOWN

            scope_raw = obs.get("availability_scope") or "GLOBAL"
            try:
                avail_scope = AvailabilityScope(scope_raw)
            except ValueError:
                avail_scope = AvailabilityScope.GLOBAL

            obs_obj = ProductObservation(
                observation_id=str(obs.get("observation_id") or uuid4()),
                product_id=canonical_pid,
                source_id=source_id,
                source_product_id=spid or canonical_pid,
                price=obs.get("price"),
                old_price=obs.get("old_price"),
                discount=obs.get("discount"),
                currency=Currency.EGP,
                raw_price_text=obs.get("raw_price_text"),
                availability_status=avail_status,
                availability_scope=avail_scope,
                stock_status=obs.get("stock_status"),
                stock_quantity=None,
                raw_availability_text=obs.get("raw_availability_text"),
                delivery_available=obs.get("delivery_available"),
                delivery_eta=obs.get("delivery_eta"),
                delivery_fee=obs.get("delivery_fee"),
                delivery_status=obs.get("delivery_status"),
                seller_name=obs.get("seller_name") or source_id,
                fulfillment_method=obs.get("fulfillment_method"),
                source_url=obs.get("source_url") or f"https://{source_id}.eg/p/{spid}",
                run_id=run_id,
            )
            valid_obs.append(obs_obj)
        except Exception:
            continue

    ext_result = ExtractionResult(
        source_id=source_id,
        run_id=run_id,
        mode=mode,
        products=valid_prods,
        locations=valid_locs,
        observations=valid_obs,
    )
    val_report = DataValidator().validate(ext_result, run_id=run_id)
    quality_score = float(val_report.get("overall_quality_score", 0.0))

    prods_out = []
    for p_obj in valid_prods:
        pd = p_obj.model_dump(mode="json")
        pd["department"] = prod_dept_by_pid.get(p_obj.product_id) or _ensure_product_department(pd)
        prods_out.append(pd)

    obs_out = []
    for o_obj in valid_obs:
        od = o_obj.model_dump(mode="json")
        od["department"] = prod_dept_by_pid.get(o_obj.product_id, "other")
        obs_out.append(od)

    locs_out = [l_obj.model_dump(mode="json") for l_obj in valid_locs]
    qi_out = [qi.model_dump(mode="json") for qi in ext_result.quality_issues]

    return prods_out, obs_out, locs_out, qi_out, quality_score


# ═══════════════════════════════════════════════════════════════════════════════
# Run live / fixture extraction
# ═══════════════════════════════════════════════════════════════════════════════

def enforce_strict_quality_gate(
    source_id: str,
    products: list[dict],
    observations: list[dict],
    locations: list[dict],
    run_date: str,
) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Step 3 Strict Quality Gate, Deduplication & NULL Validation:
    - Deduplicates observations by (source_id, product_id, collected_date).
    - Deduplicates products by (source_id, product_id).
    - Hard Stop on Critical NULLs: Rejects any product if CURRENT_PRICE is NULL
      (unless explicitly marked 'Call for Price'), or if PRODUCT_ID, PRODUCT_NAME,
      STORE, PRODUCT_URL, or STOCK_STATUS is NULL or 'UNKNOWN' due to a failed join.
    - Guarantees 100% referential integrity between products, observations and locations.
    """
    # 1. Deduplicate and validate observations by (source_id, canonical_pid, run_date)
    obs_by_pid: dict[str, dict] = {}
    for o in observations:
        spid = str(o.get("source_product_id") or "").strip()
        rpid = str(o.get("product_id") or "").strip()
        if not spid and ":" in rpid:
            spid = rpid.split(":", 1)[1]
        canonical_pid = f"{source_id}:{spid}" if spid else rpid
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
        obs_clean["product_id"] = canonical_pid
        obs_clean["source_product_id"] = spid or canonical_pid
        obs_clean["price"] = price_val
        obs_clean["stock_status"] = stock

        old_p = obs_clean.get("old_price")
        try:
            old_val = float(old_p) if old_p is not None else None
        except (ValueError, TypeError):
            old_val = None
        if old_val is not None and price_val is not None and old_val <= price_val:
            old_val = None
        obs_clean["old_price"] = old_val
        if old_val and price_val and old_val > price_val:
            obs_clean["discount"] = round((1.0 - price_val / old_val) * 100.0, 1)
        else:
            obs_clean["discount"] = None

        obs_date = str(obs_clean.get("observed_at") or obs_clean.get("collected_at") or run_date)[:10]
        if len(obs_date) != 10:
            obs_date = run_date
        obs_clean["observation_id"] = str(uuid5(NAMESPACE_DNS, f"{source_id}|{canonical_pid}|{obs_date}"))

        obs_by_pid[canonical_pid] = obs_clean

    # 2. Deduplicate products by (source_id, canonical_pid) & enforce Hard Stop on Critical NULLs
    clean_products: list[dict] = []
    clean_observations: list[dict] = []
    seen_pids: set[str] = set()

    for p in products:
        spid = str(p.get("source_product_id") or "").strip()
        rpid = str(p.get("product_id") or "").strip()
        if not spid and ":" in rpid:
            spid = rpid.split(":", 1)[1]
        canonical_pid = f"{source_id}:{spid}" if spid else rpid
        if not canonical_pid or canonical_pid in seen_pids:
            continue

        matched_obs = obs_by_pid.get(canonical_pid)
        if not matched_obs:
            continue

        pname = str(p.get("product_name") or "").strip()
        purl = str(p.get("product_url") or "").strip()
        price_val = matched_obs.get("price")
        stock_val = matched_obs.get("stock_status")
        raw_price_text = str(matched_obs.get("raw_price_text") or "").lower()
        is_call_for_price = "call for price" in raw_price_text

        if (
            not source_id
            or not canonical_pid
            or not pname
            or pname == "Unknown Product"
            or not purl
            or ((price_val is None or price_val <= 0) and not is_call_for_price)
            or not stock_val
            or stock_val == "UNKNOWN"
        ):
            continue

        seen_pids.add(canonical_pid)
        p_clean = dict(p)
        p_clean["product_id"] = canonical_pid
        p_clean["source_product_id"] = spid or canonical_pid
        p_clean["product_name"] = pname
        p_clean["product_url"] = purl
        clean_products.append(p_clean)
        clean_observations.append(matched_obs)

    # 3. Deduplicate locations by (source_id, location_id)
    clean_locations: list[dict] = []
    seen_locs: set[str] = set()
    for loc in locations:
        bname = str(loc.get("branch_name") or loc.get("location_name") or "").strip()
        if not bname:
            continue
        lid = str(loc.get("location_id") or uuid5(NAMESPACE_DNS, f"{source_id}|{bname}"))
        if lid in seen_locs:
            continue
        seen_locs.add(lid)
        l_clean = dict(loc)
        l_clean["location_id"] = lid
        l_clean["branch_name"] = bname
        l_clean["location_name"] = l_clean.get("location_name") or bname
        clean_locations.append(l_clean)

    return clean_products, clean_observations, clean_locations


async def run_live_extraction(
    source_id: str,
    offline: bool,
    limit: int,
    department: Optional[str] = None,
    with_locations: bool = True,
) -> dict:
    """Run the extractor and return fresh data.

    `with_locations=False` skips the (slow) branch/store-locator pass; used by the
    hourly price/stock pulse.
    """
    if not offline and source_id in ("tradeline", "dream2000"):
        from extractors.shopify_extractor import TradelineExtractor, Dream2000Extractor
        ext = (
            TradelineExtractor(max_products=limit)
            if source_id == "tradeline"
            else Dream2000Extractor(max_products=limit)
        )
        await ext._init_http_client()
        t0 = time.monotonic()
        try:
            prods = await ext.extract_products()
            obs = await ext.extract_availability()
            try:
                live_locs = await ext.extract_locations() if with_locations else []
                locs = [l.model_dump(mode="json") if hasattr(l, "model_dump") else l for l in live_locs]
            except Exception:
                locs = []
            duration = time.monotonic() - t0
            return {
                "products": [p.model_dump(mode="json") if hasattr(p, "model_dump") else p for p in prods],
                "observations": [o.model_dump(mode="json") if hasattr(o, "model_dump") else o for o in obs],
                "locations": locs,
                "quality_issues": [],
                "extraction_meta": {
                    "mode": "live",
                    "quality_score": 95.0,
                    "duration_seconds": duration,
                    "errors": [],
                },
            }
        except Exception as e:
            print(f"    ✗ Direct live extraction for {source_id} failed: {e}")
            return {}
        finally:
            await ext._cleanup()

    if not offline and source_id == "carrefour":
        from extractors.source_carrefour.extractor import CarrefourExtractor
        ext = CarrefourExtractor(
            data_dir=str(PROJECT_ROOT / "data"),
            max_products=limit,
        )
        t0 = time.monotonic()
        try:
            await ext._init_http_client()
            prods = await ext.extract_products()
            obs = await ext.extract_availability()
            locs = await ext.extract_locations() if with_locations else []
            duration = time.monotonic() - t0
            return {
                "products": [p.model_dump(mode="json") if hasattr(p, "model_dump") else p for p in prods],
                "observations": [o.model_dump(mode="json") if hasattr(o, "model_dump") else o for o in obs],
                "locations": [l.model_dump(mode="json") if hasattr(l, "model_dump") else l for l in locs],
                "quality_issues": [],
                "extraction_meta": {
                    "mode": "live",
                    "quality_score": 95.0,
                    "duration_seconds": duration,
                    "errors": [],
                },
            }
        except Exception as e:
            print(f"    ✗ Direct live extraction for carrefour failed: {e}")
            return {}
        finally:
            await ext._cleanup()

    if not offline and source_id == "raya":
        from extractors.source_raya.extractor import RayaExtractor
        ext = RayaExtractor(
            data_dir=str(PROJECT_ROOT / "data"),
            max_products=limit,
            live=True,
        )
        t0 = time.monotonic()
        try:
            await ext._init_http_client()
            prods = await ext.extract_products()
            obs = await ext.extract_availability()
            locs = await ext.extract_locations() if with_locations else []
            duration = time.monotonic() - t0
            return {
                "products": [p.model_dump(mode="json") if hasattr(p, "model_dump") else p for p in prods],
                "observations": [o.model_dump(mode="json") if hasattr(o, "model_dump") else o for o in obs],
                "locations": [l.model_dump(mode="json") if hasattr(l, "model_dump") else l for l in locs],
                "quality_issues": [],
                "extraction_meta": {
                    "mode": "live",
                    "quality_score": 95.0,
                    "duration_seconds": duration,
                    "errors": [],
                },
            }
        except Exception as e:
            print(f"    ✗ Direct live extraction for raya failed: {e}")
            return {}
        finally:
            await ext._cleanup()

    from run_extraction import run_extraction

    results = await run_extraction(
        source_id=source_id,
        offline_fixture=offline,
        max_products=limit,
        data_dir=str(PROJECT_ROOT / "data"),
        department=department,
    )

    if not results:
        return {}

    r = results[0]

    def _ser(obj):
        if hasattr(obj, "model_dump"):
            return obj.model_dump(mode="json")
        return obj

    return {
        "products":       [_ser(p) for p in r.products],
        "observations":   [_ser(o) for o in r.observations],
        "locations":      [_ser(l) for l in r.locations],
        "quality_issues": [_ser(qi) for qi in getattr(r, "quality_issues", [])],
        "extraction_meta": {
            "mode": getattr(r, "mode", "offline_fixture"),
            "quality_score": getattr(r, "quality_score", 0.0),
            "duration_seconds": getattr(r, "duration_seconds", 0.0),
            "errors": getattr(r, "errors", []),
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Main pipeline
# ═══════════════════════════════════════════════════════════════════════════════

async def run_pipeline(
    db_path: Path,
    sources: list[str],
    offline: bool = True,
    limit: int = 500,
    department: Optional[str] = None,
    include_raw_snapshots: Optional[bool] = None,
) -> None:
    is_main_db = db_path.resolve() == DEFAULT_DB.resolve()
    if include_raw_snapshots is None:
        include_raw_snapshots = is_main_db and offline

    target_dept = resolve_department_alias(department) if department else None
    conn = get_db(db_path)
    today = date.today().isoformat()
    now_ts = datetime.now(timezone.utc).isoformat()
    pipeline_start = time.monotonic()

    dept_label = (
        f"{target_dept} ({DEPARTMENT_CATALOG[target_dept]['name_ar']})"
        if target_dept
        else "ALL DEPARTMENTS (كل الأقسام)"
    )

    print(f"\n{'═'*65}")
    print(f"  EGYPT E-COMMERCE LEGACY STAR-SCHEMA LOADER (LOCAL DUCKDB)")
    print(f"  Date       : {today}")
    print(f"  Mode       : {'offline_fixture' if offline else 'LIVE'} (raw_snapshots={include_raw_snapshots})")
    print(f"  Department : {dept_label}")
    print(f"  DB         : {db_path}")
    print(f"{'═'*65}\n")

    total_products = 0
    total_obs = 0
    total_locs = 0
    total_qi = 0

    for source_id in sources:
        t0 = time.monotonic()
        run_id = f"{source_id}_{today}_{str(uuid4())[:8]}"
        started_at = datetime.now(timezone.utc).isoformat()
        print(f"  ── {source_id.upper()} ──────────────────────────────────")

        try:
            live_data = await run_live_extraction(
                source_id, offline=offline, limit=limit, department=target_dept
            )
        except Exception as e:
            print(f"    ✗ Extraction failed: {e}")
            live_data = {}

        fell_back = False
        if not live_data and not include_raw_snapshots and offline:
            print(f"    ↩  Falling back to samples/{source_id}/ on disk")
            live_data = load_source_samples(source_id)
            fell_back = True

        if not offline:
            data = live_data or {
                "products": [],
                "observations": [],
                "locations": [],
                "quality_issues": [],
                "extraction_meta": {"mode": "live"},
            }
        else:
            data = load_all_source_data(
                source_id=source_id,
                live_data=live_data,
                include_raw_snapshots=include_raw_snapshots,
            )
        meta = data.get("extraction_meta", {})

        if fell_back or offline:
            mode = meta.get("run_mode") or meta.get("mode") or "offline_fixture"
        else:
            mode = meta.get("mode") or meta.get("run_mode") or "live"
        errors = meta.get("errors", [])

        # Validate every record using canonical Pydantic schema + DataValidator
        products, observations, locations, quality_issues, quality_score = validate_source_bundle(
            source_id=source_id,
            bundle=data,
            run_id=run_id,
            mode=mode,
        )

        # Enforce Strict Quality Gate, Deduplication & NULL Validation
        products, observations, locations = enforce_strict_quality_gate(
            source_id=source_id,
            products=products,
            observations=observations,
            locations=locations,
            run_date=today,
        )

        # Filter by target_dept if requested
        if target_dept:
            products = [p for p in products if p.get("department") == target_dept]
            allowed_pids = {p.get("product_id") for p in products}
            observations = [
                o for o in observations
                if o.get("product_id") in allowed_pids
            ]

        # Write to DB
        upsert_source(conn, source_id, {"mode": mode})
        prod_dept_map, pid_lookup = upsert_products(conn, products, source_id, now_ts)
        upsert_locations(conn, locations, source_id, now_ts)
        insert_observations(
            conn,
            observations,
            source_id,
            run_id,
            today,
            mode,
            quality_score,
            prod_dept_map,
            pid_lookup,
        )
        insert_quality_issues(conn, quality_issues, run_id, today, source_id)

        # Save per-department JSON partitions on disk
        save_department_partitions(products, observations, today)

        elapsed = time.monotonic() - t0
        finished_at = datetime.now(timezone.utc).isoformat()

        insert_manifest(conn, run_id, today, source_id, mode, {
            "products": len(products),
            "observations": len(observations),
            "locations": len(locations),
            "quality_issues": len(quality_issues),
            "errors": len(errors),
        }, quality_score, elapsed, started_at, finished_at)

        total_products += len(products)
        total_obs      += len(observations)
        total_locs     += len(locations)
        total_qi       += len(quality_issues)

        print(
            f"    ✓ validated: products={len(products):,}  obs={len(observations):,}  "
            f"locs={len(locations):,}  quality={quality_score:.1f}%  ({elapsed:.1f}s)"
        )

    conn.close()
    total_elapsed = time.monotonic() - pipeline_start
    print(f"\n{'═'*65}")
    print(f"  PIPELINE COMPLETE  ({total_elapsed:.1f}s)")
    print(f"  Products     : {total_products:,}")
    print(f"  Observations : {total_obs:,}")
    print(f"  Locations    : {total_locs:,}")
    print(f"  Quality Issues: {total_qi:,}")
    print(f"  DB           : {db_path}")
    print(f"{'═'*65}\n")

    _print_db_summary(db_path)


def list_departments_cli() -> None:
    print(f"\n{'═'*95}")
    print(f"  📂 CANONICAL DEPARTMENTS & SQL VIEWS (تقسيم الأقسام في الكود والداتابيز)")
    print(f"{'═'*95}")
    print(f"  {'Department ID':24s} {'Sector':20s} {'SQL View':28s} {'الاسم بالعربي'}")
    print(f"  {'-'*90}")
    for dept_id, meta in DEPARTMENT_CATALOG.items():
        print(
            f"  {dept_id:24s} {meta['sector']:20s} {meta['view_name']:28s} {meta['name_ar']}"
        )
    print(f"{'═'*95}\n")


def _print_db_summary(db_path: Path) -> None:
    conn = duckdb.connect(str(db_path), read_only=True)
    print("  📊 DATABASE SUMMARY:")
    for tbl, label in [
        ("dim_department", "Departments configured"),
        ("dim_product", "Products in DB"),
        ("dim_location", "Locations in DB"),
        ("fact_observation", "Observations in DB"),
        ("run_manifest", "Runs recorded"),
    ]:
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            print(f"     {label:25s}: {count:,}")
        except Exception:
            pass

    try:
        dept_rows = conn.execute("""
            SELECT department_id, department_ar, sector, products_count,
                   observations_count, avg_price_egp, in_stock_count
            FROM v_department_summary
            WHERE products_count > 0
            ORDER BY products_count DESC
        """).fetchall()
        if dept_rows:
            print(f"\n  📂 BREAKDOWN BY DEPARTMENT (الأقسام المستقلة):")
            print(f"     {'Department':24s} {'Sector':20s} {'Products':>8s} {'Obs':>8s} {'Avg EGP':>12s} {'الاسم بالعربي'}")
            print(f"     {'-'*95}")
            for r in dept_rows:
                print(
                    f"     {r[0]:24s} {r[2]:20s} {r[3]:8,d} {r[4]:8,d} {str(r[5] or '-'):>12s} {r[1]}"
                )
    except Exception:
        pass

    conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(description="Egypt E-Commerce legacy star-schema loader (use dwh/run_pipeline.py for the local CDC pipeline)")
    parser.add_argument("--live", action="store_true",
                        help="Run live scraping (default: offline fixture)")
    parser.add_argument("--source", default=None,
                        help="Run single source only (default: all)")
    parser.add_argument("--department", "--category", dest="department", default=None,
                        help="Run/filter a specific department only (e.g. mobiles, laptops, electronics, appliances, meats, dairy, grocery, beverages, cleaning, beauty)")
    parser.add_argument("--list-departments", action="store_true",
                        help="List all canonical departments and their isolated DWH views")
    parser.add_argument("--db", default=None,
                        help="DuckDB path (REQUIRED for loading; the legacy backup DB is never a default)")
    parser.add_argument("--limit", type=int, default=1000,
                        help="Max products per source (default: 1000)")
    parser.add_argument("--query", action="store_true",
                        help="Just print DB summary, don't run pipeline")
    args = parser.parse_args()

    if args.list_departments:
        list_departments_cli()
        return

    if not args.db:
        parser.error("--db is required (legacy loader never writes to the backup DB by default)")
    db_path = Path(args.db)

    if args.query:
        _print_db_summary(db_path)
        return

    sources = [args.source] if args.source else SOURCES
    offline = not args.live

    asyncio.run(run_pipeline(
        db_path=db_path,
        sources=sources,
        offline=offline,
        limit=args.limit,
        department=args.department,
    ))


if __name__ == "__main__":
    main()
