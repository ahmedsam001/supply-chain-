"""
Extractors module for Egypt E-Commerce Data Platform.
"""

from extractors.base import BaseExtractor, ExtractionError, ComplianceError
from extractors.shopify_extractor import ShopifyExtractor, TradelineExtractor, Dream2000Extractor
from extractors.source_btech.extractor import BTechExtractor
from extractors.source_jumia.extractor import JumiaExtractor
from extractors.source_carrefour.extractor import CarrefourExtractor

__all__ = [
    "BaseExtractor",
    "ExtractionError",
    "ComplianceError",
    "ShopifyExtractor",
    "TradelineExtractor",
    "Dream2000Extractor",
    "BTechExtractor",
    "JumiaExtractor",
    "CarrefourExtractor",
]
