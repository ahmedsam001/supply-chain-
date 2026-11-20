"""
2B Egypt Extractor Configuration

2B is a major Egyptian electronics retailer using Magento 2.
Compliance: B (Conditional) — enabled for controlled prototype extraction
(LIVE_PENDING_HUMAN_TOS_CONFIRMATION for commercial production sign-off).
Method: static_html with JSON-LD extraction.
"""

BASE_URL = "https://2b.com.eg"

DEPARTMENT_URLS: dict[str, dict[str, str]] = {
    "mobiles_tablets": {
        "mobiles":          "/en/mobile-and-tablet/mobiles.html",
        "mobiles-samsung":  "/en/mobile-and-tablet/mobiles/samsung.html",
        "mobiles-apple":    "/en/mobile-and-tablet/mobiles/apple.html",
        "mobiles-honor":    "/en/mobile-and-tablet/mobiles/honor.html",
        "mobiles-xiaomi":   "/en/mobile-and-tablet/mobiles/xaiomi.html",
        "mobiles-oppo":     "/en/mobile-and-tablet/mobiles/oppo.html",
        "mobiles-realme":   "/en/mobile-and-tablet/mobiles/realme.html",
        "mobiles-vivo":     "/en/mobile-and-tablet/mobiles/vivo.html",
        "mobiles-infinix":  "/en/mobile-and-tablet/mobiles/infinix.html",
        "mobiles-hmd":      "/en/mobile-and-tablet/mobiles/hmd.html",
        "mobiles-huawei":   "/en/mobile-and-tablet/mobiles/huawei.html",
        "mobiles-tecno":    "/en/mobile-and-tablet/mobiles/tecno.html",
        "mobiles-itel":     "/en/mobile-and-tablet/mobiles/itel.html",
        "mobiles-nothing":  "/en/mobile-and-tablet/mobiles/nothing.html",
        "mobiles-other":    "/en/mobile-and-tablet/mobiles/other.html",
        "tablets":          "/en/mobile-and-tablet/mobile-tablet.html",
        "landline-phones":  "/en/mobile-and-tablet/landline-phones.html",
    },
    "computing": {
        "laptops":          "/en/computers/laptops.html",
        "computers":        "/en/computers.html",
    },
    "electronics_tv": {
        "televisions":      "/en/televisions/tvs.html",
        "gaming":           "/en/gaming.html",
    },
    "home_appliances": {
        "home-appliances":  "/en/home-appliances.html",
    },
}

CATEGORY_URLS = {
    cat_key: cat_path
    for dept_map in DEPARTMENT_URLS.values()
    for cat_key, cat_path in dept_map.items()
}

PHONE_CATEGORIES = list(DEPARTMENT_URLS["mobiles_tablets"].keys())

STORE_LOCATOR_PATH = "/en/stores"
STORE_LOCATOR_BLOCK_PATH = "/en/store_locator/location/updatemainpage"

MAX_REQUESTS_PER_MINUTE = 6
MIN_DELAY_SECONDS = 10.0
MAX_DELAY_SECONDS = 12.0
MAX_PAGES_PER_CATEGORY = 30  # full sweep

COMPLIANCE_NOTE = (
    "Compliance class B (Conditional) / LIVE_PENDING_HUMAN_TOS_CONFIRMATION. "
    "robots.txt permits crawling of catalog and store pages with Crawl-delay: 10. "
    "Terms & Conditions (https://2b.com.eg/en/terms-and-conditions) grant a personal "
    "shopping license and require prior permission for commercial use. "
    "Respect 10s rate limits. Avoid faceted filter URLs (Disallow: /*?*). "
    "No headless browser evasion."
)
