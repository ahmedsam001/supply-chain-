# Test Fixtures Inventory (WP1 / WP12)

This directory contains HTML and JSON fixtures for deterministic offline testing.
Every fixture is explicitly labeled as either **`REAL`** (sanitized capture from the live public site) or **`SYNTHETIC`** (hand-authored to test parser structure without claiming live provenance).

## 1. Real Sanitized Live Captures (`tests/fixtures/<source>/real/`)

Captured via `scripts/live_smoke.py` through the compliance gate on `2026-09-28` (no personal data, cookies, or session tokens):

| File | Source | Provenance | Details |
|---|---|---|---|
| `jumia/real/category_sample.html` | `jumia` (Jumia Egypt) | **REAL** (`2026-09-28`, `run_id=live_20260928_wp1`) | Live capture from `https://www.jumia.com.eg/phones-tablets/` |
| `two_b/real/category_sample.html` | `two_b` (2B Egypt) | **REAL** (`2026-09-28`, `run_id=live_20260928_wp1`) | Live capture from `https://2b.com.eg/en/laptops.html` (Magento 2 HTML cards + prices) |

## 2. Baseline Offline & Synthetic Fixtures (`tests/fixtures/`)

| File | Source | Provenance | Notes |
|---|---|---|---|
| `jumia_sample.html` | `jumia` | **REAL** | Captured from live Jumia Egypt catalog (`2026-09-27`) |
| `jumia_pdp_sample.html` | `jumia` | **REAL** | Captured from live Jumia Egypt PDP with JSON-LD & specs (`2026-09-27`) |
| `carrefour_sample.html` | `carrefour` | **REAL** | Captured from Carrefour Egypt during discovery research (`2026-09-27`) |
| `tradeline_products_sample.json` | `tradeline` | **REAL** | Structured from Tradeline `/products.json` public Shopify endpoint |
| `tradeline_locator_sample.html` | `tradeline` | **REAL** | Structured from Tradeline `/pages/store-locator` research (`2026-09-27`) |
| `dream2000_products_sample.json` | `dream2000` | **REAL** | Structured from Dream 2000 `/products.json` public Shopify endpoint (with EAN-13 GTINs) |
| `twob_sample.html` | `two_b` | **SYNTHETIC** | Hand-authored Magento 2 JSON-LD + HTML card fixture for unit testing (`<!-- SYNTHETIC -->`) |
| `twob_pdp_sample.html` | `two_b` | **SYNTHETIC** | Hand-authored Magento 2 PDP fixture for unit testing (`<!-- SYNTHETIC -->`) |
| `raya_sample.html` | `raya` | **SYNTHETIC** | Hand-authored Magento 2 category fixture for offline testing (`<!-- SYNTHETIC -->`) |
| `raya_pdp_sample.html` | `raya` | **SYNTHETIC** | Hand-authored Magento 2 PDP fixture for offline testing (`<!-- SYNTHETIC -->`) |
