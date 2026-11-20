"""
Tests for Carrefour Egypt Extractor and Parsers
"""

import pytest
from pathlib import Path

from extractors.source_carrefour.extractor import CarrefourExtractor
from extractors.source_carrefour.parser import (
    determine_availability,
    extract_brand,
    parse_category_page,
    parse_discount,
    parse_price,
    parse_store_locator,
)
from normalization.schema import AvailabilityStatus, ComplianceStatus, ExtractionMethod

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestCarrefourParser:
    def test_parse_category_products(self):
        html_file = FIXTURES_DIR / "carrefour_sample.html"
        assert html_file.exists()
        html = html_file.read_text(encoding="utf-8")

        products = parse_category_page(html)
        assert len(products) == 5

        # Product 1: Samsung TV 50 inch
        p1 = products[0]
        assert "UA50U8000HUXEG" in p1["product_name"]
        assert p1["source_product_id"] == "676581"
        assert p1["sku"] == "676581"
        assert p1["price"] == 18499.0
        assert p1["old_price"] == 26999.0
        assert p1["discount"] == 31.0
        assert p1["brand"] == "Samsung"
        assert p1["availability_status"] == AvailabilityStatus.LIMITED_STOCK
        assert "Only 2 left" in p1["delivery_status"]

        # Product 3: Samsung Galaxy A07
        p3 = products[2]
        assert "A07" in p3["product_name"]
        assert p3["source_product_id"] == "664317"
        assert p3["price"] == 9850.0

        # Product 5: Samsung Galaxy S26 Ultra
        p5 = products[4]
        assert "S26" in p5["product_name"]
        assert p5["source_product_id"] == "678325"
        assert p5["price"] == 72400.0

    def test_parse_prices(self):
        assert parse_price("18,499.00 EGP") == 18499.0
        assert parse_price("١٨٬٤٩٩") == 18499.0
        assert parse_discount("31%") == 31.0

    def test_brand_extraction(self):
        assert extract_brand("تليفزيون سامسونج 50 بوصة") == "Samsung"
        assert extract_brand("Samsung Galaxy S24") == "Samsung"
        assert extract_brand("موبايل شاومي ريدمي") == "Xiaomi"
        assert extract_brand("Apple iPhone 15 Pro") == "Apple"

    def test_determine_availability(self):
        status, note = determine_availability("Only 2 left")
        assert status == AvailabilityStatus.LIMITED_STOCK
        assert "Only 2 left" in note

        status, _ = determine_availability("In Stock")
        assert status == AvailabilityStatus.IN_STOCK

        status, _ = determine_availability("غير متوفر")
        assert status == AvailabilityStatus.OUT_OF_STOCK

    def test_store_locator_governorates(self):
        locations = parse_store_locator()
        assert len(locations) >= 19
        gov_names = [l["governorate"] for l in locations]
        assert "Cairo" in gov_names
        assert "Giza" in gov_names
        assert "Alexandria" in gov_names


class TestCarrefourExtractor:
    def test_source_configuration(self):
        extractor = CarrefourExtractor()
        config = extractor.source_config()
        assert config.source_id == "carrefour"
        assert config.compliance_status == ComplianceStatus.CONDITIONAL
        assert config.extraction_method == ExtractionMethod.STATIC_HTML
        assert config.rate_limit_rpm <= 20
        assert config.enabled is True



class TestCarrefourLocationSemanticsSection6:
    """Section 6: Verify Carrefour governorate presence vs real physical branch semantics."""

    def test_governorate_presence_is_not_store_or_branch(self):
        from normalization.schema import LocationType
        locs = parse_store_locator()
        assert len(locs) == 19
        for loc in locs:
            assert loc["location_type"] == LocationType.PRESENCE
            assert loc["branch_name"] is None
            assert loc["raw_location_name"].startswith("Presence in ")

    def test_real_branch_html_extracts_as_branch(self):
        from normalization.schema import LocationType
        html = """
        <div class="store-card" data-lat="30.0249" data-lng="31.4873">
          <h3 class="store-name">Carrefour Cairo Festival City</h3>
          <div class="store-address">Ring Road, New Cairo, Cairo Governorate</div>
        </div>
        """
        locs = parse_store_locator(html)
        assert len(locs) == 1
        assert locs[0]["location_type"] == LocationType.BRANCH
        assert locs[0]["branch_name"] == "Carrefour Cairo Festival City"
        assert locs[0]["governorate"] == "Cairo"
        assert locs[0]["latitude"] == pytest.approx(30.0249)


class TestCarrefourPresenceSemanticsAndValidation:
    """Tests for Carrefour LocationType.PRESENCE vs LocationType.BRANCH semantics."""

    def test_governorate_presence_locations_use_presence_type(self):
        from extractors.source_carrefour.parser import parse_store_locator
        from normalization.schema import LocationType

        locs = parse_store_locator("<html></html>")
        assert len(locs) == 19
        for loc in locs:
            assert loc["location_type"] == LocationType.PRESENCE
            assert loc["branch_name"] is None
            assert loc["address"] is None
            assert loc["latitude"] is None
            assert loc["longitude"] is None
            assert loc["raw_location_name"] is not None

    def test_validator_does_not_penalize_presence_locations_for_missing_branch_fields(self):
        from extractors.source_carrefour.parser import parse_store_locator
        from normalization.schema import ExtractionResult, Location
        from validation.data_validator import DataValidator

        raw_locs = parse_store_locator("<html></html>")
        locs = [Location(source_id="carrefour", **r) for r in raw_locs]
        result = ExtractionResult(source_id="carrefour", locations=locs)
        report = DataValidator().validate(result)

        assert report["overall_quality_score"] == 100.0
        assert len(report["quality_issues"]) == 0

    def test_real_branch_card_uses_branch_type(self):
        from extractors.source_carrefour.parser import parse_store_locator
        from normalization.schema import LocationType

        html = '''
        <div class="store-card" data-lat="30.0561" data-lng="31.3301">
          <h3 class="store-name">Carrefour City Centre Almaza</h3>
          <div class="store-address">Suez Road, Heliopolis, Cairo</div>
        </div>
        '''
        locs = parse_store_locator(html)
        assert len(locs) == 1
        assert locs[0]["location_type"] == LocationType.BRANCH
        assert locs[0]["branch_name"] == "Carrefour City Centre Almaza"
        assert locs[0]["governorate"] == "Cairo"
        assert locs[0]["latitude"] == pytest.approx(30.0561)
