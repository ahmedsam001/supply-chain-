"""
B.TECH Extractor Configuration
"""

# B.TECH website structure
BASE_URL = "https://btech.com"
CATEGORY_URLS = {
    "mobiles": "/mobiles",
    "laptops": "/laptops",
    "televisions": "/televisions",
    "home-appliances": "/home-appliances",
    "small-appliances": "/small-appliances",
}

# Store locator
STORE_LOCATOR_URL = "https://btech.com/store-locator"

# Pagination
PRODUCTS_PER_PAGE = 24
MAX_PAGES_PER_CATEGORY = 10

# Selectors (to be refined during browser research)
SELECTORS = {
    "product_card": "div[class*='product-card'], div[class*='ProductCard'], li[class*='product-item']",
    "product_name": "h2[class*='product-name'], a[class*='product-name'], span[class*='product-name']",
    "product_price": "span[class*='price'], div[class*='price']",
    "product_old_price": "span[class*='old-price'], del, span[class*='was-price']",
    "product_link": "a[href*='/product/'], a[href*='/-p-']",
    "product_image": "img[class*='product-image'], img[class*='lazy']",
    "pagination_next": "a[class*='next'], button[class*='next'], li.next a",
    "availability": "span[class*='stock'], div[class*='availability']",
    "brand": "span[class*='brand'], div[class*='brand']",
    "category_breadcrumb": "nav[class*='breadcrumb'], ol[class*='breadcrumb']",
    # Store locator
    "store_card": "div[class*='store'], div[class*='branch']",
    "store_name": "h3, h4, span[class*='name']",
    "store_address": "p[class*='address'], span[class*='address']",
    "store_phone": "a[href^='tel:'], span[class*='phone']",
}

# JSON-LD
JSON_LD_ENABLED = True
