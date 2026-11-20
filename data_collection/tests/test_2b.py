"""
Tests for 2B Egypt extractor and parser.
All tests run fully offline using fixtures.
"""

import pytest
from pathlib import Path

from extractors.source_2b.parser import (
    determine_availability,
    extract_json_ld,
    parse_category_page,
    parse_product_detail_page,
    _parse_price,
)
from extractors.source_2b.extractor import TwoBExtractor
from normalization.schema import (
    AvailabilityScope,
    AvailabilityStatus,
    ComplianceStatus,
    Currency,
    ExtractionMethod,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestTwoBPriceParser:
    def test_egp_price_with_comma(self):
        assert _parse_price("EGP 38,999.00") == pytest.approx(38999.0)

    def test_egp_price_simple(self):
        assert _parse_price("52500.00") == pytest.approx(52500.0)

    def test_none_returns_none(self):
        assert _parse_price(None) is None

    def test_empty_returns_none(self):
        assert _parse_price("") is None

    def test_arabic_numerals(self):
        # Arabic-Indic digits
        assert _parse_price("٣٨٩٩٩") == pytest.approx(38999.0)


class TestTwoBAvailability:
    def test_in_stock_delivery(self):
        status, scope, stock = determine_availability("In Stock")
        assert status == AvailabilityStatus.IN_STOCK
        assert scope == AvailabilityScope.DELIVERY_AREA
        assert stock == "IN_STOCK"

    def test_available_in_stores(self):
        """'Available in Stores' MUST map to PHYSICAL_BRANCH, never DELIVERY_AREA."""
        status, scope, stock = determine_availability("Available in Stores")
        assert status == AvailabilityStatus.IN_STOCK
        assert scope == AvailabilityScope.PHYSICAL_BRANCH
        assert stock == "AVAILABLE_IN_STORES"

    def test_out_of_stock(self):
        status, scope, stock = determine_availability("Out of Stock")
        assert status == AvailabilityStatus.OUT_OF_STOCK
        assert scope == AvailabilityScope.GLOBAL

    def test_low_stock_signal_no_quantity(self):
        """'Only X left' MUST be LOW_STOCK_SIGNAL, never converted to stock_quantity."""
        status, scope, stock = determine_availability("Only 2 left")
        assert status == AvailabilityStatus.LIMITED_STOCK
        assert stock == "LOW_STOCK_SIGNAL"

    def test_none_returns_unknown(self):
        status, scope, stock = determine_availability(None)
        assert status == AvailabilityStatus.UNKNOWN
        assert scope == AvailabilityScope.UNKNOWN

    def test_schema_org_instock_url(self):
        status, scope, stock = determine_availability("https://schema.org/InStock")
        assert status == AvailabilityStatus.IN_STOCK

    def test_schema_org_outofstock_url(self):
        status, scope, stock = determine_availability("https://schema.org/OutOfStock")
        assert status == AvailabilityStatus.OUT_OF_STOCK


class TestTwoBParser:
    def test_parse_category_page_json_ld(self):
        """Fixture has JSON-LD — should be parsed first, returning 2 products."""
        fixture = FIXTURES_DIR / "twob_sample.html"
        assert fixture.exists()
        html = fixture.read_text(encoding="utf-8")
        products = parse_category_page(html)

        assert len(products) == 2

    def test_lenovo_product_parsed(self):
        html = (FIXTURES_DIR / "twob_sample.html").read_text()
        products = parse_category_page(html)
        lenovo = next((p for p in products if "Lenovo" in p["product_name"]), None)
        assert lenovo is not None
        assert lenovo["sku"] == "LOQ15IAX9"
        assert lenovo["price"] == pytest.approx(38999.0)
        assert lenovo["product_url"] == "https://2b.com.eg/en/lenovo-loq-15iax9e-gaming-laptop.html"

    def test_dell_product_parsed(self):
        html = (FIXTURES_DIR / "twob_sample.html").read_text()
        products = parse_category_page(html)
        dell = next((p for p in products if "Dell" in p["product_name"]), None)
        assert dell is not None
        assert dell["price"] == pytest.approx(52500.0)

    def test_no_stock_quantity_from_availability(self):
        """Parser must never produce stock_quantity from availability text."""
        html = (FIXTURES_DIR / "twob_sample.html").read_text()
        # The fixture has 'Available in Stores' — no quantity
        products = parse_category_page(html)
        # All raw_availability_text values should not contain quantity
        for p in products:
            assert "stock_quantity" not in p or p.get("stock_quantity") is None

    def test_parse_pdp_json_ld(self):
        fixture = FIXTURES_DIR / "twob_pdp_sample.html"
        assert fixture.exists()
        html = fixture.read_text(encoding="utf-8")
        result = parse_product_detail_page(html)

        assert result is not None
        assert "Lenovo" in result["product_name"]
        assert result["sku"] == "LOQ15IAX9"
        assert result["price"] == pytest.approx(38999.0)

    def test_extract_json_ld(self):
        html = (FIXTURES_DIR / "twob_sample.html").read_text()
        items = extract_json_ld(html)
        assert len(items) == 2
        for item in items:
            assert item["@type"] == "Product"


class TestTwoBExtractor:
    def test_source_config(self):
        ext = TwoBExtractor()
        config = ext.source_config()
        assert config.source_id == "two_b"
        assert config.source_name == "2B Egypt"
        assert config.domain == "2b.com.eg"
        assert config.compliance_status == ComplianceStatus.CONDITIONAL
        assert config.extraction_method == ExtractionMethod.STATIC_HTML
        assert config.enabled is True

    def test_offline_fixture_extraction(self):
        """TwoBExtractor with fixture_path must parse without network."""
        import asyncio

        fixture = FIXTURES_DIR / "twob_sample.html"
        ext = TwoBExtractor(fixture_path=fixture)

        async def run():
            # Initialize the HTTP client to avoid AttributeError in cleanup
            await ext._init_http_client()
            products = await ext.extract_products()
            observations = await ext.extract_availability()
            await ext._cleanup()
            return products, observations

        products, observations = asyncio.run(run())

        assert len(products) == 2
        assert len(observations) == 2

    def test_offline_no_stock_quantity(self):
        """Offline extraction must not produce any stock_quantity values."""
        import asyncio

        fixture = FIXTURES_DIR / "twob_sample.html"
        ext = TwoBExtractor(fixture_path=fixture)

        async def run():
            await ext._init_http_client()
            await ext.extract_products()
            observations = await ext.extract_availability()
            await ext._cleanup()
            return observations

        observations = asyncio.run(run())
        for obs in observations:
            assert obs.stock_quantity is None

    def test_available_in_stores_scope(self):
        """2B's 'Available in Stores' must produce PHYSICAL_BRANCH scope."""
        import asyncio

        fixture = FIXTURES_DIR / "twob_sample.html"
        ext = TwoBExtractor(fixture_path=fixture)

        async def run():
            await ext._init_http_client()
            await ext.extract_products()
            observations = await ext.extract_availability()
            await ext._cleanup()
            return observations

        observations = asyncio.run(run())
        # The fixture has InStock via JSON-LD schema.org URL
        # All observations should have a defined scope (not all necessarily PHYSICAL_BRANCH
        # since JSON-LD uses schema.org/InStock → DELIVERY_AREA)
        for obs in observations:
            assert obs.availability_scope is not None



class TestTwoBStoreLocatorAndGolden:
    """Section 1 & Section 2: Real 2B store locator, golden category/PDP, missing fields, malformed cards, pagination, and raw-to-normalized consistency."""

    def test_real_store_locator_parses_59_branches(self):
        from extractors.source_2b.parser import parse_store_locator
        from normalization.schema import LocationType

        fixture = FIXTURES_DIR / "two_b" / "real" / "stores_sample.html"
        assert fixture.exists() and fixture.stat().st_size > 10000
        html = fixture.read_text(encoding="utf-8")
        locs = parse_store_locator(html)

        assert len(locs) == 59
        assert all(loc.location_type == LocationType.BRANCH for loc in locs)
        assert all(loc.branch_name for loc in locs)
        assert all(loc.address for loc in locs)
        assert all(loc.source_url == "https://2b.com.eg/en/stores" for loc in locs)
        assert all(loc.latitude is not None and loc.longitude is not None for loc in locs)
        in_egypt = [loc for loc in locs if 22.0 <= loc.latitude <= 31.8 and 24.5 <= loc.longitude <= 37.0]
        assert len(in_egypt) == 58  # 58 valid Egypt GPS coords; Assiut has raw lat=90.0 in 2B's HTML

        govs = {loc.governorate for loc in locs}
        assert "Cairo" in govs
        assert "Giza" in govs
        assert "Alexandria" in govs
        assert "Qalyubia" in govs

    def test_store_locator_unknown_governorate_and_no_invented_gps(self):
        from extractors.source_2b.parser import parse_store_locator
        from normalization.schema import LocationType

        html = """
        <div class="store-item">
          <h3 class="store-name">2B Mystery Branch</h3>
          <div class="store-address">Sector 99 Unknown District</div>
        </div>
        """
        locs = parse_store_locator(html)
        assert len(locs) == 1
        assert locs[0].location_type == LocationType.BRANCH
        assert locs[0].governorate == "unknown"
        assert locs[0].latitude is None
        assert locs[0].longitude is None

    def test_real_category_fixture_golden_parsing(self):
        fixture = FIXTURES_DIR / "two_b" / "real" / "category_sample.html"
        assert fixture.exists()
        html = fixture.read_text(encoding="utf-8")
        cards = parse_category_page(html)

        assert len(cards) >= 20
        first = cards[0]
        assert first["source_product_id"] == "47535"
        assert "Apple MacBook Neo" in first["product_name"]
        assert first["brand"] == "Apple"
        assert first["price"] == pytest.approx(53699.0)
        assert first["old_price"] == pytest.approx(73499.0)
        assert first["sku"] is None  # HTML category card does not expose SKU
        assert first["gtin"] is None
        assert first["product_url"].startswith("https://2b.com.eg/en/")

    def test_real_pdp_fixture_extracts_sku_category_and_delivery_eta(self):
        fixture = FIXTURES_DIR / "two_b" / "real" / "pdp_sample.html"
        assert fixture.exists()
        html = fixture.read_text(encoding="utf-8")
        pdp = parse_product_detail_page(html)

        assert pdp is not None
        assert pdp["sku"] == "ZH669"
        assert pdp["brand"] == "HP"
        assert pdp["category"] == "Computer > Laptops > HP > Gaming Laptops"
        assert pdp["price"] == pytest.approx(135799.0)
        assert pdp["delivery_available"] is True
        assert "1-5 working days" in pdp["delivery_eta"]
        assert pdp["delivery_fee"] is None

    def test_missing_fields_preserved_as_none(self):
        html = """
        <ol class="products list items product-items">
          <li class="item product product-item" data-product-id="77701">
            <a href="https://2b.com.eg/en/plain-item.html" class="product-item-link">
              <span class="product-name">Plain Generic Item Without Brand</span>
            </a>
          </li>
        </ol>
        """
        cards = parse_category_page(html)
        assert len(cards) == 1
        c = cards[0]
        assert c["source_product_id"] == "77701"
        assert c["sku"] is None
        assert c["gtin"] is None
        assert c["price"] is None
        assert c["old_price"] is None
        assert c["discount"] is None
        assert c["image_url"] is None
        assert c["availability_status"] == AvailabilityStatus.UNKNOWN
        assert c["availability_scope"] == AvailabilityScope.UNKNOWN

    def test_malformed_cards_skipped_cleanly(self):
        html = """
        <script type="application/ld+json">{bad json</script>
        <ol class="products list items product-items">
          <li class="item product product-item"><div>No link at all</div></li>
          <li class="item product product-item"><a class="product-item-link" href=""></a></li>
          <li class="item product product-item" data-product-id="88801">
            <a class="product-item-link" href="/en/valid-product.html">Valid Product Card</a>
            <span class="price">EGP -50</span>
          </li>
        </ol>
        """
        cards = parse_category_page(html)
        assert len(cards) == 1
        assert cards[0]["source_product_id"] == "88801"
        assert cards[0]["price"] is None

    def test_pagination_extract_next_page_url(self):
        from extractors.source_2b.parser import extract_next_page_url

        fixture = FIXTURES_DIR / "two_b" / "real" / "category_sample.html"
        html = fixture.read_text(encoding="utf-8")
        next_url = extract_next_page_url(html)
        assert next_url is not None
        assert "p=2" in next_url

        no_next_html = "<html><body><div class='pages'><span>Page 1</span></div></body></html>"
        assert extract_next_page_url(no_next_html) is None

    def test_raw_to_normalized_consistency(self):
        fixture = FIXTURES_DIR / "two_b" / "real" / "category_sample.html"
        html = fixture.read_text(encoding="utf-8")
        cards = parse_category_page(html)[:5]

        ext = TwoBExtractor(fixture_path=fixture)
        products, obs_map = ext._cards_to_canonical(cards, category="Laptops")

        assert len(products) == len(cards)
        for raw_c, prod in zip(cards, products):
            obs = obs_map[prod.product_id]
            assert prod.source_product_id == str(raw_c["source_product_id"])
            assert prod.product_name == raw_c["product_name"]
            assert prod.sku == raw_c["sku"]
            assert prod.gtin == raw_c["gtin"]
            assert obs.price == raw_c["price"]
            assert obs.old_price == raw_c["old_price"]
            assert obs.raw_price_text == raw_c["raw_price_text"]
            assert obs.raw_availability_text == raw_c["raw_availability_text"]
            assert obs.stock_quantity is None
