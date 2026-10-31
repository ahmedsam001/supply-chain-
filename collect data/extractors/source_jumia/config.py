"""
Jumia Egypt Extractor Configuration
"""

BASE_URL = "https://www.jumia.com.eg"

DEPARTMENT_URLS: dict[str, dict[str, str]] = {
    "mobiles_tablets": {
        "ios-phones":               "/ios-phones/",
        "cell-phones":              "/cell-phones/",
        "android-phones":           "/android-phones/",
        "mobile-phones":            "/mobile-phones/",
        "tablets":                  "/tablets/",
        "phones-tablets":           "/phones-tablets/",
        "mobile-phone-accessories": "/mobile-phone-accessories/",
        "smart-watches":            "/smart-watches/",
        "samsung-store":            "/samsung/",
        "apple-store":              "/apple/",
        "xiaomi-store":             "/xiaomi/",
        "oppo-store":               "/oppo/",
    },
    "computing": {
        "computing":                "/computing/",
        "laptops":                  "/laptops/",
        "lenovo-store":             "/lenovo/",
        "hp-store":                 "/hp/",
    },
    "electronics_tv": {
        "electronics":              "/electronics/",
        "televisions":              "/televisions/",
        "video-games":              "/video-games/",
        "tornado-store":            "/tornado/",
    },
    "home_appliances": {
        "appliances":               "/appliances/",
        "small-appliances":         "/small-appliances/",
        "fresh-store":              "/fresh/",
        "sokany-store":             "/sokany/",
        "braun-store":              "/braun/",
    },
    "grocery_pantry": {
        "supermarket":              "/groceries/",
    },
    "beverages": {
        "beverages":                "/drinks/",
    },
    "household_cleaning": {
        "household-cleaning":       "/household-supplies/",
    },
    "personal_care_beauty": {
        "health-beauty":            "/health-beauty/",
        "skin-care":                "/skin-care/",
        "hair-care":                "/hair-care/",
        "garnier-store":            "/garnier/",
        "l-oreal-store":            "/l-oreal/",
        "nivea-store":              "/nivea/",
    },
}

CATEGORY_URLS = {
    cat_key: cat_path
    for dept_map in DEPARTMENT_URLS.values()
    for cat_key, cat_path in dept_map.items()
}

# Phone-focused categories
PHONE_CATEGORIES = list(DEPARTMENT_URLS["mobiles_tablets"].keys())

# Jumia rate limit policy from robots.txt:
# "Site scraping is permitted IF user-agent clearly identifies as a bot with owner url or contact,
# and uses less than 200 requests per minute."
MAX_REQUESTS_PER_MINUTE = 30  # Conservative, well under 200 RPM limit
MIN_DELAY_SECONDS = 1.5
MAX_DELAY_SECONDS = 3.0

PRODUCTS_PER_PAGE = 40
MAX_PAGES_PER_CATEGORY = 50  # full sweep

SELECTORS = {
    # Category listing card selectors
    "product_card": "article.prd, article[class*='prd'], div[class*='prd']",
    "product_name": "h3.name, .name, [data-name]",
    "product_link": "a.core, a[href*='.html']",
    "product_price": "div.prc, .prc",
    "product_old_price": "div.old, .old, del",
    "product_discount": "div.bdg._dsct, .bdg._dsct, ._dsct, span[class*='discount']",
    "product_rating": "div.stars, .stars",
    "product_reviews": "div.rev, .rev",
    "product_image": "img.img, img[data-src], img[src]",
    "pagination_next": "a[aria-label='Next Page'], a.pg[aria-label='Next']",

    # Product detail page selectors
    "detail_sku": ".sku, [data-sku], div:contains('SKU:')",
    "detail_brand": "div.brand, a[href*='/catalog/?brand=']",
    "detail_category": "nav.brc, div.brc, ol.brc",
    "detail_availability": "p.-df.-i-ctr.-pts, div[class*='stock'], span[class*='stock']",
    "detail_seller": "section.seller-info, div.seller-name, a[href*='/seller/']",
    "detail_main_image": "img.sld-img, img[data-zoom]",

    # Delivery zone selectors
    "delivery_governorates": "select#delivery-governorate option, select[name*='governorate'] option",
}

# Disallowed paths from Jumia's robots.txt
DISALLOWED_PATH_PATTERNS = [
    r"^/cart/",
    r"^/customer/",
    r"^/wishlist/",
    r"^/checkout/",
    r"\?.*(color|price|ram|size)=",
]

# Standard Egyptian Governorates covered by Jumia Delivery
ALL_EGYPT_GOVERNORATES = [
    "Cairo", "Giza", "Alexandria", "Qalyubia", "Sharqia", "Dakahlia",
    "Monufia", "Gharbia", "Kafr El Sheikh", "Beheira", "Damietta",
    "Port Said", "Ismailia", "Suez", "North Sinai", "South Sinai",
    "Beni Suef", "Fayoum", "Minya", "Asyut", "Sohag", "Qena",
    "Luxor", "Aswan", "Red Sea", "New Valley", "Matrouh"
]
