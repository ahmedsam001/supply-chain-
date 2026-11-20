# Limitations

This document records **known limitations** of the current implementation.
It is deliberately honest. Do not delete entries unless the limitation has been
genuinely resolved.

---

## Data Collection Scope Limitations

### No Branch-Level Inventory Data

**None of the currently collected sources expose which specific branch stocks
which product.**

The platform collects:
- Online availability (in stock / out of stock for online ordering)
- Physical branch locations (addresses, GPS where available)
- Delivery zone coverage (which governorates a source delivers to)

The platform does **not** collect:
- How many units are at Branch X
- Which branches have a specific product in stock
- Warehouse inventory levels

This is a fundamental source limitation, not a technical one. Egyptian retailers
generally do not expose branch-level inventory via their public web interfaces.

---

### Stock Quantities Are Not Collected

No source currently exposes exact stock quantities via public HTML or public API.
The `stock_quantity` field is always `null` in the current dataset. "Only N left"
text is treated as a `LOW_STOCK_SIGNAL` only.

---

### Delivery Zone Coverage is Not Physical Inventory

Jumia delivers to 27 Egyptian governorates. This means:
- A customer in Aswan **can order** a product
- It does **not** mean the product is physically stocked in Aswan

The platform stores delivery zone data as `Location` records with
`location_type=DELIVERY_ZONE`. These are clearly separated from physical
branch records.

---

### GPS Coordinates are Sparse

| Source | GPS Available? |
|--------|---------------|
| Jumia | ❌ No (delivery zones only) |
| Carrefour | ❌ No (addresses only) |
| Tradeline | ✅ Yes (30 branches with lat/lng) |
| Dream 2000 | ❌ No |
| 2B Egypt | ❌ No |
| Raya Shop | ❌ No |

GPS coverage improvement requires either: a Maps API enrichment step (future
phase), or sources publishing coordinates.

---

## Compliance Limitations

### 5 of 7 Prototype Sources Are Class D (Unverified)

Only **Jumia** and **2B Egypt** are enabled. Five sources with working prototype
code are disabled pending compliance verification:

| Source | Blocker |
|--------|---------|
| Carrefour | robots.txt / ToS not confirmed |
| Tradeline | robots.txt / ToS not confirmed |
| Dream 2000 | robots.txt / ToS not confirmed |
| Raya Shop | robots.txt / ToS not confirmed |

Resolution: manual robots.txt review and ToS analysis for each source.

### B.TECH is Hard-Blocked (Class C)

B.TECH has an explicit prohibition. No live collection is possible without a
formal data partnership agreement.

---

## Geographic Limitations

### Governorate-Level Resolution Only for Most Sources

City and district resolution is available only where the source provides it.
Most sources expose governorate or city at best:

| Source | Resolution |
|--------|-----------|
| Jumia delivery zones | Governorate only |
| Carrefour branches | City (from address parsing) |
| Tradeline branches | City (GPS + address) |
| 2B branches | City (from address text) |

**No source exposes district-level data** for delivery or inventory.

### Geographic Hierarchy Not Fully Populated

The hierarchy (Egypt → Governorate → City → District → Branch → Zone) is
designed but not fully populated. District-level data is not currently collected.

### No H3 / Geohash Indexing

Geographic technical zones (H3 hexagonal indexing, Geohash) are planned for a
future phase. The current model includes a placeholder in the Location model
for `district` but no geospatial indexing is implemented.

---

## Technical Limitations

### No Real-Time Updates

The platform is batch-based. There is no streaming, webhook, or push mechanism.
Data freshness depends on how frequently the extraction is run.

### No Database

All output is stored as JSON files in `samples/`. PostgreSQL schema exists in
`storage/schema.py` but no database write logic is implemented.

### Playwright Required for Tradeline Store Locator

The `TradelineExtractor.extract_locations()` method uses Playwright to render
the JavaScript-heavy store locator page. This requires a browser binary. If
Playwright is not installed, location extraction for Tradeline will fail
silently and return an empty list.

### Carrefour Prototype Extractor Not Production-Ready

`extractors/source_carrefour/` was built as a prototype. It works on the test
fixture but has not been verified against the live site (which is Class D).

---

## Synthetic Fixture Limitations

The test fixtures for 2B Egypt and Raya Shop (`tests/fixtures/twob_*.html`,
`tests/fixtures/raya_*.html`) are **SYNTHETIC** — hand-authored to match the
known structure of these Magento 2 sites based on desk research.

**These fixtures may not perfectly reflect the current live site structure.**

If the real site has changed its HTML structure, the parser tests may pass
while the live extractor fails. Live site verification is required before
enabling Class D sources.

---

## Known Issues

| ID | Description | Status |
|----|-------------|--------|
| VAL-01 | Discount cross-check can false-positive on rounding differences | Mitigated (2% tolerance) |
| SCH-01 | `source_product_id` uniqueness is enforced by validator, not by model | Known |
| GEO-01 | `normalize_location()` can return `None` governorate for less-common cities | Known |
| FIXTU-01 | Tradeline locator fixture only has 2 branches (real site has 30) | Acceptable for testing |
