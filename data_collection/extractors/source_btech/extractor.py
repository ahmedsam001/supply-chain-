"""
B.TECH Extractor — Extracts products and store locations from btech.com

B.TECH is one of Egypt's largest electronics retailers with 100+ stores.
Uses Playwright for client-side rendered React/Next.js content.

Compliance: B (Conditional) — No explicit prohibition found.
Rate limit: Conservative 20 RPM with 2-4s delays.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from typing import Optional

import structlog

from extractors.base import BaseExtractor, ExtractionError
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
from extractors.source_btech.parser import (
    determine_availability,
    parse_category_page,
    parse_product_page,
    parse_store_locator,
)
from extractors.source_btech.config import (
    BASE_URL,
    CATEGORY_URLS,
    MAX_PAGES_PER_CATEGORY,
    PRODUCTS_PER_PAGE,
    SELECTORS,
    STORE_LOCATOR_URL,
)

logger = structlog.get_logger()


class BTechExtractor(BaseExtractor):
    """
    Extractor for B.TECH (btech.com) — Egypt's leading electronics retailer.
    """

    def source_config(self) -> Source:
        return Source(
            source_id="btech",
            source_name="B.TECH",
            domain="btech.com",
            compliance_status=ComplianceStatus.DO_NOT_AUTOMATE,
            extraction_method=ExtractionMethod.PLAYWRIGHT,
            rate_limit_rpm=20,
            min_delay_seconds=2.0,
            max_delay_seconds=4.0,
            enabled=False,
            notes="BLOCKED (Class C — DO NOT AUTOMATE). Explicit prohibition.",
        )

    async def extract_products(self) -> list[Product]:
        """
        Extract products from B.TECH category pages.

        Strategy:
        1. Visit each category page
        2. Parse product cards from the listing
        3. Handle pagination (next page links or infinite scroll)
        4. Collect basic product info from cards
        """
        all_products = []
        seen_ids = set()

        # Limit categories for responsible crawling
        categories_to_crawl = list(CATEGORY_URLS.items())[:3]

        for category_name, category_path in categories_to_crawl:
            if len(all_products) >= self.max_products:
                logger.info(
                    "extraction.max_products_reached",
                    count=len(all_products),
                )
                break

            log = logger.bind(category=category_name)
            log.info("category.start")

            try:
                products = await self._extract_category(
                    category_name, category_path, seen_ids
                )
                all_products.extend(products)
                log.info("category.done", products=len(products))
            except Exception as e:
                err = f"Category {category_name} failed: {e}"
                self._errors.append(err)
                log.error("category.error", error=str(e))

        return all_products

    async def _extract_category(
        self,
        category_name: str,
        category_path: str,
        seen_ids: set,
    ) -> list[Product]:
        """Extract all products from a single category with pagination."""
        products = []
        page_num = 1

        while page_num <= min(MAX_PAGES_PER_CATEGORY, self.max_pages):
            url = f"{BASE_URL}{category_path}"
            if page_num > 1:
                url = f"{url}?page={page_num}"

            try:
                await self.navigate(url, wait_selector="body")

                # Wait for product content to load
                await asyncio.sleep(2)

                # Take screenshot on first page for research
                if page_num == 1:
                    await self.screenshot(
                        f"category_{category_name}_p1", "btech"
                    )

                # Get page HTML
                html = await self.get_page_html()

                # Parse product cards
                raw_products = parse_category_page(html, "btech", BASE_URL)

                if not raw_products:
                    logger.info(
                        "category.no_products",
                        page=page_num,
                        category=category_name,
                    )
                    break

                # Convert to Product models
                for raw in raw_products:
                    pid = raw.get("source_product_id", "")
                    if not pid or pid in seen_ids:
                        continue
                    seen_ids.add(pid)

                    product = Product(
                        source_id="btech",
                        source_product_id=pid,
                        sku=raw.get("sku"),
                        product_name=raw.get("product_name", "Unknown"),
                        brand=raw.get("brand"),
                        category=category_name,
                        product_url=raw.get("product_url", ""),
                        image_url=raw.get("image_url"),
                    )
                    products.append(product)

                    if len(products) >= self.max_products:
                        break

                # Check for next page
                has_next = await self._has_next_page()
                if not has_next:
                    break

                page_num += 1

            except Exception as e:
                self._errors.append(
                    f"Category {category_name} page {page_num}: {e}"
                )
                logger.warning(
                    "category.page_error",
                    category=category_name,
                    page=page_num,
                    error=str(e),
                )
                break

        return products

    async def _has_next_page(self) -> bool:
        """Check if there's a next pagination page."""
        try:
            next_btn = await self._page.query_selector(
                SELECTORS["pagination_next"]
            )
            if next_btn:
                is_disabled = await next_btn.get_attribute("disabled")
                classes = await next_btn.get_attribute("class") or ""
                if not is_disabled and "disabled" not in classes:
                    return True
        except Exception:
            pass
        return False

    async def extract_product_details(
        self, product: Product
    ) -> Optional[ProductObservation]:
        """
        Extract detailed pricing and availability for a single product.
        Visits the product detail page.
        """
        if not product.product_url:
            return None

        try:
            await self.navigate(product.product_url, wait_selector="body")
            await asyncio.sleep(1.5)

            html = await self.get_page_html()
            details = parse_product_page(html, "btech", BASE_URL)

            # Update product with additional fields
            if details.get("sku"):
                product.sku = details["sku"]
            if details.get("brand"):
                product.brand = details["brand"]
            if details.get("subcategory"):
                product.subcategory = details["subcategory"]
            if details.get("specifications"):
                product.specifications = details["specifications"]

            # Create observation
            price = details.get("price")
            old_price = details.get("old_price")
            discount = None
            if price and old_price and old_price > price:
                discount = round((1 - price / old_price) * 100, 1)

            availability = details.get(
                "availability_status", AvailabilityStatus.UNKNOWN
            )
            if isinstance(availability, str):
                availability = determine_availability(availability)

            return ProductObservation(
                product_id=product.product_id,
                observed_at=datetime.now(timezone.utc),
                price=price,
                old_price=old_price,
                discount=discount,
                currency=Currency.EGP,
                availability_status=availability,
                rating=details.get("rating"),
                review_count=details.get("review_count"),
                source_url=product.product_url,
            )

        except Exception as e:
            self._errors.append(
                f"Product detail {product.source_product_id}: {e}"
            )
            return None

    async def extract_locations(self) -> list[Location]:
        """
        Extract B.TECH store locations from the store locator page.
        """
        logger.info("locations.start")

        try:
            await self.navigate(STORE_LOCATOR_URL, wait_selector="body")
            await asyncio.sleep(3)

            # Screenshot for research
            await self.screenshot("store_locator", "btech")

            html = await self.get_page_html()
            locations = parse_store_locator(html, "btech")

            # Also try to extract from network responses / embedded JSON
            if not locations:
                locations = await self._extract_locations_from_js()

            logger.info("locations.done", count=len(locations))
            return locations

        except Exception as e:
            self._errors.append(f"Store locator failed: {e}")
            logger.error("locations.error", error=str(e))
            return []

    async def _extract_locations_from_js(self) -> list[Location]:
        """
        Try to extract store data from JavaScript variables or API calls
        embedded in the page.
        """
        locations = []

        try:
            # Look for store data in window.__NEXT_DATA__ or similar
            next_data = await self._page.evaluate("""
                () => {
                    if (window.__NEXT_DATA__) {
                        return JSON.stringify(window.__NEXT_DATA__);
                    }
                    return null;
                }
            """)

            if next_data:
                data = json.loads(next_data)
                # Navigate the Next.js data structure to find store info
                props = data.get("props", {}).get("pageProps", {})
                stores = (
                    props.get("stores") or
                    props.get("branches") or
                    props.get("locations") or
                    []
                )
                for store in stores:
                    if isinstance(store, dict):
                        loc = Location(
                            source_id="btech",
                            location_type=LocationType.STORE,
                            branch_name=store.get("name") or store.get("title"),
                            address=store.get("address"),
                            city=store.get("city"),
                            governorate=store.get("governorate") or store.get("state"),
                            latitude=_safe_float(store.get("lat") or store.get("latitude")),
                            longitude=_safe_float(store.get("lng") or store.get("longitude")),
                            phone=store.get("phone"),
                            working_hours=store.get("working_hours"),
                        )
                        locations.append(loc)

        except Exception as e:
            logger.debug("js_store_extraction.error", error=str(e))

        return locations

    async def extract_availability(self) -> list[ProductObservation]:
        """
        B.TECH doesn't have a bulk availability endpoint.
        Individual availability is captured via extract_product_details.
        """
        return []


def _safe_float(val) -> Optional[float]:
    """Safely convert a value to float."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
