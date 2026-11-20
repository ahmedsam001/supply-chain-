"""
Raya Shop Extractor Configuration
==================================
Active category endpoints for Raya Shop (Nuxt.js + Fastly CDN).
"""

BASE_URL = "https://www.rayashop.com"

CATEGORY_URLS = {
    "electronics": "/en/electronics",
    "large_appliances": "/en/large-appliances",
    "small_appliances": "/en/small-appliances",
    "health_and_beauty": "/en/health-and-beauty",
    "mobiles": "/en/back-to-school-offers-mobiles",
    "coffee": "/en/coffee-corner",
    "home_decor": "/en/home-decor",
}

STORE_LOCATOR_PATH = "/en/store-locator"

MAX_REQUESTS_PER_MINUTE = 15
MIN_DELAY_SECONDS = 3.0
MAX_DELAY_SECONDS = 6.0
MAX_PAGES_PER_CATEGORY = 5

COMPLIANCE_NOTE = (
    "Compliance class D (UNKNOWN). robots.txt and ToS verification pending. "
    "Do NOT enable live extraction until compliance is verified."
)
