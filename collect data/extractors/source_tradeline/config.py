"""
Tradeline Stores Extractor Configuration

Tradeline is Apple's Premium Partner in Egypt.
Data source: public Shopify /products.json endpoint.
Compliance: D (unverified) — disabled until robots.txt and ToS confirmed.
"""

BASE_URL = "https://www.tradelinestores.com"
STORE_LOCATOR_PATH = "/pages/store-locator"

# Shopify public endpoint — no auth required
PRODUCTS_JSON_PATH = "/products.json"
MAX_PER_PAGE = 250  # Shopify max

# Rate limits — conservative
MAX_REQUESTS_PER_MINUTE = 20
MIN_DELAY_SECONDS = 2.0
MAX_DELAY_SECONDS = 4.0

# Store locator JavaScript class used to identify branch elements
STORE_LOCATOR_ITEM_CLASS = ".js-my-location-result"

# What Tradeline exposes (from research):
# products: YES (via /products.json)
# pricing: YES (variant price field)
# availability: YES (variant available bool)
# stock_quantity: NO (Shopify doesn't expose exact quantity)
# branches: YES (store locator with GPS coordinates)
# gps: YES (data-latitude, data-longitude attributes)
# delivery_zones: PARTIAL (covers major cities)
# location_specific_inventory: NO

COMPLIANCE_NOTE = (
    "Compliance class D (UNKNOWN). robots.txt and ToS verification pending. "
    "Public /products.json endpoint is accessible without authentication. "
    "Do NOT enable live extraction until compliance is verified."
)
