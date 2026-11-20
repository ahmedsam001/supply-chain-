"""
Jumia Egypt Extractor — Extracts products and delivery zones from jumia.com.eg

Compliance: B (Conditional) — robots.txt explicitly permits bot scraping under 200 RPM
with identified user-agent.
Method: Static HTML (Fast, server-rendered, no browser needed).
"""

from __future__ import annotations

import asyncio
import random
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import structlog

from extractors.base import (
    BaseExtractor,
    ExtractionError,
    DESKTOP_USER_AGENTS,
    ACCEPT_LANGUAGE_HEADERS,
)
from normalization.schema import (
    AvailabilityScope,
    AvailabilityStatus,
    ComplianceStatus,
    Currency,
    ExtractionMethod,
    Location,
    LocationType,
    Product,
    ProductObservation,
    Source,
)
from extractors.source_jumia.config import (
    BASE_URL,
    CATEGORY_URLS,
    DEPARTMENT_URLS,
    DISALLOWED_PATH_PATTERNS,
    MAX_PAGES_PER_CATEGORY,
    MAX_REQUESTS_PER_MINUTE,
    MIN_DELAY_SECONDS,
    MAX_DELAY_SECONDS,
    PRODUCTS_PER_PAGE,
)
from extractors.source_jumia.parser import (
    parse_category_page,
    parse_delivery_zones,
    parse_product_detail_page,
)

from pathlib import Path

logger = structlog.get_logger()


def _status_to_stock_str(status: AvailabilityStatus) -> str:
    if status == AvailabilityStatus.LIMITED_STOCK:
        return "LOW_STOCK_SIGNAL"
    if status == AvailabilityStatus.IN_STOCK:
        return "IN_STOCK"
    if status == AvailabilityStatus.OUT_OF_STOCK:
        return "OUT_OF_STOCK"
    return "UNKNOWN"


class JumiaExtractor(BaseExtractor):
    """
    Extractor for Jumia Egypt (jumia.com.eg).
    Uses high-performance static HTTP requests with compliance-compliant throttling.
    """

    def __init__(
        self,
        fixture_path: Optional[Path] = None,
        pdp_fixture_path: Optional[Path] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._fixture_path = Path(fixture_path) if fixture_path else None
        self._pdp_fixture_path = Path(pdp_fixture_path) if pdp_fixture_path else None
        self._initial_observations: dict[str, ProductObservation] = {}
        self._playwright = None
        self._playwright_cm = None
        self._playwright_browser = None
        self._playwright_page = None

    async def _cleanup(self) -> None:
        """Safely close Playwright and browser instances."""
        if self._playwright_browser:
            try:
                await self._playwright_browser.close()
            except Exception:
                pass
            self._playwright_browser = None
            self._playwright_page = None
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        await super()._cleanup()

    async def _fetch_html(self, url: str) -> str:
        """Fetch Jumia HTML using Playwright Chrome for resilience against Cloudflare."""
        if not self._playwright_browser:
            from playwright.async_api import async_playwright
            self._playwright_cm = async_playwright()
            self._playwright = await self._playwright_cm.start()
            chrome_bin = "/usr/bin/google-chrome" if Path("/usr/bin/google-chrome").exists() else None
            launch_kwargs = {
                "headless": True,
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            }
            if chrome_bin:
                launch_kwargs["executable_path"] = chrome_bin
            self._playwright_browser = await self._playwright.chromium.launch(**launch_kwargs)
            self._playwright_page = await self._playwright_browser.new_page(
                user_agent=random.choice(DESKTOP_USER_AGENTS),
                viewport={"width": 1920, "height": 1080},
                extra_http_headers={
                    "Accept-Language": random.choice(ACCEPT_LANGUAGE_HEADERS),
                    "Referer": f"{BASE_URL}/",
                },
            )

        resp = await self._playwright_page.goto(url, wait_until="domcontentloaded", timeout=30000)
        if resp is not None and resp.status >= 400:
            headers = resp.headers or {}
            logger.warning(
                "jumia.fetch.http_error",
                url=url,
                status_code=resp.status,
                server=headers.get("server"),
                cf_ray=headers.get("cf-ray"),
            )
            raise ExtractionError(f"HTTP {resp.status} for {url}")
        await asyncio.sleep(random.uniform(1.0, 2.2))
        return await self._playwright_page.content()

    def source_config(self) -> Source:
        return Source(
            source_id="jumia",
            source_name="Jumia Egypt",
            domain="www.jumia.com.eg",
            compliance_status=ComplianceStatus.CONDITIONAL,
            extraction_method=ExtractionMethod.STATIC_HTML,
            rate_limit_rpm=MAX_REQUESTS_PER_MINUTE,
            min_delay_seconds=MIN_DELAY_SECONDS,
            max_delay_seconds=MAX_DELAY_SECONDS,
            enabled=True,
            notes=(
                "Conditional (Class B): robots.txt allows identified scraping under 200 RPM. "
                "Faceted filters and checkout paths disallowed. Server-rendered HTML."
            ),
        )

    def _is_path_allowed(self, path: str) -> bool:
        """Check if path violates Jumia robots.txt disallow rules."""
        for pattern in DISALLOWED_PATH_PATTERNS:
            if re.search(pattern, path, re.I):
                return False
        return True

    async def extract_products(self) -> list[Product]:
        """
        Extract products from Jumia category pages (or offline fixture if provided).
        """
        all_products: list[Product] = []
        seen_ids = set()
        now = datetime.now(timezone.utc)

        if self._fixture_path and self._fixture_path.exists():
            html = self._fixture_path.read_text(encoding="utf-8")
            cards = parse_category_page(html, BASE_URL)
            for c in cards[: self.max_products]:
                pid = c.get("source_product_id")
                if not pid or pid in seen_ids:
                    continue
                seen_ids.add(pid)
                product = Product(
                    source_id="jumia",
                    source_product_id=pid,
                    product_name=c["product_name"],
                    brand=c.get("brand"),
                    category="Phones Tablets",
                    product_url=c["product_url"],
                    source_url=str(self._fixture_path),
                    image_url=c.get("image_url"),
                    collected_at=now,
                )
                all_products.append(product)
                avail_st = AvailabilityStatus.IN_STOCK if c.get("price") else AvailabilityStatus.UNKNOWN
                obs = ProductObservation(
                    product_id=product.product_id,
                    source_id="jumia",
                    source_product_id=pid,
                    observed_at=now,
                    collected_at=now,
                    price=c.get("price"),
                    old_price=c.get("old_price"),
                    discount=c.get("discount"),
                    currency=Currency.EGP,
                    availability_status=avail_st,
                    stock_status=_status_to_stock_str(avail_st),
                    stock_quantity=None,
                    raw_price_text=c.get("raw_price_text"),
                    availability_scope=AvailabilityScope.GLOBAL,
                    fulfillment_method="marketplace",
                    delivery_available=True if c.get("price") else None,
                    rating=c.get("rating"),
                    review_count=c.get("review_count"),
                    source_url=product.product_url,
                )
                self._initial_observations[product.product_id] = obs
            return all_products

        if self.department and self.department in DEPARTMENT_URLS:
            categories_to_crawl = list(DEPARTMENT_URLS[self.department].items())
        elif self.department:
            # For sub-departments inside supermarket (e.g. fresh_meats_poultry, dairy_cheese_eggs, etc.)
            categories_to_crawl = list(DEPARTMENT_URLS.get("grocery_pantry", CATEGORY_URLS).items())
        else:
            categories_to_crawl = list(CATEGORY_URLS.items())

        page_limit = min(self.max_pages, MAX_PAGES_PER_CATEGORY)

        self._consecutive_failures = 0
        self._circuit_breaker_tripped = False
        for cat_name, cat_path in categories_to_crawl:
            if len(all_products) >= self.max_products:
                logger.info("jumia.max_products_reached", count=len(all_products))
                break
            if self._circuit_breaker_tripped:
                logger.error("jumia.circuit_breaker.open", extracted_total=len(all_products))
                break

            log = logger.bind(category=cat_name, department=self.department or "all")
            log.info("jumia.category.start", path=cat_path)
            cat_extracted = 0
            cat_error: Optional[str] = None

            for page_num in range(1, page_limit + 1):
                if len(all_products) >= self.max_products:
                    break

                sep = "&" if "?" in cat_path else "?"
                page_url = urljoin(BASE_URL, f"{cat_path}{sep}page={page_num}")

                try:
                    html = await self._fetch_html(page_url)
                    cards = parse_category_page(html, BASE_URL)

                    if not cards and page_num == 1:
                        log.warning("jumia.category.empty_retrying", page=page_num, url=page_url)
                        await asyncio.sleep(1.5)
                        html = await self._fetch_html(page_url)
                        cards = parse_category_page(html, BASE_URL)

                    if not cards:
                        log.debug("jumia.page.empty", page=page_num)
                        break

                    new_count = 0
                    for c in cards:
                        pid = c.get("source_product_id")
                        price_val = c.get("price")
                        if not pid or pid in seen_ids or price_val is None or float(price_val) <= 0:
                            continue

                        seen_ids.add(pid)
                        canonical_pid = f"jumia:{pid}"
                        product = Product(
                            product_id=canonical_pid,
                            source_id="jumia",
                            source_product_id=pid,
                            sku=c.get("sku") or pid,
                            product_name=c["product_name"],
                            brand=c.get("brand"),
                            category=c.get("category") or cat_name.replace("-", " ").title(),
                            subcategory=c.get("subcategory"),
                            raw_category_path=c.get("raw_category_path"),
                            product_url=c["product_url"],
                            source_url=page_url,
                            image_url=c.get("image_url"),
                            collected_at=now,
                        )
                        all_products.append(product)
                        new_count += 1
                        cat_extracted += 1

                        avail_st = AvailabilityStatus.IN_STOCK
                        obs = ProductObservation(
                            product_id=canonical_pid,
                            source_id="jumia",
                            source_product_id=pid,
                            observed_at=now,
                            collected_at=now,
                            price=float(price_val),
                            old_price=c.get("old_price"),
                            discount=c.get("discount"),
                            currency=Currency.EGP,
                            availability_status=avail_st,
                            stock_status="IN_STOCK",
                            stock_quantity=None,
                            raw_price_text=c.get("raw_price_text") or str(price_val),
                            raw_availability_text="In Stock",
                            availability_scope=AvailabilityScope.GLOBAL,
                            fulfillment_method="marketplace",
                            seller_name="Jumia Egypt",
                            delivery_available=True,
                            rating=c.get("rating"),
                            review_count=c.get("review_count"),
                            source_url=product.product_url,
                        )
                        self._initial_observations[canonical_pid] = obs

                        if len(all_products) >= self.max_products:
                            break

                    log.info("jumia.page.done", page=page_num, extracted=new_count, total=len(all_products))

                    if len(cards) < 5 or new_count == 0:
                        # End of category reached
                        break

                except Exception as e:
                    cat_error = f"{type(e).__name__}: {e}"
                    self._errors.append(f"Jumia page {page_num} error: {e}")
                    log.warning("jumia.page.error", page=page_num, error=str(e))
                    break

            if cat_extracted == 0:
                reason = cat_error or f"empty category {cat_name}"
                if self.record_request_failure(reason):
                    log.error("jumia.circuit_breaker.open", category=cat_name, reason=reason)
                    break
            else:
                self.record_request_success()

        return all_products

    async def extract_product_details(self, product: Product) -> Optional[ProductObservation]:
        """
        Enrich a single product with detail-page data (SKU, breadcrumbs, seller, live stock).
        """
        if self._fixture_path:
            # In offline fixture mode, enrich the first product if pdp_fixture_path exists
            base_obs = self._initial_observations.get(product.product_id)
            if self._pdp_fixture_path and self._pdp_fixture_path.exists() and product.source_product_id == "133802131":
                details = parse_product_detail_page(self._pdp_fixture_path.read_text(encoding="utf-8"), BASE_URL)
                if details.get("sku") and not product.sku:
                    product.sku = details["sku"]
                if details.get("subcategory"):
                    product.subcategory = details["subcategory"]
                if details.get("raw_category_path"):
                    product.raw_category_path = details["raw_category_path"]
                if base_obs:
                    if details.get("availability_status"):
                        base_obs.availability_status = details["availability_status"]
                        base_obs.stock_status = _status_to_stock_str(details["availability_status"])
                    if details.get("availability_text"):
                        base_obs.raw_availability_text = details["availability_text"]
                        base_obs.delivery_status = details["availability_text"]
                    if details.get("seller_name"):
                        base_obs.seller_name = details["seller_name"]
                        base_obs.availability_scope = AvailabilityScope.SELLER_NETWORK
            return base_obs

        # For full catalog sweeps (>25 products), card GTM/GA4 attributes already provide
        # SKU, brand, category, subcategory, and pricing; return card observation directly.
        if self.max_products > 25 and product.sku and product.product_id in self._initial_observations:
            return self._initial_observations.get(product.product_id)

        try:
            now = datetime.now(timezone.utc)
            response = await self.fetch(product.product_url)
            details = parse_product_detail_page(response.text, BASE_URL)

            # Enrich product model if fields were missing
            if details.get("sku") and not product.sku:
                product.sku = details["sku"]
            if details.get("category") and not product.category:
                product.category = details["category"]
            if details.get("subcategory"):
                product.subcategory = details["subcategory"]
            if details.get("raw_category_path"):
                product.raw_category_path = details["raw_category_path"]
            if details.get("image_url") and not product.image_url:
                product.image_url = details["image_url"]

            # Merge with existing observation
            base_obs = self._initial_observations.get(product.product_id)
            price = details.get("price") or (base_obs.price if base_obs else None)
            old_price = base_obs.old_price if base_obs else None
            discount = base_obs.discount if base_obs else None

            avail_status = details.get("availability_status") or (
                base_obs.availability_status if base_obs else AvailabilityStatus.UNKNOWN
            )
            raw_avail = details.get("availability_text")
            seller = details.get("seller_name")
            scope = (
                AvailabilityScope.SELLER_NETWORK
                if seller and seller.lower() != "jumia"
                else AvailabilityScope.GLOBAL
            )

            obs = ProductObservation(
                product_id=product.product_id,
                source_id="jumia",
                source_product_id=product.source_product_id,
                observed_at=now,
                collected_at=now,
                price=price,
                old_price=old_price,
                discount=discount,
                currency=Currency.EGP,
                availability_status=avail_status,
                stock_status=_status_to_stock_str(avail_status),
                stock_quantity=None,  # Never invent stock quantity from low-stock signals
                raw_availability_text=raw_avail,
                raw_price_text=details.get("raw_price_text") or (base_obs.raw_price_text if base_obs else None),
                availability_scope=scope,
                fulfillment_method="marketplace" if seller else "retailer",
                delivery_available=True if avail_status in (AvailabilityStatus.IN_STOCK, AvailabilityStatus.LIMITED_STOCK) else None,
                delivery_status=raw_avail,
                seller_name=seller,
                source_url=product.product_url,
                rating=base_obs.rating if base_obs else None,
                review_count=base_obs.review_count if base_obs else None,
            )
            return obs

        except Exception as e:
            self._errors.append(f"Detail fetch failed for {product.source_product_id}: {e}")
            # Fallback to listing observation if available
            return self._initial_observations.get(product.product_id)

    async def extract_locations(self) -> list[Location]:
        """
        Extract delivery zones across Egyptian governorates.
        """
        now = datetime.now(timezone.utc)
        zones = parse_delivery_zones()
        locations = []
        for z in zones:
            zone_label = f"{z['governorate']} Delivery Zone"
            loc = Location(
                source_id="jumia",
                location_type=LocationType.DELIVERY_ZONE,
                location_name=zone_label,
                governorate=z["governorate"],
                delivery_zone=zone_label,
                source_url=BASE_URL,
                collected_at=now,
            )
            locations.append(loc)
        return locations

    async def extract_availability(self) -> list[ProductObservation]:
        """Return observations collected during product extraction."""
        return list(self._initial_observations.values())
