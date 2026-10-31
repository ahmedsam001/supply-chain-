"""
Tradeline Stores Extractor

Compliance: D (UNKNOWN) — offline/fixture mode only until compliance verified.
Delegates product extraction to ShopifyExtractor.
Delegates location extraction to source_tradeline.parser.parse_store_locator_html.

To run live: compliance must be verified and enabled=True in sources.yaml.
Currently only used in offline_fixture mode for testing.
"""

from __future__ import annotations

from extractors.shopify_extractor import TradelineExtractor as _TradelineExtractor


# Re-export for package-level import compatibility
TradelineExtractor = _TradelineExtractor

__all__ = ["TradelineExtractor"]
