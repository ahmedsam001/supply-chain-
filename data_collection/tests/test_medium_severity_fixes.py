"""
Tests for Medium Severity Fixes:
1. Canonical Stock Status Normalization (Enum: IN_STOCK, OUT_OF_STOCK, LIMITED_STOCK, LOW_STOCK_SIGNAL, PREORDER, UNKNOWN)
2. Protocol-Relative Image URL Standardization ('//...' -> 'https://...')
3. Same-Day Observation Deduplication Safeguard (Idempotent upsert on fact_observation)
4. Database views and schema consistency
"""

from __future__ import annotations

import duckdb
import pytest

from dwh.pipeline import insert_observations
from normalization.normalizers import (
    CanonicalStockStatus,
    normalize_availability_status,
    normalize_image_url,
    normalize_stock_status,
)
from normalization.schema import AvailabilityStatus, Product, ProductObservation


class TestStockStatusNormalization:
    @pytest.mark.parametrize(
        "raw_val,avail,expected",
        [
            # IN_STOCK variations
            ("in_stock", None, "IN_STOCK"),
            ("IN_STOCK", None, "IN_STOCK"),
            ("In Stock", None, "IN_STOCK"),
            ("available", None, "IN_STOCK"),
            ("AVAILABLE", None, "IN_STOCK"),
            ("available_in_stores", None, "IN_STOCK"),
            ("pickup_available", None, "IN_STOCK"),
            ("متوفر", None, "IN_STOCK"),
            ("متاح", None, "IN_STOCK"),
            ("true", None, "IN_STOCK"),
            (True, None, "IN_STOCK"),
            (1, None, "IN_STOCK"),
            # Fallback to availability_status when raw_val is None
            (None, "in_stock", "IN_STOCK"),
            (None, AvailabilityStatus.IN_STOCK, "IN_STOCK"),
            ("", "available", "IN_STOCK"),

            # OUT_OF_STOCK variations
            ("out_of_stock", None, "OUT_OF_STOCK"),
            ("OUT_OF_STOCK", None, "OUT_OF_STOCK"),
            ("Out of Stock", None, "OUT_OF_STOCK"),
            ("sold_out", None, "OUT_OF_STOCK"),
            ("sold out", None, "OUT_OF_STOCK"),
            ("نفذت الكمية", None, "OUT_OF_STOCK"),
            ("غير متوفر", None, "OUT_OF_STOCK"),
            ("غير متاح", None, "OUT_OF_STOCK"),
            ("discontinued", None, "OUT_OF_STOCK"),
            ("delisted", None, "OUT_OF_STOCK"),
            ("false", None, "OUT_OF_STOCK"),
            (False, None, "OUT_OF_STOCK"),
            (0, None, "OUT_OF_STOCK"),
            # Fallback to availability_status
            (None, "out_of_stock", "OUT_OF_STOCK"),
            (None, AvailabilityStatus.OUT_OF_STOCK, "OUT_OF_STOCK"),

            # LIMITED_STOCK and LOW_STOCK_SIGNAL variations
            ("limited_stock", None, "LIMITED_STOCK"),
            ("LIMITED_STOCK", None, "LIMITED_STOCK"),
            ("low_stock_signal", None, "LOW_STOCK_SIGNAL"),
            ("LOW_STOCK_SIGNAL", None, "LOW_STOCK_SIGNAL"),
            ("low_stock", None, "LIMITED_STOCK"),
            ("كمية محدودة", None, "LIMITED_STOCK"),
            ("only 3 left", None, "LIMITED_STOCK"),
            ("باقي 2 فقط", None, "LIMITED_STOCK"),
            (None, "limited_stock", "LIMITED_STOCK"),
            (None, AvailabilityStatus.LIMITED_STOCK, "LIMITED_STOCK"),

            # PREORDER variations
            ("preorder", None, "PREORDER"),
            ("pre_order", None, "PREORDER"),
            ("حجز مسبق", None, "PREORDER"),
            (None, "pre_order", "PREORDER"),

            # UNKNOWN fallback
            (None, None, "UNKNOWN"),
            ("invalid_status_xyz", None, "UNKNOWN"),
        ],
    )
    def test_normalize_stock_status_mapping(self, raw_val, avail, expected):
        assert normalize_stock_status(raw_val, avail) == expected

    @pytest.mark.parametrize(
        "raw_val,stock_val,expected",
        [
            ("in_stock", None, "in_stock"),
            ("IN_STOCK", None, "in_stock"),
            ("متوفر", None, "in_stock"),
            (None, "IN_STOCK", "in_stock"),
            (None, "AVAILABLE", "in_stock"),
            ("out_of_stock", None, "out_of_stock"),
            ("نفذت الكمية", None, "out_of_stock"),
            (None, "OUT_OF_STOCK", "out_of_stock"),
            ("low_stock_signal", None, "limited_stock"),
            (None, "LIMITED_STOCK", "limited_stock"),
            (None, "LOW_STOCK_SIGNAL", "limited_stock"),
            ("preorder", None, "pre_order"),
            (None, "PREORDER", "pre_order"),
            (None, None, "unknown"),
        ],
    )
    def test_normalize_availability_status_mapping(self, raw_val, stock_val, expected):
        assert normalize_availability_status(raw_val, stock_val) == expected


class TestImageUrlNormalization:
    @pytest.mark.parametrize(
        "raw_url,expected",
        [
            ("//cdn.shopify.com/s/files/1/prod.jpg", "https://cdn.shopify.com/s/files/1/prod.jpg"),
            ("//eg.jumia.is/unsafe/fit-in/product.jpg", "https://eg.jumia.is/unsafe/fit-in/product.jpg"),
            ("https://tradelinestores.com/logo.png", "https://tradelinestores.com/logo.png"),
            ("http://example.com/item.png", "http://example.com/item.png"),
            ("  https://example.com/trimmed.jpg  ", "https://example.com/trimmed.jpg"),
            (None, None),
            ("", None),
            ("   ", None),
            ("none", None),
            ("null", None),
        ],
    )
    def test_normalize_image_url(self, raw_url, expected):
        assert normalize_image_url(raw_url) == expected


class TestSchemaIntegration:
    def test_product_model_cleans_protocol_relative_image(self):
        p = Product(
            source_id="test_store",
            source_product_id="sku-101",
            product_name="Test Smartphone 5G",
            product_url="https://teststore.com/p/101",
            image_url="//cdn.shopify.com/files/phone.jpg",
        )
        assert p.image_url == "https://cdn.shopify.com/files/phone.jpg"

    def test_product_observation_normalizes_stock_status_and_availability(self):
        # 1. Raw LOW_STOCK_SIGNAL preserved as canonical LOW_STOCK_SIGNAL
        obs1 = ProductObservation(
            product_id="test:1",
            stock_status="LOW_STOCK_SIGNAL",
        )
        assert obs1.stock_status == "LOW_STOCK_SIGNAL"
        assert obs1.availability_status == AvailabilityStatus.LIMITED_STOCK

        # 2. None stock_status inferred from in_stock availability
        obs2 = ProductObservation(
            product_id="test:2",
            availability_status=AvailabilityStatus.IN_STOCK,
        )
        assert obs2.stock_status == "IN_STOCK"
        assert obs2.availability_status == AvailabilityStatus.IN_STOCK

        # 3. Arabic out of stock text
        obs3 = ProductObservation(
            product_id="test:3",
            stock_status="غير متوفر",
        )
        assert obs3.stock_status == "OUT_OF_STOCK"
        assert obs3.availability_status == AvailabilityStatus.OUT_OF_STOCK


class TestSameDayObservationDeduplication:
    def test_idempotent_insert_observations(self):
        conn = duckdb.connect(":memory:")
        conn.execute("""
            CREATE TABLE fact_observation (
                observation_id      TEXT PRIMARY KEY,
                product_id          TEXT,
                source_id           TEXT,
                source_product_id   TEXT,
                department          TEXT,
                run_date            DATE NOT NULL,
                run_id              TEXT,
                observed_at         TIMESTAMP,
                collection_mode     TEXT,
                price               DOUBLE PRECISION,
                old_price           DOUBLE PRECISION,
                discount            DOUBLE PRECISION,
                currency            TEXT DEFAULT 'EGP',
                raw_price_text      TEXT,
                availability_status TEXT,
                availability_scope  TEXT,
                stock_status        TEXT,
                raw_availability_text TEXT,
                delivery_available  BOOLEAN,
                delivery_eta        TEXT,
                delivery_fee        DOUBLE PRECISION,
                delivery_status     TEXT,
                seller_name         TEXT,
                fulfillment_method  TEXT,
                quality_score       DOUBLE PRECISION,
                row_hash            TEXT
            );
        """)

        test_obs_run1 = [
            {
                "product_id": "tradeline:iphone16",
                "price": 50000.0,
                "availability_status": "in_stock",
                "stock_status": "IN_STOCK",
                "seller_name": "Tradeline Official",
            },
            {
                "product_id": "tradeline:macbook_air",
                "price": 60000.0,
                "availability_status": "in_stock",
                "stock_status": None,
                "seller_name": "",
            },
        ]

        # First run on 2026-10-02
        insert_observations(
            conn=conn,
            observations=test_obs_run1,
            source_id="tradeline",
            run_id="run_morning",
            run_date="2026-10-02",
            mode="live",
            quality_score=0.98,
        )

        assert conn.execute("SELECT count(*) FROM fact_observation").fetchone()[0] == 2

        # Second run on the same date with price update
        test_obs_run2 = [
            {
                "product_id": "tradeline:iphone16",
                "price": 49000.0,  # Price dropped
                "availability_status": "in_stock",
                "stock_status": "IN_STOCK",
                "seller_name": "Tradeline Official",
            },
            {
                "product_id": "tradeline:macbook_air",
                "price": 59000.0,  # Price dropped
                "availability_status": "out_of_stock",
                "stock_status": "غير متوفر",
                "seller_name": "",
            },
            # Duplicate item inside the same batch
            {
                "product_id": "tradeline:macbook_air",
                "price": 59000.0,
                "availability_status": "out_of_stock",
                "stock_status": "غير متوفر",
                "seller_name": "",
            },
        ]

        insert_observations(
            conn=conn,
            observations=test_obs_run2,
            source_id="tradeline",
            run_id="run_evening",
            run_date="2026-10-02",
            mode="live",
            quality_score=0.99,
        )

        # Total rows must remain exactly 2 (no duplicates added!)
        cnt = conn.execute("SELECT count(*) FROM fact_observation").fetchone()[0]
        assert cnt == 2

        # Verify updated values
        row = conn.execute("SELECT price, stock_status, availability_status FROM fact_observation WHERE product_id = 'tradeline:macbook_air'").fetchone()
        assert row[0] == 59000.0
        assert row[1] == "OUT_OF_STOCK"
        assert row[2] == "out_of_stock"
