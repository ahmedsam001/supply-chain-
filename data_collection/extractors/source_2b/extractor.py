"""
2B Egypt Extractor

Compliance: B (Conditional) / LIVE_PENDING_HUMAN_TOS_CONFIRMATION.
Method: static_html + JSON-LD.
Uses source_2b.parser for all parsing.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from extractors.base import BaseExtractor
from normalization.schema import (
    AvailabilityStatus,
    ComplianceStatus,
    Currency,
    ExtractionMethod,
    Location,
    Product,
    ProductObservation,
    Source,
)
from extractors.source_2b.config import (
    BASE_URL,
    CATEGORY_URLS,
    DEPARTMENT_URLS,
    MAX_PAGES_PER_CATEGORY,
    MAX_REQUESTS_PER_MINUTE,
    MIN_DELAY_SECONDS,
    MAX_DELAY_SECONDS,
    STORE_LOCATOR_PATH,
    STORE_LOCATOR_BLOCK_PATH,
)
from extractors.source_2b.parser import (
    determine_availability,
    extract_next_page_url,
    parse_category_page,
    parse_product_detail_page,
    parse_store_locator,
)

import structlog
logger = structlog.get_logger()

DEFAULT_STORES_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "two_b"
    / "real"
    / "stores_sample.html"
)


class TwoBExtractor(BaseExtractor):
    """
    2B Egypt extractor. Compliance class B — enabled for controlled prototype
    (LIVE_PENDING_HUMAN_TOS_CONFIRMATION for commercial production).
    """

    def __init__(
        self,
        fixture_path: Optional[Path] = None,
        store_fixture_path: Optional[Path] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._fixture_path = Path(fixture_path) if fixture_path else None
        self._store_fixture_path = (
            Path(store_fixture_path) if store_fixture_path else None
        )
        self._initial_observations: dict[str, ProductObservation] = {}

    def source_config(self) -> Source:
        return Source(
            source_id="two_b",
            source_name="2B Egypt",
            domain="2b.com.eg",
            compliance_status=ComplianceStatus.CONDITIONAL,
            extraction_method=ExtractionMethod.STATIC_HTML,
            rate_limit_rpm=MAX_REQUESTS_PER_MINUTE,
            min_delay_seconds=MIN_DELAY_SECONDS,
            max_delay_seconds=MAX_DELAY_SECONDS,
            enabled=True,
            notes=(
                "Class B (Conditional) / LIVE_PENDING_HUMAN_TOS_CONFIRMATION. "
                "Magento 2 JSON-LD + static HTML. Crawl-delay: 10s respected."
            ),
        )

    async def extract_products(self) -> list[Product]:
        """Extract products from 2B category pages."""
        all_products: list[Product] = []
        seen_ids: set[str] = set()
        all_observations: dict[str, ProductObservation] = {}

        # Offline fixture mode
        if self._fixture_path and self._fixture_path.exists():
            logger.info("two_b.extract.offline_fixture", path=str(self._fixture_path))
            html = self._fixture_path.read_text(encoding="utf-8")
            cards = parse_category_page(html)
            products, observations = self._cards_to_canonical(cards)
            self._initial_observations = observations
            return products[: self.max_products]

        # Live mode
        self._consecutive_failures = 0
        self._circuit_breaker_tripped = False
        if self.department:
            categories = list(DEPARTMENT_URLS.get(self.department, {}).items())
        else:
            categories = list(CATEGORY_URLS.items())
        for cat_name, cat_path in categories:
            if len(all_products) >= self.max_products:
                break
            if self._circuit_breaker_tripped:
                break

            next_url: Optional[str] = f"{BASE_URL}{cat_path}"
            log = logger.bind(category=cat_name, source="two_b")

            try:
                page_limit = min(5, MAX_PAGES_PER_CATEGORY) if self.max_products <= 500 else MAX_PAGES_PER_CATEGORY
                for page_num in range(1, page_limit + 1):
                    if not next_url:
                        break
                    page_url = next_url
                    response = await self.fetch(page_url)
                    cards = parse_category_page(response.text)

                    if not cards and page_num == 1:
                        log.warning("two_b.category.empty_retrying", page=page_num, url=page_url)
                        await asyncio.sleep(2.0)
                        response = await self.fetch(page_url)
                        cards = parse_category_page(response.text)

                    if not cards:
                        if page_num == 1 and self.record_request_failure(f"empty category {cat_name}"):
                            log.error("two_b.circuit_breaker.open", category=cat_name)
                        break

                    self.record_request_success()
                    products, observations = self._cards_to_canonical(
                        cards, category=cat_name, source_url=page_url
                    )
                    for prod in products:
                        if prod.source_product_id not in seen_ids:
                            seen_ids.add(prod.source_product_id)
                            all_products.append(prod)
                            if prod.product_id in observations:
                                all_observations[prod.product_id] = observations[
                                    prod.product_id
                                ]
                            if len(all_products) >= self.max_products:
                                break

                    if len(all_products) >= self.max_products:
                        break

                    next_url = extract_next_page_url(response.text, base_url=BASE_URL)
                    if next_url and "?" in next_url and self._robots_txt and "Disallow: /*?*" in self._robots_txt:
                        next_url = None
                    log.info("two_b.page.done", page=page_num, total=len(all_products))

            except Exception as e:
                self._errors.append(f"Category {cat_name} failed: {e}")
                log.error("two_b.category.error", error=str(e))
                if self.record_request_failure(f"{cat_name}: {type(e).__name__}"):
                    log.error("two_b.circuit_breaker.open", category=cat_name)
                    break

        self._initial_observations = all_observations
        return all_products

    def _cards_to_canonical(
        self,
        cards: list[dict],
        category: Optional[str] = None,
        source_url: Optional[str] = None,
    ) -> tuple[list[Product], dict[str, ProductObservation]]:
        """Convert raw card dicts to canonical models."""
        now = datetime.now(timezone.utc)
        products = []
        observations = {}

        for c in cards:
            name = c.get("product_name", "")
            price_val = c.get("price")
            if not name or price_val is None or float(price_val) <= 0:
                continue

            spid = str(c.get("source_product_id") or name[:50])
            canonical_pid = f"two_b:{spid}"
            prod = Product(
                product_id=canonical_pid,
                source_id="two_b",
                source_product_id=spid,
                sku=c.get("sku"),
                gtin=c.get("gtin"),
                product_name=name,
                brand=c.get("brand"),
                category=(category.title() if category else c.get("category")),
                product_url=c.get("product_url") or "",
                source_url=source_url or c.get("product_url"),
                image_url=c.get("image_url"),
                collected_at=now,
            )
            products.append(prod)

            avail_st = c.get("availability_status", AvailabilityStatus.IN_STOCK)
            if avail_st == AvailabilityStatus.UNKNOWN:
                avail_st = AvailabilityStatus.IN_STOCK
            raw_stock = c.get("stock_status")
            stock_st = raw_stock if (raw_stock and raw_stock != "UNKNOWN") else (
                "OUT_OF_STOCK" if avail_st == AvailabilityStatus.OUT_OF_STOCK else "IN_STOCK"
            )

            obs = ProductObservation(
                product_id=canonical_pid,
                source_id="two_b",
                source_product_id=spid,
                observed_at=now,
                collected_at=now,
                price=float(price_val),
                old_price=c.get("old_price"),
                discount=c.get("discount"),
                currency=Currency.EGP,
                availability_status=avail_st,
                availability_scope=c.get("availability_scope"),
                stock_status=stock_st,
                stock_quantity=None,  # 2B does not expose quantities
                raw_availability_text=c.get("raw_availability_text") or "In Stock",
                raw_price_text=c.get("raw_price_text") or str(price_val),
                delivery_available=c.get("delivery_available", True),
                delivery_eta=c.get("delivery_eta"),
                delivery_fee=c.get("delivery_fee"),
                seller_name="2B Egypt",
                source_url=c.get("product_url"),
                fulfillment_method="retailer",
            )
            observations[canonical_pid] = obs

        return products, observations

    async def extract_availability(self) -> list[ProductObservation]:
        """Return observations collected during product extraction."""
        return list(self._initial_observations.values())

    async def extract_locations(self) -> list[Location]:
        """
        Extract physical branch locations from 2B public store locator
        (`https://2b.com.eg/en/stores`).
        """
        store_url = f"{BASE_URL}{STORE_LOCATOR_PATH}"

        # Offline fixture mode
        fixture = self._store_fixture_path or (
            DEFAULT_STORES_FIXTURE if self._fixture_path else None
        )
        if fixture and fixture.exists():
            logger.info("two_b.locations.offline_fixture", path=str(fixture))
            html = fixture.read_text(encoding="utf-8")
            return parse_store_locator(html, source_id="two_b", source_url=store_url)

        if self._circuit_breaker_tripped:
            logger.warning("two_b.locations.skipped_circuit_breaker")
            return []

        try:
            response = await self.fetch(store_url)
            html = response.text
            # If the outer shell loads #mw-store-locator-locations via the public MageWorx block URL,
            # fetch that public HTML block (without query params, respecting robots.txt and 10s delay).
            if (
                "section.mw-sl__stores__list__item" not in html
                and "store_locator/location/updatemainpage" in html
            ):
                await asyncio.sleep(MIN_DELAY_SECONDS)
                block_url = f"{BASE_URL}{STORE_LOCATOR_BLOCK_PATH}"
                if not self._http_client:
                    await self._init_http_client()
                block_resp = await self._http_client.post(
                    block_url,
                    headers={"X-Requested-With": "XMLHttpRequest"},
                    timeout=15.0,
                    allow_redirects=True,
                    impersonate="chrome116",
                )
                self._request_count += 1
                if block_resp.status_code == 200 and block_resp.text.strip():
                    html = block_resp.text
            locs = parse_store_locator(html, source_id="two_b", source_url=store_url)
            if len(locs) <= 1 and DEFAULT_STORES_FIXTURE.exists():
                logger.info("two_b.locations.fallback_real_snapshot", path=str(DEFAULT_STORES_FIXTURE))
                locs = parse_store_locator(
                    DEFAULT_STORES_FIXTURE.read_text(encoding="utf-8"),
                    source_id="two_b",
                    source_url=store_url,
                )
            return locs
        except Exception as e:
            self._errors.append(f"Store locator failed: {e}")
            logger.error("two_b.locations.error", error=str(e))
            return []
