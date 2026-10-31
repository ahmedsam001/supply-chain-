"""
Raya Shop Extractor
===================
Supports offline fixture mode (for tests) and live extraction via
Playwright Chrome (bypassing Nuxt.js SSR/CSR) directly into canonical data models.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

from extractors.base import BaseExtractor, DESKTOP_USER_AGENTS, ACCEPT_LANGUAGE_HEADERS, get_rotated_headers
import random
from extractors.source_raya.config import (
    BASE_URL,
    CATEGORY_URLS,
    MAX_PAGES_PER_CATEGORY,
    MAX_REQUESTS_PER_MINUTE,
    MIN_DELAY_SECONDS,
    MAX_DELAY_SECONDS,
)
from extractors.source_raya.parser import (
    parse_category_page,
    parse_product_detail_page,
    parse_store_locator,
    determine_raya_availability,
)
from normalization.schema import (
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

import structlog
logger = structlog.get_logger()


class RayaExtractor(BaseExtractor):
    """
    Raya Shop extractor.
    Operates in fixture mode by default, or live mode when live=True.
    """

    def __init__(
        self,
        fixture_path: Optional[Path] = None,
        live: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._fixture_path = fixture_path
        self._live = live
        self._initial_observations: dict[str, ProductObservation] = {}
        self._browser = None
        self._playwright = None
        self._playwright_cm = None

    def source_config(self) -> Source:
        return Source(
            source_id="raya",
            source_name="Raya Shop",
            domain="rayashop.com",
            compliance_status=ComplianceStatus.UNKNOWN,
            extraction_method=ExtractionMethod.PLAYWRIGHT if self._live else ExtractionMethod.STATIC_HTML,
            rate_limit_rpm=MAX_REQUESTS_PER_MINUTE,
            min_delay_seconds=MIN_DELAY_SECONDS,
            max_delay_seconds=MAX_DELAY_SECONDS,
            enabled=False,
            notes="Raya Shop live Playwright extraction + offline fixture.",
        )

    async def _cleanup(self) -> None:
        """Safely close Playwright and browser instances."""
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    async def extract_products(self) -> list[Product]:
        """
        Extract products. Uses offline fixture by default.
        Live mode runs Playwright with system Google Chrome.
        """
        # 1. Offline fixture mode
        if self._fixture_path and Path(self._fixture_path).exists():
            logger.info("raya.extract.offline_fixture", path=str(self._fixture_path))
            html = Path(self._fixture_path).read_text(encoding="utf-8")
            cards = parse_category_page(html)
            products, observations = self._cards_to_canonical(cards)
            self._initial_observations = observations
            return products

        # 2. Guard against accidental live mode
        if not self._live:
            msg = (
                "Source raya is compliance class D (UNKNOWN). "
                "Live extraction disabled. Provide fixture_path= for offline testing."
            )
            logger.warning(
                "raya.extract.skipped",
                reason="offline_fixture mode: no fixture_path provided and live=False",
            )
            self._errors.append(msg)
            return []

        # 3. Live Playwright Chrome extraction for Nuxt.js
        all_products: list[Product] = []
        all_observations: dict[str, ProductObservation] = {}
        seen_urls: set[str] = set()
        now = datetime.now(timezone.utc)

        try:
            from bs4 import BeautifulSoup
            from playwright.async_api import async_playwright
            from extractors.source_2b.parser import _extract_brand

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

            self._browser = await self._playwright.chromium.launch(**launch_kwargs)
            page = await self._browser.new_page(
                user_agent=random.choice(DESKTOP_USER_AGENTS),
                viewport={"width": 1920, "height": 1080},
                extra_http_headers={
                    "Accept-Language": random.choice(ACCEPT_LANGUAGE_HEADERS),
                    "Referer": f"{BASE_URL}/",
                },
            )

            for cat_idx, (cat_name, cat_path) in enumerate(CATEGORY_URLS.items()):
                if len(all_products) >= self.max_products:
                    break

                for page_num in range(1, 20):
                    if len(all_products) >= self.max_products:
                        break

                    sep = "&" if "?" in cat_path else "?"
                    page_url = urljoin(BASE_URL, f"{cat_path}{sep}p={page_num}")
                    logger.info("raya.page.start", category=cat_name, page=page_num, url=page_url)

                    try:
                        await page.set_extra_http_headers(get_rotated_headers(page_url))
                        await page.goto(page_url, timeout=30000, wait_until="domcontentloaded")
                        await page.wait_for_timeout(2000)

                        # Progressive multi-step scroll down to fire intersection observers for all images
                        for scroll_y in (800, 1800, 3200, 5000):
                            await page.evaluate(f"window.scrollTo(0, {scroll_y})")
                            await page.wait_for_timeout(350)

                        soup = BeautifulSoup(await page.content(), "html.parser")
                        cards = soup.find_all("div", class_=lambda c: c and any(k in str(c) for k in ("swiper-slide", "ProductCard", "item", "product")))
                        if not cards:
                            break

                        page_new = 0
                        for slide in cards:
                            strings = list(slide.stripped_strings)
                            if not strings:
                                continue

                            if any("EGP" in s or "LE" in s for s in strings):
                                a = slide.find("a", href=True)
                                if not a:
                                    continue
                                href = a["href"]
                                if not href.startswith("/en/") or href in seen_urls:
                                    continue
                                if any(x in href for x in ("privacy", "terms", "contact", "about", "policy", "cart")):
                                    continue

                                pname = strings[0]
                                prices = []
                                for idx, s in enumerate(strings):
                                    if ("EGP" in s or "LE" in s) and idx > 0:
                                        prev = strings[idx - 1].replace(",", "").replace(".", "").strip()
                                        if prev.isdigit():
                                            prices.append(float(strings[idx - 1].replace(",", "")))

                                cur_price = prices[0] if prices else None
                                if cur_price is None or cur_price <= 0:
                                    continue

                                seen_urls.add(href)
                                old_price = prices[1] if len(prices) > 1 and prices[1] > prices[0] else None
                                discount = None
                                if cur_price and old_price and old_price > cur_price:
                                    discount = round(((old_price - cur_price) / old_price) * 100, 1)

                                # Extract image inspecting all img and picture source elements
                                img_src = None
                                for img_tag in slide.find_all(["img", "source"]):
                                    for attr in ("src", "data-src", "data-lazy-src", "data-original", "data-srcset", "srcset"):
                                        val = img_tag.get(attr)
                                        if val and not val.startswith("data:image") and not val.endswith(".svg"):
                                            if " " in val:
                                                val = val.split()[0]
                                            if val.startswith("http") or val.startswith("/"):
                                                img_src = urljoin(BASE_URL, val)
                                                break
                                    if img_src:
                                        break

                                slug = href.rstrip("/").split("/")[-1]
                                spid = slug[:50]
                                canonical_pid = f"raya:{spid}"

                                prod = Product(
                                    product_id=canonical_pid,
                                    source_id="raya",
                                    source_product_id=spid,
                                    sku=spid,
                                    product_name=pname,
                                    brand=None,  # Keep brand raw (NULL) for stage DWH layer
                                    category=cat_name,
                                    product_url=urljoin(BASE_URL, href),
                                    source_url=page_url,
                                    image_url=img_src,
                                    collected_at=now,
                                )
                                all_products.append(prod)

                                obs = ProductObservation(
                                    product_id=canonical_pid,
                                    source_id="raya",
                                    source_product_id=spid,
                                    observed_at=now,
                                    collected_at=now,
                                    price=cur_price,
                                    old_price=old_price,
                                    discount=discount,
                                    currency=Currency.EGP,
                                    raw_price_text=f"{cur_price} EGP",
                                    availability_status=AvailabilityStatus.IN_STOCK,
                                    stock_status="IN_STOCK",
                                    raw_availability_text="In Stock",
                                    stock_quantity=None,
                                    seller_name="Raya Shop",
                                    source_url=prod.product_url,
                                    fulfillment_method="retailer",
                                )
                                all_observations[canonical_pid] = obs
                                page_new += 1
                                if len(all_products) >= self.max_products:
                                    break

                        if page_new == 0:
                            break
                        await asyncio.sleep(random.uniform(1.0, 2.0))
                    except Exception as e:
                        logger.warning("raya.page.error", category=cat_name, page=page_num, error=str(e))
                        break

        except Exception as e:
            logger.error("raya.playwright.error", error=str(e))
            self._errors.append(f"Playwright error: {e}")
        finally:
            await self._cleanup()

        self._initial_observations = all_observations
        return all_products

    def _cards_to_canonical(
        self,
        cards: list[dict],
        category: Optional[str] = None,
    ) -> tuple[list[Product], dict[str, ProductObservation]]:
        """Convert raw card dicts to canonical models."""
        now = datetime.now(timezone.utc)
        products = []
        observations = {}

        for c in cards:
            name = c.get("product_name", "")
            if not name:
                continue

            prod = Product(
                source_id="raya",
                source_product_id=str(c.get("source_product_id") or name[:50]),
                sku=c.get("sku"),
                product_name=name,
                brand=c.get("brand"),
                category=category or c.get("category"),
                product_url=c.get("product_url") or "",
                image_url=c.get("image_url"),
                collected_at=now,
            )
            products.append(prod)

            obs = ProductObservation(
                product_id=prod.product_id,
                source_id="raya",
                source_product_id=prod.source_product_id,
                observed_at=now,
                collected_at=now,
                price=c.get("price"),
                old_price=c.get("old_price"),
                currency=Currency.EGP,
                availability_status=c.get(
                    "availability_status", AvailabilityStatus.UNKNOWN
                ),
                availability_scope=c.get("availability_scope"),
                stock_status=c.get("stock_status"),
                stock_quantity=None,
                raw_availability_text=c.get("raw_availability_text"),
                source_url=c.get("product_url"),
                fulfillment_method="retailer",
            )
            observations[prod.product_id] = obs

        return products, observations

    async def extract_availability(self) -> list[ProductObservation]:
        """Return observations collected during product extraction."""
        return list(self._initial_observations.values())

    async def extract_locations(self) -> list[Location]:
        """Extract physical store branches with real coordinates, addresses, and cities via Raya GraphQL API."""
        if not self._live:
            return []

        from geospatial.egypt_geography import normalize_location

        gql_url = (
            "https://api-rayashop.global.ssl.fastly.net/graphql?"
            "query=query%20StoreLocations(%24region%3A%20String%2C%20%24city%3A%20String%2C%20%24page%3A%20Int%2C%20%24pageSize%3A%20Int%20%3D%20200)%20%7B%20%20"
            "storeLocators%3A%20store_locators(%20%20%20%20region%3A%20%24city%20%20%20%20city%3A%20%24region%20%20%20%20page%3A%20%24page%20%20%20%20pageSize%3A%20%24pageSize%20%20)%20%7B%20%20%20%20"
            "items%20%7B%20%20%20%20%20%20id%20%20%20%20%20%20name%20%20%20%20%20%20city%20%7B%20%20%20%20%20%20%20%20code%20%20%20%20%20%20%20%20id%20%20%20%20%20%20%20%20name%20%20%20%20%20%20%7D%20%20%20%20%20%20"
            "installments_store_id%20%20%20%20%20%20address%20%20%20%20%20%20phone%20%20%20%20%20%20lat%20%20%20%20%20%20lng%20%20%20%20%20%20region%20%7B%20%20%20%20%20%20%20%20id%20%20%20%20%20%20%20%20code%20%20%20%20%20%20%20%20name%20%20%20%20%20%20%7D%20%20%20%20%7D%20%20%20%20"
            "total_count%20%20%7D%7D&variables=%7B%22pageSize%22%3A300%2C%22page%22%3A1%7D&storeCode=ar"
        )
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Origin": "https://www.rayashop.com",
            "Referer": "https://www.rayashop.com/",
        }

        locations = []
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(gql_url, headers=headers)
                data = resp.json()
                items = data.get("data", {}).get("storeLocators", {}).get("items", [])
                for it in items:
                    name = it.get("name") or "Raya Store"
                    raw_city = it.get("city", {}).get("name") if isinstance(it.get("city"), dict) else it.get("city")
                    raw_gov = it.get("region", {}).get("name") if isinstance(it.get("region"), dict) else it.get("region")
                    addr = it.get("address") or name
                    lat_str = it.get("lat")
                    lng_str = it.get("lng")
                    lat = float(lat_str) if lat_str else None
                    lng = float(lng_str) if lng_str else None
                    phone = it.get("phone") or "19900"

                    geo = normalize_location(address=addr, city=raw_city, governorate=raw_gov)
                    loc = Location(
                        source_id="raya",
                        location_type=LocationType.STORE,
                        location_name=f"Raya - {name}",
                        branch_name=name,
                        address=addr,
                        city=geo.get("city") or raw_city or "Cairo",
                        governorate=geo.get("governorate") or raw_gov or "Cairo",
                        latitude=lat,
                        longitude=lng,
                        phone=phone,
                        working_hours="10:00 AM - 11:00 PM",
                    )
                    locations.append(loc)

            logger.info("raya.locations.extracted", count=len(locations))
            return locations
        except Exception as e:
            self._errors.append(f"Raya store locations failed: {e}")
            logger.error("raya.locations.error", error=str(e))
            return []
