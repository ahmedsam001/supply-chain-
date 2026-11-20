"""
Dream 2000 Extractor

Compliance: D (UNKNOWN) — offline/fixture mode only until compliance verified.
Delegates to ShopifyExtractor (Dream2000Extractor).
"""

from extractors.shopify_extractor import Dream2000Extractor as _Dream2000Extractor

Dream2000Extractor = _Dream2000Extractor

__all__ = ["Dream2000Extractor"]
