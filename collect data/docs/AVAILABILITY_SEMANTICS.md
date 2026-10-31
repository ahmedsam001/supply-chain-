# Availability Semantics

## Critical Distinction

This document is **mandatory reading** for all developers working on the data
acquisition layer. Incorrect availability semantics produce misleading supply-chain
signals and undermine the platform's core purpose.

---

## Rule 1: Delivery ≠ Physical Inventory

```
"A product can be delivered to Cairo"
  ≠
"The product is physically stocked in Cairo"
```

A product visible on an online catalog, orderable for delivery, is only evidence
of **online availability**. It says nothing about where the physical stock is
located. The stock may be in a single central warehouse, in a seller's garage, or
in a distributed fulfillment network — the platform cannot know without explicit
evidence.

---

## Rule 2: "In Stock" ≠ Branch Inventory

```
"In Stock" (on a product page)
  ≠
"The product is stocked at Branch X"
```

Unless a source explicitly provides branch-level inventory data (Carrefour's "N
left at [store]" signal, for example), availability is scoped to the **online
catalog or delivery network** — not any specific physical location.

---

## Rule 3: Low-Stock Signals are Signals, Not Quantities

```
"Only 2 left"
```

This is a **LOW_STOCK_SIGNAL** — a marketing/urgency cue. The platform must:

- Set `availability_status = LIMITED_STOCK`
- Set `stock_status = LOW_STOCK_SIGNAL`
- Leave `stock_quantity = null`
- Capture raw text in `raw_availability_text = "Only 2 left"`

**Never** set `stock_quantity = 2` from this kind of text. The number may be
approximate, delayed, or entirely fabricated by the site. Without an explicit API
field for quantity, the number must not be stored as data.

---

## The `AvailabilityScope` Enum

Every `ProductObservation` must carry an `availability_scope` value:

| Scope | Meaning |
|-------|---------|
| `GLOBAL` | Online catalog — product is orderable; no specific geographic scope |
| `DELIVERY_AREA` | Deliverable to a specific geographic area |
| `PHYSICAL_BRANCH` | Evidence of stock at a specific named branch |
| `CENTRAL_WAREHOUSE` | Evidence of stock at a central/regional warehouse |
| `SELLER_NETWORK` | Marketplace: availability depends on individual seller |
| `UNKNOWN` | Scope cannot be determined from available data |

### Default Value

When in doubt: `UNKNOWN`. Do not guess.

---

## Source-Level Scope Rules

### Jumia Egypt
- Product catalog availability = `GLOBAL` (marketplace, seller-dependent)
- Delivery zone extraction = produces `Location` records with `type=DELIVERY_ZONE`
  - These are NOT inventory locations
- `seller_network` scope applies when multiple sellers offer a product

### Carrefour Egypt
- Product catalog availability = `GLOBAL` or `DELIVERY_AREA` (online delivery)
- "N left in store" signal = `PHYSICAL_BRANCH` scope (branch must be named)
- Branch locations = `Location` records with `type=STORE`

### Tradeline Stores (Shopify)
- Product availability from `/products.json` = `GLOBAL` (online store)
- `variant.available: true` means orderable online; no branch info
- Branch GPS data from store locator = `Location` records only

### Dream 2000 (Shopify)
- Same as Tradeline. `availability_scope = GLOBAL`.

### 2B Egypt (Magento 2)
- `"Available in Stores"` → `PHYSICAL_BRANCH` scope
- `"In Stock"` (without store qualifier) → `DELIVERY_AREA` scope
- `"Out of Stock"` → `OUT_OF_STOCK`

### Raya Shop (Magento 2)
- `"Pickup from Store"` → `PHYSICAL_BRANCH` scope
- `"In Stock"` → `DELIVERY_AREA` scope
- Compliance class D — not currently collecting live data

---

## Validator Rules

The `DataValidator` enforces these rules:

1. **No stock_quantity without evidence**: If `stock_quantity` is set but
   `stock_quantity_evidence` is null → `STOCK_QUANTITY_WITHOUT_EVIDENCE` issue.
2. **No branch_name/address penalty for delivery zones**: Locations with
   `type=DELIVERY_ZONE` or `type=DELIVERY_AREA` are not penalized for missing
   `branch_name` or `address`. They only require `governorate`.
3. **Discount cross-check**: If price, old_price, and discount are all present,
   the computed discount must match within 2 percentage points.

---

## Geographic Coverage vs. Availability Coverage

These must always be kept separate:

| Concept | What it means |
|---------|---------------|
| **Delivery Zone Coverage** | The geographic areas a source can deliver to |
| **Physical Branch Coverage** | Named physical locations with known addresses |
| **Warehouse Coverage** | Fulfillment centers (rarely exposed by sources) |
| **Inventory Coverage** | Which branches stock which products (almost never exposed) |

The platform currently collects **Delivery Zone Coverage** (Jumia, governorate-level)
and **Physical Branch Coverage** (Tradeline GPS, 2B/Raya store addresses). It does
**NOT** collect branch-level inventory data — no source currently exposes this.
