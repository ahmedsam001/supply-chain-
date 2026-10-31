"""
Dream 2000 Parser

Parses Shopify /products.json format. Same format as Tradeline.
Imports and re-uses Tradeline parser with dream2000 source_id.
"""

from __future__ import annotations

from extractors.source_tradeline.parser import (
    parse_shopify_products_json as _parse_shopify,
    _parse_single_shopify_product,
    _safe_float,
)
from normalization.schema import Product, ProductObservation


def parse_shopify_products_json(
    json_data: dict | str,
    source_id: str = "dream2000",
    base_url: str = "https://dream2000.com",
) -> tuple[list[Product], list[ProductObservation]]:
    """Parse Dream 2000 Shopify /products.json response."""
    return _parse_shopify(json_data, source_id=source_id, base_url=base_url)


__all__ = ["parse_shopify_products_json"]
