"""
Tests for Tradeline source package.
All tests run fully offline using fixtures.
"""

import pytest
from pathlib import Path

from extractors.source_tradeline.parser import (
    parse_shopify_products_json,
    parse_store_locator_html,
)
from extractors.source_tradeline.extractor import TradelineExtractor
from extractors.source_tradeline import TradelineExtractor as TradelineExtractorFromInit
from normalization.schema import (
    AvailabilityScope,
    AvailabilityStatus,
    ComplianceStatus,
    ExtractionMethod,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestTradelineParser:
    def test_parse_shopify_products_json_from_fixture(self):
        """Parse the real fixture — must return 2 products and 2 observations."""
        fixture = FIXTURES_DIR / "tradeline_products_sample.json"
        assert fixture.exists(), "Fixture file must exist"

        data = fixture.read_text(encoding="utf-8")
        products, observations = parse_shopify_products_json(data)

        assert len(products) == 2
        assert len(observations) == 2

    def test_first_product_fields(self):
        data = (FIXTURES_DIR / "tradeline_products_sample.json").read_text()
        products, observations = parse_shopify_products_json(data)

        iphone = products[0]
        assert "iPhone" in iphone.product_name or "Apple" in (iphone.brand or "")
        assert iphone.source_id == "tradeline"
        assert iphone.sku is not None
        assert iphone.product_url.startswith("https://www.tradelinestores.com")
        assert iphone.image_url is not None

    def test_second_product_discount(self):
        data = (FIXTURES_DIR / "tradeline_products_sample.json").read_text()
        products, observations = parse_shopify_products_json(data)

        airpods_obs = observations[1]
        # AirPods has compare_at_price=10999, price=8999 → discount ~18.2%
        assert airpods_obs.old_price == 10999.0
        assert airpods_obs.price == 8999.0
        assert airpods_obs.discount is not None
        assert airpods_obs.discount > 0

    def test_no_stock_quantity(self):
        """Shopify sources must NEVER expose stock_quantity."""
        data = (FIXTURES_DIR / "tradeline_products_sample.json").read_text()
        _, observations = parse_shopify_products_json(data)
        for obs in observations:
            assert obs.stock_quantity is None, (
                "stock_quantity must be None — Shopify does not expose inventory counts"
            )

    def test_availability_status_in_stock(self):
        data = (FIXTURES_DIR / "tradeline_products_sample.json").read_text()
        _, observations = parse_shopify_products_json(data)
        for obs in observations:
            assert obs.availability_status in (
                AvailabilityStatus.IN_STOCK,
                AvailabilityStatus.OUT_OF_STOCK,
            )

    def test_availability_scope_global(self):
        """Shopify /products.json = global catalog scope, not location-specific."""
        data = (FIXTURES_DIR / "tradeline_products_sample.json").read_text()
        _, observations = parse_shopify_products_json(data)
        for obs in observations:
            assert obs.availability_scope == AvailabilityScope.GLOBAL

    def test_currency_egp(self):
        data = (FIXTURES_DIR / "tradeline_products_sample.json").read_text()
        _, observations = parse_shopify_products_json(data)
        from normalization.schema import Currency
        for obs in observations:
            assert obs.currency == Currency.EGP

    def test_source_id_propagates(self):
        data = (FIXTURES_DIR / "tradeline_products_sample.json").read_text()
        products, observations = parse_shopify_products_json(data, source_id="tradeline")
        for p in products:
            assert p.source_id == "tradeline"

    def test_custom_source_id(self):
        """Parser must propagate custom source_id (used by dream2000 reuse)."""
        data = (FIXTURES_DIR / "tradeline_products_sample.json").read_text()
        products, observations = parse_shopify_products_json(data, source_id="custom_test")
        for p in products:
            assert p.source_id == "custom_test"


class TestTradelineStoreLocatorParser:
    def test_parse_locator_fixture(self):
        fixture = FIXTURES_DIR / "tradeline_locator_sample.html"
        assert fixture.exists()
        html = fixture.read_text(encoding="utf-8")
        locations = parse_store_locator_html(html)

        assert len(locations) == 2

    def test_location_names(self):
        html = (FIXTURES_DIR / "tradeline_locator_sample.html").read_text()
        locations = parse_store_locator_html(html)
        names = [loc.branch_name for loc in locations]
        assert "Tradeline Arkan" in names
        assert "Tradeline City Centre Alexandria" in names

    def test_location_coordinates(self):
        html = (FIXTURES_DIR / "tradeline_locator_sample.html").read_text()
        locations = parse_store_locator_html(html)
        arkan = next(l for l in locations if "Arkan" in (l.branch_name or ""))
        assert arkan.latitude == pytest.approx(30.0203759)
        assert arkan.longitude == pytest.approx(31.0035838)

    def test_location_source_id(self):
        html = (FIXTURES_DIR / "tradeline_locator_sample.html").read_text()
        locations = parse_store_locator_html(html)
        for loc in locations:
            assert loc.source_id == "tradeline"

    def test_location_type_store(self):
        from normalization.schema import LocationType
        html = (FIXTURES_DIR / "tradeline_locator_sample.html").read_text()
        locations = parse_store_locator_html(html)
        for loc in locations:
            assert loc.location_type == LocationType.STORE


class TestTradelineExtractor:
    def test_extractor_import_from_package(self):
        """Package-level import must work."""
        from extractors.source_tradeline import TradelineExtractor as TE
        ext = TE()
        assert ext is not None

    def test_extractor_import_from_extractor_module(self):
        from extractors.source_tradeline.extractor import TradelineExtractor as TE
        ext = TE()
        config = ext.source_config()
        assert config.source_id == "tradeline"

    def test_source_config(self):
        ext = TradelineExtractor()
        config = ext.source_config()
        assert config.source_id == "tradeline"
        assert config.source_name == "Tradeline Stores"
        assert config.domain == "tradelinestores.com"
        # Tradeline is compliance D — should NOT be enabled
        # The underlying ShopifyExtractor sets enabled=True but compliance_status=UNKNOWN
        # blocks it at the compliance gate
        assert config.compliance_status == ComplianceStatus.UNKNOWN
        assert config.extraction_method == ExtractionMethod.PUBLIC_JSON

    def test_package_init_re_exports_correctly(self):
        """__init__.py re-export must be the same class."""
        assert TradelineExtractorFromInit is TradelineExtractor
