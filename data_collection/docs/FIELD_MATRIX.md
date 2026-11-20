# Canonical Field Exposure & Extraction Matrix (2026-09-28)

Every canonical field across the 6 implemented source connectors is classified with one of three strict states:

- **`EXTRACTED`** (`EXPOSED`): Publicly exposed on the inspected surface and extracted into canonical models.
- **`NOT_EXPOSED`**: Absent from the public surface; preserved as `null` (`None`) without fabrication.
- **`BLOCKED`**: Exists only behind a surface prohibited by `robots.txt` (e.g. Jumia `/mobapi/`), anti-bot protection, or session/checkout walls.

---

## 1. Product Identity & Catalog Fields (`Product`)

| Canonical Field | `jumia` (Live Pending Human ToS) | `two_b` (Live Pending Human ToS) | `carrefour` (Offline Fixture) | `tradeline` (Offline Fixture) | `dream2000` (Offline Fixture) | `raya` (Synthetic Only) | Evidence Reference |
|---|---|---|---|---|---|---|---|
| `source_product_id` | `EXTRACTED` (URL numeric ID / `data-gtm-id`) | `EXTRACTED` (`data-product-id` on card) | `EXTRACTED` (card ID / URL slug) | `EXTRACTED` (Shopify `product.id`) | `EXTRACTED` (Shopify `product.id`) | `EXTRACTED` (`data-product-id`) | `tests/fixtures/*/real/` |
| `sku` | `EXTRACTED` (`data-gtm-id` on card; JSON-LD `sku` on PDP) | `NOT_EXPOSED` on category card (`null`); `EXTRACTED` on PDP (`div.product.attribute.sku` / JSON-LD `sku`) | `EXTRACTED` (when present) / `NOT_EXPOSED` (`null`) | `EXTRACTED` (`variants[0].sku`) | `EXTRACTED` (`variants[0].sku`) | `EXTRACTED` (JSON-LD `sku`) | `tests/fixtures/jumia/real/pdp_sample.html`, `tests/fixtures/two_b/real/pdp_sample.html` |
| `gtin` | `NOT_EXPOSED` on category card (`null`); `EXTRACTED` on PDP when `gtin13`/`gtin12` populated in JSON-LD | `NOT_EXPOSED` (`null` on both category and PDP) | `NOT_EXPOSED` (`null`) | `NOT_EXPOSED` (`null` in sample) | `NOT_EXPOSED` (`null`) | `NOT_EXPOSED` (`null`) | Missing `gtin` emits `DataQualityIssue(MISSING_FIELD)` |
| `product_name` | `EXTRACTED` (`h3.name` / JSON-LD `name`) | `EXTRACTED` (`a.product-item-link` / `h1.page-title`) | `EXTRACTED` | `EXTRACTED` (Shopify `title`) | `EXTRACTED` (Shopify `title`) | `EXTRACTED` | All fixtures |
| `brand` | `EXTRACTED` (`data-gtm-brand` / JSON-LD `brand.name` / title prefix) | `EXTRACTED` (PDP spec table / JSON-LD / title prefix) | `EXTRACTED` | `EXTRACTED` (Shopify `vendor`) | `EXTRACTED` (Shopify `vendor`) | `EXTRACTED` (JSON-LD `brand.name`) | All fixtures |
| `category` | `EXTRACTED` (`data-gtm-category` root / breadcrumb) | `EXTRACTED` (category page context / PDP `.breadcrumbs`) | `EXTRACTED` | `EXTRACTED` (Shopify `product_type`) | `EXTRACTED` (Shopify `product_type`) | `EXTRACTED` (JSON-LD `category`) | `tests/fixtures/two_b/real/pdp_sample.html` |
| `subcategory` | `EXTRACTED` (`data-gtm-category` leaf / PDP breadcrumb) | `EXTRACTED` (PDP `.breadcrumbs`) | `NOT_EXPOSED` | `NOT_EXPOSED` | `NOT_EXPOSED` | `NOT_EXPOSED` | `tests/fixtures/jumia/real/pdp_sample.html` |
| `raw_category_path` | `EXTRACTED` (` > ` breadcrumb path) | `EXTRACTED` (PDP `.breadcrumbs` path) | `NOT_EXPOSED` | `NOT_EXPOSED` | `NOT_EXPOSED` | `NOT_EXPOSED` | `tests/fixtures/jumia/real/pdp_sample.html` |
| `product_url` | `EXTRACTED` | `EXTRACTED` | `EXTRACTED` | `EXTRACTED` (`/products/<handle>`) | `EXTRACTED` (`/products/<handle>`) | `EXTRACTED` | All fixtures |
| `source_url` | `EXTRACTED` | `EXTRACTED` | `EXTRACTED` | `EXTRACTED` | `EXTRACTED` | `EXTRACTED` | Populated on every `Product` |
| `image_url` | `EXTRACTED` (`data-src` / `src`) | `EXTRACTED` (`img.product-image-photo`) | `EXTRACTED` | `EXTRACTED` (`images[0].src`) | `EXTRACTED` (`images[0].src`) | `EXTRACTED` | All fixtures |
| `variants` | `NOT_EXPOSED` on listing | `NOT_EXPOSED` on listing | `NOT_EXPOSED` | `EXTRACTED` (Shopify `variants[]`) | `EXTRACTED` (Shopify `variants[]`) | `NOT_EXPOSED` | `tradeline_products_sample.json` |
| `specifications` | `EXTRACTED` (PDP key-value specs) | `EXTRACTED` (PDP attributes table when parsed) | `NOT_EXPOSED` | `NOT_EXPOSED` | `NOT_EXPOSED` | `NOT_EXPOSED` | `jumia_pdp_sample.html` |
| `collected_at` | `EXTRACTED` (UTC ISO-8601) | `EXTRACTED` (UTC ISO-8601) | `EXTRACTED` | `EXTRACTED` | `EXTRACTED` | `EXTRACTED` | All connectors |

---

## 2. Commercial, Seller, Delivery & Observation Fields (`ProductObservation`)

| Canonical Field | `jumia` (Live Pending Human ToS) | `two_b` (Live Pending Human ToS) | `carrefour` (Offline Fixture) | `tradeline` (Offline Fixture) | `dream2000` (Offline Fixture) | `raya` (Synthetic Only) | Evidence Reference |
|---|---|---|---|---|---|---|---|
| `price` | `EXTRACTED` (`div.prc`) | `EXTRACTED` (`.special-price .price` / `[data-price-type='finalPrice']`) | `EXTRACTED` | `EXTRACTED` (`variants[0].price`) | `EXTRACTED` (`variants[0].price`) | `EXTRACTED` | All fixtures & live captures |
| `old_price` | `EXTRACTED` (`div.old`) | `EXTRACTED` (`.old-price .price`) | `EXTRACTED` | `EXTRACTED` (`compare_at_price`) | `EXTRACTED` (`compare_at_price`) | `EXTRACTED` (`.old-price`) | All fixtures |
| `discount` | `EXTRACTED` (`div.bdg._dsct`) | `EXTRACTED` (computed when `old_price > price`) | `EXTRACTED` | `EXTRACTED` (computed) | `EXTRACTED` (computed) | `EXTRACTED` (computed) | `tests/fixtures/two_b/real/category_sample.html` |
| `raw_price_text` | `EXTRACTED` (exact EGP string) | `EXTRACTED` (exact EGP string) | `EXTRACTED` | `EXTRACTED` | `EXTRACTED` | `EXTRACTED` | Preserved before float parsing |
| `currency` | `EXTRACTED` (`EGP`) | `EXTRACTED` (`EGP`) | `EXTRACTED` (`EGP`) | `EXTRACTED` (`EGP`) | `EXTRACTED` (`EGP`) | `EXTRACTED` (`EGP`) | All sources |
| `availability_status` | `EXTRACTED` (`in_stock` / `out_of_stock` / `limited_stock`) | `EXTRACTED` (`in_stock` / `out_of_stock` / `limited_stock`) | `EXTRACTED` | `EXTRACTED` (`variant.available`) | `EXTRACTED` (`variant.available`) | `EXTRACTED` | All sources |
| `availability_scope` | `EXTRACTED` (`GLOBAL` / `DELIVERY_AREA`) | `EXTRACTED` (`DELIVERY_AREA` / `PHYSICAL_BRANCH`) | `EXTRACTED` (`GLOBAL`) | `EXTRACTED` (`GLOBAL`) | `EXTRACTED` (`GLOBAL`) | `EXTRACTED` (`PHYSICAL_BRANCH` / `DELIVERY_AREA`) | `docs/AVAILABILITY_SEMANTICS.md` |
| `stock_status` | `EXTRACTED` (`IN_STOCK` / `LOW_STOCK_SIGNAL` / `OUT_OF_STOCK`) | `EXTRACTED` (`IN_STOCK` / `AVAILABLE_IN_STORES`) | `EXTRACTED` (`IN_STOCK` / `LOW_STOCK_SIGNAL`) | `EXTRACTED` (`IN_STOCK` / `OUT_OF_STOCK`) | `EXTRACTED` (`IN_STOCK` / `OUT_OF_STOCK`) | `EXTRACTED` (`PICKUP_AVAILABLE` / `IN_STOCK`) | All connectors |
| `stock_quantity` | **`NOT_EXPOSED`** (`null`) | **`NOT_EXPOSED`** (`null`) | **`NOT_EXPOSED`** (`null`) | **`NOT_EXPOSED`** (`null`) | **`NOT_EXPOSED`** (`null`) | **`NOT_EXPOSED`** (`null`) | Never fabricated from `'Only N left'` |
| `stock_quantity_evidence` | **`NOT_EXPOSED`** (`null`) | **`NOT_EXPOSED`** (`null`) | **`NOT_EXPOSED`** (`null`) | **`NOT_EXPOSED`** (`null`) | **`NOT_EXPOSED`** (`null`) | **`NOT_EXPOSED`** (`null`) | Required if `stock_quantity` ever set |
| `raw_availability_text` | `EXTRACTED` | `EXTRACTED` | `EXTRACTED` (`'Only 3 left!'` preserved) | `EXTRACTED` | `EXTRACTED` | `EXTRACTED` (`'Pickup from Store'`) | `carrefour_sample.html` |
| `seller_name` | `NOT_EXPOSED` on category card (`null`); `EXTRACTED` on PDP (`offers.seller.name` / seller block) | `NOT_EXPOSED` (`null`, 1P retailer) | `NOT_EXPOSED` (`null`, 1P retailer) | `NOT_EXPOSED` (`null`, 1P retailer) | `NOT_EXPOSED` (`null`, 1P retailer) | `NOT_EXPOSED` (`null`, 1P retailer) | Missing `seller_name` emits `DataQualityIssue(MISSING_FIELD)` |
| `fulfillment_method` | `EXTRACTED` (`marketplace`) | `EXTRACTED` (`retailer`) | `EXTRACTED` (`retailer`) | `EXTRACTED` (`retailer`) | `EXTRACTED` (`retailer`) | `EXTRACTED` (`retailer`) | All connectors |
| `delivery_available` | `NOT_EXPOSED` on category card (`null`); `EXTRACTED` on PDP (`true` when delivery promise block present) | `NOT_EXPOSED` on category card (`null`); `EXTRACTED` on PDP (`true` when Estimated Delivery block present) | `NOT_EXPOSED` | `NOT_EXPOSED` | `NOT_EXPOSED` | `NOT_EXPOSED` | `tests/fixtures/jumia/real/pdp_sample.html`, `tests/fixtures/two_b/real/pdp_sample.html` |
| `delivery_eta` | `NOT_EXPOSED` on category card (`null`); `EXTRACTED` on PDP (default Cairo/Giza promise text, e.g. `'Ready for delivery on 30 September...'`); multi-city dynamic ETA via `/mobapi/` is **`BLOCKED`** by `robots.txt` | `NOT_EXPOSED` on category card (`null`); `EXTRACTED` on PDP (`'Estimated Delivery Date Within 1-5 working days'`) | `NOT_EXPOSED` | `NOT_EXPOSED` | `NOT_EXPOSED` | `NOT_EXPOSED` | `tests/fixtures/jumia/real/pdp_sample.html`, `tests/fixtures/two_b/real/pdp_sample.html` |
| `delivery_fee` | `NOT_EXPOSED` on category card (`null`); `EXTRACTED` on PDP (`35.0` from `'Delivery fees EGP 35.00'` or `0.0` from `'Free delivery'`); multi-city dynamic fee via `/mobapi/` is **`BLOCKED`** by `robots.txt` | `NOT_EXPOSED` (`null`; calculated only in checkout shipping estimator) | `NOT_EXPOSED` | `NOT_EXPOSED` | `NOT_EXPOSED` | `NOT_EXPOSED` | `data/raw/jumia/pdp_sample_2026-09-28.html`, `tests/fixtures/jumia/real/pdp_sample.html` |
| `rating` | `EXTRACTED` (`div.stars._s`) | `NOT_EXPOSED` | `NOT_EXPOSED` | `NOT_EXPOSED` | `NOT_EXPOSED` | `NOT_EXPOSED` | `jumia_sample.html` |
| `review_count` | `EXTRACTED` (`div.rev`) | `NOT_EXPOSED` | `NOT_EXPOSED` | `NOT_EXPOSED` | `NOT_EXPOSED` | `NOT_EXPOSED` | `jumia_sample.html` |
| `row_hash` | `EXTRACTED` (SHA-256 v2) | `EXTRACTED` (SHA-256 v2) | `EXTRACTED` (SHA-256 v2) | `EXTRACTED` (SHA-256 v2) | `EXTRACTED` (SHA-256 v2) | `EXTRACTED` (SHA-256 v2) | `ProductObservation.compute_row_hash()` |

---

## 3. Geographic & Location Fields (`Location`)

| Canonical Field | `jumia` (Live Pending Human ToS) | `two_b` (Live Pending Human ToS) | `carrefour` (Offline Fixture) | `tradeline` (Offline Fixture) | `dream2000` (Offline Fixture) | `raya` (Synthetic Only) | Evidence Reference |
|---|---|---|---|---|---|---|---|
| `location_id` | `EXTRACTED` (deterministic hash) | `EXTRACTED` (deterministic hash) | `EXTRACTED` (deterministic hash) | `EXTRACTED` (deterministic hash) | `NOT_EXPOSED` | `NOT_EXPOSED` | `geospatial.egypt_geography.derive_location_id` |
| `location_type` | `EXTRACTED` (`delivery_zone` / `delivery_area`) | `EXTRACTED` (`branch` — 59 physical branches from `/en/stores`) | `EXTRACTED` (`presence` for 19 governorate presence records; `branch` when real store cards parsed) | `EXTRACTED` (`store` — 30 branches) | `NOT_EXPOSED` | `NOT_EXPOSED` | `normalization/schema.py` |
| `branch_name` | `NOT_EXPOSED` (`null`, delivery zone only) | `EXTRACTED` (`section.mw-sl__stores__list__item` — 59 named branches) | `NOT_EXPOSED` (`null` on governorate `presence` records; `raw_location_name` preserved) | `EXTRACTED` (`data-name` — 30 branches) | `NOT_EXPOSED` | `NOT_EXPOSED` | `tests/fixtures/two_b/real/stores_sample.html`, `tradeline_locator_sample.html` |
| `raw_location_name` | `EXTRACTED` (`'<Gov> Delivery Zone'`) | `EXTRACTED` (exact raw branch name from 2B HTML) | `EXTRACTED` (`'Carrefour Egypt — <Gov> Governorate Presence'`) | `EXTRACTED` | `NOT_EXPOSED` | `NOT_EXPOSED` | Preserved on all location records |
| `address` | `NOT_EXPOSED` (`null`, delivery zone only) | `EXTRACTED` (street address from `<address class="mw-sl__stores__details__address">` for all 59 branches) | `NOT_EXPOSED` (`null` on governorate `presence` records) | `EXTRACTED` (`.apl-section-stores-locator-store-address-1`) | `NOT_EXPOSED` | `NOT_EXPOSED` | `tests/fixtures/two_b/real/stores_sample.html` |
| `city` | `NOT_EXPOSED` (governorate level) | `EXTRACTED` (normalized city/district for 58 of 59 branches; `2B - Aswan` has `city=null` and emits `INCONSISTENT_LOCATION_NAME`) | `EXTRACTED` (19 governorate capitals/names) | `EXTRACTED` (normalized from address) | `NOT_EXPOSED` | `NOT_EXPOSED` | `geospatial/egypt_geography.py` |
| `governorate` | `EXTRACTED` (27 delivery governorates) | `EXTRACTED` (14 verified governorates across 59 branches) | `EXTRACTED` (19 governorates) | `EXTRACTED` (8 verified governorates across 30 branches) | `NOT_EXPOSED` | `NOT_EXPOSED` | `samples/*/locations.json` |
| `latitude` / `longitude` | `NOT_EXPOSED` (`null`) | `EXTRACTED` (MageWorx `locations['id']` JS markers & Google Maps `destination=lat,lng` for all 59 branches; 58 valid Egypt coordinates, 1 raw source error `Assiut lat=90.0` flagged as `OUT_OF_EGYPT_COORDINATES`) | `NOT_EXPOSED` (`null` on governorate `presence` records) | `EXTRACTED` (`data-latitude`, `data-longitude` for 30 branches) | `NOT_EXPOSED` | `NOT_EXPOSED` | `tests/fixtures/two_b/real/stores_sample.html` |
| `phone` | `NOT_EXPOSED` (`null`) | `EXTRACTED` (`16420` hotline on all 59 branches) | `NOT_EXPOSED` | `EXTRACTED` (`19857`) | `NOT_EXPOSED` | `NOT_EXPOSED` | `tests/fixtures/two_b/real/stores_sample.html` |
| `working_hours` | `NOT_EXPOSED` (`null`) | `EXTRACTED` (`div.mw-sl__stores__details__hours` table for all 59 branches) | `NOT_EXPOSED` | `EXTRACTED` | `NOT_EXPOSED` | `NOT_EXPOSED` | `tests/fixtures/two_b/real/stores_sample.html` |
| `source_url` | `EXTRACTED` | `EXTRACTED` (`https://2b.com.eg/en/stores`) | `EXTRACTED` (`https://www.carrefouregypt.com/mafegy/en/store-finder`) | `EXTRACTED` | `NOT_EXPOSED` | `NOT_EXPOSED` | All location extractors |
| `warehouse_name` / `warehouse_data` | **`NOT_EXPOSED`** | **`NOT_EXPOSED`** | **`NOT_EXPOSED`** | **`NOT_EXPOSED`** | **`NOT_EXPOSED`** | **`NOT_EXPOSED`** | No Egyptian source exposes warehouse stock publicly |
