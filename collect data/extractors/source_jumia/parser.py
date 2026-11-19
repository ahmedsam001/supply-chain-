"""
Jumia HTML and JSON-LD Parser
Parses product cards, product detail pages, and delivery zones.
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
from extractors.source_jumia.config import BASE_URL, ALL_EGYPT_GOVERNORATES


def parse_price(text: Optional[str]) -> Optional[float]:
    """Parse price string to float (supports EGP, commas, and Arabic digits)."""
    if not text:
        return None

    # Replace Arabic numerals
    arabic_to_western = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
    cleaned = text.translate(arabic_to_western)

    # If price range (e.g. 'EGP 120,000.00 - EGP 130,000.00'), take the first price
    if "-" in cleaned:
        cleaned = cleaned.split("-")[0]

    # Strip currency labels and non-numeric characters except . and ,
    cleaned = re.sub(r"[^\d.,]", "", cleaned).strip()
    if not cleaned:
        return None

    # Handle commas
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
    """Parse discount string into a percentage float."""
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


def determine_availability(text: Optional[str]) -> AvailabilityStatus:
    """Classify availability status from text."""
    if not text:
        return AvailabilityStatus.UNKNOWN

    t = text.lower()
    if any(k in t for k in ["out of stock", "غير متوفر", "نفدت الكمية", "sold out"]):
        return AvailabilityStatus.OUT_OF_STOCK
    if any(k in t for k in ["only", "left", "low stock", "متبقي", "قطع متبقية"]):
        return AvailabilityStatus.LIMITED_STOCK
    if any(k in t for k in ["in stock", "متوفر", "instock", "units left"]):
        return AvailabilityStatus.IN_STOCK
    return AvailabilityStatus.IN_STOCK


def extract_brand_from_name(name: str) -> Optional[str]:
    """Infer brand from product name prefix if available."""
    if not name:
        return None
    known_brands = [
        "Samsung", "Apple", "Honor", "Xiaomi", "XIAOMI", "Redmi", "OPPO", "Oppo",
        "Realme", "Infinix", "Lenovo", "Dell", "HP", "Asus", "Acer", "Huawei",
        "Nokia", "LG", "Tornado", "Toshiba", "Sharp", "Sony", "Beko", "Unionaire",
        "Carrier", "Fresh", "Zanussi", "Bosch", "Ariston", "Philips", "Braun",
        "Kenwood", "Moulinex", "Black+Decker", "Tefal", "Mienta"
    ]
    for brand in known_brands:
        if re.search(r"\b" + re.escape(brand) + r"\b", name, re.IGNORECASE):
            return brand
    # Fallback: first word if alphanumeric
    words = name.split()
    if words and len(words[0]) >= 2:
        return words[0]
    return None


def parse_category_page(html: str, base_url: str = BASE_URL) -> list[dict]:
    """
    Parse Jumia category listing page.
    Extracts product cards, names, prices, discounts, and URLs.
    """
    soup = BeautifulSoup(html, "lxml")
    products = []

    # Find product cards
    cards = soup.select("article.prd, article[class*='prd'], div[class*='prd']")

    # Fallback to links if no article cards matched
    if not cards:
        links = soup.select("a.core, a[href*='.html']")
        cards = [l for l in links if l.get("href")]

    for card in cards:
        item = _parse_product_card(card, base_url)
        if item and item.get("product_name"):
            products.append(item)

    return products


def _parse_product_card(card, base_url: str) -> Optional[dict]:
    """Parse a single product card element from category listing."""
    data = {}

    # Link & URL
    if card.name == "a":
        link_el = card
    else:
        # Prefer the real product link; skip login/wishlist/account anchors
        # (e.g. /customer/account/login/?tkWl=...) that also live inside cards.
        link_el = card.select_one("a.core") or next(
            (
                a for a in card.select("a[href]")
                if re.search(r"-\d+\.html", a.get("href", ""))
                and "/customer/" not in a.get("href", "")
            ),
            None,
        )
    if not link_el:
        return None

    href = link_el.get("href", "")
    if not href:
        return None

    full_url = urljoin(base_url, href)
    data["product_url"] = full_url

    # Product ID from URL (e.g. /{slug}-{id}.html)
    id_match = re.search(r"-(\d+)\.html", full_url)
    if id_match:
        data["source_product_id"] = id_match.group(1)
    else:
        # Fallback to data attribute or hash
        data["source_product_id"] = card.get("data-id") or re.sub(r"\D", "", full_url)[-8:] or "unknown"

    # Name
    name_el = card.select_one("h3.name, .name, [data-name]")
    if name_el:
        data["product_name"] = name_el.get_text(strip=True)
    elif link_el.get("title"):
        data["product_name"] = link_el.get("title").strip()
    elif link_el.get("aria-label"):
        data["product_name"] = link_el.get("aria-label").strip()

    if not data.get("product_name"):
        return None

    # Explicit SKU from card data-gtm-id / data-ga4-item_id / data-sku if exposed
    card_sku = (
        link_el.get("data-gtm-id")
        or link_el.get("data-ga4-item_id")
        or card.get("data-sku")
        or link_el.get("data-sku")
    )
    if card_sku:
        data["sku"] = str(card_sku).strip()

    # Category from card data-gtm-category / data-ga4-item_category if exposed
    gtm_cat = link_el.get("data-gtm-category") or card.get("data-gtm-category")
    ga4_cat = link_el.get("data-ga4-item_category") or card.get("data-ga4-item_category")
    if gtm_cat:
        parts = [p.strip() for p in str(gtm_cat).split("/") if p.strip()]
        if parts:
            data["category"] = parts[0]
            data["raw_category_path"] = " > ".join(parts)
    elif ga4_cat:
        data["category"] = str(ga4_cat).strip()

    # Brand
    brand_el = card.select_one("div.brand, [data-brand]")
    gtm_brand = link_el.get("data-gtm-brand") or link_el.get("data-ga4-item_brand")
    if brand_el:
        data["brand"] = brand_el.get_text(strip=True) or brand_el.get("data-brand")
    elif gtm_brand:
        data["brand"] = str(gtm_brand).strip()
    else:
        data["brand"] = extract_brand_from_name(data.get("product_name", ""))

    # Price
    price_el = card.select_one("div.prc, .prc")
    if price_el:
        raw_p = price_el.get_text(strip=True)
        data["raw_price_text"] = raw_p
        data["price"] = parse_price(raw_p)

    # Old price
    old_price_el = card.select_one("div.old, .old, del")
    if old_price_el:
        data["old_price"] = parse_price(old_price_el.get_text(strip=True))

    # Discount
    disc_el = card.select_one("div.bdg._dsct, .bdg._dsct, ._dsct, [class*='discount']")
    if disc_el:
        data["discount"] = parse_discount(disc_el.get_text(strip=True))
    elif data.get("price") and data.get("old_price") and data["old_price"] > data["price"]:
        data["discount"] = round((1 - data["price"] / data["old_price"]) * 100, 1)

    # Rating & Reviews
    stars_el = card.select_one("div.stars, .stars")
    if stars_el:
        star_match = re.search(r"(\d+(?:\.\d+)?)", stars_el.get_text(strip=True))
        if star_match:
            try:
                data["rating"] = float(star_match.group(1))
            except ValueError:
                pass

    rev_el = card.select_one("div.rev, .rev")
    if rev_el:
        rev_text = rev_el.get_text(strip=True)
        # Often formatted as (15) or 15 reviews
        paren_match = re.search(r"\((\d+)\)", rev_text)
        if paren_match:
            try:
                data["review_count"] = int(paren_match.group(1))
            except ValueError:
                pass
        else:
            # Strip out stars text if nested
            if stars_el:
                rev_text = rev_text.replace(stars_el.get_text(strip=True), "")
            num_match = re.search(r"(\d+)", rev_text)
            if num_match:
                try:
                    data["review_count"] = int(num_match.group(1))
                except ValueError:
                    pass

    # Image URL
    img_el = card.select_one("img.img, img[data-src], img[src]")
    if img_el:
        data["image_url"] = img_el.get("data-src") or img_el.get("src")

    return data


def parse_product_detail_page(html: str, base_url: str = BASE_URL) -> dict:
    """
    Parse a single Jumia product detail page.
    Extracts SKU, full breadcrumbs, seller info, image, and availability.
    """
    soup = BeautifulSoup(html, "lxml")
    data = {}

    # JSON-LD Structured Data (supports @graph, list, mainEntity, and direct Product)
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            raw_ld = json.loads(script.get_text())
            candidates = []
            if isinstance(raw_ld, list):
                candidates.extend(raw_ld)
            elif isinstance(raw_ld, dict):
                if isinstance(raw_ld.get("@graph"), list):
                    candidates.extend(raw_ld["@graph"])
                candidates.append(raw_ld)
            for ld in candidates:
                if not isinstance(ld, dict):
                    continue
                if isinstance(ld.get("mainEntity"), dict):
                    ld = ld["mainEntity"]
                if ld.get("@type") == "Product":
                    if "sku" in ld:
                        data["sku"] = str(ld["sku"])
                    if "name" in ld:
                        data["product_name"] = ld["name"]
                    if "brand" in ld:
                        brand_info = ld["brand"]
                        data["brand"] = brand_info.get("name") if isinstance(brand_info, dict) else str(brand_info)
                    if "category" in ld and isinstance(ld["category"], str):
                        data.setdefault("category", ld["category"])
                    if "image" in ld:
                        img = ld["image"]
                        if isinstance(img, list):
                            data["image_url"] = img[0] if img else None
                        elif isinstance(img, dict):
                            cu = img.get("contentUrl") or img.get("url")
                            data["image_url"] = cu[0] if isinstance(cu, list) and cu else (str(cu) if cu else None)
                        else:
                            data["image_url"] = str(img)
                    if "offers" in ld:
                        offers = ld["offers"]
                        if isinstance(offers, list) and offers:
                            all_sellers = []
                            for off in offers:
                                if isinstance(off, dict):
                                    s_obj = off.get("seller")
                                    s_name = s_obj.get("name") if isinstance(s_obj, dict) else (s_obj if isinstance(s_obj, str) else None)
                                    if s_name and s_name not in all_sellers:
                                        all_sellers.append(s_name)
                            if all_sellers:
                                data["sellers"] = all_sellers
                                data.setdefault("seller_name", all_sellers[0])
                            offers = offers[0]
                        if isinstance(offers, dict):
                            p_str = offers.get("price")
                            if p_str is not None:
                                data["raw_price_text"] = f"{p_str} {offers.get('priceCurrency', 'EGP')}".strip()
                            data["price"] = float(offers.get("price", 0)) or None
                            data["availability"] = offers.get("availability")
                            s_obj = offers.get("seller")
                            s_name = s_obj.get("name") if isinstance(s_obj, dict) else (s_obj if isinstance(s_obj, str) else None)
                            if s_name:
                                data.setdefault("seller_name", s_name)
        except Exception:
            continue

    # HTML Fallbacks:
    # SKU
    if not data.get("sku"):
        sku_el = soup.find(text=re.compile(r"SKU:", re.I))
        if sku_el and sku_el.parent:
            sku_match = re.search(r"SKU:\s*([A-Za-z0-9_-]+)", sku_el.parent.get_text())
            if sku_match:
                data["sku"] = sku_match.group(1).strip()
        if not data.get("sku"):
            sku_tag = soup.select_one("[data-sku], .sku")
            if sku_tag:
                data["sku"] = sku_tag.get("data-sku") or sku_tag.get_text(strip=True)

    # Breadcrumbs (Category / Subcategory)
    breadcrumbs = []
    brc_links = soup.select("nav.brc a, div.brc a, div.brcbs a.cbs, ol.brc li")
    for link in brc_links:
        t = link.get_text(strip=True)
        if t and t.lower() not in ["home", "الرئيسية", ">", "/"]:
            breadcrumbs.append(t)

    if breadcrumbs:
        data["category"] = breadcrumbs[0]
        data["raw_category_path"] = " > ".join(breadcrumbs)
        if len(breadcrumbs) > 1:
            data["subcategory"] = " > ".join(breadcrumbs[1:])

    # Seller Name
    seller_el = soup.select_one("section.seller-info, div.seller-name, a[href*='/seller/']")
    if seller_el:
        seller_text = seller_el.get_text(separator=" ", strip=True)
        seller_match = re.search(r"(?:Seller Information:?|Sold by:?|البائع:?)\s*([A-Za-z0-9\s]+?)(?:Marketplace|\d+%|$)", seller_text, re.I)
        if seller_match:
            data["seller_name"] = seller_match.group(1).strip()
        else:
            data["seller_name"] = seller_text.split("\n")[0].strip()

    # Availability Text
    avail_el = soup.select_one("p.-df.-i-ctr.-pts, div[class*='stock'], span[class*='stock']")
    if avail_el:
        data["availability_text"] = avail_el.get_text(strip=True)
        data["availability_status"] = determine_availability(data["availability_text"])
    elif data.get("availability"):
        raw_av = str(data["availability"])
        data["availability_text"] = raw_av
        data["availability_status"] = determine_availability(raw_av)

    # Public PDP Delivery Info (default location shown on public HTML, no session spoofing)
    delivery_eta_list = []
    delivery_fee_val = None
    for m_el in soup.select("section.-pr div.markup, article div.markup"):
        m_txt = m_el.get_text(" ", strip=True)
        if not m_txt:
            continue
        low = m_txt.lower()
        if "ready for delivery" in low or "ready for pickup" in low or "delivery by" in low:
            if m_txt not in delivery_eta_list:
                delivery_eta_list.append(m_txt)
        elif "free delivery" in low and delivery_fee_val is None:
            delivery_fee_val = 0.0
        elif "delivery fees" in low and delivery_fee_val is None:
            fee_p = parse_price(m_txt)
            if fee_p is not None:
                delivery_fee_val = fee_p

    if delivery_eta_list:
        data["delivery_eta"] = " | ".join(delivery_eta_list)
        data["delivery_available"] = True
    else:
        data.setdefault("delivery_eta", None)
        data.setdefault("delivery_available", None)
    data["delivery_fee"] = delivery_fee_val

    return data


def parse_delivery_zones(html: Optional[str] = None) -> list[dict]:
    """
    Parse delivery zones for Jumia.
    Jumia covers all 27 Egyptian governorates for home delivery / pickup.
    """
    zones = []
    if html:
        soup = BeautifulSoup(html, "lxml")
        options = soup.select("select[name*='governorate'] option, select#delivery-governorate option")
        for opt in options:
            val = opt.get_text(strip=True)
            if val and "select" not in val.lower() and "اختر" not in val:
                zones.append({
                    "governorate": val,
                    "location_type": LocationType.DELIVERY_ZONE,
                })

    if not zones:
        # Fallback to standard 27 governorates
        for gov in ALL_EGYPT_GOVERNORATES:
            zones.append({
                "governorate": gov,
                "location_type": LocationType.DELIVERY_ZONE,
            })

    return zones
