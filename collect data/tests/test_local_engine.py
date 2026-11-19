"""Tests: hash-based CDC + preserved ERP business-logic rules (local engine)."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
import pytest

from dwh.cdc_snapshot import (
    apply_cdc, compute_state_hash, ensure_live_market_schema, seed_stores,
)
from dwh.supply_chain_generator import (
    apply_price_cap_to_qty, ensure_supply_chain_tables, generate_raw_supply_chain_tables,
    run_erp_sync,
)


def _row(pid="jumia:1", price=100.0, old=None, disc=None, stock="IN_STOCK"):
    return {
        "STORE": "jumia", "PRODUCT_ID": pid, "PRODUCT_NAME": f"Item {pid}", "CATEGORY": "Phones",
        "BRAND": "X", "CURRENT_PRICE": price, "OLD_PRICE": old, "DISCOUNT": disc,
        "STOCK_STATUS": stock, "PRODUCT_URL": "https://e.x/p", "IMAGE_URL": None,
    }


@pytest.fixture()
def conn():
    c = duckdb.connect(":memory:")
    ensure_live_market_schema(c)
    seed_stores(c)
    ensure_supply_chain_tables(c)
    yield c
    c.close()


NOW = datetime(2026, 11, 19, 6, 0, 0)


class TestStateHash:
    def test_deterministic_and_normalised(self):
        a = compute_state_hash("p", 10.0, None, None, "in_stock")
        b = compute_state_hash("p", 10.001, None, None, "IN_STOCK")
        assert a == b and len(a) == 64

    @pytest.mark.parametrize("args", [
        ("p", 11.0, None, None, "IN_STOCK"),
        ("p", 10.0, 12.0, None, "IN_STOCK"),
        ("p", 10.0, None, 5.0, "IN_STOCK"),
        ("p", 10.0, None, None, "OUT_OF_STOCK"),
        ("q", 10.0, None, None, "IN_STOCK"),
    ])
    def test_any_tracked_field_changes_hash(self, args):
        assert compute_state_hash("p", 10.0, None, None, "IN_STOCK") != compute_state_hash(*args)


class TestCDC:
    def test_unchanged_produces_no_snapshot(self, conn):
        r1 = apply_cdc(conn, "jumia", [_row("jumia:1"), _row("jumia:2")], "run1", NOW)
        assert (r1.inserted, r1.updated, r1.unchanged) == (2, 0, 0)

        later = NOW + timedelta(hours=1)
        r2 = apply_cdc(conn, "jumia", [_row("jumia:1"), _row("jumia:2")], "run2", later)
        assert (r2.inserted, r2.updated, r2.unchanged) == (0, 0, 2)
        assert r2.changed_rows == []
        assert conn.execute("SELECT COUNT(*) FROM live_market.PRICE_HISTORY").fetchone()[0] == 2
        checked = conn.execute("SELECT MIN(LAST_CHECKED_AT) FROM live_market.PRODUCTS").fetchone()[0]
        assert checked == later  # only LAST_CHECKED_AT moved
        assert conn.execute("SELECT MAX(LAST_UPDATED_AT) FROM live_market.PRODUCTS").fetchone()[0] == NOW

    def test_changed_price_appends_update_row(self, conn):
        apply_cdc(conn, "jumia", [_row("jumia:1", 100.0)], "run1", NOW)
        res = apply_cdc(conn, "jumia", [_row("jumia:1", 90.0, old=100.0, disc=10.0)], "run2", NOW + timedelta(hours=1))
        assert (res.inserted, res.updated, res.unchanged) == (0, 1, 0)
        assert res.changed_rows[0]["CHANGE_TYPE"] == "UPDATE"
        types = [r[0] for r in conn.execute(
            "SELECT CHANGE_TYPE FROM live_market.PRICE_HISTORY ORDER BY COLLECTED_AT").fetchall()]
        assert types == ["INSERT", "UPDATE"]
        assert conn.execute("SELECT CURRENT_PRICE FROM live_market.PRODUCTS").fetchone()[0] == 90.0
        assert conn.execute("SELECT COUNT(*) FROM live_market.PRODUCTS").fetchone()[0] == 1

    def test_no_consecutive_duplicate_hashes(self, conn):
        for i in range(4):
            apply_cdc(conn, "jumia", [_row("jumia:1", 100.0 + (i // 2))], f"r{i}", NOW + timedelta(hours=i))
        dups = conn.execute("""
            SELECT COUNT(*) FROM (
              SELECT STATE_HASH, LAG(STATE_HASH) OVER (PARTITION BY PRODUCT_ID ORDER BY COLLECTED_AT) p
              FROM live_market.PRICE_HISTORY) WHERE STATE_HASH = p""").fetchone()[0]
        assert dups == 0


def _catalog(n=40):
    rng = random.Random(1)
    prods = []
    for i in range(n):
        price = rng.choice([80.0, 450.0, 900.0, 2500.0, 5200.0, 18000.0])
        prods.append({"STORE": "jumia", "PRODUCT_ID": f"jumia:{i}", "PRODUCT_NAME": f"P{i}",
                      "CATEGORY": rng.choice(["Smartphones", "Dairy", "Laptops", "Detergent"]),
                      "BRAND": None, "CURRENT_PRICE": price, "OLD_PRICE": None,
                      "DISCOUNT": None, "STOCK_STATUS": "IN_STOCK"})
    branches = [{"BRANCH_ID": f"b{i}", "STORE": "jumia", "BRANCH_NAME": f"B{i}", "CITY": "Cairo",
                 "GOVERNORATE": "Giza", "LATITUDE": None, "LONGITUDE": None} for i in range(5)]
    return prods, branches


class TestERPRules:
    def test_price_cap_guard(self):
        rng = random.Random(0)
        for _ in range(500):
            assert apply_price_cap_to_qty(10, rng.uniform(3000.01, 90000), rng) == 1
            assert apply_price_cap_to_qty(10, rng.uniform(500.01, 3000), rng) <= 2
            assert apply_price_cap_to_qty(25, rng.uniform(1, 500), rng) <= 10

    def test_generated_tables_follow_rules(self):
        prods, branches = _catalog()
        t = generate_raw_supply_chain_tables(prods, branches, seed=7, num_cust_orders_override=800,
                                             num_pos_override=40, base_now_override=datetime(2026, 11, 19, tzinfo=timezone.utc))
        price_by_item = {}
        for it in t["RAW_ORDER_ITEMS"]:
            assert "GROSS_PROFIT_EGP" not in it and "LINE_REVENUE_EGP" not in it
            p, q = it["UNIT_PRICE_EGP"], it["QUANTITY"]
            assert q <= (1 if p > 3000 else 2 if p > 500 else 10)
        cancelled = {o["ORDER_ID"] for o in t["RAW_CUSTOMER_ORDERS"] if o["ORDER_STATUS_RAW"].upper() == "CANCELLED"}
        assert cancelled
        for s in t["RAW_SHIPMENTS"]:
            if s["ORDER_ID"] in cancelled:
                assert s["SHIPMENT_STATUS_RAW"] in ("RETURNED_TO_SENDER", "CANCELLED")
        # raw anomalies preserved
        ids = [o["ORDER_ID"] for o in t["RAW_CUSTOMER_ORDERS"]]
        assert len(ids) > len(set(ids)), "webhook retry duplicates expected"
        fmts = {("T" in o["ORDER_TS_RAW"], "/" in o["ORDER_TS_RAW"]) for o in t["RAW_CUSTOMER_ORDERS"]}
        assert len(fmts) >= 3, "mixed timestamp formats expected"
        assert len({o["CUSTOMER_GOVERNORATE_RAW"] for o in t["RAW_CUSTOMER_ORDERS"]}) > 1

    def test_incremental_sync_keeps_cancelled_shipments_clean(self, conn, tmp_path: Path):
        prods, branches = _catalog()
        for p in prods:
            apply_cdc(conn, "jumia", [dict(p, **{"IMAGE_URL": None, "PRODUCT_URL": "u"})], "r", NOW)
        conn.executemany(
            "INSERT INTO live_market.BRANCHES VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(b["BRANCH_ID"], "jumia", b["BRANCH_NAME"], "Giza", "Cairo", None, None, None, None, NOW) for b in branches])
        t0 = datetime(2026, 11, 19, 6, 0, tzinfo=timezone.utc)
        base = run_erp_sync(conn, "daily", t0, "daily_x", bronze_root=tmp_path)
        assert base["mode"] == "baseline_full_load"
        hourly = run_erp_sync(conn, "hourly", t0 + timedelta(hours=1), "hourly_x", bronze_root=tmp_path)
        assert hourly["mode"] == "incremental_hourly"
        assert hourly["appended_rows"]["RAW_CUSTOMER_ORDERS"] >= 20
        bad = conn.execute("""
            SELECT COUNT(*) FROM supply_chain_stage.RAW_SHIPMENTS s
            JOIN supply_chain_stage.RAW_CUSTOMER_ORDERS o USING (ORDER_ID)
            WHERE UPPER(o.ORDER_STATUS_RAW) = 'CANCELLED'
              AND UPPER(s.SHIPMENT_STATUS_RAW) IN ('DELIVERED','IN_TRANSIT','OUT_FOR_DELIVERY','LABEL_CREATED')
        """).fetchone()[0]
        assert bad == 0
        assert any("raw_customer_orders" in f for f in hourly["bronze_files"])
