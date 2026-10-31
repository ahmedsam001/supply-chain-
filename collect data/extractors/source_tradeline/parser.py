"""
Tradeline Stores Parser

Parses:
1. Shopify /products.json responses → canonical Product + ProductObservation
2. Store locator HTML → canonical Location records

All parsing is OFFLINE — no network calls.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from bs4 import BeautifulSoup

from normalization.schema import (
    AvailabilityScope,
    AvailabilityStatus,
    Currency,
    Location,
    LocationType,
    Product,
    ProductObservation,
)
from geospatial.egypt_geography import normalize_location


def parse_shopify_products_json(
    json_data: dict | str,
    source_id: str = "tradeline",
    base_url: str = "https://www.tradelinestores.com",
) -> tuple[list[Product], list[ProductObservation]]:
    """
    Parse Shopify /products.json response.
    Returns (products, observations).
    """
    if isinstance(json_data, str):
        json_data = json.loads(json_data)

    products = []
    observations = []
    now = datetime.now(timezone.utc)

    for sp in json_data.get("products", []):
        product, obs = _parse_single_shopify_product(sp, source_id, base_url, now)
        if product:
            products.append(product)
            if obs:
                observations.append(obs)

    return products, observations


def _parse_single_shopify_product(
    sp: dict,
    source_id: str,
    base_url: str,
    now: datetime,
) -> tuple[Optional[Product], Optional[ProductObservation]]:
    """Parse one Shopify product object."""
    title = sp.get("title", "").strip()
    if not title:
        return None, None

    product_id = str(sp.get("id", ""))
    handle = sp.get("handle", "")
    product_url = f"{base_url}/products/{handle}" if handle else ""
    brand = sp.get("vendor", "") or None
    category = sp.get("product_type", "") or None
    images = sp.get("images", [])
    image_url = images[0].get("src") if images else None

    variants = sp.get("variants", [])
    sku = None
    price = None
    old_price = None
    available = True  # default

    if variants:
        v = variants[0]
        sku = v.get("sku") or None
        price_str = v.get("price") or v.get("price_min")
        compare_str = v.get("compare_at_price")
        available = bool(v.get("available", True))

        try:
            price = float(price_str) if price_str else None
        except (ValueError, TypeError):
            price = None

        try:
            old_price = float(compare_str) if compare_str else None
        except (ValueError, TypeError):
            old_price = None

    # Compute discount
    discount = None
    if price and old_price and old_price > price:
        discount = round((old_price - price) / old_price * 100, 1)

    gtin = sku if (sku and str(sku).strip().isdigit() and 8 <= len(str(sku).strip()) <= 14) else None
    variant_list = [
        {
            "variant_id": str(v.get("id", "")),
            "title": v.get("title"),
            "sku": v.get("sku") or None,
            "price": v.get("price"),
            "compare_at_price": v.get("compare_at_price"),
            "available": bool(v.get("available", True)),
        }
        for v in variants
    ] if variants else None
    raw_price_str = str(variants[0].get("price") or variants[0].get("price_min")) if variants and (variants[0].get("price") or variants[0].get("price_min")) else None

    product = Product(
        source_id=source_id,
        source_product_id=product_id,
        sku=sku,
        gtin=gtin,
        product_name=title,
        brand=brand,
        category=category,
        product_url=product_url,
        source_url=product_url,
        image_url=image_url,
        variants=variant_list,
        collected_at=now,
    )

    obs = ProductObservation(
        product_id=product.product_id,
        source_id=source_id,
        source_product_id=product_id,
        observed_at=now,
        collected_at=now,
        price=price,
        old_price=old_price,
        discount=discount,
        currency=Currency.EGP,
        availability_status=(
            AvailabilityStatus.IN_STOCK if available
            else AvailabilityStatus.OUT_OF_STOCK
        ),
        stock_status="IN_STOCK" if available else "OUT_OF_STOCK",
        stock_quantity=None,  # Shopify doesn't expose exact quantity
        raw_availability_text=str(available) if variants else None,
        raw_price_text=raw_price_str,
        availability_scope=AvailabilityScope.GLOBAL,
        fulfillment_method="retailer",
        source_url=product_url,
    )

    return product, obs


def parse_store_locator_html(
    html: str,
    source_id: str = "tradeline",
) -> list[Location]:
    """
    Parse Tradeline store locator HTML.
    Looks for .js-my-location-result elements with data attributes.
    """
    soup = BeautifulSoup(html, "lxml")
    elements = soup.select(".js-my-location-result")
    locations = []

    for el in elements:
        name = el.get("data-name")
        if not name:
            name_el = el.select_one(".my-location-result__name")
            name = name_el.get_text(strip=True) if name_el else "Tradeline Branch"

        lat = _safe_float(el.get("data-latitude"))
        lng = _safe_float(el.get("data-longitude"))

        addr_el = el.select_one(".apl-section-stores-locator-store-address-1 a")
        full_address = addr_el.get_text(strip=True) if addr_el else None

        city_hint_el = el.select_one(".apl-section-stores-locator-store-address")
        city_hint = city_hint_el.get_text(" ", strip=True) if city_hint_el else ""

        phone_el = el.select_one("a[href^='tel:']")
        phone = phone_el.get_text(strip=True) if phone_el else "19857"

        hours_el = el.select_one(
            ".apl-section-stores-locator-store-address-hours span:nth-of-type(2)"
        )
        hours = hours_el.get_text(strip=True) if hours_el else None

        city_guess = city_hint.split(",")[0].strip() if "," in city_hint else None
        geo = normalize_location(address=full_address, city=city_guess)

        loc = Location(
            source_id=source_id,
            location_type=LocationType.STORE,
            location_name=name,
            branch_name=name,
            address=full_address or city_hint or None,
            city=geo.get("city"),
            governorate=geo.get("governorate"),
            latitude=lat,
            longitude=lng,
            phone=phone,
            working_hours=hours,
        )
        locations.append(loc)

    return locations


def _safe_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
