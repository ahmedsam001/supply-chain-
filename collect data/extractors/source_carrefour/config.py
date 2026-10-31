"""
Carrefour Egypt Extractor Configuration
========================================
High-yield department & category endpoints for Carrefour Egypt (MAF).
"""

BASE_URL = "https://www.carrefouregypt.com"

# Department-partitioned verified category listing URLs
DEPARTMENT_URLS: dict[str, dict[str, str]] = {
    "grocery_pantry": {
        "food_cupboard": "/mafegy/en/c/FEGY1000000",
        "cooking_ingredients": "/mafegy/en/n/c/clp_cooking-ingredients",
    },
    "beverages": {
        "beverages": "/mafegy/en/c/FEGY1500000",
        "beverages_circular": "/mafegy/en/n/c/clp_beverages-circular-icon",
    },
    "fresh_meats_poultry": {
        "meats_poultry": "/mafegy/en/n/c/clp_protein-lovers",
        "fresh_meats": "/mafegy/en/c/FEGY1610000",
    },
    "dairy_cheese_eggs": {
        "dairy_eggs": "/mafegy/en/c/FEGY1660000",
        "milk_dairy": "/mafegy/en/n/c/clp_milk-dairy",
    },
    "fruits_vegetables": {
        "fruits_vegetables": "/mafegy/en/c/FEGY1600000",
    },
    "frozen_foods": {
        "frozen_foods": "/mafegy/en/c/FEGY6000000",
    },
    "household_cleaning": {
        "laundry_detergents": "/mafegy/en/n/c/clp_NFEGY3080000",
        "tissues": "/mafegy/en/n/c/clp_NFEGY3090000",
    },
    "personal_care_beauty": {
        "beauty_personal_care": "/mafegy/en/c/NFEGY2000000",
    },
    "electronics_tv": {
        "tvs": "/mafegy/en/n/c/clp_shop-tvs",
        "electronics": "/mafegy/en/c/NFEGY4000000",
    },
    "mobiles_tablets": {
        "smartphones_accessories": "/mafegy/en/c/NFEGY1200000",
    },
    "home_appliances": {
        "appliances": "/mafegy/en/n/c/clp_Appliances-offer",
    },
    "bakery_snacks": {
        "snacks_chocolates": "/mafegy/en/n/c/clp_FEGY1740000",
    },
    "baby_products": {
        "baby_products": "/mafegy/en/n/c/clp_FEGY1000000",
    },
    "pet_supplies": {
        "pet_food_care": "/mafegy/en/c/FEGY1100000",
    },
    "bio_organic": {
        "bio_organic": "/mafegy/en/c/FEGY1200000",
    },
}

CATEGORY_URLS = {
    cat_key: cat_path
    for dept_map in DEPARTMENT_URLS.values()
    for cat_key, cat_path in dept_map.items()
}

STORE_LOCATOR_URL = "https://www.carrefouregypt.com/mafegy/en/n/c/clp_carrefour-store-finder-egypt"

MAX_REQUESTS_PER_MINUTE = 20
MIN_DELAY_SECONDS = 2.0
MAX_DELAY_SECONDS = 4.0

PRODUCTS_PER_PAGE = 24
MAX_PAGES_PER_CATEGORY = 10

SELECTORS = {
    "product_card": "div.group",
    "product_link": "a[href*='/p/']",
    "product_name": "a[href*='/p/']",
    "current_price": "div",
    "old_price": "del, s, span",
    "image": "img",
    "brand": "span, p",
}

# 19 Egyptian Governorates where Carrefour stores/delivery operate
CARREFOUR_EGYPT_GOVERNORATES = [
    "Cairo", "Giza", "Alexandria", "Qalyubia", "Sharqia", "Dakahlia",
    "Gharbia", "Monufia", "Beheira", "Kafr El Sheikh", "Damietta",
    "Port Said", "Ismailia", "Suez", "Beni Suef", "Fayoum",
    "Minya", "Asyut", "Red Sea"
]
