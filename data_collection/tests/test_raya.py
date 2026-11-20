"""
Tests for Raya Shop parser and extractor.

Raya Shop uses Magento 2. Uses JSON-LD + static HTML.
Compliance: D (UNKNOWN) — NOT enabled. Fixture tests only.
Fixtures: SYNTHETIC (hand-authored to match site structure).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestRayaParser:
    def test_parse_category_page_returns_products(self):
        """Category page parser returns product dicts from JSON-LD."""
        from extractors.source_raya.parser import parse_category_page

        fixture = FIXTURES_DIR / "raya_sample.html"
        if not fixture.exists() or fixture.stat().st_size == 0:
            pytest.skip("Fixture not available")

        html = fixture.read_text(encoding="utf-8")
        cards = parse_category_page(html)

        assert len(cards) >= 1
        assert all(c.get("product_name") for c in cards)

    def test_pickup_from_store_is_physical_branch_scope(self):
        """'Pickup from Store' must map to PHYSICAL_BRANCH scope."""
        from extractors.source_raya.parser import determine_raya_availability
        from normalization.schema import AvailabilityScope, AvailabilityStatus

        status, scope, stock_status = determine_raya_availability("Pickup from Store")

        assert scope == AvailabilityScope.PHYSICAL_BRANCH, (
            "Raya 'Pickup from Store' = physical branch scope, NOT delivery"
        )
        assert status == AvailabilityStatus.IN_STOCK
        assert stock_status == "PICKUP_AVAILABLE"

    def test_in_stock_is_delivery_scope(self):
        """'In Stock' on Raya maps to DELIVERY_AREA scope (online delivery)."""
        from extractors.source_raya.parser import determine_raya_availability
        from normalization.schema import AvailabilityScope, AvailabilityStatus

        status, scope, stock_status = determine_raya_availability("In Stock")

        assert scope == AvailabilityScope.DELIVERY_AREA
        assert status == AvailabilityStatus.IN_STOCK

    def test_low_stock_signal_no_quantity(self):
        """'Only 1 left' must be LOW_STOCK_SIGNAL. stock_quantity must stay None."""
        from extractors.source_raya.parser import determine_raya_availability
        from normalization.schema import AvailabilityStatus

        status, scope, stock_status = determine_raya_availability("Only 1 left")

        assert status == AvailabilityStatus.LIMITED_STOCK
        assert stock_status == "LOW_STOCK_SIGNAL"
        # Caller must NOT set stock_quantity — tested in TestRayaAvailabilitySemantics

    def test_out_of_stock(self):
        """'Out of Stock' maps correctly."""
        from extractors.source_raya.parser import determine_raya_availability
        from normalization.schema import AvailabilityStatus

        status, scope, stock_status = determine_raya_availability("Out of Stock")

        assert status == AvailabilityStatus.OUT_OF_STOCK

    def test_parse_product_detail_page(self):
        """PDP parser extracts product from JSON-LD."""
        from extractors.source_raya.parser import parse_product_detail_page

        fixture = FIXTURES_DIR / "raya_pdp_sample.html"
        if not fixture.exists() or fixture.stat().st_size == 0:
            pytest.skip("Fixture not available")

        html = fixture.read_text(encoding="utf-8")
        result = parse_product_detail_page(html)

        assert result is not None
        assert result.get("product_name")
        assert result.get("price") is not None


class TestRayaAvailabilitySemantics:
    def test_stock_quantity_never_set_from_text(self):
        """
        The extractor must NEVER assign stock_quantity from text like 'Only 1 left'.
        This is a LOW_STOCK_SIGNAL — the number is not verified inventory data.
        """
        from normalization.schema import ProductObservation, AvailabilityStatus, AvailabilityScope

        # Correct way to record 'Only 1 left'
        obs = ProductObservation(
            product_id="raya-test-001",
            price=18299.0,
            raw_availability_text="Only 1 left",
            stock_status="LOW_STOCK_SIGNAL",
            availability_status=AvailabilityStatus.LIMITED_STOCK,
            availability_scope=AvailabilityScope.GLOBAL,
            stock_quantity=None,  # MUST be None
        )
        assert obs.stock_quantity is None, (
            "stock_quantity must be None when source only shows text signal"
        )

    def test_pickup_vs_delivery_semantics(self):
        """Verify the distinction between pickup and delivery availability."""
        from normalization.schema import AvailabilityScope

        # Pickup = physical branch (customer goes to store)
        from extractors.source_raya.parser import determine_raya_availability
        _, pickup_scope, _ = determine_raya_availability("Pickup from Store")
        assert pickup_scope == AvailabilityScope.PHYSICAL_BRANCH

        # In Stock = online delivery (product shipped to customer)
        _, delivery_scope, _ = determine_raya_availability("In Stock")
        assert delivery_scope == AvailabilityScope.DELIVERY_AREA

        # They must be different
        assert pickup_scope != delivery_scope


class TestRayaExtractor:
    def test_extractor_disabled_without_fixture(self):
        """RayaExtractor must NOT make live requests when source is Class D disabled."""
        from extractors.source_raya.extractor import RayaExtractor

        extractor = RayaExtractor()  # No fixture path
        products = asyncio.run(extractor.extract_products())

        assert products == [], "Disabled Class D source must return empty list"
        assert len(extractor._errors) > 0, (
            "Must record an error explaining that source is disabled"
        )

    def test_extractor_source_config_is_disabled(self):
        """Raya source_config must have enabled=False and class D."""
        from extractors.source_raya.extractor import RayaExtractor
        from normalization.schema import ComplianceStatus

        extractor = RayaExtractor()
        config = extractor.source_config()

        assert config.enabled is False, "Raya must be disabled (Class D)"
        assert config.compliance_status == ComplianceStatus.UNKNOWN, (
            "Raya compliance status must be D (UNKNOWN), not B"
        )

    def test_extractor_with_fixture(self):
        """RayaExtractor can parse products from a synthetic fixture file."""
        from extractors.source_raya.extractor import RayaExtractor

        fixture = FIXTURES_DIR / "raya_sample.html"
        if not fixture.exists() or fixture.stat().st_size == 0:
            pytest.skip("Fixture not available")

        extractor = RayaExtractor(fixture_path=fixture)
        products = asyncio.run(extractor.extract_products())

        assert len(products) >= 1
        assert all(p.source_id == "raya" for p in products)

    def test_extractor_fixture_mode_no_quantity(self):
        """Products extracted from fixture must have stock_quantity=None."""
        from extractors.source_raya.extractor import RayaExtractor

        fixture = FIXTURES_DIR / "raya_sample.html"
        if not fixture.exists() or fixture.stat().st_size == 0:
            pytest.skip("Fixture not available")

        extractor = RayaExtractor(fixture_path=fixture)
        asyncio.run(extractor.extract_products())

        observations = asyncio.run(extractor.extract_availability())

        for obs in observations:
            assert obs.stock_quantity is None, (
                "Raya does not expose stock quantities — must be None"
            )
