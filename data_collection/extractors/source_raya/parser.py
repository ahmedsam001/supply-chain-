"""
Raya Shop Parser

Parses Raya Shop's Magento 2 pages. Same structure as 2B Egypt.
Imports and re-uses the Magento 2 JSON-LD parser from source_2b.

Availability semantics:
- 'Pickup from Store' = PHYSICAL_BRANCH scope
- 'In Stock' = DELIVERY_AREA scope (online delivery)
- Never assume stock_quantity from text signals.
"""

from __future__ import annotations

from typing import Optional

from normalization.schema import AvailabilityScope, AvailabilityStatus, Location, LocationType
from extractors.source_2b.parser import (
    extract_json_ld,
    parse_category_page as _parse_cat,
    parse_product_detail_page as _parse_pdp,
    parse_store_locator as _parse_locator,
    determine_availability as _determine_avail_2b,
    _parse_price,
)
from geospatial.egypt_geography import normalize_location


BASE_URL = "https://www.rayashop.com"
SOURCE_ID = "raya"


# Raya-specific availability text overrides
_RAYA_PICKUP_TEXTS = [
    "pickup from store", "pickup", "استلام من الفرع", "available for pickup",
]


def determine_raya_availability(
    text: Optional[str],
) -> tuple[AvailabilityStatus, AvailabilityScope, str]:
    """
    Raya-specific availability parser.
    'Pickup from Store' = PHYSICAL_BRANCH.
    Falls back to 2B parser for everything else.
    """
    if not text:
        return AvailabilityStatus.UNKNOWN, AvailabilityScope.UNKNOWN, "UNKNOWN"

    t = text.lower().strip()
    if any(k in t for k in _RAYA_PICKUP_TEXTS):
        return AvailabilityStatus.IN_STOCK, AvailabilityScope.PHYSICAL_BRANCH, "PICKUP_AVAILABLE"

    return _determine_avail_2b(text)


def parse_category_page(
    html: str,
    source_id: str = SOURCE_ID,
    base_url: str = BASE_URL,
) -> list[dict]:
    """Parse Raya Shop category page (JSON-LD first, HTML fallback)."""
    products = _parse_cat(html, source_id=source_id, base_url=base_url)
    # Re-apply Raya-specific availability parsing
    for p in products:
        raw = p.get("raw_availability_text")
        if raw:
            status, scope, stock = determine_raya_availability(raw)
            p["availability_status"] = status
            p["availability_scope"] = scope
            p["stock_status"] = stock
    return products


def parse_product_detail_page(
    html: str,
    source_id: str = SOURCE_ID,
    base_url: str = BASE_URL,
) -> Optional[dict]:
    """Parse a Raya Shop product detail page."""
    result = _parse_pdp(html, source_id=source_id, base_url=base_url)
    if result:
        raw = result.get("raw_availability_text")
        if raw:
            status, scope, stock = determine_raya_availability(raw)
            result["availability_status"] = status
            result["availability_scope"] = scope
            result["stock_status"] = stock
    return result


def parse_store_locator(
    html: str,
    source_id: str = SOURCE_ID,
) -> list[Location]:
    """Parse Raya Shop store locator HTML."""
    return _parse_locator(html, source_id=source_id)
