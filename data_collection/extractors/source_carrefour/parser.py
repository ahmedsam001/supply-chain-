"""
Carrefour Egypt HTML/JSON Parser
Parses product listings, stock status, and store locations.
"""

from __future__ import annotations

import json
import re
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from normalization.schema import (
    AvailabilityStatus,
    Currency,
    Location,
    LocationType,
    Product,
    ProductObservation,
)
from extractors.source_carrefour.config import (
    BASE_URL,
    CARREFOUR_EGYPT_GOVERNORATES,
)


def parse_price(text: Optional[str]) -> Optional[float]:
    """Parse price string to float, handling EGP and Arabic numerals."""
    if not text:
        return None

    arabic_to_western = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
    cleaned = text.translate(arabic_to_western)

    # Clean out currency text
    cleaned = re.sub(r"[^\d.,]", "", cleaned).strip()
    if not cleaned:
        return None

    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(",", "")
    elif "," in cleaned and "." not in cleaned:
        cleaned = cleaned.replace(",", "")

    try:
        val = float(cleaned)
        return val if val >= 0 else None
    except ValueError:
        return None


def parse_discount(text: Optional[str]) -> Optional[float]:
    """Parse discount string to percentage."""
    if not text:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    if match:
        try:
            val = float(match.group(1))
            return min(max(val, 0.0), 100.0)
        except ValueError:
            return None
    return None


def determine_availability(text: Optional[str]) -> tuple[AvailabilityStatus, Optional[str]]:
    """
    Parse stock text (e.g. 'InStock (only 2 left)' or 'Only 2 left' or 'Out of stock').
    Returns (AvailabilityStatus, delivery_status_text).
    """
    if not text:
        return AvailabilityStatus.UNKNOWN, None

    t = text.lower()
    delivery_note = text.strip()

    if any(k in t for k in ["out of stock", "غير متوفر", "نفدت الكمية"]):
        return AvailabilityStatus.OUT_OF_STOCK, delivery_note

    if any(k in t for k in ["only", "متبقي", "قطع متبقية", "left"]):
        return AvailabilityStatus.LIMITED_STOCK, delivery_note

    if any(k in t for k in ["in stock", "متوفر", "instock"]):
        return AvailabilityStatus.IN_STOCK, delivery_note

    return AvailabilityStatus.IN_STOCK, delivery_note


def extract_brand(name: str) -> Optional[str]:
    """Detect brand in English or Arabic."""
    if not name:
        return None
    brand_map = {
        "سامسونج": "Samsung",
        "samsung": "Samsung",
        "ابل": "Apple",
        "أبل": "Apple",
        "apple": "Apple",
        "شاومي": "Xiaomi",
        "xiaomi": "Xiaomi",
        "redmi": "Xiaomi",
        "هونر": "Honor",
        "honor": "Honor",
        "اوبو": "OPPO",
        "أوبو": "OPPO",
        "oppo": "OPPO",
        "ريلمي": "Realme",
        "realme": "Realme",
        "ال جي": "LG",
        "lg": "LG",
        "توشيبا": "Toshiba",
        "toshiba": "Toshiba",
        "تورنيدو": "Tornado",
        "tornado": "Tornado",
        "فريش": "Fresh",
        "fresh": "Fresh",
        "شارب": "Sharp",
        "sharp": "Sharp",
    }
    for key, val in brand_map.items():
        if re.search(r"\b" + re.escape(key) + r"\b", name, re.IGNORECASE):
            return val
    # Fallback to English words
    words = name.split()
    for w in words:
        clean_w = re.sub(r"[^\w]", "", w)
        if clean_w.lower() in brand_map:
            return brand_map[clean_w.lower()]
    return None


def parse_category_page(html: str, base_url: str = BASE_URL) -> list[dict]:
    """
    Parse Carrefour Egypt category/listing HTML.
    Extracts product cards with names, prices, discounts, availability, and URLs.
    """
    soup = BeautifulSoup(html, "lxml")
    products = []

    # Find product cards
    card_selectors = [
        "div[data-testid='product-card']",
        "div[class*='product-card']",
        "div[class*='productCard']",
        "article",
        "div[class*='product-item']",
    ]

    cards = []
    for sel in card_selectors:
        found = soup.select(sel)
        if found:
            cards = found
            break

    # Fallback to links containing /p/
    if not cards:
        links = soup.select("a[href*='/p/']")
        seen_parents = set()
        for link in links:
            parent = link.find_parent("div") or link
            if parent not in seen_parents:
                seen_parents.add(parent)
                cards.append(parent)

    for card in cards:
        item = _parse_product_card(card, base_url)
        if item and item.get("product_name"):
            products.append(item)

    return products


def _parse_product_card(card, base_url: str) -> Optional[dict]:
    """Parse single product card from listing."""
    data = {}

    # Link & URL
    link_el = card if card.name == "a" else card.select_one("a[href*='/p/'], a[href]")
    if not link_el:
        return None

    href = link_el.get("href", "")
    if not href:
        return None

    full_url = urljoin(base_url, href)
    data["product_url"] = full_url

    # SKU / Product ID from URL (e.g. /p/676581)
    id_match = re.search(r"/p/(\d+)", full_url)
    if id_match:
        data["source_product_id"] = id_match.group(1)
        data["sku"] = id_match.group(1)
    else:
        data["source_product_id"] = re.sub(r"\D", "", full_url)[-6:] or "unknown"
        data["sku"] = data["source_product_id"]

    # Product Name
    title_el = (
        card.select_one("[data-testid='product-title']") or
        card.select_one("h2, h3, h4") or
        card.select_one("a[title]") or
        card.select_one("[class*='title'], [class*='name']")
    )
    if title_el:
        data["product_name"] = title_el.get_text(strip=True) or title_el.get("title", "").strip()
    elif link_el.get("title"):
        data["product_name"] = link_el.get("title").strip()

    if not data.get("product_name"):
        return None

    # Brand
    data["brand"] = extract_brand(data["product_name"])

    # Price
    price_el = card.select_one("[data-testid='product-price'], [class*='price'], span[class*='Price']")
    if price_el:
        raw_p = price_el.get_text(strip=True)
        data["raw_price_text"] = raw_p
        data["price"] = parse_price(raw_p)

    # Old price
    old_price_el = card.select_one("[data-testid='old-price'], del, s, span[class*='oldPrice'], [class*='wasPrice']")
    if old_price_el:
        data["old_price"] = parse_price(old_price_el.get_text(strip=True))

    # Discount
    disc_el = card.select_one("[data-testid='discount-badge'], span[class*='discount'], div[class*='discount']")
    if disc_el:
        data["discount"] = parse_discount(disc_el.get_text(strip=True))
    elif data.get("price") and data.get("old_price") and data["old_price"] > data["price"]:
        data["discount"] = round((1 - data["price"] / data["old_price"]) * 100, 1)

    # Availability / Stock
    stock_el = card.select_one("[data-testid='stock-message'], [class*='stock'], span[class*='badge']")
    if stock_el:
        stock_text = stock_el.get_text(strip=True)
        status, note = determine_availability(stock_text)
        data["availability_status"] = status
        data["delivery_status"] = note
    else:
        # Check text within card for low stock messages like "Only 2 left"
        card_text = card.get_text(separator=" ", strip=True)
        low_stock_match = re.search(r"(Only \d+ left|متبقي \d+ فقط)", card_text, re.I)
        if low_stock_match:
            data["availability_status"] = AvailabilityStatus.LIMITED_STOCK
            data["delivery_status"] = f"InStock ({low_stock_match.group(1).lower()})"
        elif data.get("price"):
            data["availability_status"] = AvailabilityStatus.IN_STOCK
            data["delivery_status"] = "InStock"
        else:
            data["availability_status"] = AvailabilityStatus.UNKNOWN

    # Image URL
    img_el = card.select_one("img[data-testid='product-image'], img[src*='mafretailproxy'], img[src]")
    if img_el:
        data["image_url"] = img_el.get("src") or img_el.get("data-src")

    return data


def parse_store_locator(html: Optional[str] = None) -> list[dict]:
    """
    Parse Carrefour store locator data.
    - If real branch elements with branch_name + street address/GPS are present,
      extract them as LocationType.BRANCH / LocationType.STORE.
    - If only governorate-level presence/coverage options are present (or fallback
      to confirmed 19 Carrefour Egypt governorates), emit LocationType.PRESENCE
      records (NOT physical stores/branches) and preserve raw source text.
    """
    from geospatial.egypt_geography import normalize_location
    locations = []
    if html:
        soup = BeautifulSoup(html, "lxml")

        # 1. Check for real physical branch cards with street address or GPS
        branch_cards = soup.select(
            ".store-card, .branch-item, [data-testid='store-item'], li.store-item"
        )
        for card in branch_cards:
            name_el = card.select_one(".store-name, .branch-name, h3, h4")
            addr_el = card.select_one(".store-address, .branch-address, .address")
            bname = name_el.get_text(strip=True) if name_el else None
            addr = addr_el.get_text(strip=True) if addr_el else None
            lat = card.get("data-lat") or card.get("data-latitude")
            lng = card.get("data-lng") or card.get("data-longitude")
            if bname and (addr or (lat and lng)):
                geo = normalize_location(address=f"{bname}, {addr or ''}")
                locations.append({
                    "governorate": geo.get("governorate") or "unknown",
                    "city": geo.get("city"),
                    "location_type": LocationType.BRANCH,
                    "branch_name": bname,
                    "location_name": bname,
                    "raw_location_name": bname,
                    "address": addr,
                    "latitude": float(lat) if lat else None,
                    "longitude": float(lng) if lng else None,
                })
        if locations:
            return locations

        # 2. Governorate-level presence/coverage options (NOT physical branches)
        select_el = soup.select_one("select#governorate, select[name*='governorate']")
        if select_el:
            for opt in select_el.select("option"):
                raw_text = opt.get_text(strip=True)
                if raw_text and "select" not in raw_text.lower() and "اختر" not in raw_text:
                    geo = normalize_location(address=raw_text, governorate=raw_text)
                    gov = geo.get("governorate") or "unknown"
                    locations.append({
                        "governorate": gov,
                        "city": None,
                        "location_type": LocationType.PRESENCE,
                        "branch_name": None,
                        "location_name": f"Carrefour Presence - {gov}",
                        "raw_location_name": raw_text,
                        "address": None,
                        "latitude": None,
                        "longitude": None,
                    })

    if not locations:
        for gov in CARREFOUR_EGYPT_GOVERNORATES:
            raw_text = f"Presence in {gov}"
            locations.append({
                "governorate": gov,
                "city": None,
                "location_type": LocationType.PRESENCE,
                "branch_name": None,
                "location_name": f"Carrefour Presence - {gov}",
                "raw_location_name": raw_text,
                "address": None,
                "latitude": None,
                "longitude": None,
            })

    return locations
