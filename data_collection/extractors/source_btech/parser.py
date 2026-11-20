"""
B.TECH HTML/JSON Parser

Parses product data from B.TECH product pages and category listings.
Uses BeautifulSoup for HTML parsing and handles JSON-LD structured data.
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


def parse_category_page(
    html: str,
    source_id: str = "btech",
    base_url: str = "https://btech.com",
) -> list[dict]:
    """
    Parse a B.TECH category page and extract product card data.

    Returns a list of dicts with raw product info.
    """
    soup = BeautifulSoup(html, "lxml")
    products = []

    # Try multiple possible selectors for product cards
    card_selectors = [
        "div[class*='product-card']",
        "div[class*='ProductCard']",
        "li[class*='product-item']",
        "div[class*='product-tile']",
        "article[class*='product']",
        "div[data-product-id]",
    ]

    cards = []
    for selector in card_selectors:
        cards = soup.select(selector)
        if cards:
            break

    # Fallback: look for product links
    if not cards:
        links = soup.select("a[href*='/product/'], a[href*='/-p-']")
        for link in links:
            parent = link.find_parent("div") or link.find_parent("li")
            if parent and parent not in cards:
                cards.append(parent)

    for card in cards:
        product = _parse_product_card(card, base_url)
        if product and product.get("product_name"):
            products.append(product)

    return products


def _parse_product_card(card, base_url: str) -> Optional[dict]:
    """Parse a single product card element."""
    data = {}

    # Product name
    name_el = (
        card.select_one("h2, h3, h4") or
        card.select_one("[class*='name']") or
        card.select_one("[class*='title']")
    )
    if name_el:
        data["product_name"] = name_el.get_text(strip=True)

    # Product URL
    link_el = card.select_one("a[href]")
    if link_el:
        href = link_el.get("href", "")
        data["product_url"] = urljoin(base_url, href)

    # Product ID from URL or data attribute
    if "product_url" in data:
        url = data["product_url"]
        # Try to extract product ID from URL patterns like /-p-12345 or /product/12345
        id_match = re.search(r'-p-(\d+)', url) or re.search(r'/product/(\d+)', url)
        if id_match:
            data["source_product_id"] = id_match.group(1)

    # Data attributes
    for attr in ["data-product-id", "data-id", "data-sku"]:
        val = card.get(attr)
        if val:
            data["source_product_id"] = val
            break

    # Price
    price_el = card.select_one(
        "[class*='price']:not([class*='old']):not([class*='was'])"
    )
    if price_el:
        data["price"] = _parse_price(price_el.get_text())

    # Old price
    old_price_el = (
        card.select_one("[class*='old-price']") or
        card.select_one("del") or
        card.select_one("[class*='was-price']") or
        card.select_one("[class*='original']")
    )
    if old_price_el:
        data["old_price"] = _parse_price(old_price_el.get_text())

    # Image
    img_el = card.select_one("img")
    if img_el:
        src = img_el.get("data-src") or img_el.get("src") or ""
        if src and not src.startswith("data:"):
            data["image_url"] = urljoin(base_url, src)

    # Brand
    brand_el = card.select_one("[class*='brand']")
    if brand_el:
        data["brand"] = brand_el.get_text(strip=True)

    # Availability
    stock_el = card.select_one(
        "[class*='stock'], [class*='availability'], [class*='out-of-stock']"
    )
    if stock_el:
        text = stock_el.get_text(strip=True).lower()
        data["availability_text"] = text

    return data if data else None


def parse_product_page(
    html: str,
    source_id: str = "btech",
    base_url: str = "https://btech.com",
) -> dict:
    """
    Parse a B.TECH product detail page.

    Returns a dict with detailed product info.
    """
    soup = BeautifulSoup(html, "lxml")
    data = {}

    # Try JSON-LD first (most reliable)
    json_ld = _extract_json_ld(soup)
    if json_ld:
        data.update(_parse_json_ld_product(json_ld))

    # Supplement with HTML parsing
    # Product name
    if "product_name" not in data:
        name_el = soup.select_one("h1")
        if name_el:
            data["product_name"] = name_el.get_text(strip=True)

    # Price from HTML
    if "price" not in data:
        price_el = soup.select_one(
            "[class*='current-price'], [class*='selling-price'], "
            "[class*='product-price']"
        )
        if price_el:
            data["price"] = _parse_price(price_el.get_text())

    # SKU
    sku_el = soup.select_one("[class*='sku'], [class*='model']")
    if sku_el:
        data["sku"] = sku_el.get_text(strip=True)

    # Breadcrumb for category
    breadcrumb = soup.select("nav[class*='breadcrumb'] a, ol[class*='breadcrumb'] a")
    if len(breadcrumb) >= 2:
        data["category"] = breadcrumb[1].get_text(strip=True)
    if len(breadcrumb) >= 3:
        data["subcategory"] = breadcrumb[2].get_text(strip=True)

    # Specifications
    specs = {}
    spec_rows = soup.select(
        "table[class*='spec'] tr, "
        "div[class*='specification'] div[class*='row'], "
        "ul[class*='spec'] li"
    )
    for row in spec_rows:
        cells = row.select("td, th, span, div")
        if len(cells) >= 2:
            key = cells[0].get_text(strip=True)
            value = cells[1].get_text(strip=True)
            if key and value:
                specs[key] = value

    if specs:
        data["specifications"] = specs

    # Rating
    rating_el = soup.select_one("[class*='rating'] [class*='value'], [itemprop='ratingValue']")
    if rating_el:
        try:
            data["rating"] = float(rating_el.get_text(strip=True))
        except ValueError:
            pass

    # Review count
    review_el = soup.select_one("[class*='review-count'], [itemprop='reviewCount']")
    if review_el:
        count_text = review_el.get_text(strip=True)
        count_match = re.search(r'(\d+)', count_text)
        if count_match:
            data["review_count"] = int(count_match.group(1))

    return data


def _extract_json_ld(soup: BeautifulSoup) -> Optional[dict]:
    """Extract JSON-LD Product data from a page."""
    scripts = soup.select('script[type="application/ld+json"]')
    for script in scripts:
        try:
            data = json.loads(script.string)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("@type") == "Product":
                        return item
            elif isinstance(data, dict):
                if data.get("@type") == "Product":
                    return data
                # Check @graph
                graph = data.get("@graph", [])
                for item in graph:
                    if isinstance(item, dict) and item.get("@type") == "Product":
                        return item
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def _parse_json_ld_product(json_ld: dict) -> dict:
    """Convert JSON-LD Product schema to our format."""
    data = {}

    data["product_name"] = json_ld.get("name", "")
    data["brand"] = (
        json_ld.get("brand", {}).get("name")
        if isinstance(json_ld.get("brand"), dict)
        else json_ld.get("brand")
    )
    data["sku"] = json_ld.get("sku")
    data["source_product_id"] = json_ld.get("productID") or json_ld.get("sku", "")
    data["product_url"] = json_ld.get("url", "")
    data["image_url"] = (
        json_ld.get("image", [None])[0]
        if isinstance(json_ld.get("image"), list)
        else json_ld.get("image")
    )

    # Price from offers
    offers = json_ld.get("offers", {})
    if isinstance(offers, list) and offers:
        offers = offers[0]
    if isinstance(offers, dict):
        price = offers.get("price")
        if price:
            try:
                data["price"] = float(price)
            except (ValueError, TypeError):
                pass
        data["currency"] = offers.get("priceCurrency", "EGP")

        availability = offers.get("availability", "")
        if "InStock" in availability:
            data["availability_status"] = AvailabilityStatus.IN_STOCK
        elif "OutOfStock" in availability:
            data["availability_status"] = AvailabilityStatus.OUT_OF_STOCK
        elif "PreOrder" in availability:
            data["availability_status"] = AvailabilityStatus.PRE_ORDER

    # Rating
    rating_data = json_ld.get("aggregateRating", {})
    if rating_data:
        try:
            data["rating"] = float(rating_data.get("ratingValue", 0))
            data["review_count"] = int(rating_data.get("reviewCount", 0))
        except (ValueError, TypeError):
            pass

    # Description
    data["description"] = json_ld.get("description", "")

    # Category
    data["category"] = json_ld.get("category", "")

    return data


def parse_store_locator(
    html: str,
    source_id: str = "btech",
) -> list[Location]:
    """
    Parse B.TECH store locator page to extract branch information.
    """
    soup = BeautifulSoup(html, "lxml")
    locations = []

    # Look for store cards
    store_cards = soup.select(
        "div[class*='store'], div[class*='branch'], "
        "div[class*='location'], li[class*='store']"
    )

    for card in store_cards:
        location = _parse_store_card(card, source_id)
        if location:
            locations.append(location)

    # Also try to find store data in script tags (some sites embed JSON)
    scripts = soup.select("script")
    for script in scripts:
        if script.string and ("stores" in script.string or "branches" in script.string):
            try:
                # Look for JSON arrays in the script
                json_matches = re.findall(r'\[{.*?}\]', script.string, re.DOTALL)
                for match in json_matches:
                    try:
                        stores_data = json.loads(match)
                        for store in stores_data:
                            if isinstance(store, dict) and ("name" in store or "address" in store):
                                loc = _parse_store_json(store, source_id)
                                if loc:
                                    locations.append(loc)
                    except json.JSONDecodeError:
                        continue
            except Exception:
                continue

    return locations


def _parse_store_card(card, source_id: str) -> Optional[Location]:
    """Parse a single store card HTML element."""
    name_el = card.select_one("h3, h4, h5, [class*='name']")
    address_el = card.select_one("p, [class*='address']")
    phone_el = card.select_one("a[href^='tel:'], [class*='phone']")

    if not (name_el or address_el):
        return None

    name = name_el.get_text(strip=True) if name_el else None
    address = address_el.get_text(strip=True) if address_el else None
    phone = phone_el.get_text(strip=True) if phone_el else None

    # Try to extract city and governorate from address
    city, governorate = _parse_egyptian_address(address) if address else (None, None)

    # Try to extract coordinates from data attributes or embedded maps
    lat = card.get("data-lat") or card.get("data-latitude")
    lng = card.get("data-lng") or card.get("data-longitude")

    return Location(
        source_id=source_id,
        location_type=LocationType.STORE,
        branch_name=name,
        address=address,
        city=city,
        governorate=governorate,
        latitude=float(lat) if lat else None,
        longitude=float(lng) if lng else None,
        phone=phone,
    )


def _parse_store_json(store: dict, source_id: str) -> Optional[Location]:
    """Parse a store from embedded JSON data."""
    name = store.get("name") or store.get("title") or store.get("branch_name")
    address = store.get("address") or store.get("full_address")
    city = store.get("city")
    governorate = store.get("governorate") or store.get("state")

    if not name and not address:
        return None

    lat = store.get("lat") or store.get("latitude")
    lng = store.get("lng") or store.get("longitude")

    return Location(
        source_id=source_id,
        location_type=LocationType.STORE,
        branch_name=name,
        address=address,
        city=city,
        governorate=governorate,
        latitude=float(lat) if lat else None,
        longitude=float(lng) if lng else None,
        phone=store.get("phone"),
        working_hours=store.get("working_hours") or store.get("hours"),
    )


def _parse_egyptian_address(address: str) -> tuple[Optional[str], Optional[str]]:
    """
    Try to extract city and governorate from an Egyptian address string.
    """
    # Egyptian governorate names (English)
    governorates = [
        "Cairo", "Giza", "Alexandria", "Qalyubia", "Sharqia",
        "Dakahlia", "Beheira", "Monufia", "Gharbia", "Kafr El Sheikh",
        "Damietta", "Port Said", "Ismailia", "Suez", "North Sinai",
        "South Sinai", "Fayoum", "Beni Suef", "Minya", "Asyut",
        "Sohag", "Qena", "Luxor", "Aswan", "Red Sea",
        "New Valley", "Matrouh",
    ]

    # Major Egyptian cities
    cities = [
        "Cairo", "Giza", "Alexandria", "Heliopolis", "Nasr City",
        "Maadi", "6th of October", "Sheikh Zayed", "New Cairo",
        "Mansoura", "Tanta", "Zagazig", "Hurghada", "Sharm El Sheikh",
        "Port Said", "Suez", "Ismailia", "Aswan", "Luxor",
        "Fayoum", "Minya", "Asyut", "Sohag", "Damanhour",
        "Obour", "10th of Ramadan",
    ]

    address_lower = address.lower()
    found_city = None
    found_gov = None

    for city in cities:
        if city.lower() in address_lower:
            found_city = city
            break

    for gov in governorates:
        if gov.lower() in address_lower:
            found_gov = gov
            break

    return found_city, found_gov


def _parse_price(text: str) -> Optional[float]:
    """Extract numeric price from text like 'EGP 1,234.56' or '١٬٢٣٤'."""
    if not text:
        return None

    # Remove currency symbols and common text
    cleaned = re.sub(r'[^\d.,٠١٢٣٤٥٦٧٨٩]', '', text)

    # Handle Arabic numerals
    arabic_map = str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')
    cleaned = cleaned.translate(arabic_map)

    # Remove thousands separators
    cleaned = cleaned.replace(',', '')

    # Handle Arabic decimal separator
    cleaned = cleaned.replace('٫', '.')

    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def determine_availability(text: str) -> AvailabilityStatus:
    """Determine availability status from text."""
    if not text:
        return AvailabilityStatus.UNKNOWN

    text_lower = text.lower()

    if any(kw in text_lower for kw in ["in stock", "available", "متوفر", "متاح"]):
        return AvailabilityStatus.IN_STOCK
    elif any(kw in text_lower for kw in ["out of stock", "sold out", "غير متوفر", "نفذ"]):
        return AvailabilityStatus.OUT_OF_STOCK
    elif any(kw in text_lower for kw in ["limited", "few left", "محدود"]):
        return AvailabilityStatus.LIMITED_STOCK
    elif any(kw in text_lower for kw in ["pre-order", "coming soon", "قريبا"]):
        return AvailabilityStatus.PRE_ORDER
    elif any(kw in text_lower for kw in ["discontinued", "إيقاف"]):
        return AvailabilityStatus.DISCONTINUED

    return AvailabilityStatus.UNKNOWN
