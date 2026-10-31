# Data Sources

This document describes every source in the platform registry. Statuses are
verified as of **2026-09-28**. Compliance classifications follow the four-class
system defined in [`COMPLIANCE.md`](COMPLIANCE.md).

---

## Class Legend

| Class | Symbol | Meaning |
|-------|--------|---------|
| A | ✅ | Clearly permitted for automated access |
| B | 🟡 | Conditional — specific conditions must be met |
| C | 🔴 | Explicitly prohibited — do not automate |
| D | ❓ | Unknown — not yet verified |

---

## Enabled Sources

### Jumia Egypt
| Field | Value |
|-------|-------|
| Domain | `jumia.com.eg` |
| Compliance | 🟡 **B** (Conditional) |
| Enabled | ✅ Yes |
| Method | Static HTML |
| Extractor | `extractors/source_jumia/` |
| robots.txt | Allows scraping with identified user-agent, <200 RPM |

**What it exposes:**
- Product catalog (name, price, old price, discount, rating, review count)
- Online availability status
- Delivery zone coverage (27 governorates, delivery only)
- Marketplace seller names

**What it does NOT expose:**
- Stock quantity
- Branch-level inventory
- GPS coordinates of fulfillment centers
- Physical store inventory

**Availability scope:** `GLOBAL` (marketplace, seller-dependent)

---

### 2B Egypt
| Field | Value |
|-------|-------|
| Domain | `2b.com.eg` |
| Compliance | 🟡 **B** (Conditional) |
| Enabled | ✅ Yes |
| Method | Static HTML + JSON-LD |
| Extractor | `extractors/source_2b/` |

**What it exposes:**
- Product catalog via JSON-LD schema.org markup
- Prices, availability status
- Store branch addresses and phone numbers
- "Available in Stores" vs "In Stock" (delivery) distinction

**What it does NOT expose:**
- Stock quantity
- Branch-level inventory (which store has which product)
- GPS coordinates

**Availability scopes:** `PHYSICAL_BRANCH` ("Available in Stores"), `DELIVERY_AREA` ("In Stock")

---

## Disabled Sources — Compliance Unverified (Class D)

### Carrefour Egypt
| Field | Value |
|-------|-------|
| Domain | `carrefouregypt.com` |
| Compliance | ❓ **D** (Unverified) |
| Enabled | ❌ No |
| Reason | robots.txt / ToS not confirmed |
| Method | Static HTML (prototype only) |
| Extractor | `extractors/source_carrefour/` (prototype, offline only) |

**Verified data from research:**
- Physical presence: 19 governorates
- "N left in store" signal = low-stock proxy
- No GPS coordinates exposed

**Required for enablement:** robots.txt verification, ToS review

---

### Tradeline Stores
| Field | Value |
|-------|-------|
| Domain | `tradelinestores.com` |
| Compliance | ❓ **D** (Unverified) |
| Enabled | ❌ No |
| Method | Shopify `/products.json` (public JSON) |
| Extractor | `extractors/source_tradeline/` → delegates to `ShopifyExtractor` |

**Research confirmed:**
- 30 physical branches with GPS coordinates
- Shopify `/products.json` public endpoint
- Apple Premium Partner (Apple, accessories, audio)

**Availability scope:** `GLOBAL` (online Shopify store)

**Required for enablement:** robots.txt / ToS verification

---

### Dream 2000
| Field | Value |
|-------|-------|
| Domain | `dream2000.com` |
| Compliance | ❓ **D** (Unverified) |
| Enabled | ❌ No |
| Method | Shopify `/products.json` |
| Extractor | `extractors/source_dream2000/` → delegates to `ShopifyExtractor` |

**Available when enabled:** Full product catalog from Shopify endpoint

---

### Raya Shop
| Field | Value |
|-------|-------|
| Domain | `rayashop.com` |
| Compliance | ❓ **D** (Unverified) |
| Enabled | ❌ No |
| Method | Static HTML + JSON-LD (Magento 2) |
| Extractor | `extractors/source_raya/` |

**Availability semantics:** "Pickup from Store" → `PHYSICAL_BRANCH`, "In Stock" → `DELIVERY_AREA`

---

## Prohibited Sources (Class C)

### B.TECH
| Field | Value |
|-------|-------|
| Domain | `btech.com` |
| Compliance | 🔴 **C** (Do Not Automate) |
| Enabled | ❌ No |
| Reason | Explicit prohibition in robots.txt or ToS |

> **Do NOT automate B.TECH.** The `source_btech/` extractor code exists for
> reference and offline analysis only. No live requests may be made.

---

## Other Sources (Unimplemented)

The following sources are in `config/sources.yaml` as research placeholders.
No extractor code exists. Status is all **Class D** (unverified):

| Source | Domain | Notes |
|--------|--------|-------|
| Noon Egypt | `noon.com` | International marketplace |
| Amazon Egypt | `amazon.eg` | International marketplace |
| Samsung Egypt | `samsung.com/eg` | Brand direct |
| Vodafone Egypt | `web.vodafone.com.eg` | Telecom |
| Orange Egypt | `shop.orange.eg` | Telecom |
| WE / Telecom Egypt | `te.eg` | Telecom |
| El Araby | `elarabygroup.com` | Egyptian electronics |
| Metro Markets | `metro-markets.com` | Grocery |
| HyperOne | `hyperone.com` | Grocery |
| Spinneys Egypt | `spinneys-egypt.com` | Grocery |
| Fresh | `freshegy.com` | Grocery |
| Talabat Mart | `talabat.com/egypt` | Quick delivery |

---

## Adding a New Source

1. Add entry to `config/sources.yaml`
2. Verify robots.txt and ToS manually
3. Set `compliance_status: B` or `A` if permitted
4. Create `extractors/source_<id>/` package
5. Add extractor to `get_extractor()` factory in `run_extraction.py`
6. Create test fixtures and test file
7. Run `python run_extraction.py --audit` to verify compliance
