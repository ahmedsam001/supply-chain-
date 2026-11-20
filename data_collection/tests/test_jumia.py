"""
Tests for Jumia Egypt Extractor and Parsers
"""

import pytest
from pathlib import Path

from extractors.source_jumia.extractor import JumiaExtractor
from extractors.source_jumia.parser import (
    determine_availability,
    parse_category_page,
    parse_delivery_zones,
    parse_discount,
    parse_price,
    parse_product_detail_page,
)
from normalization.schema import AvailabilityStatus, ComplianceStatus, ExtractionMethod

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestJumiaParser:
    def test_parse_category_products(self):
        html_file = FIXTURES_DIR / "jumia_sample.html"
        assert html_file.exists()
        html = html_file.read_text(encoding="utf-8")

        products = parse_category_page(html)
        assert len(products) == 5

        # Product 1: Samsung Galaxy A07
        p1 = products[0]
        assert "Samsung Galaxy A07" in p1["product_name"]
        assert p1["source_product_id"] == "133802131"
        assert p1["price"] == 10490.0
        assert p1["old_price"] == 13110.0
        assert p1["discount"] == 20.0
        assert p1["brand"] == "Samsung"
        assert p1["rating"] == 4.2
        assert p1["review_count"] == 15
        assert "133802131.html" in p1["product_url"]

        # Product 4: Samsung S26 Ultra
        p4 = products[3]
        assert "S26 Ultra" in p4["product_name"]
        assert p4["price"] == 72650.0
        assert p4["discount"] == 18.0

    def test_parse_product_detail(self):
        pdp_file = FIXTURES_DIR / "jumia_pdp_sample.html"
        assert pdp_file.exists()
        html = pdp_file.read_text(encoding="utf-8")

        detail = parse_product_detail_page(html)
        assert detail["sku"] == "SA024MP1VCKLDNAFAMZ"
        assert detail["category"] == "Phones & Tablets"
        assert "Mobile Phones" in detail["subcategory"]
        assert "Dream 2000" in detail["seller_name"]
        assert detail["price"] == 10490.0

    def test_parse_prices_and_discounts(self):
        assert parse_price("10,490.00 EGP") == 10490.0
        assert parse_price("١٣٬١١٠") == 13110.0
        assert parse_discount("20%") == 20.0
        assert parse_discount("-18%") == 18.0

    def test_determine_availability(self):
        assert determine_availability("InStock (low stock)") == AvailabilityStatus.LIMITED_STOCK
        assert determine_availability("Only 2 units left") == AvailabilityStatus.LIMITED_STOCK
        assert determine_availability("In Stock") == AvailabilityStatus.IN_STOCK
        assert determine_availability("غير متوفر") == AvailabilityStatus.OUT_OF_STOCK

    def test_delivery_zones(self):
        zones = parse_delivery_zones()
        assert len(zones) == 27
        gov_names = [z["governorate"] for z in zones]
        assert "Cairo" in gov_names
        assert "Giza" in gov_names
        assert "Alexandria" in gov_names


class TestJumiaExtractor:
    def test_source_configuration(self):
        extractor = JumiaExtractor()
        config = extractor.source_config()
        assert config.source_id == "jumia"
        assert config.compliance_status == ComplianceStatus.CONDITIONAL
        assert config.extraction_method == ExtractionMethod.STATIC_HTML
        assert config.rate_limit_rpm <= 30
        assert config.enabled is True



class TestJumiaRealFixturesAndDelivery:
    """Section 3, 4 & 9: Real Jumia category & PDP fixtures, delivery extraction, and malformed card resilience."""

    def test_real_category_fixture_extracts_gtm_sku_and_category(self):
        real_cat = FIXTURES_DIR / "jumia" / "real" / "category_sample.html"
        assert real_cat.exists()
        cards = parse_category_page(real_cat.read_text(encoding="utf-8"))
        assert len(cards) >= 10
        first = cards[0]
        assert first["source_product_id"] == "135151551"
        assert first.get("sku") == "AP848MP1WRW29NAFAMZ"
        assert first.get("brand") == "Apple"
        assert first.get("category") == "Phones & Tablets"

    def test_real_pdp_fixture_extracts_graph_jsonld_seller_and_delivery(self):
        real_pdp = FIXTURES_DIR / "jumia" / "real" / "pdp_sample.html"
        assert real_pdp.exists()
        data = parse_product_detail_page(real_pdp.read_text(encoding="utf-8"))
        assert data["sku"] == "AP848MP1WRW29NAFAMZ"
        assert data["brand"] == "Apple"
        assert data["seller_name"] == "Jumia"
        assert data["price"] == pytest.approx(155500.0)
        assert data["delivery_available"] is True
        assert data["delivery_fee"] == pytest.approx(0.0)
        assert "Ready for delivery" in data["delivery_eta"]

    def test_malformed_jumia_cards_skipped(self):
        html = """
        <section class="card">
          <article class="prd"><div>No anchor</div></article>
          <article class="prd"><a class="core" href="/empty-name-12345.html"></a></article>
          <article class="prd">
            <a class="core" href="/valid-phone-99999.html" data-gtm-id="SKU999">
              <h3 class="name">Valid Phone Model</h3>
              <div class="prc">EGP 5,000</div>
            </a>
          </article>
        </section>
        """
        cards = parse_category_page(html)
        assert len(cards) == 1
        assert cards[0]["source_product_id"] == "99999"
        assert cards[0]["sku"] == "SKU999"


class TestJumiaRealPdpAndDelivery:
    """Tests for Jumia real PDP JSON-LD @graph parsing, delivery extraction, and GTM attributes."""

    def test_real_pdp_fixture_extracts_seller_and_delivery(self):
        from extractors.source_jumia.parser import parse_product_detail_page

        fixture = FIXTURES_DIR / "jumia" / "real" / "pdp_sample.html"
        assert fixture.exists()
        html = fixture.read_text(encoding="utf-8")
        pdp = parse_product_detail_page(html)

        assert pdp is not None
        assert pdp["sku"] == "AP848MP1WRW29NAFAMZ"
        assert pdp["brand"] == "Apple"
        assert pdp["seller_name"] == "Jumia"
        assert pdp["delivery_available"] is True
        assert "Ready for delivery" in pdp["delivery_eta"]
        assert pdp["delivery_fee"] == pytest.approx(0.0)

    def test_card_gtm_attributes_extracted(self):
        from bs4 import BeautifulSoup
        from extractors.source_jumia.parser import _parse_product_card, BASE_URL

        html = '''
        <article class="prd _fb col c-prd">
          <a class="core" href="/samsung-galaxy-a55-123456.html"
             data-gtm-id="SA123MP456"
             data-gtm-brand="Samsung"
             data-gtm-category="Phones &amp; Tablets/Mobile Phones/Smartphones">
            <div class="info">
              <h3 class="name">Samsung Galaxy A55 5G</h3>
              <div class="prc">EGP 18,999.00</div>
            </div>
          </a>
        </article>
        '''
        soup = BeautifulSoup(html, "lxml")
        card = _parse_product_card(soup.select_one("article.prd"), BASE_URL)
        assert card is not None
        assert card["sku"] == "SA123MP456"
        assert card["brand"] == "Samsung"
        assert card["category"] == "Phones & Tablets"
        assert card["raw_category_path"] == "Phones & Tablets > Mobile Phones > Smartphones"
        assert card["price"] == pytest.approx(18999.0)

    def test_delivery_zones_use_delivery_area_type(self):
        from extractors.source_jumia.parser import parse_delivery_zones
        from normalization.schema import LocationType

        zones = parse_delivery_zones("<html></html>")
        assert len(zones) == 27
        for z in zones:
            assert z["location_type"] in (LocationType.DELIVERY_AREA, LocationType.DELIVERY_ZONE)
            assert z.get("branch_name") is None
