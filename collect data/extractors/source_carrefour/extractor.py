"""
Carrefour Egypt Extractor — Extracts products and branch locations from carrefouregypt.com

Compliance: B (Conditional) — Server-rendered HTML catalog on MAF Retail Proxy.
Method: Static HTML (No browser required for product catalog).
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin

import structlog

from pathlib import Path
import random
from extractors.base import BaseExtractor, ExtractionError, DESKTOP_USER_AGENTS, ACCEPT_LANGUAGE_HEADERS, get_rotated_headers
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
from extractors.source_carrefour.config import (
    BASE_URL,
    CATEGORY_URLS,
    MAX_PAGES_PER_CATEGORY,
    MAX_REQUESTS_PER_MINUTE,
    MIN_DELAY_SECONDS,
    MAX_DELAY_SECONDS,
    STORE_LOCATOR_URL,
)
from extractors.source_carrefour.parser import (
    extract_brand,
    parse_category_page,
    parse_store_locator,
)

logger = structlog.get_logger()


def _carrefour_stock_status(status: AvailabilityStatus) -> str:
    if status == AvailabilityStatus.LIMITED_STOCK:
        return "LOW_STOCK_SIGNAL"
    if status == AvailabilityStatus.IN_STOCK:
        return "IN_STOCK"
    if status == AvailabilityStatus.OUT_OF_STOCK:
        return "OUT_OF_STOCK"
    return "UNKNOWN"


class CarrefourExtractor(BaseExtractor):
    """
    Extractor for Carrefour Egypt (carrefouregypt.com).
    Extracts hypermarket and electronics offerings, stock signals, and store locations.
    """

    def __init__(self, fixture_path: Optional[Path] = None, **kwargs):
        super().__init__(**kwargs)
        self._fixture_path = Path(fixture_path) if fixture_path else None
        self._observations: dict[str, ProductObservation] = {}

    def source_config(self) -> Source:
        return Source(
            source_id="carrefour",
            source_name="Carrefour Egypt",
            domain="www.carrefouregypt.com",
            compliance_status=ComplianceStatus.CONDITIONAL,
            extraction_method=ExtractionMethod.STATIC_HTML,
            rate_limit_rpm=MAX_REQUESTS_PER_MINUTE,
            min_delay_seconds=MIN_DELAY_SECONDS,
            max_delay_seconds=MAX_DELAY_SECONDS,
            enabled=True,
            notes=(
                "Conditional (Class B): Server-rendered catalog on MAF Retail Proxy. "
                "Method A (static HTML) for products; Method D/E for branch locators. "
                "Conservative rate limiting."
            ),
        )

    async def extract_products(self) -> list[Product]:
        """Extract products across Carrefour categories (or offline fixture)."""
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
                    source_id="carrefour",
                    source_product_id=pid,
                    sku=c.get("sku"),
                    product_name=c["product_name"],
                    brand=c.get("brand"),
                    category="Televisions & Electronics",
                    product_url=c["product_url"],
                    source_url=str(self._fixture_path),
                    image_url=c.get("image_url"),
                    collected_at=now,
                )
                all_products.append(product)
                avail_st = c.get("availability_status", AvailabilityStatus.IN_STOCK)
                obs = ProductObservation(
                    product_id=product.product_id,
                    source_id="carrefour",
                    source_product_id=pid,
                    observed_at=now,
                    collected_at=now,
                    price=c.get("price"),
                    old_price=c.get("old_price"),
                    discount=c.get("discount"),
                    currency=Currency.EGP,
                    availability_status=avail_st,
                    stock_status=_carrefour_stock_status(avail_st),
                    stock_quantity=None,  # Low-stock text is a signal, never exact quantity
                    raw_availability_text=c.get("delivery_status"),
                    raw_price_text=c.get("raw_price_text"),
                    availability_scope=AvailabilityScope.GLOBAL,
                    fulfillment_method="retailer",
                    delivery_status=c.get("delivery_status"),
                    source_url=product.product_url,
                )
                self._observations[product.product_id] = obs
            return all_products

        categories = list(CATEGORY_URLS.items())

        # ── Live Extraction via Playwright Chrome ─────────────────────────────
        browser = None
        playwright_cm = None
        try:
            from bs4 import BeautifulSoup
            from playwright.async_api import async_playwright

            playwright_cm = async_playwright()
            p = await playwright_cm.start()
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

            browser = await p.chromium.launch(**launch_kwargs)
            page = await browser.new_page(
                user_agent=random.choice(DESKTOP_USER_AGENTS),
                viewport={"width": 1920, "height": 1080},
                extra_http_headers={
                    "Accept-Language": random.choice(ACCEPT_LANGUAGE_HEADERS),
                    "Referer": f"{BASE_URL}/",
                },
            )

            for cat_idx, (cat_name, cat_path) in enumerate(categories):
                if len(all_products) >= self.max_products:
                    logger.info("carrefour.max_products_reached", count=len(all_products))
                    break

                if cat_idx > 0:
                    await asyncio.sleep(random.uniform(1.5, 3.5))

                category_url = urljoin(BASE_URL, cat_path)
                logger.info("carrefour.category.start", category=cat_name, url=category_url)

                try:
                    await page.set_extra_http_headers(get_rotated_headers(category_url))
                    await page.goto(category_url, timeout=40000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(3000)
                    html = await page.content()
                    soup = BeautifulSoup(html, "lxml")

                    links = soup.select('a[href*="/p/"]')
                    if not links:
                        logger.warning("carrefour.category.empty_retrying", category=cat_name, url=category_url)
                        await page.wait_for_timeout(2500)
                        await page.goto(category_url, timeout=40000, wait_until="domcontentloaded")
                        await page.wait_for_timeout(3000)
                        soup = BeautifulSoup(await page.content(), "lxml")
                        links = soup.select('a[href*="/p/"]')
                    new_count = 0
                    for a in links:
                        href = a.get("href", "")
                        m = re.search(r"/p/(\w+)", href)
                        if not m:
                            continue
                        pid = m.group(1)
                        if pid in seen_ids:
                            continue

                        title_span = a.find("span")
                        name = (title_span.get_text(strip=True) if title_span else a.get_text(strip=True))
                        if not name or len(name) < 3:
                            continue

                        card = a.find_parent("div", class_=re.compile(r"group|relative")) or a.parent
                        price_text = card.get_text(separator=" ", strip=True) if card else ""

                        p_matches = re.findall(r"EGP\s*([0-9,]+(?:\.[0-9]+)?)", price_text)
                        price = float(p_matches[0].replace(",", "")) if p_matches else None
                        if price is None or price <= 0:
                            continue

                        old_price = None
                        discount = None
                        if len(p_matches) > 1:
                            cand_old = float(p_matches[1].replace(",", ""))
                            if cand_old > price:
                                old_price = cand_old
                                discount = round((1 - price / old_price) * 100, 1)

                        seen_ids.add(pid)

                        img_el = card.find("img") if card else None
                        img_url = img_el.get("src") if img_el else None

                        full_url = urljoin(BASE_URL, href)
                        canonical_pid = f"carrefour:{pid}"
                        product = Product(
                            product_id=canonical_pid,
                            source_id="carrefour",
                            source_product_id=pid,
                            sku=pid,
                            product_name=name,
                            brand=extract_brand(name),
                            category=cat_name.replace("_", " ").title(),
                            product_url=full_url,
                            source_url=category_url,
                            image_url=img_url,
                            collected_at=now,
                        )
                        all_products.append(product)
                        new_count += 1

                        avail_st = AvailabilityStatus.IN_STOCK
                        obs = ProductObservation(
                            product_id=canonical_pid,
                            source_id="carrefour",
                            source_product_id=pid,
                            observed_at=now,
                            collected_at=now,
                            price=price,
                            old_price=old_price,
                            discount=discount,
                            currency=Currency.EGP,
                            availability_status=avail_st,
                            stock_status="IN_STOCK",
                            stock_quantity=None,
                            raw_price_text=price_text[:50] if price_text else str(price),
                            raw_availability_text="InStock",
                            availability_scope=AvailabilityScope.GLOBAL,
                            fulfillment_method="retailer",
                            seller_name="Carrefour Egypt",
                            source_url=full_url,
                        )
                        self._observations[canonical_pid] = obs

                        if len(all_products) >= self.max_products:
                            break

                    logger.info("carrefour.category.done", category=cat_name, extracted=new_count, total=len(all_products))

                except Exception as ce:
                    self._errors.append(f"Carrefour category '{cat_name}' error: {ce}")
                    logger.warning("carrefour.category.error", category=cat_name, error=str(ce))

        except Exception as be:
            logger.error("carrefour.browser.error", error=str(be))
        finally:
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass
            if playwright_cm:
                try:
                    await playwright_cm.stop()
                except Exception:
                    pass

        return all_products

    async def extract_product_details(self, product: Product) -> Optional[ProductObservation]:
        """Return observation collected during category crawl."""
        return self._observations.get(product.product_id)

    async def extract_locations(self) -> list[Location]:
        """
        Extract physical store branches across 19 Egyptian governorates.
        """
        now = datetime.now(timezone.utc)
        html_content = None
        if not self._fixture_path:
            try:
                resp = await self.fetch(STORE_LOCATOR_URL)
                html_content = resp.text
            except Exception:
                pass

        from geospatial.egypt_geography import derive_location_id
        raw_locs = parse_store_locator(html_content)
        locations = []
        for rl in raw_locs:
            ltype = rl.get("location_type", LocationType.PRESENCE)
            bname = rl.get("branch_name")
            lname = rl.get("location_name") or bname or f"Carrefour Presence - {rl['governorate']}"
            raw_lname = rl.get("raw_location_name") or lname
            addr = rl.get("address")
            loc_id = derive_location_id(
                source_id="carrefour",
                location_type=ltype.value if hasattr(ltype, "value") else str(ltype),
                normalized_name=lname,
                address=addr or rl["governorate"],
            )
            loc = Location(
                location_id=loc_id,
                source_id="carrefour",
                location_type=ltype,
                location_name=lname,
                branch_name=bname,
                raw_location_name=raw_lname,
                address=addr,
                governorate=rl["governorate"],
                city=rl.get("city"),
                latitude=rl.get("latitude"),
                longitude=rl.get("longitude"),
                delivery_zone=f"{rl['governorate']} Coverage Area" if ltype == LocationType.PRESENCE else None,
                source_url=STORE_LOCATOR_URL,
                collected_at=now,
            )
            locations.append(loc)

        return locations

    async def extract_availability(self) -> list[ProductObservation]:
        return list(self._observations.values())
