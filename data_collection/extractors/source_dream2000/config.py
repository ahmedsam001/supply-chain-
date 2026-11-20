"""
Dream 2000 Extractor Configuration

Dream 2000 is a mobile phones and electronics retailer.
Data source: public Shopify /products.json endpoint.
Compliance: D (unverified) — disabled until robots.txt and ToS confirmed.
"""

BASE_URL = "https://dream2000.com"
STORE_LOCATOR_PATH = "/pages/branches"
PRODUCTS_JSON_PATH = "/products.json"
MAX_PER_PAGE = 250

MAX_REQUESTS_PER_MINUTE = 20
MIN_DELAY_SECONDS = 2.0
MAX_DELAY_SECONDS = 4.0

COMPLIANCE_NOTE = (
    "Compliance class D (UNKNOWN). robots.txt and ToS verification pending. "
    "Do NOT enable live extraction until compliance is verified."
)
