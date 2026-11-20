"""
Tests for Dream 2000 source package.
All tests run fully offline using fixtures.
"""

import pytest
from pathlib import Path

from extractors.source_dream2000.parser import parse_shopify_products_json
from extractors.source_dream2000.extractor import Dream2000Extractor
from extractors.source_dream2000 import Dream2000Extractor as Dream2000ExtractorFromInit
from normalization.schema import (
    AvailabilityScope,
    AvailabilityStatus,
    ComplianceStatus,
    Currency,
    ExtractionMethod,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestDream2000Parser:
    def test_parse_fixture_returns_two_products(self):
        fixture = FIXTURES_DIR / "dream2000_products_sample.json"
        assert fixture.exists(), "Dream2000 fixture must exist"
        data = fixture.read_text(encoding="utf-8")
        products, observations = parse_shopify_products_json(data)

        assert len(products) == 2
        assert len(observations) == 2

    def test_source_id_is_dream2000(self):
        data = (FIXTURES_DIR / "dream2000_products_sample.json").read_text()
        products, _ = parse_shopify_products_json(data)
        for p in products:
            assert p.source_id == "dream2000"

    def test_arabic_title_preserved(self):
        """Arabic product titles must be stored as-is."""
        data = (FIXTURES_DIR / "dream2000_products_sample.json").read_text()
        products, _ = parse_shopify_products_json(data)
        # First product has Arabic title starting with هونر
        assert any("\u0647\u0648\u0646\u0631" in p.product_name for p in products)

    def test_prices_parsed_correctly(self):
        data = (FIXTURES_DIR / "dream2000_products_sample.json").read_text()
        _, observations = parse_shopify_products_json(data)
        honor_obs = observations[0]
        assert honor_obs.price == 29990.0
        assert honor_obs.old_price == 36000.0
        assert honor_obs.discount is not None and honor_obs.discount > 0

    def test_no_stock_quantity(self):
        """Shopify sources must NEVER expose stock_quantity."""
        data = (FIXTURES_DIR / "dream2000_products_sample.json").read_text()
        _, observations = parse_shopify_products_json(data)
        for obs in observations:
            assert obs.stock_quantity is None

    def test_currency_egp(self):
        data = (FIXTURES_DIR / "dream2000_products_sample.json").read_text()
        _, observations = parse_shopify_products_json(data)
        for obs in observations:
            assert obs.currency == Currency.EGP

    def test_availability_scope_global(self):
        data = (FIXTURES_DIR / "dream2000_products_sample.json").read_text()
        _, observations = parse_shopify_products_json(data)
        for obs in observations:
            assert obs.availability_scope == AvailabilityScope.GLOBAL

    def test_product_urls_correct_domain(self):
        data = (FIXTURES_DIR / "dream2000_products_sample.json").read_text()
        products, _ = parse_shopify_products_json(data)
        for p in products:
            assert "dream2000.com" in p.product_url


class TestDream2000Extractor:
    def test_extractor_import_from_package(self):
        from extractors.source_dream2000 import Dream2000Extractor as DE
        ext = DE()
        assert ext is not None

    def test_source_config(self):
        ext = Dream2000Extractor()
        config = ext.source_config()
        assert config.source_id == "dream2000"
        assert config.source_name == "Dream 2000"
        assert config.domain == "dream2000.com"
        assert config.compliance_status == ComplianceStatus.UNKNOWN
        assert config.extraction_method == ExtractionMethod.PUBLIC_JSON

    def test_package_init_re_exports_correctly(self):
        assert Dream2000ExtractorFromInit is Dream2000Extractor
