# Egypt-Wide E-Commerce Data Platform — Data Collection Status Report

- **Audit Date:** `2026-09-28`
- **Phase Status:** **`MOSTLY COMPLETE`**
- **Why Capped at `MOSTLY COMPLETE`:**
  1. The two live-validated connectors (`jumia` and `two_b`) are technically verified end-to-end with raw snapshots, SHA-256 verification, and live-to-live repeatability proofs, but their retrieved Terms of Use require human legal sign-off (`LIVE PENDING HUMAN TOS CONFIRMATION`) before ongoing or commercial scraping (`robots.txt` does NOT override Terms of Service).
  2. Three implemented connectors (`carrefour`, `tradeline`, `dream2000`) operate in `offline_fixture` mode pending human ToS sign-off (`HUMAN SIGN-OFF REQUIRED`).
  3. One implemented connector (`raya`) operates in `synthetic` mode because its live surface is behind a Cloudflare challenge.
  4. Three sources (`btech`, `noon`, `amazon_eg`) are `BLOCKED` (Class C) by explicit anti-scraping Terms of Use, and the remaining 12 candidate sources are `DEFERRED` (`RESEARCH REQUIRED`).

---

## 1. Complete 21-Source Implementation & Compliance Table

| Source ID | Name | Class | `enabled` | Run Mode | Implementation Status | Robots Status | ToS Status | Authorization Status |
|-----------|------|-------|-----------|----------|-----------------------|---------------|------------|----------------------|
| `jumia` | Jumia Egypt | `B` | `true` | `live` | `LIVE VALIDATED` | `ROBOTS VERIFIED` | `TOS RETRIEVED AND READ` | `LIVE PENDING HUMAN TOS CONFIRMATION` |
| `carrefour` | Carrefour Egypt | `D` | `false` | `offline_fixture` | `OFFLINE FIXTURE ONLY` | `ROBOTS VERIFIED` | `TOS NOT RETRIEVED` | `HUMAN SIGN-OFF REQUIRED` |
| `btech` | B.TECH | `C` | `false` | `none` | `BLOCKED` | `ROBOTS VERIFIED` | `TOS RETRIEVED AND READ` | `BLOCKED (PROHIBITED BY TOS)` |
| `two_b` | 2B Egypt | `B` | `true` | `live` | `LIVE VALIDATED` | `ROBOTS VERIFIED` | `TOS RETRIEVED AND READ` | `LIVE PENDING HUMAN TOS CONFIRMATION` |
| `tradeline` | Tradeline Stores | `D` | `false` | `offline_fixture` | `OFFLINE FIXTURE ONLY` | `ROBOTS VERIFIED` | `TOS NOT RETRIEVED` | `HUMAN SIGN-OFF REQUIRED` |
| `dream2000` | Dream 2000 | `D` | `false` | `offline_fixture` | `OFFLINE FIXTURE ONLY` | `ROBOTS VERIFIED` | `TOS NOT RETRIEVED` | `HUMAN SIGN-OFF REQUIRED` |
| `raya` | Raya Shop | `D` | `false` | `synthetic` | `SYNTHETIC ONLY` | `ROBOTS VERIFIED` | `TOS NOT RETRIEVED` | `HUMAN SIGN-OFF REQUIRED` |
| `noon` | Noon Egypt | `D` | `false` | `none` | `BLOCKED` | `ROBOTS VERIFIED` | `TOS NOT RETRIEVED` | `HUMAN SIGN-OFF REQUIRED` |
| `spinneys` | Spinneys Egypt | `D` | `false` | `none` | `RESEARCH REQUIRED` | `ROBOTS VERIFIED` | `TOS NOT RETRIEVED` | `HUMAN SIGN-OFF REQUIRED` |
| `samsung_eg` | Samsung Egypt | `D` | `false` | `none` | `RESEARCH REQUIRED` | `ROBOTS VERIFIED` | `TOS NOT RETRIEVED` | `HUMAN SIGN-OFF REQUIRED` |
| `orange_eg` | Orange Egypt | `D` | `false` | `none` | `RESEARCH REQUIRED` | `ASSUMED / UNVERIFIED` | `TOS NOT RETRIEVED` | `HUMAN SIGN-OFF REQUIRED` |
| `vodafone_eg` | Vodafone Egypt | `D` | `false` | `none` | `RESEARCH REQUIRED` | `ROBOTS VERIFIED` | `TOS NOT RETRIEVED` | `HUMAN SIGN-OFF REQUIRED` |
| `we_eg` | WE / Telecom Egypt | `D` | `false` | `none` | `RESEARCH REQUIRED` | `ROBOTS VERIFIED` | `TOS NOT RETRIEVED` | `HUMAN SIGN-OFF REQUIRED` |
| `eand_eg` | e& Egypt | `D` | `false` | `none` | `RESEARCH REQUIRED` | `ROBOTS VERIFIED` | `TOS NOT RETRIEVED` | `HUMAN SIGN-OFF REQUIRED` |
| `metro` | Metro Markets | `D` | `false` | `none` | `RESEARCH REQUIRED` | `ROBOTS VERIFIED` | `TOS NOT RETRIEVED` | `HUMAN SIGN-OFF REQUIRED` |
| `hyperone` | Hyper One | `D` | `false` | `none` | `RESEARCH REQUIRED` | `ASSUMED / UNVERIFIED` | `TOS NOT RETRIEVED` | `HUMAN SIGN-OFF REQUIRED` |
| `elaraby` | Elaraby Group | `D` | `false` | `none` | `RESEARCH REQUIRED` | `ROBOTS VERIFIED` | `TOS NOT RETRIEVED` | `HUMAN SIGN-OFF REQUIRED` |
| `amazon_eg` | Amazon Egypt | `C` | `false` | `none` | `BLOCKED` | `ROBOTS VERIFIED` | `TOS RETRIEVED AND READ` | `BLOCKED (PROHIBITED BY TOS)` |
| `talabat` | Talabat Mart / Talabat Egypt | `D` | `false` | `none` | `RESEARCH REQUIRED` | `ROBOTS VERIFIED` | `TOS NOT RETRIEVED` | `HUMAN SIGN-OFF REQUIRED` |
| `instashop` | InstaShop Egypt | `D` | `false` | `none` | `RESEARCH REQUIRED` | `ROBOTS VERIFIED` | `TOS NOT RETRIEVED` | `HUMAN SIGN-OFF REQUIRED` |
| `lulu` | Lulu Hypermarket Egypt | `D` | `false` | `none` | `RESEARCH REQUIRED` | `ASSUMED / UNVERIFIED` | `TOS NOT RETRIEVED` | `HUMAN SIGN-OFF REQUIRED` |

---

## 2. 2B Store Locator (`https://2b.com.eg/en/stores`) — Real Live Collection

- **Public Surface Inspected:** `https://2b.com.eg/en/stores` and its embedded public MageWorx StoreLocator HTML block (`https://2b.com.eg/en/store_locator/location/updatemainpage`), permitted by `https://2b.com.eg/robots.txt` with `Crawl-delay: 10`.
- **Raw Snapshots Saved:** `data/raw/two_b/stores_2026-09-28.html` and `data/raw/two_b/stores_updatemainpage_2026-09-28.html`.
- **Sanitized Real Fixture:** `tests/fixtures/two_b/real/stores_sample.html`.
- **Extracted Records (`samples/two_b/locations.json`):**
  - **59 physical branches** (`LocationType.BRANCH`) across **14 Egyptian governorates** (`Cairo`, `Giza`, `Alexandria`, `Qalyubia`, `Gharbia`, `Dakahlia`, `Sharqia`, `Beheira`, `Monufia`, `Port Said`, `Suez`, `Beni Suef`, `Asyut`, `Aswan`, `Red Sea`, `Matrouh`).
  - Every branch includes `branch_name`, `raw_location_name`, `address`, `phone` (`16420`), `working_hours`, `source_url` (`https://2b.com.eg/en/stores`), and `latitude`/`longitude` from MageWorx `locations['id']` / Google Maps `destination=` coordinates.
  - **Raw Coordinate Fidelity & Validation:** 58 of 59 branches have valid Egypt GPS coordinates (`22.0 <= lat <= 31.8`, `24.5 <= lon <= 37.0`). One branch (`Assiut`) has a raw data-entry error in 2B's HTML (`latitude=90.0, longitude=31.1859722`), which is preserved without fabrication and flagged by `DataValidator` as `OUT_OF_EGYPT_COORDINATES` (`high` severity).

---

## 3. Actual 2B Product Scraper & Pagination (`extractors/source_2b/`)

- **Category & PDP Extraction:** Parses live Magento 2 category pages (`li.product-item`) and PDPs (`div.product.attribute.sku`, `.breadcrumbs`, `.special-price .price`, `.old-price .price`, delivery ETA).
- **Pagination Support:** `extract_next_page_url()` parses `a.action.next` pagination links and `TwoBExtractor.extract_products()` traverses pages up to `MAX_PAGES_PER_CATEGORY` while enforcing the 10-second `Crawl-delay` (`<=6 RPM`).
- **No Fabricated Identifiers:** Category cards on 2B expose `data-product-id` (`source_product_id`) but do not expose `sku` or `gtin`; both remain `null` (`None`) on category cards and emit honest `MISSING_SKU` / `MISSING_FIELD` quality issues. On PDPs (`tests/fixtures/two_b/real/pdp_sample.html`), explicit `sku` (`ZH669`) and breadcrumb `category` (`Computer > Laptops > HP > Gaming Laptops`) are extracted.

---

## 4. Jumia Public Terms of Use & Authorization Assessment

- **Retrieved Public Terms:**
  - Wrapper page: `https://www.jumia.com.eg/terms-of-use/?internal=footer` (`data/raw/jumia/terms_2026-09-28.html`)
  - Embedded Terms content: `https://www.jumia.com.eg/fragment/contents/sp-terms-of-use/?lang=en` (`data/raw/jumia/terms_fragment_2026-09-28.html`)
- **Key Clauses:**
  - **Section 10.9.9:** Prohibits conducting *"any systematic or automated data collection activities (including without limitation scraping, data mining, data extraction and data harvesting) on or in relation to our website without our express written consent"*.
  - **Section 10.9.10:** Prohibits accessing or interacting with the website using any robot, spider, or other automated means except for search engine indexing.
- **Assessment:** While `https://www.jumia.com.eg/robots.txt` permits public HTML requests under 200 RPM (and disallows `/mobapi/`), `robots.txt` does **not** override the Terms of Use. Jumia is therefore classified as `LIVE PENDING HUMAN TOS CONFIRMATION` (`LIVE_PENDING_HUMAN_AUTHORIZATION`).

---

## 5. Delivery Data Exposure (`jumia` & `two_b`)

| Source | Surface | `delivery_available` | `delivery_eta` | `delivery_fee` | Notes |
|--------|---------|----------------------|----------------|----------------|-------|
| `jumia` | Category Listing | `NOT_EXPOSED` (`null`) | `NOT_EXPOSED` (`null`) | `NOT_EXPOSED` (`null`) | Category cards only show `Jumia Express` badge |
| `jumia` | Public PDP (`pdp_sample.html`) | `EXTRACTED` (`true`) | `EXTRACTED` (`Ready for delivery on 30 September...`) | `EXTRACTED` (`0.0` Free delivery / `35.0` EGP) | Default Cairo/Giza session; dynamic multi-city API `/mobapi/` is `BLOCKED` by `robots.txt` |
| `two_b` | Category Listing | `NOT_EXPOSED` (`null`) | `NOT_EXPOSED` (`null`) | `NOT_EXPOSED` (`null`) | Category cards only show `In Stock` / `Available in Stores` |
| `two_b` | Public PDP (`pdp_sample.html`) | `EXTRACTED` (`true`) | `EXTRACTED` (`Estimated Delivery Date Within 1-5 working days`) | `NOT_EXPOSED` (`null`) | Shipping fee calculated only at checkout |

---

## 6. Repeatability Proof — Two Live Runs on Persisted Watchlist (`watchlist_v1`)

- **Watchlist File:** `config/watchlist.json` (`watchlist_id: "watchlist_v1"`)
- **Live Run #1:** `live_repeat_run_1` (`jumia` at `2026-09-28T16:12:42Z`, `two_b` at `2026-09-28T16:12:56Z`)
- **Live Run #2:** `live_repeat_run_2` (`jumia` at `2026-09-28T16:13:51Z`, `two_b` at `2026-09-28T16:14:05Z`, after respecting rate limits)
- **Live-to-Live Diff Report (`data/manifests/live_repeatability_diff.json`):**

| Metric | `jumia` (`live_repeat_run_1` vs `live_repeat_run_2`) | `two_b` (`live_repeat_run_1` vs `live_repeat_run_2`) |
|--------|-----------------------------------------------------|-----------------------------------------------------|
| `run_mode` | `live` | `live` |
| `watchlist_id` | `watchlist_v1` | `watchlist_v1` |
| `products_in_run_1` (`products_in_a`) | `6` | `6` |
| `products_in_run_2` (`products_in_b`) | `6` | `6` |
| `products_in_a == products_in_b` | `true` | `true` |
| `added` (`new_products`) | `0` (`[]`) | `0` (`[]`) |
| `removed` (`removed_products`) | `0` (`[]`) | `0` (`[]`) |
| `changed` (price/availability/scope/id) | `0` (`[]`) | `0` (`[]`) |

- **Cross-Run Diff Guards:** `ObservationHistory.cross_run_diff()` stamps every JSONL row with `run_id`, `run_mode`, `watchlist_id`, `source`, and `timestamp`, and raises `ValueError` if comparing `live` vs `offline_fixture`, `live` vs `synthetic`, or runs from different `watchlist_id`s.

---

## 7. Carrefour Location Semantics (`LocationType.PRESENCE`)

- Carrefour's 19 governorate-level footprint entries are modeled as `LocationType.PRESENCE` (`"presence"`), **never** as `LocationType.STORE` or `LocationType.BRANCH`.
- `branch_name`, `address`, `latitude`, and `longitude` are `null` (`None`), while `raw_location_name` (`"Carrefour Egypt — <Governorate> Governorate Presence"`) and `governorate` are preserved.
- `DataValidator` treats `LocationType.PRESENCE` and `LocationType.COVERAGE` as area/presence records and does not penalize them for missing street addresses or GPS coordinates (`carrefour` location validation score = `100.0%`, `0` location issues).

---

## 8. Quality Score Audit — Why Earlier Jumia/2B Runs Showed `100%` / `0` Issues

### Root Cause of Earlier `100.0%` / `0` Issues
1. Previously, `DataValidator._validate_products()` only counted 3 checks per product (`product_name`, `product_url`, `sku` warning without deducting `passed_checks`) and did **not** check or penalize missing `gtin`, `brand`, or `category`.
2. Previously, `DataValidator._validate_observations()` only counted 2 checks per observation (`price > 0`, `old_price >= price`) and did **not** check or penalize missing `seller_name` or `availability_scope == UNKNOWN`.
3. Previously, `scripts/live_smoke.py` copied `source_product_id` (`data-product-id`) into `Product.sku` on 2B category cards, hiding the fact that 2B category cards do not expose `sku`.

### Updated Quality Scoring & Real Scores (`2026-09-28`)
- `DataValidator._validate_products()` now performs **6 checks per product** (`product_name`, `product_url`, `sku`, `gtin`, `brand`, `category`) and emits `DataQualityIssue` records (`MISSING_SKU`, `MISSING_FIELD`) that deduct from `passed_checks`.
- `DataValidator._validate_observations()` now performs **4 checks per observation** (`price`, `old_price`, `seller_name`, `availability_scope != UNKNOWN`) and emits `DataQualityIssue` records (`MISSING_FIELD`, `AMBIGUOUS_AVAILABILITY`) that deduct from `passed_checks`.
- **Resulting Honest Quality Scores:**
  - **`jumia` (`live_repeat_run_2`):** `86.21%` (`12` issues: `6` missing `gtin` on products + `6` missing `seller_name` on category-card observations).
  - **`two_b` (`live_repeat_run_2`):** `94.94%` (`20` issues: `6` missing `sku` on category cards + `6` missing `gtin` + `6` missing `seller_name` + `1` `INCONSISTENT_LOCATION_NAME` on `2B - Aswan` + `1` `OUT_OF_EGYPT_COORDINATES` on `Assiut lat=90.0`).
  - **`tests/fixtures/degraded_live_like_sample.html`:** `50.0%` (`10` issues across 2 degraded cards missing `sku`, `gtin`, `brand`, `category`, `seller_name`, and `availability_scope`).

---

## 9. Sample Bundles Summary (`samples/<source>/`)

| Source | `run_mode` | `run_id` | `watchlist_id` | Products | Observations | Locations | Quality Score | Quality Issues |
|--------|------------|----------|----------------|----------|--------------|-----------|---------------|----------------|
| `jumia` | `live` | `live_repeat_run_2` | `watchlist_v1` | `6` | `6` | `27` (`delivery_zone`) | `86.21%` | `12` |
| `two_b` | `live` | `live_repeat_run_2` | `watchlist_v1` | `6` | `6` | `59` (`branch`) | `94.94%` | `20` |
| `carrefour` | `offline_fixture` | `sample_carrefour_20260928` | `watchlist_v1` | `5` | `5` | `19` (`presence`) | `85.51%` | `10` |
| `tradeline` | `offline_fixture` | `sample_tradeline_20260928` | `watchlist_v1` | `2` | `2` | `2` (`store`) | `84.62%` | `4` |
| `dream2000` | `offline_fixture` | `sample_dream2000_20260928` | `watchlist_v1` | `2` | `2` | `0` | `90.00%` | `2` |
| `raya` | `synthetic` | `sample_raya_20260928` | `watchlist_v1` | `2` | `2` | `0` | `80.00%` | `4` |
