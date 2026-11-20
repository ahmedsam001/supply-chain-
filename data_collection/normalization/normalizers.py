"""
Normalizers and Sanitizers for the Egypt E-Commerce Data Platform.
Provides robust, canonical standardization for:
- Stock Status (canonical enum: IN_STOCK, OUT_OF_STOCK, LIMITED_STOCK, LOW_STOCK_SIGNAL, PREORDER, UNKNOWN)
- Availability Status (canonical enum: in_stock, out_of_stock, limited_stock, pre_order, unknown)
- Image URLs (protocol-relative '//' -> 'https://', trimming, validation)
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Optional


class CanonicalStockStatus(str, Enum):
    IN_STOCK = "IN_STOCK"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    LIMITED_STOCK = "LIMITED_STOCK"
    LOW_STOCK_SIGNAL = "LOW_STOCK_SIGNAL"
    PREORDER = "PREORDER"
    UNKNOWN = "UNKNOWN"


_IN_STOCK_TERMS = {
    "in_stock", "instock", "in stock", "available", "available_in_stores",
    "pickup_available", "متوفر", "متاح", "true", "1", "in-stock",
    "ready_to_ship", "on_shelf", "in_store", "available for delivery",
    "available online", "available_online",
}

_OUT_OF_STOCK_TERMS = {
    "out_of_stock", "outofstock", "out of stock", "نفذت الكمية",
    "غير متوفر", "غير متاح", "sold_out", "sold out", "soldout",
    "false", "0", "out-of-stock", "discontinued", "delisted", "unavailable",
    "منتهي الصلاحية", "غير موجود", "غير متوفر حالياً", "غير متوفر حاليا",
}

_LIMITED_STOCK_TERMS = {
    "limited_stock", "low_stock_signal", "low_stock", "low stock",
    "كمية محدودة", "متبقي عدد قليل", "limited", "few_left",
    "almost_gone", "كمية قليلة", "باقي كمية قليلة",
}

_PREORDER_TERMS = {
    "preorder", "pre_order", "pre-order", "حجز مسبق", "طلب مسبق",
    "coming_soon", "قريباً", "قريبا",
}

_LOW_STOCK_REGEX = re.compile(
    r"(only\s+\d+\s+left|few\s+units\s+left|باقي\s+\d+|متبقي\s+\d+|كمية\s+متبقية\s+\d+)",
    re.IGNORECASE,
)


def normalize_image_url(url: Optional[str]) -> Optional[str]:
    """
    Standardize image URLs.
    Fixes protocol-relative URLs (e.g. '//cdn.shopify.com/...' or '//eg.jumia.is/...')
    by prepending 'https:'.
    """
    if url is None:
        return None
    url_str = str(url).strip()
    if not url_str or url_str.lower() in ("none", "null", "undefined", "n/a", "false", ""):
        return None
    if url_str.startswith("//"):
        return f"https:{url_str}"
    return url_str


def normalize_stock_status(
    raw_val: Any,
    availability_status: Optional[Any] = None,
) -> str:
    """
    Normalize any raw stock status string or boolean to a canonical enum:
    IN_STOCK | OUT_OF_STOCK | LIMITED_STOCK | LOW_STOCK_SIGNAL | PREORDER | UNKNOWN.

    If raw_val is missing or empty, infer from availability_status.
    """
    if raw_val is not None:
        raw_clean = getattr(raw_val, "value", raw_val)
        s = str(raw_clean).strip().lower()
        if s in _IN_STOCK_TERMS:
            return CanonicalStockStatus.IN_STOCK.value
        if s in _OUT_OF_STOCK_TERMS:
            return CanonicalStockStatus.OUT_OF_STOCK.value
        if s == "low_stock_signal":
            return CanonicalStockStatus.LOW_STOCK_SIGNAL.value
        if s in _LIMITED_STOCK_TERMS or _LOW_STOCK_REGEX.search(s):
            return CanonicalStockStatus.LIMITED_STOCK.value
        if s in _PREORDER_TERMS:
            return CanonicalStockStatus.PREORDER.value

    # Fallback to availability_status if raw_val is missing, empty, or unmapped
    if availability_status is not None:
        avail_clean = getattr(availability_status, "value", availability_status)
        avail = str(avail_clean).strip().lower()
        if avail in ("in_stock", "instock", "available", "true"):
            return CanonicalStockStatus.IN_STOCK.value
        if avail in ("out_of_stock", "outofstock", "discontinued", "delisted", "sold_out", "false"):
            return CanonicalStockStatus.OUT_OF_STOCK.value
        if avail in ("limited_stock", "low_stock"):
            return CanonicalStockStatus.LIMITED_STOCK.value
        if avail in ("pre_order", "preorder"):
            return CanonicalStockStatus.PREORDER.value

    return CanonicalStockStatus.UNKNOWN.value


def normalize_availability_status(
    raw_val: Any,
    stock_status: Optional[Any] = None,
) -> str:
    """
    Normalize availability status to canonical lowercase:
    in_stock | out_of_stock | limited_stock | pre_order | unknown.

    If raw_val is missing or unknown, infer from stock_status.
    """
    if raw_val is not None:
        raw_clean = getattr(raw_val, "value", raw_val)
        s = str(raw_clean).strip().lower()
        if s in _IN_STOCK_TERMS or s == "in_stock":
            return "in_stock"
        if s in _OUT_OF_STOCK_TERMS or s == "out_of_stock":
            return "out_of_stock"
        if s in _LIMITED_STOCK_TERMS or s == "limited_stock" or _LOW_STOCK_REGEX.search(s):
            return "limited_stock"
        if s in _PREORDER_TERMS or s in ("pre_order", "preorder"):
            return "pre_order"

    if stock_status is not None:
        stock_clean = getattr(stock_status, "value", stock_status)
        st = str(stock_clean).strip().upper()
        if st in ("IN_STOCK", "AVAILABLE"):
            return "in_stock"
        if st in ("OUT_OF_STOCK", "SOLD_OUT"):
            return "out_of_stock"
        if st in ("LIMITED_STOCK", "LOW_STOCK_SIGNAL"):
            return "limited_stock"
        if st in ("PREORDER", "PRE_ORDER"):
            return "pre_order"

    return "unknown"
