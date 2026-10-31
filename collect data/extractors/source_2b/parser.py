"""
2B Egypt Parser

Parses 2B Egypt's Magento 2 pages using JSON-LD schema.org markup,
fallback HTML product cards, pagination links, and the public MageWorx
store locator (`https://2b.com.eg/en/stores`).

Availability semantics:
- 2B shows 'Available in Stores', 'In Stock', 'Out of Stock'
- 'Available in Stores' means PHYSICAL_BRANCH scope, NOT delivery
- Never assume a stock quantity from '2 left' style text
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from typing import Optional
from urllib.parse import urljoin

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
from geospatial.egypt_geography import derive_location_id, normalize_location


BASE_URL = "https://2b.com.eg"
SOURCE_ID = "two_b"


# --- Availability parsing for 2B ---

_STORE_AVAILABILITY_TEXTS = [
    "available in stores", "available in store", "in stores",
    "pickup", "in-store",
]
_DELIVERY_AVAILABILITY_TEXTS = [
    "in stock", "متوفر", "instock",
]
_OUT_TEXTS = [
    "out of stock", "غير متوفر", "sold out", "unavailable",
]
_LIMITED_TEXTS = [
    "only", "left", "low stock", "limited",
]


def determine_availability(
    text: Optional[str],
) -> tuple[AvailabilityStatus, AvailabilityScope, str]:
    """
    Return (AvailabilityStatus, AvailabilityScope, stock_status_str).

    Critically: 'Available in Stores' = PHYSICAL_BRANCH scope.
    Never assign stock_quantity from low-stock text.
    """
    if not text:
        return AvailabilityStatus.UNKNOWN, AvailabilityScope.UNKNOWN, "UNKNOWN"

    t = text.lower().strip()

    if any(k in t for k in _OUT_TEXTS):
        return AvailabilityStatus.OUT_OF_STOCK, AvailabilityScope.GLOBAL, "OUT_OF_STOCK"

    if any(k in t for k in _LIMITED_TEXTS):
        # LOW_STOCK_SIGNAL — do NOT extract quantity
        return AvailabilityStatus.LIMITED_STOCK, AvailabilityScope.GLOBAL, "LOW_STOCK_SIGNAL"

    if any(k in t for k in _STORE_AVAILABILITY_TEXTS):
        return AvailabilityStatus.IN_STOCK, AvailabilityScope.PHYSICAL_BRANCH, "AVAILABLE_IN_STORES"

    if any(k in t for k in _DELIVERY_AVAILABILITY_TEXTS):
        return AvailabilityStatus.IN_STOCK, AvailabilityScope.DELIVERY_AREA, "IN_STOCK"

    # JSON-LD schema.org availability URL matching
    schema_avail_map = {
        "instock": (AvailabilityStatus.IN_STOCK, AvailabilityScope.DELIVERY_AREA, "IN_STOCK"),
        "limitedavailability": (
            AvailabilityStatus.LIMITED_STOCK, AvailabilityScope.GLOBAL, "LOW_STOCK_SIGNAL"
        ),
        "outofstock": (AvailabilityStatus.OUT_OF_STOCK, AvailabilityScope.GLOBAL, "OUT_OF_STOCK"),
        "instoreonly": (
            AvailabilityStatus.IN_STOCK, AvailabilityScope.PHYSICAL_BRANCH, "AVAILABLE_IN_STORES"
        ),
    }
    for key, val in schema_avail_map.items():
        if key in t:
            return val

    return AvailabilityStatus.UNKNOWN, AvailabilityScope.UNKNOWN, "UNKNOWN"


def _parse_price(text: Optional[str]) -> Optional[float]:
    """Extract float price from EGP price text."""
    if not text:
        return None
    text = str(text)
    arabic_map = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
    text = text.translate(arabic_map)
    text = re.sub(r"[EGPجنيه ٪%,،\xa0]", "", text, flags=re.I)
    text = text.strip()
    try:
        val = float(text)
        return val if val > 0 else None
    except ValueError:
        return None


def extract_json_ld(html: str) -> list[dict]:
    """Extract all JSON-LD blocks from an HTML page."""
    soup = BeautifulSoup(html, "lxml")
    results = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, list):
                results.extend(d for d in data if isinstance(d, dict))
            elif isinstance(data, dict):
                results.append(data)
        except (json.JSONDecodeError, AttributeError, TypeError):
            continue
    return results


_KNOWN_BRANDS = [
    "Lenovo", "Dell", "HP", "Asus", "ASUS", "Acer", "Apple", "Samsung",
    "MSI", "Honor", "Xiaomi", "Redmi", "LG", "Tornado", "Toshiba", "Sharp",
    "Fresh", "Canon", "Epson", "Logitech", "Anker", "JBL", "Sony", "Huawei",
    "OPPO", "Realme", "Infinix", "Gigabyte", "Razer", "Generic",
]


def _extract_brand(name: str) -> Optional[str]:
    if not name:
        return None
    for b in _KNOWN_BRANDS:
        if re.search(r"\b" + re.escape(b) + r"\b", name, re.I):
            return "ASUS" if b.lower() == "asus" else b
    return None


def extract_next_page_url(html: str, base_url: str = BASE_URL) -> Optional[str]:
    """Extract the next pagination URL from a 2B Magento 2 category page if present."""
    if not html:
        return None
    soup = BeautifulSoup(html, "lxml")
    next_el = soup.select_one(
        "a.action.next, li.pages-item-next a.next, ul.pages-items a.action.next, a[title='Next']"
    )
    if not next_el:
        return None
    href = (next_el.get("href") or "").strip()
    if not href or href.startswith("#") or href.lower().startswith("javascript:"):
        return None
    return urljoin(base_url, href)


def parse_category_page(
    html: str,
    source_id: str = SOURCE_ID,
    base_url: str = BASE_URL,
) -> list[dict]:
    """
    Parse 2B category page. Prefers JSON-LD, falls back to HTML card parsing.
    When both exist, enriches JSON-LD items with HTML card fields (old_price,
    store/pickup availability text, data-product-id).
    """
    if not html or not html.strip():
        return []

    html_cards = _parse_html_cards(html, source_id, base_url)
    html_by_url = {c["product_url"]: c for c in html_cards if c.get("product_url")}

    json_ld_items = [
        item for item in extract_json_ld(html)
        if item.get("@type") == "Product"
    ]

    if json_ld_items:
        products = []
        for item in json_ld_items:
            p = _json_ld_to_product_dict(item, source_id, base_url)
            if p:
                hc = html_by_url.get(p.get("product_url", ""))
                if hc:
                    if hc.get("source_product_id") and p.get("source_product_id") == p.get("product_name", "")[:50]:
                        p["source_product_id"] = hc["source_product_id"]
                    if hc.get("old_price") and not p.get("old_price"):
                        p["old_price"] = hc["old_price"]
                        if p.get("price") and p["old_price"] > p["price"]:
                            p["discount"] = round(
                                (p["old_price"] - p["price"]) / p["old_price"] * 100, 1
                            )
                    if hc.get("raw_price_text") and not p.get("raw_price_text"):
                        p["raw_price_text"] = hc["raw_price_text"]
                    if hc.get("raw_availability_text"):
                        p["raw_availability_text"] = hc["raw_availability_text"]
                        p["availability_status"] = hc["availability_status"]
                        p["availability_scope"] = hc["availability_scope"]
                        p["stock_status"] = hc["stock_status"]
                products.append(p)
        if products:
            return products

    return html_cards


def _json_ld_to_product_dict(
    item: dict, source_id: str, base_url: str
) -> Optional[dict]:
    """Convert a JSON-LD Product object to a raw product dict."""
    name = (item.get("name") or "").strip()
    if not name:
        return None

    url = item.get("url") or item.get("@id", "")
    if url and not url.startswith("http"):
        url = urljoin(base_url, url)

    source_product_id = None
    if url:
        id_match = re.search(r"-(\d{4,})(?:\.html)?$", url)
        if id_match:
            source_product_id = id_match.group(1)

    sku = item.get("sku") or item.get("mpn") or None
    gtin = item.get("gtin") or item.get("gtin13") or item.get("gtin12") or item.get("ean") or None

    brand_data = item.get("brand", {})
    brand = brand_data.get("name") if isinstance(brand_data, dict) else brand_data
    if not brand:
        brand = None

    category = item.get("category")

    image = item.get("image")
    if isinstance(image, list):
        image = image[0] if image else None
    if isinstance(image, dict):
        image = image.get("url") or image.get("@id")

    offers = item.get("offers", {})
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    if not isinstance(offers, dict):
        offers = {}

    price_str = offers.get("price")
    price = None
    try:
        price = float(price_str) if price_str is not None else None
        if price is not None and price <= 0:
            price = None
    except (ValueError, TypeError):
        price = None

    currency = offers.get("priceCurrency", "EGP")
    avail_text = offers.get("availability", "")
    avail_status, avail_scope, stock_status = determine_availability(avail_text)

    return {
        "source_product_id": str(source_product_id or sku or name[:50]),
        "product_name": name,
        "brand": brand,
        "category": category,
        "sku": str(sku) if sku else None,
        "gtin": str(gtin) if gtin else None,
        "product_url": url,
        "image_url": image,
        "price": price,
        "old_price": None,
        "discount": None,
        "raw_price_text": f"{currency} {price_str}" if price_str is not None else None,
        "currency": currency,
        "availability_status": avail_status,
        "availability_scope": avail_scope,
        "stock_status": stock_status,
        "raw_availability_text": avail_text or None,
    }


def _parse_html_cards(
    html: str,
    source_id: str,
    base_url: str,
) -> list[dict]:
    """Fallback HTML card parser for Magento 2 product listings."""
    soup = BeautifulSoup(html, "lxml")
    products = []

    cards = soup.select("li.product-item, li.item.product, div.product-item")

    for card in cards:
        p = _parse_html_card(card, base_url)
        if p:
            products.append(p)

    return products


def _parse_html_card(card, base_url: str) -> Optional[dict]:
    """Parse a single Magento 2 product card without inventing missing fields."""
    product_id = card.get("data-product-id") or card.get("data-id")
    if not product_id:
        pb = card.select_one("[data-product-id]")
        if pb:
            product_id = pb.get("data-product-id")
    if not product_id:
        inp = card.select_one("input[name='product']")
        if inp:
            product_id = inp.get("value")

    link_el = card.select_one("a.product-item-link, a[href*='.html']")
    if not link_el:
        return None

    href = (link_el.get("href") or "").strip()
    if not href:
        return None
    url = urljoin(base_url, href)

    name_el = card.select_one(
        ".product-name, .product-item-name, span.product-name, a.product-item-link"
    )
    name = name_el.get_text(strip=True) if name_el else link_el.get_text(strip=True)

    if not name:
        return None

    # Explicit SKU only if publicly exposed on the card (never copy entity_id into sku)
    explicit_sku = card.get("data-product-sku") or card.get("data-sku")
    if not explicit_sku:
        form_el = card.select_one("form[data-product-sku]")
        if form_el:
            explicit_sku = form_el.get("data-product-sku")
    if not explicit_sku:
        sku_el = card.select_one(".product-item-sku, [data-sku]")
        if sku_el:
            explicit_sku = sku_el.get("data-sku") or sku_el.get_text(strip=True)

    img_el = card.select_one("img")
    image_url = None
    if img_el:
        image_url = img_el.get("src") or img_el.get("data-src")

    price_el = (
        card.select_one(".special-price .price, [data-price-type='finalPrice'] .price, .regular-price .price")
        or card.select_one(".price")
    )
    raw_price_text = price_el.get_text(strip=True) if price_el else None
    price = _parse_price(raw_price_text)

    old_price_el = card.select_one(
        ".old-price .price, [data-price-type='oldPrice'] .price, del .price, del"
    )
    old_price = _parse_price(old_price_el.get_text() if old_price_el else None)
    if old_price is not None and price is not None and old_price <= price:
        old_price = None

    discount = None
    if price and old_price and old_price > price:
        discount = round((old_price - price) / old_price * 100, 1)

    avail_el = card.select_one(".stock, .availability, [class*='stock']")
    avail_text = avail_el.get_text(strip=True) if avail_el else None
    if not avail_text:
        tocart_el = card.select_one("button.tocart, form[data-role='tocart-form']")
        if tocart_el:
            btn_text = tocart_el.get_text(strip=True) or "In Stock"
            avail_text = "In Stock" if "add to cart" in btn_text.lower() else btn_text
    avail_status, avail_scope, stock_status = determine_availability(avail_text)

    slug_id = url.split("/")[-1].replace(".html", "") if url else name[:50]
    return {
        "source_product_id": str(product_id) if product_id else slug_id,
        "product_name": name,
        "brand": None,
        "category": None,
        "sku": str(explicit_sku).strip() if explicit_sku else None,
        "gtin": None,
        "product_url": url,
        "image_url": image_url,
        "price": price,
        "old_price": old_price,
        "discount": discount,
        "raw_price_text": raw_price_text,
        "currency": "EGP",
        "availability_status": avail_status,
        "availability_scope": avail_scope,
        "stock_status": stock_status,
        "raw_availability_text": avail_text,
    }


def parse_product_detail_page(
    html: str,
    source_id: str = SOURCE_ID,
    base_url: str = BASE_URL,
) -> Optional[dict]:
    """
    Parse a 2B product detail page.
    Extracts JSON-LD Product + BreadcrumbList + OfferShippingDetails,
    and enriches with public HTML SKU (`.sku-availability`) and delivery ETA
    (`.delivery-info-section`).
    """
    if not html or not html.strip():
        return None

    soup = BeautifulSoup(html, "lxml")
    ld_blocks = extract_json_ld(html)
    json_ld_items = [item for item in ld_blocks if item.get("@type") == "Product"]

    result: Optional[dict] = None
    if json_ld_items:
        result = _json_ld_to_product_dict(json_ld_items[0], source_id, base_url)
    else:
        name_el = soup.select_one("h1[itemprop='name'], h1.page-title, h1")
        price_el = soup.select_one(".price-final_price .price, .price")
        avail_el = soup.select_one(".stock, .availability")

        name = name_el.get_text(strip=True) if name_el else None
        if not name:
            return None
        raw_price_text = price_el.get_text(strip=True) if price_el else None
        price = _parse_price(raw_price_text)
        avail_text = avail_el.get_text(strip=True) if avail_el else None
        avail_status, avail_scope, stock_status = determine_availability(avail_text)
        result = {
            "source_product_id": None,
            "product_name": name,
            "brand": None,
            "category": None,
            "sku": None,
            "gtin": None,
            "product_url": None,
            "image_url": None,
            "price": price,
            "old_price": None,
            "discount": None,
            "raw_price_text": raw_price_text,
            "currency": "EGP",
            "availability_status": avail_status,
            "availability_scope": avail_scope,
            "stock_status": stock_status,
            "raw_availability_text": avail_text,
        }

    # Enrich SKU from public HTML `.sku-availability` if missing in JSON-LD
    if not result.get("sku"):
        sku_avail_el = soup.select_one(".sku-availability, .product.attribute.sku")
        if sku_avail_el:
            m_sku = re.search(
                r"SKU\s*:\s*([A-Za-z0-9_./-]+)",
                sku_avail_el.get_text(" ", strip=True),
                re.I,
            )
            if m_sku:
                result["sku"] = m_sku.group(1).strip()

    # Enrich Category from BreadcrumbList JSON-LD if missing
    if not result.get("category"):
        for blk in ld_blocks:
            if blk.get("@type") == "BreadcrumbList":
                elems = blk.get("itemListElement", [])
                crumbs = []
                for el in elems:
                    if isinstance(el, dict):
                        it = el.get("item", {})
                        cname = it.get("name") if isinstance(it, dict) else None
                        if cname and cname.lower() != "home":
                            crumbs.append(cname.strip())
                if len(crumbs) >= 2:
                    result["category"] = " > ".join(crumbs[:-1])
                    result["raw_category_path"] = " > ".join(crumbs)
                break

    # Enrich public delivery ETA / delivery_available from `.delivery-info-section` or OfferShippingDetails
    delivery_items = []
    for item_el in soup.select(".delivery-info-section .info-item"):
        txt = re.sub(r"\s+", " ", item_el.get_text(" ", strip=True))
        if "delivery time" in txt.lower():
            delivery_items.append(txt)
    if delivery_items:
        result["delivery_eta"] = " | ".join(delivery_items)
        result["delivery_available"] = True
    else:
        for blk in ld_blocks:
            if blk.get("@type") == "OfferShippingDetails":
                dt = blk.get("deliveryTime", {})
                transit = dt.get("transitTime", {}) if isinstance(dt, dict) else {}
                min_d = transit.get("minValue")
                max_d = transit.get("maxValue")
                if min_d is not None and max_d is not None:
                    result["delivery_eta"] = f"{min_d}-{max_d} days"
                    result["delivery_available"] = True
                break

    result.setdefault("delivery_fee", None)
    return result


def parse_store_locator(
    html: str,
    source_id: str = SOURCE_ID,
    source_url: str = f"{BASE_URL}/en/stores",
) -> list[Location]:
    """
    Parse 2B public store locator HTML into canonical Location (BRANCH) records.

    Supports:
    1. Live MageWorx StoreLocator HTML (`section.mw-sl__stores__list__item` +
       `locations['id'] = {lat: ..., lng: ...}` / Google Maps destination links).
    2. Generic `.store-item, .store-card, li.store` cards (for synthetic/offline tests).
    3. Embedded JSON-LD `@type: Store` fallback if only the outer shell page is provided.
    """
    if not html or not html.strip():
        return []

    soup = BeautifulSoup(html, "lxml")
    now = datetime.now(timezone.utc)
    locations: list[Location] = []

    script_coords: dict[str, tuple[float, float]] = {}
    for script in soup.find_all("script"):
        st = script.string or script.get_text() or ""
        if "locations[" in st:
            for m in re.finditer(
                r"""locations\[['"](\d+)['"]\]\s*=\s*\{\s*lat:\s*([0-9.-]+)\s*,\s*lng:\s*([0-9.-]+)\s*\}""",
                st,
            ):
                try:
                    script_coords[m.group(1)] = (float(m.group(2)), float(m.group(3)))
                except ValueError:
                    continue

    # 1. Live MageWorx StoreLocator sections
    mw_sections = soup.select("section.mw-sl__stores__list__item")
    if mw_sections:
        seen_keys: set[str] = set()
        for sec in mw_sections:
            classes = sec.get("class", [])
            block_id = next(
                (c.split("_")[-1] for c in classes if c.startswith("location-info-block_")),
                None,
            )
            name_el = sec.select_one(".mw-sl__store__info__name")
            name = name_el.get_text(strip=True) if name_el else None
            if not name:
                continue

            addr_el = sec.select_one("div.address")
            raw_addr = (
                re.sub(r"\s+", " ", addr_el.get_text(" ", strip=True)).strip()
                if addr_el
                else None
            )

            dedup_key = block_id or f"{name.lower()}|{raw_addr or ''}"
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)

            lat: Optional[float] = None
            lng: Optional[float] = None
            if block_id and block_id in script_coords:
                lat, lng = script_coords[block_id]
            else:
                route_el = sec.select_one(
                    ".mw-sl__stores__details__route a[href*='destination=']"
                )
                if route_el:
                    m_dest = re.search(
                        r"destination=([0-9.-]+),([0-9.-]+)",
                        route_el.get("href", ""),
                    )
                    if m_dest:
                        try:
                            lat = float(m_dest.group(1))
                            lng = float(m_dest.group(2))
                        except ValueError:
                            lat, lng = None, None

            hours_el = sec.select_one(".mw-sl__store__info__open")
            hours = (
                re.sub(r"\s+", " ", hours_el.get_text(" ", strip=True)).strip()
                if hours_el
                else None
            )

            phone_el = sec.select_one("a[href^='tel:']")
            phone = phone_el.get_text(strip=True) if phone_el else None

            combined_addr = f"{name}, {raw_addr}" if raw_addr else name
            geo = normalize_location(address=combined_addr)
            gov = geo.get("governorate") or "unknown"

            loc_id = derive_location_id(
                source_id=source_id,
                location_type=LocationType.BRANCH.value,
                normalized_name=name,
                address=raw_addr,
            )
            locations.append(
                Location(
                    location_id=loc_id,
                    source_id=source_id,
                    location_type=LocationType.BRANCH,
                    location_name=name,
                    branch_name=name,
                    raw_location_name=name,
                    address=raw_addr,
                    city=geo.get("city"),
                    governorate=gov,
                    latitude=lat,
                    longitude=lng,
                    phone=phone,
                    working_hours=hours,
                    source_url=source_url,
                    collected_at=now,
                )
            )
        return locations

    # 2. Generic .store-item / .store-card fallback
    store_cards = soup.select(
        ".store-item, .store-card, li.store, [class*='store-item']"
    )
    for card in store_cards:
        name_el = card.select_one(".store-name, h3, h4, [class*='name']")
        name = name_el.get_text(strip=True) if name_el else None
        if not name:
            continue

        addr_el = card.select_one(".store-address, .address, [class*='address']")
        address = addr_el.get_text(strip=True) if addr_el else None

        phone_el = card.select_one("a[href^='tel:'], .store-phone")
        phone = phone_el.get_text(strip=True) if phone_el else None

        lat = None
        lng = None
        if card.get("data-lat") and card.get("data-lng"):
            try:
                lat = float(card["data-lat"])
                lng = float(card["data-lng"])
            except ValueError:
                lat, lng = None, None

        combined_addr = f"{name}, {address}" if address else name
        geo = normalize_location(address=combined_addr)
        gov = geo.get("governorate") or "unknown"

        loc_id = derive_location_id(
            source_id=source_id,
            location_type=LocationType.BRANCH.value,
            normalized_name=name,
            address=address,
        )
        locations.append(
            Location(
                location_id=loc_id,
                source_id=source_id,
                location_type=LocationType.BRANCH,
                location_name=name,
                branch_name=name,
                raw_location_name=name,
                address=address,
                city=geo.get("city"),
                governorate=gov,
                latitude=lat,
                longitude=lng,
                phone=phone,
                source_url=source_url,
                collected_at=now,
            )
        )
    if locations:
        return locations

    # 3. Embedded JSON-LD Store fallback (from /en/stores outer shell)
    for blk in extract_json_ld(html):
        if blk.get("@type") == "Store":
            addr_obj = blk.get("address", {})
            if isinstance(addr_obj, dict):
                street = addr_obj.get("streetAddress") or ""
                locality = addr_obj.get("addressLocality") or ""
                region = addr_obj.get("addressRegion") or ""
                full_addr = ", ".join(p for p in (street, locality, region) if p).strip() or None
                name = blk.get("name") or "2B Egypt Main Store"
                geo = normalize_location(address=full_addr, city=region or None)
                gov = geo.get("governorate") or "unknown"
                loc_id = derive_location_id(
                    source_id=source_id,
                    location_type=LocationType.BRANCH.value,
                    normalized_name=name,
                    address=full_addr,
                )
                locations.append(
                    Location(
                        location_id=loc_id,
                        source_id=source_id,
                        location_type=LocationType.BRANCH,
                        location_name=name,
                        branch_name=name,
                        raw_location_name=name,
                        address=full_addr,
                        city=geo.get("city"),
                        governorate=gov,
                        phone=blk.get("telephone"),
                        source_url=source_url,
                        collected_at=now,
                    )
                )
    return locations
