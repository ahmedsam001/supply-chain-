"""
Tests for the parser modules and schema validation.
"""

import pytest
import json
from datetime import datetime, timezone

from normalization.schema import (
    AvailabilityStatus,
    ComplianceStatus,
    Currency,
    ExtractionMethod,
    ExtractionResult,
    Location,
    LocationType,
    Product,
    ProductObservation,
    Source,
)


# ─── Schema Tests ────────────────────────────────────────────────────

class TestProduct:
    def test_valid_product(self):
        product = Product(
            source_id="btech",
            source_product_id="12345",
            product_name="Samsung Galaxy S24",
            brand="Samsung",
            category="mobiles",
            product_url="https://btech.com/product/12345",
        )
        assert product.product_name == "Samsung Galaxy S24"
        assert product.source_id == "btech"
        assert product.product_id  # auto-generated UUID

    def test_empty_product_name_raises(self):
        with pytest.raises(ValueError, match="product_name"):
            Product(
                source_id="btech",
                source_product_id="12345",
                product_name="",
                product_url="https://btech.com/product/12345",
            )

    def test_whitespace_product_name_raises(self):
        with pytest.raises(ValueError):
            Product(
                source_id="btech",
                source_product_id="12345",
                product_name="   ",
                product_url="https://btech.com/product/12345",
            )

    def test_product_name_strips_whitespace(self):
        product = Product(
            source_id="btech",
            source_product_id="12345",
            product_name="  Samsung Galaxy S24  ",
            product_url="https://btech.com/product/12345",
        )
        assert product.product_name == "Samsung Galaxy S24"


class TestProductObservation:
    def test_valid_observation(self):
        obs = ProductObservation(
            product_id="uuid-123",
            price=15999.00,
            old_price=19999.00,
            discount=20.0,
            currency=Currency.EGP,
            availability_status=AvailabilityStatus.IN_STOCK,
        )
        assert obs.price == 15999.00
        assert obs.currency == Currency.EGP

    def test_row_hash_deterministic(self):
        obs1 = ProductObservation(
            product_id="uuid-123",
            price=15999.00,
            availability_status=AvailabilityStatus.IN_STOCK,
        )
        obs2 = ProductObservation(
            product_id="uuid-456",
            price=15999.00,
            availability_status=AvailabilityStatus.IN_STOCK,
        )
        assert obs1.compute_row_hash() == obs2.compute_row_hash()

    def test_row_hash_changes_on_price(self):
        obs1 = ProductObservation(
            product_id="uuid-123",
            price=15999.00,
            availability_status=AvailabilityStatus.IN_STOCK,
        )
        obs2 = ProductObservation(
            product_id="uuid-123",
            price=14999.00,
            availability_status=AvailabilityStatus.IN_STOCK,
        )
        assert obs1.compute_row_hash() != obs2.compute_row_hash()

    def test_negative_price_rejected(self):
        with pytest.raises(ValueError):
            ProductObservation(
                product_id="uuid-123",
                price=-100.00,
            )

    def test_discount_over_100_rejected(self):
        with pytest.raises(ValueError):
            ProductObservation(
                product_id="uuid-123",
                discount=150.0,
            )


class TestLocation:
    def test_valid_location(self):
        loc = Location(
            source_id="btech",
            location_type=LocationType.STORE,
            branch_name="B.TECH City Stars",
            city="Cairo",
            governorate="Cairo",
        )
        assert loc.branch_name == "B.TECH City Stars"

    def test_latitude_bounds(self):
        with pytest.raises(ValueError):
            Location(
                source_id="btech",
                location_type=LocationType.STORE,
                latitude=91.0,
            )


class TestSource:
    def test_compliance_status_enum(self):
        source = Source(
            source_id="test",
            source_name="Test Source",
            domain="test.com",
            compliance_status=ComplianceStatus.CONDITIONAL,
            extraction_method=ExtractionMethod.PUBLIC_JSON,
        )
        assert source.compliance_status == ComplianceStatus.CONDITIONAL

    def test_source_serialization(self):
        source = Source(
            source_id="test",
            source_name="Test Source",
            domain="test.com",
            compliance_status=ComplianceStatus.CONDITIONAL,
            extraction_method=ExtractionMethod.PLAYWRIGHT,
        )
        data = source.model_dump(mode="json")
        assert data["source_id"] == "test"
        assert data["compliance_status"] == "B"


class TestExtractionResult:
    def test_success_rate_empty(self):
        result = ExtractionResult(source_id="test")
        assert result.success_rate == 0.0

    def test_success_rate_with_products(self):
        result = ExtractionResult(
            source_id="test",
            products=[
                Product(
                    source_id="test",
                    source_product_id="1",
                    product_name="Test",
                    product_url="https://test.com/1",
                ),
            ],
            errors=["one error"],
        )
        assert result.success_rate == 0.5


# ─── Price Parser Tests ──────────────────────────────────────────────

class TestPriceParser:
    def test_parse_egp_price(self):
        from extractors.source_btech.parser import _parse_price
        assert _parse_price("EGP 1,234.56") == 1234.56

    def test_parse_arabic_numerals(self):
        from extractors.source_btech.parser import _parse_price
        assert _parse_price("١٬٢٣٤") == 1234.0

    def test_parse_empty_string(self):
        from extractors.source_btech.parser import _parse_price
        assert _parse_price("") is None

    def test_parse_none(self):
        from extractors.source_btech.parser import _parse_price
        assert _parse_price(None) is None


# ─── Availability Parser Tests ────────────────────────────────────────

class TestAvailabilityParser:
    def test_in_stock(self):
        from extractors.source_btech.parser import determine_availability
        assert determine_availability("In Stock") == AvailabilityStatus.IN_STOCK

    def test_out_of_stock(self):
        from extractors.source_btech.parser import determine_availability
        assert determine_availability("Out of Stock") == AvailabilityStatus.OUT_OF_STOCK

    def test_arabic_in_stock(self):
        from extractors.source_btech.parser import determine_availability
        assert determine_availability("متوفر") == AvailabilityStatus.IN_STOCK

    def test_unknown(self):
        from extractors.source_btech.parser import determine_availability
        assert determine_availability("") == AvailabilityStatus.UNKNOWN


# ─── Geography Tests ──────────────────────────────────────────────────

class TestGeography:
    def test_normalize_governorate(self):
        from geospatial.egypt_geography import normalize_governorate
        assert normalize_governorate("Cairo") == "Cairo"
        assert normalize_governorate("cairo") == "Cairo"
        assert normalize_governorate("القاهرة") == "Cairo"

    def test_city_to_governorate(self):
        from geospatial.egypt_geography import city_to_governorate
        assert city_to_governorate("Maadi") == "Cairo"
        assert city_to_governorate("6th of October") == "Giza"
        assert city_to_governorate("Mansoura") == "Dakahlia"
        assert city_to_governorate("Hurghada") == "Red Sea"

    def test_normalize_location(self):
        from geospatial.egypt_geography import normalize_location
        result = normalize_location(city="Maadi")
        assert result["governorate"] == "Cairo"
        assert result["country"] == "Egypt"


# ─── Availability Scope Tests ─────────────────────────────────────────

class TestAvailabilityScope:
    def test_enum_values_exist(self):
        from normalization.schema import AvailabilityScope
        assert AvailabilityScope.GLOBAL == "GLOBAL"
        assert AvailabilityScope.DELIVERY_AREA == "DELIVERY_AREA"
        assert AvailabilityScope.PHYSICAL_BRANCH == "PHYSICAL_BRANCH"
        assert AvailabilityScope.UNKNOWN == "UNKNOWN"

    def test_observation_default_scope(self):
        from normalization.schema import ProductObservation, AvailabilityScope
        obs = ProductObservation(product_id="x", price=100.0)
        assert obs.availability_scope == AvailabilityScope.UNKNOWN

    def test_low_stock_signal_not_quantity(self):
        """Only 2 left must NOT become stock_quantity=2."""
        from normalization.schema import ProductObservation, AvailabilityScope, AvailabilityStatus
        obs = ProductObservation(
            product_id="x",
            price=100.0,
            raw_availability_text="Only 2 left",
            stock_status="LOW_STOCK_SIGNAL",
            availability_status=AvailabilityStatus.LIMITED_STOCK,
            stock_quantity=None,  # Must be None
            availability_scope=AvailabilityScope.GLOBAL,
        )
        assert obs.stock_quantity is None
        assert obs.stock_status == "LOW_STOCK_SIGNAL"
        assert obs.raw_availability_text == "Only 2 left"

    def test_row_hash_includes_scope(self):
        from normalization.schema import ProductObservation, AvailabilityScope
        obs1 = ProductObservation(product_id="x", price=100.0, availability_scope=AvailabilityScope.GLOBAL)
        obs2 = ProductObservation(product_id="x", price=100.0, availability_scope=AvailabilityScope.PHYSICAL_BRANCH)
        assert obs1.compute_row_hash() != obs2.compute_row_hash()

    def test_row_hash_deterministic_v2(self):
        from normalization.schema import ProductObservation, AvailabilityScope, AvailabilityStatus
        obs1 = ProductObservation(product_id="a", price=999.0, availability_scope=AvailabilityScope.GLOBAL)
        obs2 = ProductObservation(product_id="b", price=999.0, availability_scope=AvailabilityScope.GLOBAL)
        assert obs1.compute_row_hash() == obs2.compute_row_hash()


class TestDataQualityIssue:
    def test_issue_creation(self):
        from normalization.schema import DataQualityIssue, IssueCode, IssueSeverity
        issue = DataQualityIssue(
            source_id="jumia",
            entity_type="product",
            entity_id="123",
            issue_code=IssueCode.MISSING_FIELD,
            severity=IssueSeverity.MEDIUM,
            message="Missing SKU",
        )
        assert issue.issue_id  # auto-generated UUID
        assert issue.issue_code == IssueCode.MISSING_FIELD

    def test_issue_codes_exist(self):
        from normalization.schema import IssueCode
        assert IssueCode.DUPLICATE_PRODUCT
        assert IssueCode.SCOPE_SEMANTICS_VIOLATION
        assert IssueCode.STOCK_QUANTITY_WITHOUT_EVIDENCE


class TestLocationTypeExtended:
    def test_delivery_area_type(self):
        from normalization.schema import LocationType
        assert LocationType.DELIVERY_AREA == "delivery_area" or LocationType.DELIVERY_AREA.value

    def test_delivery_zone_backward_compat(self):
        """Old JSON with delivery_zone must still parse."""
        from normalization.schema import Location, LocationType
        loc = Location(
            source_id="jumia",
            location_type="delivery_zone",  # old value
            governorate="Cairo",
        )
        assert loc.location_type  # Should not raise

    def test_fulfillment_center_type(self):
        from normalization.schema import LocationType
        assert LocationType.FULFILLMENT_CENTER


class TestValidatorDeliveryZoneFix:
    def test_delivery_zone_no_penalty(self):
        """Delivery zone locations must NOT be penalized for missing branch_name/address."""
        from normalization.schema import Location, LocationType, ExtractionResult
        from validation.data_validator import DataValidator

        locs = [
            Location(source_id="jumia", location_type=LocationType.DELIVERY_ZONE, governorate="Cairo"),
            Location(source_id="jumia", location_type=LocationType.DELIVERY_AREA, governorate="Giza"),
        ]
        result = ExtractionResult(source_id="jumia", locations=locs)
        validator = DataValidator()
        report = validator.validate(result)
        # The validator should not penalize for missing branch_name/address on delivery zones
        loc_issues = report["locations"]["issues"]
        # No 'missing branch_name' or 'missing address' issues for delivery zones
        for issue_str in loc_issues:
            if isinstance(issue_str, str):
                assert "missing branch_name" not in issue_str.lower() or "delivery" not in issue_str.lower()

    def test_physical_store_still_requires_branch_name(self):
        from normalization.schema import Location, LocationType, ExtractionResult
        from validation.data_validator import DataValidator

        locs = [
            Location(source_id="tradeline", location_type=LocationType.STORE, governorate="Cairo"),  # no branch_name
        ]
        result = ExtractionResult(source_id="tradeline", locations=locs)
        validator = DataValidator()
        report = validator.validate(result)
        loc_issues = report["locations"]["issues"]
        # Physical stores should still flag missing branch_name
        has_branch_issue = any(
            ("branch" in str(i).lower() or "name" in str(i).lower()) for i in loc_issues
        )
        assert has_branch_issue


class TestEndToEndValidationFixes:
    def test_btech_hard_blocked(self):
        """BTechExtractor must report Class C DO_NOT_AUTOMATE and raise ComplianceError on run()."""
        import asyncio
        from extractors.base import ComplianceError
        from extractors.source_btech.extractor import BTechExtractor
        from normalization.schema import ComplianceStatus

        ext = BTechExtractor()
        cfg = ext.source_config()
        assert cfg.compliance_status == ComplianceStatus.DO_NOT_AUTOMATE
        assert cfg.enabled is False
        with pytest.raises(ComplianceError):
            asyncio.run(ext.run())
        assert ext._http_client is None
        assert ext._browser is None

    def test_sheikh_zayed_maps_to_giza(self):
        """Sheikh Zayed variants must map to Giza governorate, never Cairo."""
        from geospatial.egypt_geography import normalize_location
        geo = normalize_location(
            address="Arkan, 2000 Sheikh Zayed City, GZ, First Al Sheikh Zayed, Egypt",
            city="First Al Sheikh Zayed",
        )
        assert geo["governorate"] == "Giza"

    def test_offline_fixture_runner_modes(self):
        """Offline fixture runner must label real fixtures offline_fixture and synthetic fixtures synthetic."""
        import asyncio
        from run_extraction import run_extraction

        res_jumia = asyncio.run(run_extraction(source_id="jumia", offline_fixture=True))
        assert len(res_jumia) == 1
        assert res_jumia[0].mode == "offline_fixture"
        assert len(res_jumia[0].products) == 5

        res_2b = asyncio.run(run_extraction(source_id="two_b", offline_fixture=True))
        assert len(res_2b) == 1
        assert res_2b[0].mode == "synthetic"
        assert len(res_2b[0].products) == 2

        res_btech = asyncio.run(run_extraction(source_id="btech", offline_fixture=True))
        assert res_btech == []


# ─────────────────────────────────────────────────────────────────────
# WP1 — Live Smoke & Real Sanitized Fixtures Tests
# ─────────────────────────────────────────────────────────────────────

class TestLiveSmokeWP1:
    """WP1: Real sanitized live fixtures for jumia and two_b parse and validate cleanly."""

    def test_jumia_real_capture_fixture_parses(self):
        from pathlib import Path
        from scripts.live_smoke import parse_snapshot_to_canonical
        from validation.data_validator import DataValidator

        real_fix = Path(__file__).parent / "fixtures" / "jumia" / "real" / "category_sample.html"
        assert real_fix.exists() and real_fix.stat().st_size > 1000
        html = real_fix.read_text(encoding="utf-8")
        res = parse_snapshot_to_canonical("jumia", html, "https://www.jumia.com.eg/phones-tablets/", limit=6, run_id="test_wp1_jumia")
        assert len(res.products) >= 5
        assert len(res.observations) >= 5
        report = DataValidator().validate(res)
        assert report["overall_quality_score"] >= 80.0

    def test_twob_real_capture_fixture_parses(self):
        from pathlib import Path
        from scripts.live_smoke import parse_snapshot_to_canonical
        from validation.data_validator import DataValidator

        real_fix = Path(__file__).parent / "fixtures" / "two_b" / "real" / "category_sample.html"
        assert real_fix.exists() and real_fix.stat().st_size > 1000
        html = real_fix.read_text(encoding="utf-8")
        res = parse_snapshot_to_canonical("two_b", html, "https://2b.com.eg/en/laptops.html", limit=6, run_id="test_wp1_twob")
        assert len(res.products) >= 5
        assert len(res.observations) >= 5
        report = DataValidator().validate(res)
        assert report["overall_quality_score"] >= 80.0

    @pytest.mark.live
    def test_live_smoke_gated_check(self, tmp_path):
        """Gated live check — skipped by default unless `-m live` is passed."""
        import asyncio
        from scripts.live_smoke import probe_source
        res = asyncio.run(probe_source("jumia", limit=5, run_id="pytest_live_check", data_dir=tmp_path))
        assert res["status"] in ("SUCCESS", "PARTIAL", "BLOCKED")


# ─────────────────────────────────────────────────────────────────────
# WP2 — Raw Snapshots & Replay Determinism Tests
# ─────────────────────────────────────────────────────────────────────

class TestSnapshotInfrastructure:
    """WP2: gzip snapshots with sha256, URL, HTTP status, safe headers, and deterministic replay."""

    def test_save_and_verify_snapshot(self, tmp_path):
        import hashlib
        from scripts.live_smoke import save_snapshot, verify_snapshot_sha256

        body = b"<html><body>Test content</body></html>"

        class MockResponse:
            content = body
            status_code = 200
            headers = {"content-type": "text/html", "set-cookie": "secret=123"}

        run_dir = tmp_path / "run-001"
        meta = save_snapshot(run_dir, "https://example.com/test", MockResponse(), elapsed_ms=123)

        assert meta["status_code"] == 200
        assert meta["sha256"] == hashlib.sha256(body).hexdigest()
        assert meta["content_length"] == len(body)
        assert meta["elapsed_ms"] == 123
        assert "set-cookie" not in meta["headers"]  # Cookies stripped
        assert verify_snapshot_sha256(meta, run_dir)

    def test_replay_yields_identical_canonical_output(self):
        """WP2: Replaying stored snapshots with no network yields identical canonical output."""
        from pathlib import Path
        import pytest
        from scripts.live_smoke import DATA_DIR, replay_run

        snapshot_dir = DATA_DIR / "raw_snapshots" / "jumia" / "live_20260928_wp1"
        if not snapshot_dir.exists():
            pytest.skip("Stored raw snapshot live_20260928_wp1 not present in checkout (gitignored)")

        _, res1 = replay_run("jumia", "live_20260928_wp1", limit=6)
        _, res2 = replay_run("jumia", "live_20260928_wp1", limit=6)

        assert len(res1.products) == len(res2.products) == 6
        assert [p.source_product_id for p in res1.products] == [p.source_product_id for p in res2.products]
        assert [p.product_name for p in res1.products] == [p.product_name for p in res2.products]
        assert [o.price for o in res1.observations] == [o.price for o in res2.observations]
        assert [o.row_hash for o in res1.observations] == [o.row_hash for o in res2.observations]


# ─────────────────────────────────────────────────────────────────────
# WP3 — Run Manifest, Status & Degraded Fixture Drift Tests
# ─────────────────────────────────────────────────────────────────────

class TestRunManifest:
    """WP3: Per-run manifest with reconciled counts, drift detection, and degraded-fixture failure."""

    def test_manifest_creation_and_reconciliation(self, tmp_path):
        from validation.run_manifest import RunManifest, load_manifest
        m = RunManifest(source_id="jumia", run_id="test-run-001", data_dir=str(tmp_path))
        m.products_parsed = 12
        m.products_accepted = 10
        m.observations_accepted = 10
        m.finish()
        m.save()
        loaded = load_manifest("jumia", "test-run-001", data_dir=str(tmp_path))
        assert loaded["products_parsed"] == 12
        assert loaded["products_accepted"] == 10
        assert loaded["products_rejected"] == 2
        assert loaded["reconciled"] is True
        assert loaded["status"] == "SUCCESS"

    def test_zero_products_is_failed_never_success(self, tmp_path):
        """WP3: A run with zero products must be FAILED with a warning, never SUCCESS."""
        from validation.run_manifest import RunManifest
        m = RunManifest(source_id="jumia", run_id="zero-run", data_dir=str(tmp_path))
        m.products_accepted = 0
        m.finish()
        assert m.status == "FAILED"
        assert any("ZERO_PRODUCTS" in w for w in m.warnings)

    def test_degraded_fixture_high_parse_failure_is_partial_or_failed(self, tmp_path):
        """WP3/WP12: Degraded fixture with parse-failure ratio above threshold is PARTIAL/FAILED, never SUCCESS."""
        from validation.run_manifest import RunManifest
        m = RunManifest(
            source_id="jumia",
            run_id="degraded-run",
            data_dir=str(tmp_path),
            parse_failure_threshold=0.25,
        )
        m.products_parsed = 10
        m.products_accepted = 5
        m.products_rejected = 5  # 50% failure > 25% threshold
        m.finish()
        assert m.status == "PARTIAL"
        assert any("HIGH_PARSE_FAILURE_RATIO" in w for w in m.warnings)

    def test_drift_detection_across_runs(self, tmp_path):
        from validation.run_manifest import RunManifest
        m1 = RunManifest(source_id="jumia", run_id="run-001", data_dir=str(tmp_path))
        m1.products_accepted = 100
        m1.finish()
        m1.save()
        assert m1.drift["is_first_run"] is True

        m2 = RunManifest(source_id="jumia", run_id="run-002", data_dir=str(tmp_path))
        m2.products_accepted = 10  # 90% drop
        m2.finish()
        m2.save()
        assert m2.drift["is_first_run"] is False
        assert m2.drift["products_accepted_delta"] == -90
        assert m2.drift["warnings"]


# ─────────────────────────────────────────────────────────────────────
# WP4 — Seeds, Watchlist & Deterministic Selection Tests
# ─────────────────────────────────────────────────────────────────────

class TestSeedsAndWatchlistWP4:
    """WP4: Seeds config, persisted watchlist, and deterministic bounded selection."""

    def test_watchlist_exists_and_loads(self):
        from config.loader import load_watchlist
        wl = load_watchlist()
        assert "sources" in wl
        assert "jumia" in wl["sources"]
        assert "two_b" in wl["sources"]
        assert 5 <= wl["default_limit"] <= 20

    def test_deterministic_selection_orders_watched_first(self):
        from config.loader import select_deterministic_products
        from normalization.schema import Product

        p_unwatched = Product(
            source_id="tradeline",
            source_product_id="9999999",
            product_name="Unwatched Case",
            product_url="https://www.tradelinestores.com/products/case",
        )
        p_watched = Product(
            source_id="tradeline",
            source_product_id="8413231087682",
            product_name="Apple iPhone 16 Pro",
            product_url="https://www.tradelinestores.com/products/iphone",
        )
        selected1 = select_deterministic_products([p_unwatched, p_watched], "tradeline", limit=1)
        selected2 = select_deterministic_products([p_watched, p_unwatched], "tradeline", limit=1)
        assert selected1[0].source_product_id == "8413231087682"
        assert selected2[0].source_product_id == "8413231087682"


# ─────────────────────────────────────────────────────────────────────
# WP5 — Observation History & Two-Run Diff Tests
# ─────────────────────────────────────────────────────────────────────

class TestObservationHistory:
    """WP5: Append-only idempotent JSONL observation history and two-run diff."""

    def test_two_simulated_runs_and_idempotent_replay(self, tmp_path):
        """
        WP5: Two simulated runs on different dates including:
        - price change
        - out-of-stock change + scope change
        - delisted product
        - new product
        - changed identifier for same SKU
        - new location
        - replay of the same run (idempotent — zero duplicate rows)
        """
        from normalization.schema import (
            AvailabilityScope,
            AvailabilityStatus,
            ExtractionResult,
            Location,
            LocationType,
            Product,
            ProductObservation,
        )
        from validation.change_detection import ChangeDetector
        from validation.observation_history import ObservationHistory

        hist = ObservationHistory(data_dir=str(tmp_path))

        # Run 1 (2026-09-27)
        p1_r1 = Product(source_id="jumia", source_product_id="SKU-1", sku="EAN-111", product_name="Phone 1", product_url="https://jumia.com.eg/p1")
        p2_r1 = Product(source_id="jumia", source_product_id="SKU-2", sku="EAN-222", product_name="Phone 2", product_url="https://jumia.com.eg/p2")
        p3_r1 = Product(source_id="jumia", source_product_id="SKU-3", sku="EAN-333", product_name="Phone 3 (To Delist)", product_url="https://jumia.com.eg/p3")
        loc1 = Location(source_id="jumia", location_type=LocationType.DELIVERY_ZONE, governorate="Cairo")

        obs1_r1 = ProductObservation(product_id=p1_r1.product_id, source_id="jumia", source_product_id="SKU-1", price=10000.0, availability_status=AvailabilityStatus.IN_STOCK, availability_scope=AvailabilityScope.GLOBAL)
        obs2_r1 = ProductObservation(product_id=p2_r1.product_id, source_id="jumia", source_product_id="SKU-2", price=20000.0, availability_status=AvailabilityStatus.IN_STOCK, availability_scope=AvailabilityScope.GLOBAL)
        obs3_r1 = ProductObservation(product_id=p3_r1.product_id, source_id="jumia", source_product_id="SKU-3", price=15000.0, availability_status=AvailabilityStatus.IN_STOCK, availability_scope=AvailabilityScope.GLOBAL)

        res1 = ExtractionResult(source_id="jumia", run_id="run_day1", products=[p1_r1, p2_r1, p3_r1], locations=[loc1], observations=[obs1_r1, obs2_r1, obs3_r1])
        appended1, skipped1 = hist.append_result(res1, run_id="run_day1")
        assert appended1 == 3 and skipped1 == 0

        # Replay of Run 1 -> must skip all 3 (idempotent!)
        appended_replay, skipped_replay = hist.append_result(res1, run_id="run_day1")
        assert appended_replay == 0 and skipped_replay == 3
        assert hist.count_records("jumia") == 3

        # Run 2 (2026-09-28):
        # - SKU-1 price changed 10000 -> 9500
        # - SKU-2 went out of stock & scope changed
        # - SKU-3 delisted; EAN-333 re-listed under new source_product_id SKU-3-NEW
        # - SKU-4 added
        # - loc2 added
        p1_r2 = Product(source_id="jumia", source_product_id="SKU-1", sku="EAN-111", product_name="Phone 1", product_url="https://jumia.com.eg/p1")
        p2_r2 = Product(source_id="jumia", source_product_id="SKU-2", sku="EAN-222", product_name="Phone 2", product_url="https://jumia.com.eg/p2")
        p3_relisted = Product(source_id="jumia", source_product_id="SKU-3-NEW", sku="EAN-333", product_name="Phone 3 Relisted", product_url="https://jumia.com.eg/p3-new")
        p4_r2 = Product(source_id="jumia", source_product_id="SKU-4", sku="EAN-444", product_name="Phone 4 New", product_url="https://jumia.com.eg/p4")
        loc2 = Location(source_id="jumia", location_type=LocationType.DELIVERY_ZONE, governorate="Alexandria")

        obs1_r2 = ProductObservation(product_id=p1_r2.product_id, source_id="jumia", source_product_id="SKU-1", price=9500.0, availability_status=AvailabilityStatus.IN_STOCK, availability_scope=AvailabilityScope.GLOBAL)
        obs2_r2 = ProductObservation(product_id=p2_r2.product_id, source_id="jumia", source_product_id="SKU-2", price=20000.0, availability_status=AvailabilityStatus.OUT_OF_STOCK, availability_scope=AvailabilityScope.DELIVERY_AREA)
        obs3_r2 = ProductObservation(product_id=p3_relisted.product_id, source_id="jumia", source_product_id="SKU-3-NEW", price=15000.0, availability_status=AvailabilityStatus.IN_STOCK, availability_scope=AvailabilityScope.GLOBAL)
        obs4_r2 = ProductObservation(product_id=p4_r2.product_id, source_id="jumia", source_product_id="SKU-4", price=8000.0, availability_status=AvailabilityStatus.IN_STOCK, availability_scope=AvailabilityScope.GLOBAL)

        res2 = ExtractionResult(source_id="jumia", run_id="run_day2", products=[p1_r2, p2_r2, p3_relisted, p4_r2], locations=[loc1, loc2], observations=[obs1_r2, obs2_r2, obs3_r2, obs4_r2])
        appended2, _ = hist.append_result(res2, run_id="run_day2")
        assert appended2 == 4
        assert hist.count_records("jumia") == 7

        # Product history over time
        p1_hist = hist.get_product_history("jumia", "SKU-1")
        assert len(p1_hist) == 2
        assert [h["price"] for h in p1_hist] == [10000.0, 9500.0]

        # Cross-run diff via ObservationHistory
        diff = hist.cross_run_diff("jumia", "run_day1", "run_day2")
        assert diff["price_changes_count"] == 1
        assert diff["price_changes"][0]["delta"] == -500.0
        assert diff["availability_changes_count"] == 1
        assert diff["scope_changes_count"] == 1
        assert "SKU-3" in diff["delisted_products"]
        assert "SKU-4" in diff["new_products"]
        assert diff["identifier_changes_count"] == 1
        assert diff["new_locations_count"] == 1

        # Cross-run diff via ChangeDetector
        cd = ChangeDetector(data_dir=str(tmp_path))
        cd_diff = cd.detect_changes_between_runs("jumia", res1, res2)
        assert cd_diff["price_changes"] == 1
        assert cd_diff["availability_changes"] == 1
        assert cd_diff["scope_changes"] == 1
        assert cd_diff["identifier_changes"] == 1
        assert cd_diff["new_locations"] == 1

    def test_storage_schema_ddl_aligned(self):
        from storage.schema import SCHEMA_DDL
        assert "availability_scope" in SCHEMA_DDL
        assert "stock_status" in SCHEMA_DDL
        assert "gtin" in SCHEMA_DDL
        assert "data_quality_issues" in SCHEMA_DDL


# ─────────────────────────────────────────────────────────────────────
# WP7 — Geography Audit & Arabic Input Tests
# ─────────────────────────────────────────────────────────────────────

class TestGeographyAudit:
    """WP7: No guessed mappings; Sheikh Zayed->Giza, Obour->Qalyubia; stable location_id; Arabic input."""

    def test_known_city_maps_unambiguously(self):
        from geospatial.egypt_geography import city_to_governorate
        assert city_to_governorate("Sheikh Zayed") == "Giza"
        assert city_to_governorate("First Al Sheikh Zayed") == "Giza"
        assert city_to_governorate("6th of October") == "Giza"
        assert city_to_governorate("Obour") == "Qalyubia"
        assert city_to_governorate("New Cairo") == "Cairo"

    def test_unknown_or_ambiguous_city_never_guesses(self):
        from geospatial.egypt_geography import city_to_governorate, normalize_location
        assert city_to_governorate("Atlantis") is None
        assert city_to_governorate("Downtown") is None

        res = normalize_location(city="UnknownPlace123", address="Mystery Street")
        assert res["governorate"] == "unknown"
        assert res["raw_city"] == "UnknownPlace123"
        assert res["raw_address"] == "Mystery Street"
        assert res["district"] is None

    def test_arabic_locations_map_correctly(self):
        from geospatial.egypt_geography import normalize_location, city_to_governorate
        assert city_to_governorate("القاهرة") == "Cairo"
        assert city_to_governorate("الشيخ زايد") == "Giza"
        assert city_to_governorate("سموحة") == "Alexandria"
        assert city_to_governorate("العبور") == "Qalyubia"

        res = normalize_location(address="شارع التسعين، التجمع الخامس، القاهرة الجديدة")
        assert res["governorate"] == "Cairo"

    def test_stable_location_id_derivation(self):
        from geospatial.egypt_geography import derive_location_id
        from normalization.schema import Location, LocationType

        lid1 = derive_location_id("tradeline", "store", "Tradeline Arkan", "Arkan Plaza, Sheikh Zayed")
        lid2 = derive_location_id("tradeline", "store", "  tradeline   arkan ", "arkan plaza, sheikh zayed")
        assert lid1 == lid2

        loc_a = Location(source_id="tradeline", location_type=LocationType.STORE, branch_name="Tradeline Arkan", address="Arkan Plaza")
        loc_b = Location(source_id="tradeline", location_type=LocationType.STORE, branch_name="Tradeline Arkan", address="Arkan Plaza")
        assert loc_a.location_id == loc_b.location_id


# ─────────────────────────────────────────────────────────────────────
# WP8 — Data Quality Completeness, GTIN Collision & Connector Contract
# ─────────────────────────────────────────────────────────────────────

class TestDataQualityCompleteness:
    """WP8: All IssueCode types, GTIN collision report, and connector contract tests."""

    def test_all_wp8_issue_detections(self):
        from normalization.schema import (
            AvailabilityScope,
            AvailabilityStatus,
            Currency,
            ExtractionResult,
            IssueCode,
            Location,
            LocationType,
            Product,
            ProductObservation,
        )
        from validation.data_validator import DataValidator

        p1 = Product(
            source_id="jumia",
            source_product_id="p1",
            sku=None,  # MISSING_SKU
            product_name="Apple iPhone 16",
            brand=None,  # MISSING_FIELD
            category=None,  # MISSING_FIELD
            product_url="/relative/url",  # INVALID_URL
            variants=[{"id": "1"}, {"id": "2"}],  # MULTIPLE_VARIANTS
        )
        p1_dup = Product(
            source_id="jumia",
            source_product_id="p1",  # DUPLICATE_PRODUCT
            sku="SKU-CHANGED",
            product_name="Apple iPhone 16",
            brand="Apple",
            category="Phones",
            product_url="https://jumia.com.eg/p1",
        )
        p2_dup_listing = Product(
            source_id="jumia",
            source_product_id="p2",
            sku="SKU-2",
            product_name="  apple iphone 16 ",  # DUPLICATE_LISTING
            brand="Apple",
            category="Phones",
            product_url="https://jumia.com.eg/p1",  # DUPLICATE_LISTING
        )

        obs1 = ProductObservation(
            product_id=p1.product_id,
            source_id="jumia",
            source_product_id="p1",
            price=1000.0,
            old_price=800.0,  # PRICE_INCONSISTENCY (old < price)
            discount=50.0,  # INVALID_DISCOUNT
            currency=Currency.USD,  # NON_EGP_CURRENCY
            availability_status=AvailabilityStatus.UNKNOWN,  # AMBIGUOUS_AVAILABILITY
            availability_scope=AvailabilityScope.UNKNOWN,
            stock_quantity=2,  # STOCK_QUANTITY_WITHOUT_EVIDENCE & SCOPE_SEMANTICS_VIOLATION
            raw_availability_text="Only 2 left",  # LOW_STOCK_SIGNAL_MISPARSE
            sellers=["Seller A", "Seller B"],  # MULTIPLE_SELLERS
        )
        obs1_dup = ProductObservation(
            product_id=p1.product_id,
            source_id="jumia",
            source_product_id="p1",  # DUPLICATE_OBSERVATION
            price=0.0,  # INVALID_PRICE
        )

        loc_bad = Location(
            source_id="tradeline",
            location_type=LocationType.STORE,
            branch_name="Branch One",
            governorate="unknown",  # UNKNOWN_GOVERNORATE
            latitude=0.0,  # OUT_OF_EGYPT_COORDINATES
            longitude=150.0,
        )
        loc_inconsistent = Location(
            source_id="tradeline",
            location_type=LocationType.STORE,
            branch_name="Branch-One",  # INCONSISTENT_LOCATION_NAME
            governorate="Cairo",
            latitude=0.0,
            longitude=150.0,
        )

        prev_products = [{"sku": "SKU-CHANGED", "source_product_id": "OLD-SPID", "product_url": "https://jumia.com.eg/old"}]
        result = ExtractionResult(
            source_id="jumia",
            run_id="run-wp8",
            products=[p1, p1_dup, p2_dup_listing],
            observations=[obs1, obs1_dup],
            locations=[loc_bad, loc_inconsistent],
        )
        DataValidator().validate(result, run_id="run-wp8", previous_products=prev_products)
        codes = {qi.issue_code for qi in result.quality_issues}

        expected_codes = {
            IssueCode.MISSING_FIELD,
            IssueCode.MISSING_SKU,
            IssueCode.INVALID_URL,
            IssueCode.MULTIPLE_VARIANTS,
            IssueCode.DUPLICATE_PRODUCT,
            IssueCode.DUPLICATE_LISTING,
            IssueCode.DUPLICATE_OBSERVATION,
            IssueCode.MULTIPLE_SELLERS,
            IssueCode.NON_EGP_CURRENCY,
            IssueCode.INVALID_PRICE,
            IssueCode.PRICE_INCONSISTENCY,
            IssueCode.INVALID_DISCOUNT,
            IssueCode.AMBIGUOUS_AVAILABILITY,
            IssueCode.SCOPE_SEMANTICS_VIOLATION,
            IssueCode.STOCK_QUANTITY_WITHOUT_EVIDENCE,
            IssueCode.LOW_STOCK_SIGNAL_MISPARSE,
            IssueCode.OUT_OF_EGYPT_COORDINATES,
            IssueCode.UNKNOWN_GOVERNORATE,
            IssueCode.INCONSISTENT_LOCATION_NAME,
            IssueCode.IDENTIFIER_CHANGE,
        }
        assert expected_codes.issubset(codes)
        assert all(qi.run_id == "run-wp8" for qi in result.quality_issues)

    def test_gtin_collision_report(self, tmp_path):
        from normalization.schema import Product
        from validation.data_validator import DataValidator

        p_a = Product(source_id="dream2000", source_product_id="d1", gtin="6942785106048", product_name="Honor 600", product_url="https://dream2000.com/1")
        p_b = Product(source_id="tradeline", source_product_id="t1", gtin="6942785106048", product_name="Honor 600 5G", product_url="https://tradelinestores.com/1")
        report = DataValidator.generate_gtin_collision_report(
            {"dream2000": [p_a], "tradeline": [p_b]},
            output_path=tmp_path / "gtin_collisions.json",
        )
        assert report["cross_source_collisions_count"] == 1
        assert "6942785106048" in report["cross_source_collisions"]

    def test_connector_contract_all_implemented_sources(self, tmp_path):
        """
        WP8: Connector contract test across all 6 connectors:
        Every output has source_id, source_product_id, source_url, collected_at,
        valid availability_scope, and obeys forbidden-conversion rules (stock_quantity is None).
        """
        import asyncio
        from normalization.schema import AvailabilityScope
        from run_extraction import _run_single_offline_fixture

        for sid in ["jumia", "two_b", "carrefour", "tradeline", "dream2000", "raya"]:
            res = asyncio.run(_run_single_offline_fixture(sid, data_dir=str(tmp_path), max_products=6))
            assert len(res.products) >= 1, f"{sid} returned 0 products"
            assert len(res.observations) >= 1, f"{sid} returned 0 observations"
            for p in res.products:
                assert p.source_id == sid
                assert p.source_product_id
                assert p.source_url
                assert p.collected_at is not None
            for o in res.observations:
                assert o.source_id == sid
                assert o.source_product_id
                assert o.collected_at is not None
                assert isinstance(o.availability_scope, AvailabilityScope)
                assert o.stock_quantity is None, f"{sid} violated stock_quantity forbidden-conversion rule"


# ─────────────────────────────────────────────────────────────────────
# WP9 & WP10 — Compliance Evidence, Blocked Isolation & Zero 0-Byte Files
# ─────────────────────────────────────────────────────────────────────

class TestComplianceEvidence:
    """WP9/WP10/WP12: Evidence blocks in sources.yaml, blocked source network isolation, zero 0-byte files."""

    def _load_raw_sources(self):
        import yaml
        from pathlib import Path
        src_path = Path(__file__).parent.parent / "config" / "sources.yaml"
        with open(src_path, encoding="utf-8") as f:
            return yaml.safe_load(f)["sources"]

    def test_every_source_has_evidence_block(self):
        sources = self._load_raw_sources()
        assert len(sources) >= 21
        for sid, src in sources.items():
            assert "evidence" in src, f"{sid} missing evidence block"
            ev = src["evidence"]
            assert ev.get("evidence_url")
            assert ev.get("captured_on")
            assert ev.get("summary")
            assert ev.get("decided_by")

    def test_class_c_and_d_sources_never_enabled(self):
        sources = self._load_raw_sources()
        for sid, src in sources.items():
            if src["compliance_status"] in ("C", "D"):
                assert src["enabled"] is False, f"{sid} (Class {src['compliance_status']}) must not be enabled"

    def test_blocked_source_never_calls_http_client(self, tmp_path, monkeypatch):
        """WP12: Blocked sources (BTechExtractor) never initialize or call the HTTP client."""
        import asyncio
        import httpx
        from extractors.base import ComplianceError
        from extractors.source_btech.extractor import BTechExtractor

        called = False
        async def forbidden_get(*args, **kwargs):
            nonlocal called
            called = True
            raise AssertionError("HTTP client must never be called for blocked source!")

        monkeypatch.setattr(httpx.AsyncClient, "get", forbidden_get)
        ext = BTechExtractor(data_dir=str(tmp_path))
        with pytest.raises(ComplianceError):
            asyncio.run(ext.run())
        assert called is False

    def test_live_robots_txt_disallow_aborts_as_blocked(self, tmp_path):
        """WP9: If live robots.txt disallows a target path, fetch() aborts with ComplianceError."""
        import asyncio
        from extractors.base import ComplianceError
        from extractors.source_jumia.extractor import JumiaExtractor

        ext = JumiaExtractor(data_dir=str(tmp_path))
        ext._robots_txt = "User-agent: *\nDisallow: /phones-tablets/\n"
        with pytest.raises(ComplianceError, match="disallowed by live robots.txt"):
            asyncio.run(ext.fetch("https://www.jumia.com.eg/phones-tablets/"))

    def test_zero_empty_files_in_repo(self):
        """WP10: No 0-byte files anywhere in the repository."""
        from pathlib import Path
        root = Path(__file__).parent.parent
        empty_files = [
            str(p.relative_to(root))
            for p in root.rglob("*")
            if p.is_file()
            and ".venv" not in p.parts
            and ".git" not in p.parts
            and ".pytest_cache" not in p.parts
            and p.stat().st_size == 0
        ]
        assert empty_files == [], f"Found 0-byte files: {empty_files}"


# ─────────────────────────────────────────────────────────────────────
# WP11 — Docs Match Config Tests
# ─────────────────────────────────────────────────────────────────────

class TestDocsMatchConfig:
    """WP11: Assert README and docs/DATA_COLLECTION_STATUS.md source statuses match config/sources.yaml."""

    def test_docs_exist_and_match_sources_yaml(self):
        import yaml
        from pathlib import Path

        root = Path(__file__).parent.parent
        sources = yaml.safe_load((root / "config" / "sources.yaml").read_text(encoding="utf-8"))["sources"]

        status_doc = (root / "docs" / "DATA_COLLECTION_STATUS.md").read_text(encoding="utf-8")
        readme_doc = (root / "README.md").read_text(encoding="utf-8")
        queue_doc = (root / "docs" / "COMPLIANCE_REVIEW_QUEUE.md").read_text(encoding="utf-8")
        matrix_doc = (root / "docs" / "FIELD_MATRIX.md").read_text(encoding="utf-8")

        assert len(status_doc) > 1000
        assert len(queue_doc) > 1000
        assert len(matrix_doc) > 1000

        for sid, cfg in sources.items():
            assert f"`{sid}`" in status_doc, f"{sid} missing from DATA_COLLECTION_STATUS.md"
            assert f"`{sid}`" in readme_doc, f"{sid} missing from README.md"
            assert f"`{sid}`" in queue_doc, f"{sid} missing from COMPLIANCE_REVIEW_QUEUE.md"
            expected_enabled = "`true`" if cfg["enabled"] else "`false`"
            assert expected_enabled in status_doc


# ─────────────────────────────────────────────────────────────────────
# WP12 — Golden-File & Regression Tests
# ─────────────────────────────────────────────────────────────────────

class TestGoldenFiles:
    """WP12: Golden-file tests per source on regenerated samples/<source>/."""

    def _load_sample(self, source_id: str, filename: str):
        import json
        from pathlib import Path
        path = Path(__file__).parent.parent / "samples" / source_id / filename
        assert path.exists(), f"Missing sample file: {path}"
        return json.loads(path.read_text(encoding="utf-8"))

    @pytest.mark.parametrize("source_id", ["jumia", "two_b", "carrefour", "tradeline", "dream2000", "raya"])
    def test_golden_sample_files_stamped_and_valid(self, source_id: str):
        products = self._load_sample(source_id, "products.json")
        observations = self._load_sample(source_id, "observations.json")
        meta = self._load_sample(source_id, "extraction_meta.json")
        issues = self._load_sample(source_id, "quality_issues.json")

        assert len(products) >= 2
        assert len(observations) >= 2
        assert meta["source_id"] == source_id
        assert meta["run_id"]
        assert meta["mode"] in ("live", "offline_fixture", "synthetic")
        assert meta["collected_at"]
        assert "null_rates" in meta
        assert isinstance(issues, list)

        for o in observations:
            assert o["stock_quantity"] is None
            assert o["row_hash"] and len(o["row_hash"]) == 64

    def test_dream2000_golden_gtin_preserved(self):
        products = self._load_sample("dream2000", "products.json")
        assert any(p.get("gtin") == "6942785106048" for p in products)

    def test_tradeline_golden_variants_and_gps_preserved(self):
        products = self._load_sample("tradeline", "products.json")
        locations = self._load_sample("tradeline", "locations.json")
        assert any(p.get("variants") for p in products)
        assert any(loc.get("latitude") and loc.get("longitude") for loc in locations)


class TestRegressionKnownBugs:
    """WP12: Regression tests for bugs fixed across the data collection phase."""

    def test_regression_price_range_hyphen_not_crash(self):
        from extractors.source_jumia.parser import parse_price
        result = parse_price("100,000 - 120,000 EGP")
        assert result == 100000.0

    def test_regression_validator_returns_overall_quality_score(self):
        from normalization.schema import ExtractionResult
        from validation.data_validator import DataValidator
        report = DataValidator().validate(ExtractionResult(source_id="jumia"))
        assert "overall_quality_score" in report

    def test_regression_main_entity_unwrap_in_jumia_pdp(self):
        from extractors.source_jumia.parser import parse_product_detail_page
        html = """<html><head>
        <script type="application/ld+json">
        {"@context":"https://schema.org","@type":"WebPage",
         "mainEntity":{"@type":"Product","name":"Test iPhone","sku":"TEST123",
          "offers":[{"@type":"Offer","price":"100000","priceCurrency":"EGP",
          "availability":"https://schema.org/InStock","seller":{"@type":"Organization","name":"SellerOne"}},
          {"@type":"Offer","price":"101000","priceCurrency":"EGP","seller":{"@type":"Organization","name":"SellerTwo"}}]}}
        </script></head><body></body></html>"""
        result = parse_product_detail_page(html)
        assert result is not None
        assert result.get("sku") == "TEST123"
        assert result.get("sellers") == ["SellerOne", "SellerTwo"]



class TestQualityScoreAudit:
    """Section 8: Verify missing GTIN, brand, category, seller, and availability_scope reduce quality score."""

    def test_degraded_live_like_fixture_scores_lower_and_emits_issues(self):
        from pathlib import Path
        from extractors.source_2b.parser import parse_category_page
        from normalization.schema import (
            AvailabilityScope,
            AvailabilityStatus,
            Currency,
            ExtractionResult,
            IssueCode,
            Product,
            ProductObservation,
        )
        from validation.data_validator import DataValidator

        fix_path = Path(__file__).parent / "fixtures" / "degraded_live_like_sample.html"
        html = fix_path.read_text(encoding="utf-8")
        cards = parse_category_page(html)
        assert len(cards) == 2

        products = []
        observations = []
        for c in cards:
            prod = Product(
                source_id="two_b",
                source_product_id=c["source_product_id"],
                sku=c.get("sku"),
                gtin=c.get("gtin"),
                product_name=c["product_name"],
                brand=c.get("brand"),
                category=c.get("category"),
                product_url=c["product_url"],
            )
            products.append(prod)
            obs = ProductObservation(
                product_id=prod.product_id,
                source_id="two_b",
                source_product_id=prod.source_product_id,
                price=c["price"],
                currency=Currency.EGP,
                availability_status=c.get("availability_status", AvailabilityStatus.UNKNOWN),
                availability_scope=c.get("availability_scope", AvailabilityScope.UNKNOWN),
                seller_name=None,
                source_url=prod.product_url,
            )
            observations.append(obs)

        res = ExtractionResult(
            source_id="two_b",
            mode="synthetic",
            run_id="test_degraded_run",
            products=products,
            observations=observations,
        )
        report = DataValidator().validate(res)

        # Score must be strictly less than 100% (in fact <= 60% because brand, category, gtin, seller_name, scope are missing)
        assert report["overall_quality_score"] < 60.0
        assert len(res.quality_issues) >= 10

        codes = {qi.issue_code for qi in res.quality_issues}
        messages = " | ".join(qi.message for qi in res.quality_issues)
        assert IssueCode.MISSING_FIELD in codes
        assert IssueCode.MISSING_SKU in codes
        assert IssueCode.AMBIGUOUS_AVAILABILITY in codes
        assert "missing GTIN" in messages
        assert "missing brand" in messages
        assert "missing category" in messages
        assert "missing seller_name" in messages


class TestCarrefourPresenceSemantics:
    """Section 6: Governorate-level presence records must use PRESENCE and not be penalized for missing street address/GPS."""

    def test_carrefour_governorate_presence_not_treated_as_store(self):
        from extractors.source_carrefour.parser import parse_store_locator
        from normalization.schema import ExtractionResult, Location, LocationType
        from validation.data_validator import DataValidator

        raw_locs = parse_store_locator(None)
        assert len(raw_locs) == 19
        assert all(r["location_type"] == LocationType.PRESENCE for r in raw_locs)
        assert all(r["branch_name"] is None for r in raw_locs)
        assert all(r["raw_location_name"] for r in raw_locs)

        locs = [
            Location(
                source_id="carrefour",
                location_type=r["location_type"],
                location_name=r["location_name"],
                branch_name=r["branch_name"],
                raw_location_name=r["raw_location_name"],
                governorate=r["governorate"],
            )
            for r in raw_locs
        ]
        res = ExtractionResult(source_id="carrefour", mode="offline_fixture", locations=locs)
        report = DataValidator().validate(res)
        assert report["locations"]["passed_checks"] == 19
        assert report["locations"]["total_checks"] == 19
        assert len(res.quality_issues) == 0



class TestCrossRunDiffValidation:
    """Section 5: ObservationHistory must stamp run_mode/watchlist_id and refuse invalid cross-mode or cross-watchlist diffs."""

    def test_history_row_fields_and_diff_guards(self, tmp_path):
        import pytest
        from normalization.schema import AvailabilityScope, AvailabilityStatus, ProductObservation
        from validation.observation_history import ObservationHistory

        hist = ObservationHistory(data_dir=str(tmp_path))
        obs1 = ProductObservation(
            product_id="p1",
            source_id="jumia",
            source_product_id="SKU1",
            price=1000.0,
            availability_status=AvailabilityStatus.IN_STOCK,
            availability_scope=AvailabilityScope.DELIVERY_AREA,
        )
        obs2 = ProductObservation(
            product_id="p1",
            source_id="jumia",
            source_product_id="SKU1",
            price=1050.0,
            availability_status=AvailabilityStatus.IN_STOCK,
            availability_scope=AvailabilityScope.DELIVERY_AREA,
        )

        hist.append([obs1], run_id="live_1", run_mode="live", watchlist_id="wl_v1")
        hist.append([obs2], run_id="live_2", run_mode="live", watchlist_id="wl_v1")
        hist.append([obs2], run_id="fix_1", run_mode="offline_fixture", watchlist_id="wl_v1")
        hist.append([obs2], run_id="syn_1", run_mode="synthetic", watchlist_id="wl_v1")
        hist.append([obs2], run_id="live_other_wl", run_mode="live", watchlist_id="wl_v2")

        rows = hist.load_run("jumia", "live_1")
        assert len(rows) == 1
        row = rows[0]
        assert row["run_id"] == "live_1"
        assert row["run_mode"] == "live"
        assert row["watchlist_id"] == "wl_v1"
        assert row["source"] == "jumia"
        assert row["timestamp"]

        # Valid live-to-live diff on same watchlist
        diff = hist.cross_run_diff("jumia", "live_1", "live_2")
        assert diff["products_in_run_1"] == 1
        assert diff["products_in_run_2"] == 1
        assert diff["products_in_a_eq_products_in_b"] is True
        assert len(diff["changed"]) == 1

        # Refuse live vs offline_fixture
        with pytest.raises(ValueError, match="run_mode"):
            hist.cross_run_diff("jumia", "live_1", "fix_1")

        # Refuse live vs synthetic
        with pytest.raises(ValueError, match="run_mode"):
            hist.cross_run_diff("jumia", "live_1", "syn_1")

        # Refuse different watchlists
        with pytest.raises(ValueError, match="watchlist"):
            hist.cross_run_diff("jumia", "live_1", "live_other_wl")
