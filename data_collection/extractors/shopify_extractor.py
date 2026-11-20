"""
Shopify JSON Extractor — Generic extractor for Shopify-powered stores.

Works with Tradeline (tradelinestores.com) and Dream 2000 (dream2000.com).
Uses the public /products.json Shopify endpoint — NO browser needed.
"""

from __future__ import annotations

import asyncio
import json
import random
from datetime import datetime, timezone
from typing import Optional

import httpx
import structlog

from extractors.base import BaseExtractor, get_rotated_headers
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

logger = structlog.get_logger()


class ShopifyExtractor(BaseExtractor):
    """
    Generic extractor for Shopify-based Egyptian electronics retailers.

    Uses the public /products.json endpoint which returns clean structured
    JSON with product variants, prices, availability, and images.

    No browser automation needed.
    """

    def __init__(
        self,
        source_id: str,
        source_name: str,
        domain: str,
        base_url: str,
        store_locator_path: str = "/pages/store-locator",
        compliance_status: ComplianceStatus = ComplianceStatus.CONDITIONAL,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._source_id = source_id
        self._source_name = source_name
        self._domain = domain
        self._base_url = base_url
        self._store_locator_path = store_locator_path
        self._compliance_status = compliance_status
        self._cached_observations: list[ProductObservation] = []
        self._pw = None
        self._pw_browser = None
        self._pw_page = None

    def source_config(self) -> Source:
        return Source(
            source_id=self._source_id,
            source_name=self._source_name,
            domain=self._domain,
            compliance_status=self._compliance_status,
            extraction_method=ExtractionMethod.PUBLIC_JSON,
            rate_limit_rpm=20,
            min_delay_seconds=1.5,
            max_delay_seconds=3.5,
            enabled=True,
            notes="Shopify /products.json public endpoint. Single-pass extraction.",
        )

    async def _cleanup(self):
        """Clean up both BaseExtractor resources and Playwright fallback instances."""
        if hasattr(self, "_pw_browser") and self._pw_browser:
            try:
                await self._pw_browser.close()
            except Exception:
                pass
            self._pw_browser = None
        if hasattr(self, "_pw") and self._pw:
            try:
                await self._pw.stop()
            except Exception:
                pass
            self._pw = None
        self._pw_page = None
        await super()._cleanup()

    async def _fetch_json_page(self, url: str) -> dict:
        """Fetch Shopify JSON with httpx, falling back immediately to Playwright Chrome if blocked or rate-limited."""
        import os
        if self._http_client is None:
            await self._init_http_client()

        use_pw = getattr(self, "_force_playwright", False)
        if not use_pw:
            try:
                headers = get_rotated_headers(url)
                resp = await self._http_client.get(url, headers=headers)
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code in (403, 429, 503):
                    logger.warning(
                        "shopify.httpx_blocked_switching_to_playwright",
                        status=resp.status_code,
                        url=url,
                    )
                    self._force_playwright = True
            except Exception as e:
                logger.warning(
                    "shopify.httpx_failed_switching_to_playwright",
                    error=str(e),
                    url=url,
                )
                self._force_playwright = True

        if not hasattr(self, "_pw_page") or self._pw_page is None:
            from playwright.async_api import async_playwright
            self._pw = await async_playwright().start()
            self._pw_browser = await self._pw.chromium.launch(
                headless=True,
                executable_path="/usr/bin/google-chrome" if os.path.exists("/usr/bin/google-chrome") else None,
            )
            self._pw_page = await self._pw_browser.new_page(
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
            )

        await self._pw_page.goto(url, wait_until="networkidle", timeout=30000)
        body = await self._pw_page.inner_text("body")
        return json.loads(body)

    async def extract_products(self) -> list[Product]:
        """
        Single-pass extraction of both Product catalog metadata AND ProductObservation
        (price, old_price, discount, stock_status) from Shopify's public /products.json endpoint.
        Eliminates the second pass in extract_availability(), cutting requests by 50%.
        """
        all_products: list[Product] = []
        self._cached_observations = []
        seen_ids: set[str] = set()
        page = 1
        max_per_page = 250  # Shopify max
        effective_max_pages = max(self.max_pages, (self.max_products // max_per_page) + 5)
        backoff_schedule = [10.0, 20.0, 40.0, 80.0]
        page_retries = 0

        log = logger.bind(source=self._source_name)
        log.info("shopify.extract.start", max_products=self.max_products, max_pages=effective_max_pages)

        while page <= effective_max_pages:
            url = (
                f"{self._base_url}/products.json"
                f"?limit={max_per_page}&page={page}"
            )

            try:
                if page > 1:
                    await asyncio.sleep(random.uniform(1.0, 2.0))

                data = await self._fetch_json_page(url)
                page_retries = 0
                shopify_products = data.get("products", []) if isinstance(data, dict) else []

                if not shopify_products:
                    log.info("shopify.pagination.end", page=page)
                    break

                for sp in shopify_products:
                    product, obs = self._parse_shopify_product_and_observation(sp)
                    if product and obs and obs.price is not None and obs.price > 0:
                        if product.source_product_id not in seen_ids:
                            seen_ids.add(product.source_product_id)
                            all_products.append(product)
                            self._cached_observations.append(obs)
                            if len(all_products) >= self.max_products:
                                break

                log.info(
                    "shopify.page.done",
                    page=page,
                    products_in_page=len(shopify_products),
                    total_products=len(all_products),
                    total_observations=len(self._cached_observations),
                )

                if len(all_products) >= self.max_products or len(shopify_products) < max_per_page:
                    break

                page += 1

            except Exception as e:
                self._errors.append(f"Page {page} failed: {e}")
                log.error("shopify.page.error", page=page, error=str(e))
                break

        log.info(
            "shopify.extract.done",
            total_products=len(all_products),
            total_observations=len(self._cached_observations),
        )
        return all_products

    def _parse_shopify_product_and_observation(
        self, sp: dict
    ) -> tuple[Optional[Product], Optional[ProductObservation]]:
        """
        Single-pass parser: extracts both canonical Product and ProductObservation
        from a single Shopify product JSON object.
        """
        try:
            product_id = str(sp.get("id", "")).strip()
            title = str(sp.get("title", "")).strip()
            handle = str(sp.get("handle", "")).strip()

            if not product_id or not title or not handle:
                return None, None

            canonical_pid = f"{self._source_id}:{product_id}"
            product_url = f"{self._base_url}/products/{handle}"
            brand = str(sp.get("vendor", "")).strip() or None
            category = str(sp.get("product_type", "")).strip() or None

            images = sp.get("images", [])
            image_url = images[0].get("src") if images else None

            tags = sp.get("tags", [])
            tag_str = ", ".join(tags) if isinstance(tags, list) else str(tags or "").strip()
            raw_cat = f"{category} > {tag_str}" if (category and tag_str) else (tag_str or category or None)

            variants = sp.get("variants", [])
            if not variants:
                return None, None

            # Pick the best variant: prefer first available variant with price > 0, else first variant with price > 0
            chosen_variant = None
            for v in variants:
                p_val = _safe_float(v.get("price"))
                if p_val and p_val > 0 and v.get("available", False):
                    chosen_variant = v
                    break
            if chosen_variant is None:
                for v in variants:
                    p_val = _safe_float(v.get("price"))
                    if p_val and p_val > 0:
                        chosen_variant = v
                        break
            if chosen_variant is None:
                return None, None

            price = _safe_float(chosen_variant.get("price"))
            compare_at = _safe_float(chosen_variant.get("compare_at_price"))
            if compare_at is not None and price is not None and compare_at <= price:
                compare_at = None

            discount = None
            if price and compare_at and compare_at > price:
                discount = round((1 - price / compare_at) * 100, 1)

            available = any(bool(v.get("available", False)) for v in variants if _safe_float(v.get("price")))
            avail_enum = AvailabilityStatus.IN_STOCK if available else AvailabilityStatus.OUT_OF_STOCK
            stock_str = "IN_STOCK" if available else "OUT_OF_STOCK"

            sku = str(chosen_variant.get("sku") or "").strip() or None
            now = datetime.now(timezone.utc)

            product = Product(
                product_id=canonical_pid,
                source_id=self._source_id,
                source_product_id=product_id,
                sku=sku,
                product_name=title,
                brand=brand,
                category=category,
                raw_category_path=raw_cat,
                product_url=product_url,
                source_url=product_url,
                image_url=image_url,
                collected_at=now,
            )

            obs = ProductObservation(
                product_id=canonical_pid,
                source_id=self._source_id,
                source_product_id=product_id,
                observed_at=now,
                collected_at=now,
                price=price,
                old_price=compare_at,
                discount=discount,
                currency=Currency.EGP,
                raw_price_text=str(chosen_variant.get("price")),
                availability_status=avail_enum,
                availability_scope=AvailabilityScope.GLOBAL,
                stock_status=stock_str,
                raw_availability_text="In Stock" if available else "Out of Stock",
                seller_name=self._source_name,
                fulfillment_method="retailer",
                source_url=product_url,
            )

            return product, obs
        except Exception as e:
            logger.debug("shopify.parse.error", error=str(e))
            return None, None

    def _parse_shopify_product(self, sp: dict) -> Optional[Product]:
        """Parse a single Shopify product JSON into our canonical model."""
        product, _ = self._parse_shopify_product_and_observation(sp)
        return product

    async def extract_product_details(
        self, product: Product
    ) -> Optional[ProductObservation]:
        """
        Single-pass extraction already populated self._cached_observations during extract_products().
        """
        return None

    async def extract_availability(self) -> list[ProductObservation]:
        """
        Return observations already extracted in a single pass during extract_products().
        Eliminates the redundant second pass over /products.json.
        """
        if self._cached_observations:
            return list(self._cached_observations)

        # Fallback only if extract_availability() was invoked standalone without extract_products()
        await self.extract_products()
        return list(self._cached_observations)

    def _parse_shopify_observation(
        self, sp: dict
    ) -> list[ProductObservation]:
        """Parse availability observation from Shopify product variants."""
        _, obs = self._parse_shopify_product_and_observation(sp)
        return [obs] if obs else []

    async def extract_locations(self) -> list[Location]:
        """
        Shopify stores typically have a store locator page.
        This requires HTML parsing — optionally uses Playwright.
        """
        # For now, return empty — store locator requires HTML parsing
        # which we implement separately if needed
        return []


# ─── Concrete Shopify Extractors ────────────────────────────────────

class TradelineExtractor(ShopifyExtractor):
    """Extractor for Tradeline Stores (Apple Premium Partner in Egypt)."""

    def __init__(self, **kwargs):
        super().__init__(
            source_id="tradeline",
            source_name="Tradeline Stores",
            domain="tradelinestores.com",
            base_url="https://www.tradelinestores.com",
            store_locator_path="/pages/store-locator",
            # Compliance class D (UNKNOWN): robots.txt/ToS not yet verified.
            # Do NOT change to B without completing a compliance review.
            compliance_status=ComplianceStatus.UNKNOWN,
            **kwargs,
        )

    async def extract_locations(self) -> list[Location]:
        """
        Extract physical store branches with real geographic coordinates,
        addresses, phone numbers, and operating hours using Playwright.
        """
        from bs4 import BeautifulSoup
        from playwright.async_api import async_playwright
        from geospatial.egypt_geography import normalize_location

        url = f"{self._base_url}{self._store_locator_path}"
        logger.info("tradeline.locations.playwright_fetch", url=url)
        locations = []

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page(
                    user_agent=(
                        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
                    )
                )
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_selector(".js-my-location-result", timeout=15000)
                html = await page.content()
                await browser.close()

            soup = BeautifulSoup(html, "lxml")
            elements = soup.select(".js-my-location-result")

            for el in elements:
                name = el.get("data-name")
                if not name:
                    name_el = el.select_one(".my-location-result__name")
                    name = name_el.get_text(strip=True) if name_el else "Tradeline Branch"

                lat = _safe_float(el.get("data-latitude"))
                lng = _safe_float(el.get("data-longitude"))

                # Address link
                addr_el = el.select_one(".apl-section-stores-locator-store-address-1 a")
                full_address = addr_el.get_text(strip=True) if addr_el else None

                # Suburb / city line
                city_hint_el = el.select_one(".apl-section-stores-locator-store-address")
                city_hint = city_hint_el.get_text(strip=True) if city_hint_el else ""

                # Phone
                phone_el = el.select_one("a[href^='tel:']")
                phone = phone_el.get_text(strip=True) if phone_el else "19857"

                # Hours
                hours_el = el.select_one(".apl-section-stores-locator-store-address-hours span:nth-of-type(2)")
                hours = hours_el.get_text(strip=True) if hours_el else None

                # Normalize Egyptian Geography
                geo = normalize_location(
                    address=full_address,
                    city=city_hint.split(",")[0].strip() if city_hint else None
                )

                loc = Location(
                    source_id=self._source_id,
                    location_type=LocationType.STORE,
                    location_name=name,
                    branch_name=name,
                    address=full_address or city_hint,
                    city=geo.get("city"),
                    governorate=geo.get("governorate"),
                    latitude=lat,
                    longitude=lng,
                    phone=phone,
                    working_hours=hours,
                )
                locations.append(loc)

            logger.info("tradeline.locations.extracted", count=len(locations))
            return locations

        except Exception as e:
            self._errors.append(f"Store locator failed: {e}")
            logger.error("tradeline.locations.error", error=str(e))
            return []


class Dream2000Extractor(ShopifyExtractor):
    """Extractor for Dream 2000 (Mobile phones & electronics retailer)."""

    def __init__(self, **kwargs):
        super().__init__(
            source_id="dream2000",
            source_name="Dream 2000",
            domain="dream2000.com",
            base_url="https://dream2000.com",
            store_locator_path="/pages/branches",
            # Compliance class D (UNKNOWN): robots.txt/ToS not yet verified.
            # Do NOT change to B without completing a compliance review.
            compliance_status=ComplianceStatus.UNKNOWN,
            **kwargs,
        )

    async def extract_locations(self) -> list[Location]:
        """
        Extract physical store branches with real geographic coordinates,
        addresses, and names from Dream 2000 branches page.
        """
        import os, re
        from bs4 import BeautifulSoup
        from geospatial.egypt_geography import normalize_location

        url = f"{self._base_url}/pages/branches"
        logger.info("dream2000.locations.playwright_fetch", url=url)
        locations = []

        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    executable_path="/usr/bin/google-chrome" if os.path.exists("/usr/bin/google-chrome") else None,
                )
                page = await browser.new_page(
                    user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
                )
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(3000)
                html = await page.content()
                await browser.close()

            soup = BeautifulSoup(html, "lxml")
            map_links = soup.find_all("a", href=lambda h: h and "google.com/maps" in h)

            for a in map_links:
                href = a["href"]
                m = re.search(r"q=([0-9.]+),([0-9.]+)", href)
                lat = float(m.group(1)) if m else None
                lng = float(m.group(2)) if m else None

                card = a.find_parent("div")
                while card and len(card.get_text(strip=True)) < 30:
                    card = card.find_parent("div")

                parts = [s.strip() for s in card.stripped_strings if s.strip() and s.strip() != "اتجاهات ↗"] if card else []
                name = parts[0] if parts else "Dream 2000 Branch"
                address = parts[1] if len(parts) > 1 else name

                geo = normalize_location(address=address, city=name)
                loc = Location(
                    source_id=self._source_id,
                    location_type=LocationType.STORE,
                    location_name=f"Dream 2000 - {name}",
                    branch_name=name,
                    address=address,
                    city=geo.get("city") or "Cairo",
                    governorate=geo.get("governorate") or "Cairo",
                    latitude=lat,
                    longitude=lng,
                    phone="19916",
                    working_hours="10:00 AM - 11:00 PM",
                )
                locations.append(loc)

            logger.info("dream2000.locations.extracted", count=len(locations))
            return locations
        except Exception as e:
            logger.error("dream2000.locations.error", error=str(e))
            return []


def _safe_float(val) -> Optional[float]:
    """Safely convert a value to float."""
    if val is None:
        return None
    try:
        f = float(val)
        return f if f > 0 else None
    except (ValueError, TypeError):
        return None
