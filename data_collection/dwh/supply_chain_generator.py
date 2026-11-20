#!/usr/bin/env python3
"""
Supply Chain & ERP Raw Operational Data Generator (Phase 1 & Phase 2)
=====================================================================
Generates realistic, category-aware OLTP / ERP operational tables tied 100%
to the live products and physical branches stored in the local DuckDB
`live_market` schema (dwh/retail_lakehouse_fresh.duckdb).

Target Schema: `supply_chain_stage` (local DuckDB) + local Bronze Parquet
Tables:
  1. RAW_SUPPLIERS
  2. RAW_WAREHOUSES
  3. RAW_PURCHASE_ORDERS
  4. RAW_PO_LINES
  5. RAW_INVENTORY_LOGS
  6. RAW_CUSTOMER_ORDERS
  7. RAW_ORDER_ITEMS
  8. RAW_SHIPMENTS

Includes realistic raw OLTP nuances (mixed timestamp formats, unstandardized
Egyptian city/governorate spellings, casing variations, and ~1.5% retry duplicates)
so downstream Star Schema (`DIM_` / `FACT_`) transformations can be built later.
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _resolve_db_path(db_path: str | Path) -> Path:
    p = Path(db_path)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return p


# ─────────────────────────────────────────────────────────────────────────────
# 1. Category-to-ERP Supply Chain Mapping Rules
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CategorySupplyChainProfile:
    archetype_code: str
    archetype_name: str
    supplier_type: str
    wh_stock_range: tuple[int, int]        # Central Warehouse (min_qty, max_qty)
    branch_stock_range: tuple[int, int]    # Retail Branch (min_qty, max_qty)
    reorder_point: int                     # Branch/WH reorder trigger
    lead_time_days: tuple[int, int]        # Supplier lead time (min_days, max_days)
    cust_order_qty_range: tuple[int, int]  # Units per customer order line
    order_velocity: str                    # VERY_HIGH | HIGH | MEDIUM | LOW_HIGH_TICKET
    velocity_weight: float                 # Relative probability weight for order sampling
    wholesale_margin_pct: tuple[float, float]  # % below live CURRENT_PRICE (min%, max%)


ARCHETYPES: dict[str, CategorySupplyChainProfile] = {
    "APPLE_FLAGSHIP": CategorySupplyChainProfile(
        archetype_code="APPLE_FLAGSHIP",
        archetype_name="Apple Flagship Hardware (iPhone, Mac, iPad, Watch, AirPods)",
        supplier_type="Official Apple Tier-1 Authorized Distributor",
        wh_stock_range=(40, 180),
        branch_stock_range=(3, 18),
        reorder_point=8,
        lead_time_days=(10, 21),
        cust_order_qty_range=(1, 1),
        order_velocity="LOW_HIGH_TICKET",
        velocity_weight=1.2,
        wholesale_margin_pct=(6.5, 11.5),
    ),
    "APPLE_ECOSYSTEM_ACC": CategorySupplyChainProfile(
        archetype_code="APPLE_ECOSYSTEM_ACC",
        archetype_name="Premium Apple Ecosystem & Audio Accessories",
        supplier_type="Official Apple & Premium Audio Distributor",
        wh_stock_range=(120, 450),
        branch_stock_range=(10, 45),
        reorder_point=18,
        lead_time_days=(5, 12),
        cust_order_qty_range=(1, 2),
        order_velocity="MEDIUM",
        velocity_weight=2.2,
        wholesale_margin_pct=(18.0, 28.0),
    ),
    "SMARTPHONES_TABLETS": CategorySupplyChainProfile(
        archetype_code="SMARTPHONES_TABLETS",
        archetype_name="Smartphones, Tablets & Smart Wearables",
        supplier_type="Authorized Mobile & Telecom Distributor",
        wh_stock_range=(80, 320),
        branch_stock_range=(6, 30),
        reorder_point=12,
        lead_time_days=(4, 10),
        cust_order_qty_range=(1, 2),
        order_velocity="HIGH",
        velocity_weight=3.0,
        wholesale_margin_pct=(9.0, 15.5),
    ),
    "LAPTOPS_COMPUTING": CategorySupplyChainProfile(
        archetype_code="LAPTOPS_COMPUTING",
        archetype_name="Laptops, Desktops, Monitors, Printers & IT",
        supplier_type="IT & Enterprise Hardware Distributor",
        wh_stock_range=(35, 140),
        branch_stock_range=(2, 14),
        reorder_point=6,
        lead_time_days=(7, 15),
        cust_order_qty_range=(1, 1),
        order_velocity="LOW_HIGH_TICKET",
        velocity_weight=1.4,
        wholesale_margin_pct=(8.5, 14.0),
    ),
    "MAJOR_APPLIANCES_TV": CategorySupplyChainProfile(
        archetype_code="MAJOR_APPLIANCES_TV",
        archetype_name="Large Home Appliances, Air Conditioners & Televisions",
        supplier_type="Domestic OEM Factory & Heavy Appliance Distributor",
        wh_stock_range=(30, 110),
        branch_stock_range=(2, 10),
        reorder_point=5,
        lead_time_days=(5, 14),
        cust_order_qty_range=(1, 1),
        order_velocity="LOW_HIGH_TICKET",
        velocity_weight=1.3,
        wholesale_margin_pct=(11.0, 18.0),
    ),
    "SMALL_APPLIANCES_COFFEE": CategorySupplyChainProfile(
        archetype_code="SMALL_APPLIANCES_COFFEE",
        archetype_name="Small Kitchen, Coffee Machines & Home Care Appliances",
        supplier_type="Small Domestic Appliances (SDA) Wholesaler",
        wh_stock_range=(90, 280),
        branch_stock_range=(8, 28),
        reorder_point=12,
        lead_time_days=(4, 9),
        cust_order_qty_range=(1, 2),
        order_velocity="MEDIUM",
        velocity_weight=2.4,
        wholesale_margin_pct=(15.0, 24.0),
    ),
    "TECH_ACC_PERIPHERALS": CategorySupplyChainProfile(
        archetype_code="TECH_ACC_PERIPHERALS",
        archetype_name="Cables, Chargers, Audio, Gaming & Mobile Accessories",
        supplier_type="Consumer Electronics & Gaming Accessories Importer",
        wh_stock_range=(200, 750),
        branch_stock_range=(18, 70),
        reorder_point=25,
        lead_time_days=(3, 7),
        cust_order_qty_range=(1, 3),
        order_velocity="HIGH",
        velocity_weight=3.2,
        wholesale_margin_pct=(24.0, 38.0),
    ),
    "FMCG_FRESH_COLDCHAIN": CategorySupplyChainProfile(
        archetype_code="FMCG_FRESH_COLDCHAIN",
        archetype_name="Fresh Meats, Poultry, Dairy, Eggs, Fruits & Frozen Foods",
        supplier_type="Cold-Chain Agro-Food & Dairy Direct Producer",
        wh_stock_range=(450, 1800),
        branch_stock_range=(45, 220),
        reorder_point=60,
        lead_time_days=(1, 2),
        cust_order_qty_range=(2, 8),
        order_velocity="VERY_HIGH",
        velocity_weight=5.0,
        wholesale_margin_pct=(16.0, 26.0),
    ),
    "FMCG_DRY_HOUSEHOLD": CategorySupplyChainProfile(
        archetype_code="FMCG_DRY_HOUSEHOLD",
        archetype_name="Dry Grocery, Beverages, Detergents & Household Tissues",
        supplier_type="FMCG National Dry-Goods & Detergent Wholesaler",
        wh_stock_range=(600, 2500),
        branch_stock_range=(60, 300),
        reorder_point=75,
        lead_time_days=(2, 4),
        cust_order_qty_range=(2, 10),
        order_velocity="VERY_HIGH",
        velocity_weight=4.8,
        wholesale_margin_pct=(14.0, 23.0),
    ),
    "BEAUTY_HEALTH_DECOR": CategorySupplyChainProfile(
        archetype_code="BEAUTY_HEALTH_DECOR",
        archetype_name="Personal Care, Beauty, Grooming & Home Decor",
        supplier_type="Cosmetics, Wellness & Home Lifestyle Distributor",
        wh_stock_range=(150, 550),
        branch_stock_range=(14, 55),
        reorder_point=20,
        lead_time_days=(3, 8),
        cust_order_qty_range=(1, 4),
        order_velocity="HIGH",
        velocity_weight=2.8,
        wholesale_margin_pct=(22.0, 34.0),
    ),
}


def resolve_category_profile(store: str, category: str) -> CategorySupplyChainProfile:
    """Deterministically map every (store, category) pair to its supply chain archetype."""
    s = (store or "").lower().strip()
    c = (category or "").lower().strip()

    # 1. Tradeline (Apple Authorized Partner)
    if s == "tradeline":
        if any(k in c for k in ("iphone 17", "iphone", "ipad", "macbook", "imac", "mac mini", "apple watch", "airpods", "laptops", "smartphones")):
            if "case" not in c and "band" not in c and "strap" not in c and "lens" not in c and "protector" not in c and "accessories" not in c:
                return ARCHETYPES["APPLE_FLAGSHIP"]
        if c == "mac":
            return ARCHETYPES["APPLE_FLAGSHIP"]
        return ARCHETYPES["APPLE_ECOSYSTEM_ACC"]

    # 2. FMCG Fresh & Cold Chain (Carrefour & grocery items)
    if any(k in c for k in ("meats", "poultry", "dairy", "eggs", "milk", "frozen", "fruits", "vegetables")):
        return ARCHETYPES["FMCG_FRESH_COLDCHAIN"]

    # 3. FMCG Dry Grocery, Beverages & Household Cleaning
    if any(k in c for k in ("detergent", "laundry", "cooking", "beverage", "cupboard", "tissues", "pantry", "bakery", "household", "bottles", "kitchenware", "water treatment")):
        return ARCHETYPES["FMCG_DRY_HOUSEHOLD"]

    # 4. Beauty, Personal Care, Grooming & Home Decor
    if any(k in c for k in ("beauty", "personal", "hair", "grooming", "decor", "diffuser")):
        return ARCHETYPES["BEAUTY_HEALTH_DECOR"]

    # 5. Major Home Appliances & TVs
    if any(k in c for k in ("large_appliances", "large appliances", "home-appliances", "home appliances", "appliances", "televisions", "tvs", "vehicles", "treadmill")):
        if "small" not in c and "care" not in c:
            return ARCHETYPES["MAJOR_APPLIANCES_TV"]

    # 6. Small Appliances & Coffee
    if any(k in c for k in ("small", "coffee", "home care")):
        return ARCHETYPES["SMALL_APPLIANCES_COFFEE"]

    # 7. Laptops, Desktops, Monitors, Printers & Computing
    if any(k in c for k in ("laptop", "desktop", "computer", "computing", "monitor", "printer", "storage", "networking", "projector")):
        if "accessories" not in c:
            return ARCHETYPES["LAPTOPS_COMPUTING"]

    # 8. Smartphones, Mobiles & Tablets (including Carrefour 'Smartphones Accessories' which is Smartphones & Accessories)
    if c == "smartphones accessories" or (
        any(k in c for k in ("phone", "mobile", "tablet", "smartwatch", "wearable"))
        and not any(x in c for x in ("audio", "protection", "landline", "case", "strap", "lens", "protector"))
    ):
        if "apple" in c:
            return ARCHETYPES["APPLE_FLAGSHIP"]
        return ARCHETYPES["SMARTPHONES_TABLETS"]

    # 9. Tech Accessories, Peripherals, Gaming & Audio
    if any(k in c for k in ("cables", "power", "charging", "keyboard", "audio", "protection", "accessories", "gaming", "camera", "speaker", "headphone", "microphone", "landline")):
        return ARCHETYPES["TECH_ACC_PERIPHERALS"]

    # 10. General Electronics fallback
    return ARCHETYPES["SMALL_APPLIANCES_COFFEE"]


# ─────────────────────────────────────────────────────────────────────────────
# 2. Reference Master Data (Suppliers & Warehouses)
# ─────────────────────────────────────────────────────────────────────────────

SUPPLIERS_CATALOG = [
    {
        "SUPPLIER_ID": "SUP-EG-101",
        "SUPPLIER_NAME": "Arab Business Machine (ABM) Apple MENA",
        "SUPPLIER_TYPE": "Official Apple Tier-1 Authorized Distributor",
        "ARCHETYPE_CODE": "APPLE_FLAGSHIP",
        "COUNTRY": "UAE / Egypt Free Zone",
        "CITY": "Cairo",
        "CURRENCY": "EGP",
        "PAYMENT_TERMS": "NET_30_LC",
        "RATING": 4.95,
    },
    {
        "SUPPLIER_ID": "SUP-EG-102",
        "SUPPLIER_NAME": "Metra Computer & Redington Apple Distribution",
        "SUPPLIER_TYPE": "Official Apple & Premium Audio Distributor",
        "ARCHETYPE_CODE": "APPLE_ECOSYSTEM_ACC",
        "COUNTRY": "Egypt",
        "CITY": "6th of October",
        "CURRENCY": "EGP",
        "PAYMENT_TERMS": "NET_45",
        "RATING": 4.85,
    },
    {
        "SUPPLIER_ID": "SUP-EG-103",
        "SUPPLIER_NAME": "KMG & Raya Telecom Distribution Egypt",
        "SUPPLIER_TYPE": "Authorized Mobile & Telecom Distributor",
        "ARCHETYPE_CODE": "SMARTPHONES_TABLETS",
        "COUNTRY": "Egypt",
        "CITY": "Giza",
        "CURRENCY": "EGP",
        "PAYMENT_TERMS": "NET_30",
        "RATING": 4.80,
    },
    {
        "SUPPLIER_ID": "SUP-EG-104",
        "SUPPLIER_NAME": "Delta & Connect Mobile Trading (Xiaomi/Oppo/Honor)",
        "SUPPLIER_TYPE": "Authorized Mobile & Telecom Distributor",
        "ARCHETYPE_CODE": "SMARTPHONES_TABLETS",
        "COUNTRY": "Egypt",
        "CITY": "Cairo ",
        "CURRENCY": "EGP",
        "PAYMENT_TERMS": "NET_30",
        "RATING": 4.72,
    },
    {
        "SUPPLIER_ID": "SUP-EG-105",
        "SUPPLIER_NAME": "Mantrac & BDL Enterprise IT Distribution",
        "SUPPLIER_TYPE": "IT & Enterprise Hardware Distributor",
        "ARCHETYPE_CODE": "LAPTOPS_COMPUTING",
        "COUNTRY": "Egypt",
        "CITY": "Al Qahirah",
        "CURRENCY": "EGP",
        "PAYMENT_TERMS": "NET_60",
        "RATING": 4.88,
    },
    {
        "SUPPLIER_ID": "SUP-EG-106",
        "SUPPLIER_NAME": "El-Araby Group & Fresh Industrial Complex",
        "SUPPLIER_TYPE": "Domestic OEM Factory & Heavy Appliance Distributor",
        "ARCHETYPE_CODE": "MAJOR_APPLIANCES_TV",
        "COUNTRY": "Egypt",
        "CITY": "10th of Ramadan",
        "CURRENCY": "EGP",
        "PAYMENT_TERMS": "NET_45",
        "RATING": 4.90,
    },
    {
        "SUPPLIER_ID": "SUP-EG-107",
        "SUPPLIER_NAME": "LG & Beko Egypt Regional Factory Supply",
        "SUPPLIER_TYPE": "Domestic OEM Factory & Heavy Appliance Distributor",
        "ARCHETYPE_CODE": "MAJOR_APPLIANCES_TV",
        "COUNTRY": "Egypt",
        "CITY": "10th of Ramadan - Sharqia",
        "CURRENCY": "EGP",
        "PAYMENT_TERMS": "NET_45",
        "RATING": 4.86,
    },
    {
        "SUPPLIER_ID": "SUP-EG-108",
        "SUPPLIER_NAME": "Nile Small Domestic Appliances & Coffee Co.",
        "SUPPLIER_TYPE": "Small Domestic Appliances (SDA) Wholesaler",
        "ARCHETYPE_CODE": "SMALL_APPLIANCES_COFFEE",
        "COUNTRY": "Egypt",
        "CITY": "Obour City",
        "CURRENCY": "EGP",
        "PAYMENT_TERMS": "NET_30",
        "RATING": 4.68,
    },
    {
        "SUPPLIER_ID": "SUP-EG-109",
        "SUPPLIER_NAME": "XPRS Gaming & Anker Accessories Import",
        "SUPPLIER_TYPE": "Consumer Electronics & Gaming Accessories Importer",
        "ARCHETYPE_CODE": "TECH_ACC_PERIPHERALS",
        "COUNTRY": "Egypt",
        "CITY": "Nasr City, Cairo",
        "CURRENCY": "EGP",
        "PAYMENT_TERMS": "NET_30",
        "RATING": 4.65,
    },
    {
        "SUPPLIER_ID": "SUP-EG-110",
        "SUPPLIER_NAME": "Juhayna & Cairo Poultry Cold-Chain Logistics",
        "SUPPLIER_TYPE": "Cold-Chain Agro-Food & Dairy Direct Producer",
        "ARCHETYPE_CODE": "FMCG_FRESH_COLDCHAIN",
        "COUNTRY": "Egypt",
        "CITY": "6th OctoberGiza",
        "CURRENCY": "EGP",
        "PAYMENT_TERMS": "NET_15",
        "RATING": 4.92,
    },
    {
        "SUPPLIER_ID": "SUP-EG-111",
        "SUPPLIER_NAME": "Unilever, P&G & Savola Mashreq FMCG Wholesale",
        "SUPPLIER_TYPE": "FMCG National Dry-Goods & Detergent Wholesaler",
        "ARCHETYPE_CODE": "FMCG_DRY_HOUSEHOLD",
        "COUNTRY": "Egypt",
        "CITY": "Badr City - Cairo",
        "CURRENCY": "EGP",
        "PAYMENT_TERMS": "NET_30",
        "RATING": 4.89,
    },
    {
        "SUPPLIER_ID": "SUP-EG-112",
        "SUPPLIER_NAME": "L'Oreal & Mansour Lifestyle Egypt Distribution",
        "SUPPLIER_TYPE": "Cosmetics, Wellness & Home Lifestyle Distributor",
        "ARCHETYPE_CODE": "BEAUTY_HEALTH_DECOR",
        "COUNTRY": "Egypt",
        "CITY": "New Cairo",
        "CURRENCY": "EGP",
        "PAYMENT_TERMS": "NET_30",
        "RATING": 4.78,
    },
]

WAREHOUSES_CATALOG = [
    {
        "WAREHOUSE_ID": "WH-CAI-01",
        "WAREHOUSE_NAME": "6th of October Mega Tech & Appliance CDC",
        "WAREHOUSE_TYPE": "CENTRAL_DC",
        "GOVERNORATE_RAW": "Giza",
        "CITY_RAW": "6th of October City",
        "CAPACITY_PALLETS": 25000,
        "COLD_CHAIN_ENABLED": "N",
        "LATITUDE": 29.9381,
        "LONGITUDE": 30.8924,
    },
    {
        "WAREHOUSE_ID": "WH-SHR-02",
        "WAREHOUSE_NAME": "10th of Ramadan Heavy Appliances & OEM Hub",
        "WAREHOUSE_TYPE": "CENTRAL_DC",
        "GOVERNORATE_RAW": "Sharqia",
        "CITY_RAW": "10th of Ramadan",
        "CAPACITY_PALLETS": 30000,
        "COLD_CHAIN_ENABLED": "N",
        "LATITUDE": 30.2969,
        "LONGITUDE": 31.7418,
    },
    {
        "WAREHOUSE_ID": "WH-CAI-03",
        "WAREHOUSE_NAME": "Obour & Badr Cold-Chain FMCG Fulfillment Center",
        "WAREHOUSE_TYPE": "COLD_CHAIN_DC",
        "GOVERNORATE_RAW": "Al Qahirah",
        "CITY_RAW": "Badr / Obour Industrial",
        "CAPACITY_PALLETS": 18000,
        "COLD_CHAIN_ENABLED": "Y",
        "LATITUDE": 30.1419,
        "LONGITUDE": 31.7145,
    },
    {
        "WAREHOUSE_ID": "WH-ALX-04",
        "WAREHOUSE_NAME": "Borg El Arab Coastal & Port Import Depot",
        "WAREHOUSE_TYPE": "REGIONAL_DEPOT",
        "GOVERNORATE_RAW": "Alexandria",
        "CITY_RAW": "Alex - Borg El Arab",
        "CAPACITY_PALLETS": 14000,
        "COLD_CHAIN_ENABLED": "Y",
        "LATITUDE": 30.8886,
        "LONGITUDE": 29.5800,
    },
    {
        "WAREHOUSE_ID": "WH-DAK-05",
        "WAREHOUSE_NAME": "Mansoura Central Delta Cross-Dock Hub",
        "WAREHOUSE_TYPE": "REGIONAL_DEPOT",
        "GOVERNORATE_RAW": "Dakahlia",
        "CITY_RAW": "El-Mansoura",
        "CAPACITY_PALLETS": 8500,
        "COLD_CHAIN_ENABLED": "N",
        "LATITUDE": 31.0409,
        "LONGITUDE": 31.3785,
    },
    {
        "WAREHOUSE_ID": "WH-ASY-06",
        "WAREHOUSE_NAME": "Assiut Upper Egypt Regional Distribution Depot",
        "WAREHOUSE_TYPE": "REGIONAL_DEPOT",
        "GOVERNORATE_RAW": "Asyut",
        "CITY_RAW": "Assiut Industrial",
        "CAPACITY_PALLETS": 7500,
        "COLD_CHAIN_ENABLED": "N",
        "LATITUDE": 27.1783,
        "LONGITUDE": 31.1859,
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# 3. OLTP Nuance Helpers (Mixed Timestamps, Dirty Cities, Minor Duplicates)
# ─────────────────────────────────────────────────────────────────────────────

CITY_VARIANTS = {
    "Cairo": ["Cairo", "CAIRO ", "Al Qahirah", "القاهرة", "Greater Cairo", "Cairo, EG"],
    "Giza": ["Giza", "GIZA", "Al Jizah", "الجيزة", "6th of October - Giza"],
    "Alexandria": ["Alexandria", "Alex", "ALX", "الإسكندرية", "Alexandria, Egypt"],
    "Dakahlia": ["Dakahlia", "Mansoura", "El-Mansoura", "الدقهلية"],
    "Sharqia": ["Sharqia", "Zagazig", "10th of Ramadan", "الشرقية"],
    "Qalyubia": ["Qalyubia", "Banha / Shubra", "القليوبية"],
    "Gharbia": ["Gharbia", "Tanta", "الغربية"],
    "Red Sea": ["Red Sea", "Hurghada", "الغردقة - البحر الأحمر"],
    "Suez": ["Suez", "السويس", "Suez Canal Zone"],
}


def format_oltp_timestamp(dt: datetime, rng: random.Random) -> str:
    """Return a timestamp in mixed OLTP formats to test stage normalization."""
    fmt_choice = rng.random()
    if fmt_choice < 0.55:
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    elif fmt_choice < 0.80:
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    elif fmt_choice < 0.93:
        return dt.strftime("%d/%m/%Y %H:%M")
    else:
        return dt.strftime("%Y/%m/%d %H:%M:%S")


def mess_up_city(gov: str | None, rng: random.Random) -> str:
    g = (gov or "Cairo").strip()
    if g in CITY_VARIANTS:
        return rng.choice(CITY_VARIANTS[g])
    return g


def apply_price_cap_to_qty(raw_qty: int, unit_price: float, rng: random.Random) -> int:
    """
    Price-cap guard on basket quantities (business rule #2):
      - UNIT_PRICE_EGP > 3000        -> max 1 unit
      - 500 < UNIT_PRICE_EGP <= 3000 -> max 2 units
      - UNIT_PRICE_EGP <= 500        -> max 10 units
    """
    if unit_price > 3000.0:
        return 1
    if unit_price > 500.0:
        return min(raw_qty, rng.randint(1, 2), 2)
    return min(raw_qty, 10)



# ─────────────────────────────────────────────────────────────────────────────
# 4. Fetch Live Catalog & Branches
# ─────────────────────────────────────────────────────────────────────────────

def load_live_catalog_and_branches(
    conn: duckdb.DuckDBPyConnection,
) -> tuple[list[dict], list[dict]]:
    """Load live products (latest CDC state) and branches from local `live_market`."""
    prods_raw = conn.execute("""
        SELECT STORE, PRODUCT_ID, PRODUCT_NAME, COALESCE(CATEGORY, 'Uncategorized'), BRAND,
               CURRENT_PRICE, OLD_PRICE, DISCOUNT, COALESCE(STOCK_STATUS, 'IN_STOCK')
        FROM live_market.PRODUCTS
        WHERE CURRENT_PRICE IS NOT NULL AND CURRENT_PRICE > 0
        ORDER BY STORE, PRODUCT_ID
    """).fetchall()
    pcols = ["STORE", "PRODUCT_ID", "PRODUCT_NAME", "CATEGORY", "BRAND",
             "CURRENT_PRICE", "OLD_PRICE", "DISCOUNT", "STOCK_STATUS"]
    products = [dict(zip(pcols, r)) for r in prods_raw]

    branches_raw = conn.execute("""
        SELECT BRANCH_ID, STORE, BRANCH_NAME, COALESCE(CITY, 'Cairo'),
               COALESCE(GOVERNORATE, 'Cairo'), LATITUDE, LONGITUDE
        FROM live_market.BRANCHES
        ORDER BY STORE, BRANCH_ID
    """).fetchall()
    bcols = ["BRANCH_ID", "STORE", "BRANCH_NAME", "CITY", "GOVERNORATE", "LATITUDE", "LONGITUDE"]
    branches = [dict(zip(bcols, r)) for r in branches_raw]
    return products, branches


# ─────────────────────────────────────────────────────────────────────────────
# 5. Build Complete Category Mapping Matrix
# ─────────────────────────────────────────────────────────────────────────────

def build_category_mapping_matrix(products: list[dict]) -> list[dict[str, Any]]:
    """Group live products by (STORE, CATEGORY) and attach exact ERP parameters."""
    grouped: dict[tuple[str, str], list[float]] = {}
    for p in products:
        key = (p["STORE"], p["CATEGORY"] or "Uncategorized")
        grouped.setdefault(key, []).append(float(p["CURRENT_PRICE"]))

    matrix = []
    for (store, category), prices in sorted(grouped.items(), key=lambda x: (x[0][0], -len(x[1]))):
        prof = resolve_category_profile(store, category)
        matrix.append({
            "STORE": store,
            "CATEGORY": category,
            "PRODUCT_COUNT": len(prices),
            "AVG_LIVE_PRICE_EGP": round(sum(prices) / len(prices), 2),
            "ARCHETYPE": prof.archetype_code,
            "SUPPLIER_TYPE": prof.supplier_type,
            "WH_STOCK_RANGE": f"{prof.wh_stock_range[0]}..{prof.wh_stock_range[1]}",
            "BRANCH_STOCK_RANGE": f"{prof.branch_stock_range[0]}..{prof.branch_stock_range[1]}",
            "REORDER_POINT": prof.reorder_point,
            "LEAD_TIME_DAYS": f"{prof.lead_time_days[0]}-{prof.lead_time_days[1]}d",
            "CUST_ORDER_QTY": f"{prof.cust_order_qty_range[0]}-{prof.cust_order_qty_range[1]} units",
            "ORDER_VELOCITY": prof.order_velocity,
            "WHOLESALE_COST_MARGIN": f"{prof.wholesale_margin_pct[0]:.1f}%-{prof.wholesale_margin_pct[1]:.1f}% below retail",
        })
    return matrix


# ─────────────────────────────────────────────────────────────────────────────
# 6. Generate the 8 RAW Transactional Tables
# ─────────────────────────────────────────────────────────────────────────────

def generate_raw_supply_chain_tables(
    products: list[dict],
    branches: list[dict],
    seed: int = 42,
    sample_only: bool = False,
    start_po_seq: int = 1,
    start_inv_seq: int = 1,
    start_ord_seq: int = 1,
    num_pos_override: int | None = None,
    num_cust_orders_override: int | None = None,
    num_inv_products_override: int | None = None,
    base_now_override: datetime | None = None,
    lookback_hours: int | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """
    Generate realistic ERP & Supply Chain raw records tied to live products and branches.
    Supports initial baseline generation, daily deltas, and hourly deltas
    (`lookback_hours` confines PO / order / inventory-snapshot timestamps to the last N hours).
    """
    if not products:
        raise ValueError("Cannot generate ERP data: live_market.PRODUCTS is empty (run --mode daily first).")
    if not branches:
        raise ValueError("Cannot generate ERP data: live_market.BRANCHES is empty (run --mode daily first).")
    rng = random.Random(seed)
    base_now = base_now_override or datetime(2026, 10, 31, 2, 0, 0, tzinfo=timezone.utc)

    # 1. RAW_SUPPLIERS
    raw_suppliers = []
    suppliers_by_archetype: dict[str, list[dict]] = {}
    for s in SUPPLIERS_CATALOG:
        rec = {
            **s,
            "CONTACT_EMAIL": f"orders@{s['SUPPLIER_ID'].lower().replace('-', '')}.com.eg",
            "ACTIVE_FLAG": rng.choice(["Y", "true", "1", "ACTIVE"]),
            "CREATED_AT_RAW": format_oltp_timestamp(base_now - timedelta(days=rng.randint(180, 720)), rng),
        }
        raw_suppliers.append(rec)
        suppliers_by_archetype.setdefault(s["ARCHETYPE_CODE"], []).append(rec)

    # 2. RAW_WAREHOUSES
    raw_warehouses = []
    for w in WAREHOUSES_CATALOG:
        raw_warehouses.append({
            **w,
            "OPERATIONAL_STATUS": rng.choice(["OPERATIONAL", "Active", "ACTIVE"]),
            "LAST_AUDIT_RAW": format_oltp_timestamp(base_now - timedelta(days=rng.randint(5, 45)), rng),
        })

    # Pre-compute product ERP metadata (unit cost, profile, supplier, warehouse)
    prod_meta: dict[str, dict] = {}
    for p in products:
        pid = p["PRODUCT_ID"]
        prof = resolve_category_profile(p["STORE"], p["CATEGORY"])
        margin = rng.uniform(prof.wholesale_margin_pct[0], prof.wholesale_margin_pct[1]) / 100.0
        unit_cost = round(float(p["CURRENT_PRICE"]) * (1.0 - margin), 2)
        sup_candidates = suppliers_by_archetype.get(prof.archetype_code, raw_suppliers)
        supplier = rng.choice(sup_candidates)
        if prof.archetype_code in ("FMCG_FRESH_COLDCHAIN", "FMCG_DRY_HOUSEHOLD"):
            wh = raw_warehouses[2]  # Cold-chain / FMCG DC
        elif prof.archetype_code == "MAJOR_APPLIANCES_TV":
            wh = raw_warehouses[1]  # 10th of Ramadan OEM Hub
        else:
            wh = raw_warehouses[0]  # 6th of October Tech CDC

        prod_meta[pid] = {
            "product": p,
            "profile": prof,
            "unit_cost": unit_cost,
            "supplier": supplier,
            "primary_wh": wh,
        }

    # Group branches by store
    branches_by_store: dict[str, list[dict]] = {}
    for b in branches:
        branches_by_store.setdefault(b["STORE"], []).append(b)

    if num_inv_products_override is not None:
        target_products = rng.sample(products, k=min(num_inv_products_override, len(products)))
    else:
        target_products = products[:60] if sample_only else products

    num_pos = num_pos_override if num_pos_override is not None else (15 if sample_only else 450)
    num_cust_orders = num_cust_orders_override if num_cust_orders_override is not None else (20 if sample_only else 2500)

    # 3. RAW_PURCHASE_ORDERS & 4. RAW_PO_LINES
    raw_purchase_orders = []
    raw_po_lines = []
    prod_keys = list(prod_meta.keys())

    for po_idx in range(start_po_seq, start_po_seq + num_pos):
        po_id = f"PO-2026-{po_idx:05d}"
        anchor_pid = rng.choice(prod_keys)
        anchor_info = prod_meta[anchor_pid]
        sup = anchor_info["supplier"]
        wh = anchor_info["primary_wh"]
        prof: CategorySupplyChainProfile = anchor_info["profile"]

        max_lookback_days = 1 if start_po_seq > 1 else 60
        if lookback_hours is not None:
            order_dt = base_now - timedelta(minutes=rng.randint(0, lookback_hours * 60))
        else:
            order_dt = base_now - timedelta(days=rng.randint(0, max_lookback_days), hours=rng.randint(0, 23))
        lead_days = rng.randint(prof.lead_time_days[0], prof.lead_time_days[1])
        expected_dt = order_dt + timedelta(days=lead_days)
        is_received = expected_dt <= base_now
        status_pool = ["RECEIVED", "Received", "CLOSED"] if is_received else ["IN_TRANSIT", "APPROVED", "Pending_Delivery"]

        # Pick 1 to 4 products from the same archetype
        same_arch_pids = [k for k, v in prod_meta.items() if v["profile"].archetype_code == prof.archetype_code]
        chosen_pids = rng.sample(same_arch_pids, k=min(rng.randint(1, 4), len(same_arch_pids)))

        po_total = 0.0
        for line_no, lpid in enumerate(chosen_pids, start=1):
            linfo = prod_meta[lpid]
            lprof: CategorySupplyChainProfile = linfo["profile"]
            ordered_qty = rng.randint(lprof.wh_stock_range[0], lprof.wh_stock_range[1])
            received_qty = ordered_qty if is_received else 0
            if is_received and rng.random() < 0.08:
                # Realistic partial short-ship from supplier
                received_qty = max(1, int(ordered_qty * rng.uniform(0.85, 0.98)))
            line_cost = round(ordered_qty * linfo["unit_cost"], 2)
            po_total += line_cost

            raw_po_lines.append({
                "PO_LINE_ID": f"{po_id}-L{line_no:02d}",
                "PO_ID": po_id,
                "PRODUCT_ID": lpid,
                "STORE": linfo["product"]["STORE"],
                "CATEGORY": linfo["product"]["CATEGORY"],
                "ORDERED_QTY": ordered_qty,
                "RECEIVED_QTY": received_qty,
                "UNIT_COST_EGP": linfo["unit_cost"],
                "LINE_TOTAL_EGP": line_cost,
            })

        po_record = {
            "PO_ID": po_id,
            "SUPPLIER_ID": sup["SUPPLIER_ID"],
            "WAREHOUSE_ID": wh["WAREHOUSE_ID"],
            "STORE": anchor_info["product"]["STORE"],
            "PO_STATUS_RAW": rng.choice(status_pool),
            "ORDER_DATE_RAW": format_oltp_timestamp(order_dt, rng),
            "EXPECTED_DELIVERY_RAW": format_oltp_timestamp(expected_dt, rng),
            "TOTAL_AMOUNT_EGP": round(po_total, 2),
            "CURRENCY": "EGP",
        }
        raw_purchase_orders.append(po_record)

        # ~1.5% duplicate ERP webhook retry nuance
        if rng.random() < 0.015:
            dup_po = dict(po_record)
            dup_po["ORDER_DATE_RAW"] = format_oltp_timestamp(order_dt + timedelta(seconds=2), rng)
            raw_purchase_orders.append(dup_po)

    # 5. RAW_INVENTORY_LOGS (Warehouse + Branch Stock Snapshots)
    raw_inventory_logs = []
    inv_seq = start_inv_seq
    branch_cursors: dict[str, int] = {}
    for p in target_products:
        pid = p["PRODUCT_ID"]
        info = prod_meta[pid]
        prof = info["profile"]
        wh = info["primary_wh"]
        is_oos = str(p.get("STOCK_STATUS", "")).upper() == "OUT_OF_STOCK"

        # Central Warehouse inventory snapshot
        wh_qty = rng.randint(0, prof.reorder_point) if is_oos else rng.randint(prof.wh_stock_range[0], prof.wh_stock_range[1])
        reserved_qty = rng.randint(0, max(1, int(wh_qty * 0.15))) if wh_qty > 0 else 0
        if lookback_hours is not None:
            snap_dt = base_now - timedelta(minutes=rng.randint(0, lookback_hours * 60))
        else:
            snap_dt = base_now - timedelta(hours=rng.randint(1, 36))

        wh_log = {
            "INV_LOG_ID": f"INV-LOG-{inv_seq:06d}",
            "PRODUCT_ID": pid,
            "STORE": p["STORE"],
            "LOCATION_TYPE": "WAREHOUSE",
            "WAREHOUSE_ID": wh["WAREHOUSE_ID"],
            "BRANCH_ID": None,
            "QTY_ON_HAND": wh_qty,
            "RESERVED_QTY": reserved_qty,
            "REORDER_POINT": prof.reorder_point * 3,
            "STOCK_STATUS_RAW": "LOW_STOCK" if wh_qty <= prof.reorder_point * 3 else "IN_STOCK",
            "SNAPSHOT_TS_RAW": format_oltp_timestamp(snap_dt, rng),
        }
        raw_inventory_logs.append(wh_log)
        inv_seq += 1

        # Cycle across all store branches so 100% of the 250 physical branches are represented
        store_branches = branches_by_store.get(p["STORE"], branches[:5])
        cur_idx = branch_cursors.get(p["STORE"], 0)
        br = store_branches[cur_idx % len(store_branches)]
        branch_cursors[p["STORE"]] = cur_idx + 1

        b_qty = 0 if is_oos else rng.randint(prof.branch_stock_range[0], prof.branch_stock_range[1])
        b_res = rng.randint(0, max(1, int(b_qty * 0.2))) if b_qty > 0 else 0
        br_log = {
            "INV_LOG_ID": f"INV-LOG-{inv_seq:06d}",
            "PRODUCT_ID": pid,
            "STORE": p["STORE"],
            "LOCATION_TYPE": "STORE_BRANCH",
            "WAREHOUSE_ID": None,
            "BRANCH_ID": str(br["BRANCH_ID"]),
            "QTY_ON_HAND": b_qty,
            "RESERVED_QTY": b_res,
            "REORDER_POINT": prof.reorder_point,
            "STOCK_STATUS_RAW": "OUT_OF_STOCK" if b_qty == 0 else ("REORDER_NEEDED" if b_qty <= prof.reorder_point else "OK"),
            "SNAPSHOT_TS_RAW": format_oltp_timestamp(snap_dt, rng),
        }
        raw_inventory_logs.append(br_log)
        if rng.random() < 0.015:
            dup_inv = dict(br_log)
            dup_inv["SNAPSHOT_TS_RAW"] = format_oltp_timestamp(snap_dt + timedelta(seconds=2), rng)
            raw_inventory_logs.append(dup_inv)
        inv_seq += 1

    # 6. RAW_CUSTOMER_ORDERS, 7. RAW_ORDER_ITEMS & 8. RAW_SHIPMENTS
    raw_customer_orders = []
    raw_order_items = []
    raw_shipments = []

    # Weighted sampling pool based on category velocity_weight
    weighted_pids = [p["PRODUCT_ID"] for p in products]
    weights = [prod_meta[pid]["profile"].velocity_weight for pid in weighted_pids]

    carriers = ["Bosta Egypt", "Mylerz Express", "Aramex EG", "Raya Fleet", "Jumia Logistics"]
    channels = ["ONLINE_DELIVERY", "MOBILE_APP", "CLICK_AND_COLLECT", "POS_IN_STORE"]
    payment_methods = ["COD (Cash on Delivery)", "Credit Card / Visa", "ValU Installments", "Fawry Pay", "Apple Pay / InstaPay"]

    for ord_idx in range(start_ord_seq, start_ord_seq + num_cust_orders):
        order_id = f"ORD-EG-{ord_idx:06d}"
        first_pid = rng.choices(weighted_pids, weights=weights, k=1)[0]
        first_info = prod_meta[first_pid]
        store_id = first_info["product"]["STORE"]
        store_branches = branches_by_store.get(store_id, branches)
        branch = rng.choice(store_branches)
        channel = rng.choice(channels)

        max_ord_lookback = 1 if start_ord_seq > 1 else 30
        if lookback_hours is not None:
            ord_dt = base_now - timedelta(minutes=rng.randint(0, lookback_hours * 60))
        else:
            ord_dt = base_now - timedelta(days=rng.randint(0, max_ord_lookback), hours=rng.randint(0, 23), minutes=rng.randint(0, 59))
        num_lines = rng.choices([1, 2, 3], weights=[0.65, 0.25, 0.10], k=1)[0]

        store_pids = [p["PRODUCT_ID"] for p in products if p["STORE"] == store_id]
        line_pids = [first_pid]
        if num_lines > 1 and len(store_pids) > 1:
            line_pids.extend(rng.sample(store_pids, k=min(num_lines - 1, len(store_pids))))

        order_subtotal = 0.0
        for item_no, ipid in enumerate(line_pids, start=1):
            iinfo = prod_meta[ipid]
            iprof: CategorySupplyChainProfile = iinfo["profile"]
            unit_price = float(iinfo["product"]["CURRENT_PRICE"])
            raw_qty = rng.randint(iprof.cust_order_qty_range[0], iprof.cust_order_qty_range[1])
            # Business rule #2: Price-Cap Guard (>3000 -> 1; 500-3000 -> max 2; <=500 -> max 10)
            qty = apply_price_cap_to_qty(raw_qty, unit_price, rng)
            unit_cost = float(iinfo["unit_cost"])

            gross_line = round(qty * unit_price, 2)
            # Optional promotional line discount (0.0 for ~75% of lines, 3%-10% off for ~25% of lines)
            if rng.random() < 0.25:
                max_disc_pct = max(0.0, (unit_price - unit_cost) / unit_price * 0.5)
                disc_pct = min(rng.uniform(0.03, 0.10), max_disc_pct)
                discount_amount = round(gross_line * disc_pct, 2)
            else:
                discount_amount = 0.0

            order_subtotal += round(gross_line - discount_amount, 2)

            # Refinement #3: Keep Derived KPIs (net revenue, gross profit, margin) out of RAW_ORDER_ITEMS
            raw_order_items.append({
                "ORDER_ITEM_ID": f"{order_id}-I{item_no:02d}",
                "ORDER_ID": order_id,
                "PRODUCT_ID": ipid,
                "STORE": store_id,
                "CATEGORY": iinfo["product"]["CATEGORY"],
                "QUANTITY": qty,
                "UNIT_PRICE_EGP": unit_price,
                "DISCOUNT_AMOUNT_EGP": discount_amount,
                "UNIT_COST_EGP": unit_cost,
            })

        shipping_fee = 0.0 if channel in ("POS_IN_STORE", "CLICK_AND_COLLECT") else rng.choice([0.0, 45.0, 65.0, 95.0, 150.0])
        ord_status = rng.choice(["DELIVERED", "Delivered", "SHIPPED", "PROCESSING", "COMPLETED", "CANCELLED"])
        dirty_gov = mess_up_city(branch.get("GOVERNORATE"), rng)

        cust_order = {
            "ORDER_ID": order_id,
            "CUSTOMER_ID": f"CUST-EG-{rng.randint(10000, 99999)}",
            "STORE": store_id,
            "FULFILLMENT_BRANCH_ID": str(branch["BRANCH_ID"]),
            "ORDER_CHANNEL_RAW": channel,
            "PAYMENT_METHOD_RAW": rng.choice(payment_methods),
            "CUSTOMER_GOVERNORATE_RAW": dirty_gov,
            "ORDER_STATUS_RAW": ord_status,
            "ORDER_TS_RAW": format_oltp_timestamp(ord_dt, rng),
            "SUBTOTAL_EGP": round(order_subtotal, 2),
            "SHIPPING_FEE_EGP": shipping_fee,
            "TOTAL_ORDER_EGP": round(order_subtotal + shipping_fee, 2),
        }
        raw_customer_orders.append(cust_order)
        if rng.random() < 0.015:
            dup_ord = dict(cust_order)
            dup_ord["ORDER_TS_RAW"] = format_oltp_timestamp(ord_dt + timedelta(seconds=2), rng)
            raw_customer_orders.append(dup_ord)

        # Refinement #1: Cancelled Order Shipment Logic
        # POS_IN_STORE orders never generate a shipment.
        # For CANCELLED orders: 60% cancelled before dispatch (no shipment record);
        # 40% cancelled after dispatch -> SHIPMENT_STATUS_RAW in ('RETURNED_TO_SENDER', 'CANCELLED'), never 'DELIVERED'.
        if channel != "POS_IN_STORE":
            upper_status = ord_status.upper()
            if upper_status == "CANCELLED" and rng.random() < 0.60:
                continue  # Cancelled before dispatch -> no shipment record

            wh = first_info["primary_wh"]
            ship_dt = ord_dt + timedelta(hours=rng.randint(2, 18))
            deliv_dt = ship_dt + timedelta(days=rng.randint(1, 4), hours=rng.randint(1, 12))

            if upper_status == "CANCELLED":
                shp_status = rng.choice(["RETURNED_TO_SENDER", "CANCELLED"])
                dispatched_ts = format_oltp_timestamp(ship_dt, rng)
                delivered_ts = None
            elif upper_status in ("DELIVERED", "COMPLETED"):
                shp_status = rng.choice(["DELIVERED", "Delivered"])
                dispatched_ts = format_oltp_timestamp(ship_dt, rng)
                delivered_ts = format_oltp_timestamp(deliv_dt, rng)
            elif upper_status == "PROCESSING":
                shp_status = "LABEL_CREATED"
                dispatched_ts = None
                delivered_ts = None
            else:
                shp_status = rng.choice(["IN_TRANSIT", "In_Transit", "OUT_FOR_DELIVERY"])
                dispatched_ts = format_oltp_timestamp(ship_dt, rng)
                delivered_ts = None

            raw_shipments.append({
                "SHIPMENT_ID": f"SHP-EG-{ord_idx:06d}",
                "ORDER_ID": order_id,
                "STORE": store_id,
                "ORIGIN_WAREHOUSE_ID": wh["WAREHOUSE_ID"],
                "DESTINATION_BRANCH_ID": str(branch["BRANCH_ID"]),
                "DESTINATION_GOV_RAW": dirty_gov,
                "CARRIER_NAME": "Internal Cold-Chain Van" if first_info["profile"].archetype_code == "FMCG_FRESH_COLDCHAIN" else rng.choice(carriers),
                "SHIPMENT_TYPE": "B2B_BRANCH_PICKUP" if channel == "CLICK_AND_COLLECT" else "B2C_LAST_MILE",
                "DISPATCHED_TS_RAW": dispatched_ts,
                "DELIVERED_TS_RAW": delivered_ts,
                "SHIPMENT_STATUS_RAW": shp_status,
                "SHIPPING_COST_EGP": round(max(35.0, shipping_fee * rng.uniform(0.7, 1.1)), 2),
            })

    return {
        "RAW_SUPPLIERS": raw_suppliers,
        "RAW_WAREHOUSES": raw_warehouses,
        "RAW_PURCHASE_ORDERS": raw_purchase_orders,
        "RAW_PO_LINES": raw_po_lines,
        "RAW_INVENTORY_LOGS": raw_inventory_logs,
        "RAW_CUSTOMER_ORDERS": raw_customer_orders,
        "RAW_ORDER_ITEMS": raw_order_items,
        "RAW_SHIPMENTS": raw_shipments,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 7. DDL & Local Loaders (DuckDB supply_chain_stage + Bronze Parquet)
# ─────────────────────────────────────────────────────────────────────────────

SUPPLY_CHAIN_DDL: dict[str, str] = {
    "RAW_SUPPLIERS": """
        CREATE TABLE IF NOT EXISTS {schema}RAW_SUPPLIERS (
            SUPPLIER_ID STRING,
            SUPPLIER_NAME STRING,
            SUPPLIER_TYPE STRING,
            ARCHETYPE_CODE STRING,
            COUNTRY STRING,
            CITY STRING,
            CURRENCY STRING,
            PAYMENT_TERMS STRING,
            RATING DOUBLE,
            CONTACT_EMAIL STRING,
            ACTIVE_FLAG STRING,
            CREATED_AT_RAW STRING
        )
    """,
    "RAW_WAREHOUSES": """
        CREATE TABLE IF NOT EXISTS {schema}RAW_WAREHOUSES (
            WAREHOUSE_ID STRING,
            WAREHOUSE_NAME STRING,
            WAREHOUSE_TYPE STRING,
            GOVERNORATE_RAW STRING,
            CITY_RAW STRING,
            CAPACITY_PALLETS INT,
            COLD_CHAIN_ENABLED STRING,
            LATITUDE DOUBLE,
            LONGITUDE DOUBLE,
            OPERATIONAL_STATUS STRING,
            LAST_AUDIT_RAW STRING
        )
    """,
    "RAW_PURCHASE_ORDERS": """
        CREATE TABLE IF NOT EXISTS {schema}RAW_PURCHASE_ORDERS (
            PO_ID STRING,
            SUPPLIER_ID STRING,
            WAREHOUSE_ID STRING,
            STORE STRING,
            PO_STATUS_RAW STRING,
            ORDER_DATE_RAW STRING,
            EXPECTED_DELIVERY_RAW STRING,
            TOTAL_AMOUNT_EGP DOUBLE,
            CURRENCY STRING
        )
    """,
    "RAW_PO_LINES": """
        CREATE TABLE IF NOT EXISTS {schema}RAW_PO_LINES (
            PO_LINE_ID STRING,
            PO_ID STRING,
            PRODUCT_ID STRING,
            STORE STRING,
            CATEGORY STRING,
            ORDERED_QTY INT,
            RECEIVED_QTY INT,
            UNIT_COST_EGP DOUBLE,
            LINE_TOTAL_EGP DOUBLE
        )
    """,
    "RAW_INVENTORY_LOGS": """
        CREATE TABLE IF NOT EXISTS {schema}RAW_INVENTORY_LOGS (
            INV_LOG_ID STRING,
            PRODUCT_ID STRING,
            STORE STRING,
            LOCATION_TYPE STRING,
            WAREHOUSE_ID STRING,
            BRANCH_ID STRING,
            QTY_ON_HAND INT,
            RESERVED_QTY INT,
            REORDER_POINT INT,
            STOCK_STATUS_RAW STRING,
            SNAPSHOT_TS_RAW STRING
        )
    """,
    "RAW_CUSTOMER_ORDERS": """
        CREATE TABLE IF NOT EXISTS {schema}RAW_CUSTOMER_ORDERS (
            ORDER_ID STRING,
            CUSTOMER_ID STRING,
            STORE STRING,
            FULFILLMENT_BRANCH_ID STRING,
            ORDER_CHANNEL_RAW STRING,
            PAYMENT_METHOD_RAW STRING,
            CUSTOMER_GOVERNORATE_RAW STRING,
            ORDER_STATUS_RAW STRING,
            ORDER_TS_RAW STRING,
            SUBTOTAL_EGP DOUBLE,
            SHIPPING_FEE_EGP DOUBLE,
            TOTAL_ORDER_EGP DOUBLE
        )
    """,
    "RAW_ORDER_ITEMS": """
        CREATE TABLE IF NOT EXISTS {schema}RAW_ORDER_ITEMS (
            ORDER_ITEM_ID STRING,
            ORDER_ID STRING,
            PRODUCT_ID STRING,
            STORE STRING,
            CATEGORY STRING,
            QUANTITY INT,
            UNIT_PRICE_EGP DOUBLE,
            DISCOUNT_AMOUNT_EGP DOUBLE,
            UNIT_COST_EGP DOUBLE
        )
    """,
    "RAW_SHIPMENTS": """
        CREATE TABLE IF NOT EXISTS {schema}RAW_SHIPMENTS (
            SHIPMENT_ID STRING,
            ORDER_ID STRING,
            STORE STRING,
            ORIGIN_WAREHOUSE_ID STRING,
            DESTINATION_BRANCH_ID STRING,
            DESTINATION_GOV_RAW STRING,
            CARRIER_NAME STRING,
            SHIPMENT_TYPE STRING,
            DISPATCHED_TS_RAW STRING,
            DELIVERED_TS_RAW STRING,
            SHIPMENT_STATUS_RAW STRING,
            SHIPPING_COST_EGP DOUBLE
        )
    """,
}


def ensure_supply_chain_tables(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute("CREATE SCHEMA IF NOT EXISTS supply_chain_stage")
    for ddl in SUPPLY_CHAIN_DDL.values():
        conn.execute(ddl.format(schema="supply_chain_stage.").replace("STRING", "VARCHAR"))


def _insert_rows(conn: duckdb.DuckDBPyConnection, table: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    cols = list(rows[0].keys())
    conn.executemany(
        f"INSERT INTO supply_chain_stage.{table} ({', '.join(cols)}) VALUES ({', '.join(['?'] * len(cols))})",
        [tuple(r[c] for c in cols) for r in rows],
    )


# Open-status progression: (table, business key, SET clause, WHERE clause)
def _status_advances(now_iso: str) -> list[tuple[str, str, str, str]]:
    return [
        ("RAW_SHIPMENTS", "SHIPMENT_ID",
         f"SHIPMENT_STATUS_RAW = 'DELIVERED', DELIVERED_TS_RAW = '{now_iso}'",
         "UPPER(SHIPMENT_STATUS_RAW) IN ('IN_TRANSIT', 'OUT_FOR_DELIVERY', 'LABEL_CREATED')"),
        ("RAW_CUSTOMER_ORDERS", "ORDER_ID",
         "ORDER_STATUS_RAW = 'DELIVERED'",
         "UPPER(ORDER_STATUS_RAW) IN ('SHIPPED', 'PROCESSING')"),
        ("RAW_PURCHASE_ORDERS", "PO_ID",
         "PO_STATUS_RAW = 'RECEIVED'",
         "UPPER(PO_STATUS_RAW) IN ('IN_TRANSIT', 'APPROVED', 'PENDING_DELIVERY')"),
        ("RAW_PO_LINES", "PO_LINE_ID",
         "RECEIVED_QTY = ORDERED_QTY",
         "RECEIVED_QTY = 0"),
    ]


def advance_open_statuses(
    conn: duckdb.DuckDBPyConnection, now_iso: str
) -> dict[str, list[dict[str, Any]]]:
    """Progress in-flight POs / orders / shipments; return the updated rows (for bronze).

    Cancelled orders are never touched: their shipments carry RETURNED_TO_SENDER /
    CANCELLED so they never match the in-flight WHERE clauses (business rule #1).
    """
    updated: dict[str, list[dict[str, Any]]] = {}
    for table, key, set_sql, where_sql in _status_advances(now_iso):
        full = f"supply_chain_stage.{table}"
        keys = [r[0] for r in conn.execute(f"SELECT DISTINCT {key} FROM {full} WHERE {where_sql}").fetchall()]
        if not keys:
            continue
        conn.execute(f"UPDATE {full} SET {set_sql} WHERE {where_sql}")
        conn.register("adv_keys", pd.DataFrame({"k": keys}))
        cur = conn.execute(f"SELECT * FROM {full} WHERE {key} IN (SELECT k FROM adv_keys)")
        cols = [d[0] for d in cur.description]
        updated[table] = [dict(zip(cols, r)) for r in cur.fetchall()]
        conn.unregister("adv_keys")
    return updated


def _max_seq(conn: duckdb.DuckDBPyConnection, table: str, col: str, default: int) -> int:
    """Numeric max of the trailing digits in an ID like PO-2026-00533 / ORD-EG-002500."""
    val = conn.execute(
        f"SELECT MAX(TRY_CAST(regexp_extract({col}, '([0-9]+)$', 1) AS BIGINT)) "
        f"FROM supply_chain_stage.{table}"
    ).fetchone()[0]
    return int(val) if val is not None else default


# Per-mode volume profiles for incremental deltas
ERP_PROFILES: dict[str, dict[str, Any]] = {
    "daily":  {"pos": 25, "inv_products": 250, "orders": 120, "lookback_hours": None},
    "hourly": {"pos": 2,  "inv_products": 60,  "orders": 20,  "lookback_hours": 1},
}


def run_erp_sync(
    conn: duckdb.DuckDBPyConnection,
    mode: str,
    run_ts: datetime,
    run_id: str,
    bronze_root: Path | None = None,
) -> dict[str, Any]:
    """
    Local ERP sync, invoked after the market scrape + CDC step:
      1. First ever run (no RAW_CUSTOMER_ORDERS): full baseline load from live prices.
      2. Otherwise: advance open POs / orders / shipments, then append a daily or
         hourly delta batch anchored to the latest live prices.
    All rows go to DuckDB `supply_chain_stage` and to local Bronze Parquet.
    """
    from dwh.bronze_writer import arrow_schema_for_table, write_bronze

    if mode not in ERP_PROFILES:
        raise ValueError(f"unknown mode {mode!r}")
    ensure_supply_chain_tables(conn)
    products, branches = load_live_catalog_and_branches(conn)
    now_iso = run_ts.strftime("%Y-%m-%dT%H:%M:%SZ")

    has_baseline = conn.execute("SELECT COUNT(*) FROM supply_chain_stage.RAW_CUSTOMER_ORDERS").fetchone()[0] > 0
    appended: dict[str, int] = {}
    updated_counts: dict[str, int] = {}
    bronze_files: list[str] = []

    def _bronze(table: str, rows: list[dict], op: str) -> None:
        schema = arrow_schema_for_table(conn, f"supply_chain_stage.{table}")
        f = write_bronze(table.lower(), rows, schema, run_ts, run_id, op=op, root=bronze_root)
        if f:
            bronze_files.append(str(f))

    if not has_baseline:
        tables = generate_raw_supply_chain_tables(
            products, branches, seed=int(run_ts.timestamp()), sample_only=False, base_now_override=run_ts,
        )
        for tname, rows in tables.items():
            _insert_rows(conn, tname, rows)
            appended[tname] = len(rows)
            _bronze(tname, rows, "INSERT")
        sync_mode = "baseline_full_load"
    else:
        updated = advance_open_statuses(conn, now_iso)
        for tname, rows in updated.items():
            updated_counts[tname] = len(rows)
            _bronze(tname, rows, "UPDATE")

        prof = ERP_PROFILES[mode]
        start_po = _max_seq(conn, "RAW_PURCHASE_ORDERS", "PO_ID", 0) + 1
        start_inv = _max_seq(conn, "RAW_INVENTORY_LOGS", "INV_LOG_ID", 0) + 1
        start_ord = _max_seq(conn, "RAW_CUSTOMER_ORDERS", "ORDER_ID", 0) + 1
        delta = generate_raw_supply_chain_tables(
            products=products, branches=branches, seed=int(run_ts.timestamp()),
            sample_only=False, start_po_seq=start_po, start_inv_seq=start_inv,
            start_ord_seq=start_ord, num_pos_override=prof["pos"],
            num_cust_orders_override=prof["orders"], num_inv_products_override=prof["inv_products"],
            base_now_override=run_ts, lookback_hours=prof["lookback_hours"],
        )
        for tname in ("RAW_PURCHASE_ORDERS", "RAW_PO_LINES", "RAW_INVENTORY_LOGS",
                      "RAW_CUSTOMER_ORDERS", "RAW_ORDER_ITEMS", "RAW_SHIPMENTS"):
            rows = delta[tname]
            _insert_rows(conn, tname, rows)
            appended[tname] = len(rows)
            _bronze(tname, rows, "INSERT")
        sync_mode = f"incremental_{mode}"

    totals = {
        t: conn.execute(f"SELECT COUNT(*) FROM supply_chain_stage.{t}").fetchone()[0]
        for t in SUPPLY_CHAIN_DDL
    }
    return {
        "mode": sync_mode,
        "appended_rows": appended,
        "status_updates": updated_counts,
        "table_totals": totals,
        "bronze_files": bronze_files,
    }


def main() -> None:
    """Dry-run helper: print the category mapping matrix + 5-row previews (no writes)."""
    parser = argparse.ArgumentParser(description="Supply Chain & ERP raw data generator (preview only)")
    parser.add_argument("--db", default=str(PROJECT_ROOT / "dwh" / "retail_lakehouse_fresh.duckdb"))
    parser.add_argument("--output-json", default="", help="Optional path for the preview JSON")
    args = parser.parse_args()

    conn = duckdb.connect(args.db, read_only=True)
    try:
        products, branches = load_live_catalog_and_branches(conn)
    finally:
        conn.close()
    matrix = build_category_mapping_matrix(products)
    tables = generate_raw_supply_chain_tables(products, branches, sample_only=True)
    print(f"Loaded {len(products)} live products and {len(branches)} branches across {len(matrix)} (STORE, CATEGORY) pairs.")
    for tname, rows in tables.items():
        print(f"\n=== {tname} (Preview 5 of {len(rows)} rows) ===")
        for r in rows[:5]:
            print(" ", json.dumps(r, ensure_ascii=False, default=str))
    if args.output_json:
        Path(args.output_json).write_text(
            json.dumps({"category_mapping_matrix": matrix}, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
