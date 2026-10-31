# Data Dictionary

All field definitions for the canonical data model defined in
[`normalization/schema.py`](../normalization/schema.py).

---

## Product

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `product_id` | UUID string | Auto | Internal UUID, generated on creation |
| `source_id` | string | Yes | Source identifier (e.g., `jumia`, `two_b`) |
| `source_product_id` | string | Yes | Product ID as given by the source |
| `sku` | string | No | Stock-Keeping Unit from source |
| `gtin` | string | No | GTIN / EAN / barcode (only if source exposes it) |
| `product_name` | string | Yes | Cleaned product title (stripped whitespace) |
| `brand` | string | No | Brand name, normalized where possible |
| `category` | string | No | Top-level category from source |
| `subcategory` | string | No | Subcategory from source |
| `raw_category_path` | string | No | Full breadcrumb path as captured (e.g., `"Electronics > TVs > OLED"`) |
| `product_url` | string | Yes | Canonical URL at source |
| `source_url` | string | No | URL where product was found (may differ from canonical) |
| `image_url` | string | No | Primary product image URL |
| `specifications` | dict | No | Arbitrary key-value specs from source |
| `collected_at` | datetime | No | UTC timestamp when this product was first collected |

### Rules
- `product_name` must not be empty or whitespace-only
- `source_product_id` must be unique per source
- `gtin` must be null unless source explicitly provides a barcode field

---

## ProductObservation

A point-in-time observation. Append-only — historical records are never deleted.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `observation_id` | UUID string | Auto | Internal UUID |
| `product_id` | string | Yes | FK to Product |
| `source_id` | string | No | Source identifier (for traceability) |
| `source_product_id` | string | No | Source's product ID (for traceability) |
| `location_id` | string | No | FK to Location (null = no specific location) |
| `observed_at` | datetime | Auto | UTC timestamp of observation |
| `collected_at` | datetime | No | Alias for observed_at |
| `price` | float | No | Current price in EGP |
| `old_price` | float | No | Original / pre-discount price |
| `discount` | float | No | Discount percentage (0–100) |
| `currency` | enum | Default EGP | Currency code |
| `availability_status` | enum | Default UNKNOWN | Coarse availability classification |
| `availability_scope` | enum | Default UNKNOWN | **Semantic scope of availability claim** |
| `stock_status` | string | No | Fine-grained status string (e.g., `IN_STOCK`, `LOW_STOCK_SIGNAL`, `AVAILABLE_IN_STORES`) |
| `stock_quantity` | int | No | **Only set when source explicitly provides a quantity count** |
| `stock_quantity_evidence` | string | No | Where the quantity came from (required if stock_quantity is set) |
| `raw_availability_text` | string | No | Exact text captured from source (e.g., `"Only 2 left"`) |
| `raw_price_text` | string | No | Exact price text before parsing (e.g., `"EGP 10,490.00"`) |
| `delivery_status` | string | No | Delivery info text from source |
| `delivery_available` | bool | No | Whether delivery is available |
| `delivery_eta` | string | No | Delivery ETA text from source |
| `delivery_fee` | float | No | Delivery fee in EGP |
| `fulfillment_method` | string | No | `retailer`, `marketplace`, `pickup`, `unknown` |
| `rating` | float | No | Average customer rating (0–5) |
| `review_count` | int | No | Number of customer reviews |
| `seller_name` | string | No | Third-party seller name (marketplace only) |
| `source_url` | string | No | URL of the observed page |
| `hash_version` | int | Default 2 | Version of the row-hash algorithm |

### `availability_status` Values

| Value | Meaning |
|-------|---------|
| `in_stock` | Available |
| `out_of_stock` | Not available |
| `limited_stock` | Low-stock signal (do not set quantity from text) |
| `pre_order` | Available for pre-order |
| `discontinued` | Product discontinued |
| `delisted` | Removed from catalog |
| `unknown` | Cannot determine |

### `availability_scope` Values

| Value | Meaning |
|-------|---------|
| `GLOBAL` | Online catalog — orderable anywhere |
| `DELIVERY_AREA` | Deliverable to specific geographic area |
| `PHYSICAL_BRANCH` | Evidence of stock at a named physical branch |
| `CENTRAL_WAREHOUSE` | Central warehouse stock |
| `SELLER_NETWORK` | Marketplace — depends on individual seller |
| `UNKNOWN` | Scope undetermined |

### `stock_quantity` Rule

> `stock_quantity` **must be null** unless the source explicitly provides a
> numeric quantity via an API field or structured data attribute. The text
> "Only 2 left" is NOT sufficient evidence to set `stock_quantity=2`.
> In that case: `stock_status="LOW_STOCK_SIGNAL"`, `raw_availability_text="Only 2 left"`, `stock_quantity=null`.

---

## Location

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `location_id` | UUID string | Auto | Internal UUID |
| `source_id` | string | Yes | Source identifier |
| `location_type` | enum | Yes | Type of location |
| `location_name` | string | No | Canonical location name |
| `branch_name` | string | No | Branch / store display name |
| `warehouse_name` | string | No | Warehouse identifier (if applicable) |
| `address` | string | No | Full address text as captured |
| `city` | string | No | City name (normalized) |
| `governorate` | string | No | Egyptian governorate (normalized) |
| `district` | string | No | District or area within a city |
| `raw_location_name` | string | No | Raw name from source before normalization |
| `latitude` | float | No | GPS latitude (–90 to 90) |
| `longitude` | float | No | GPS longitude (–180 to 180) |
| `delivery_zone` | string | No | Delivery zone name or code |
| `phone` | string | No | Contact phone number |
| `working_hours` | string | No | Working hours text |
| `source_url` | string | No | URL of store locator page |
| `collected_at` | datetime | No | When the location data was collected |

### `location_type` Values

| Value | Physical? | Notes |
|-------|-----------|-------|
| `store` | Yes | Retail store (same as branch) |
| `branch` | Yes | Named retail branch |
| `warehouse` | Yes | Inventory warehouse |
| `fulfillment_center` | Yes | E-commerce fulfillment center |
| `pickup_point` | Yes | Click-and-collect point |
| `delivery_zone` | **No** | Geographic delivery coverage area |
| `delivery_area` | **No** | Preferred term for delivery coverage |
| `service_center` | Yes | After-sales service center |
| `unknown` | Unknown | Type not determined |

### Delivery Zone Rule

> Locations with `location_type = delivery_zone` or `delivery_area` are
> **NOT physical inventory locations**. They must NOT have `branch_name` or
> `address` required. They represent geographic coverage, not stocking points.
> The validator does not penalize them for missing `branch_name`/`address`.

---

## Source

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `source_id` | string | Yes | Unique source identifier |
| `source_name` | string | Yes | Human-readable name |
| `domain` | string | Yes | Domain (e.g., `jumia.com.eg`) |
| `official_url` | string | No | Official website URL |
| `business_type` | string | No | `marketplace`, `retailer`, `hypermarket`, etc. |
| `compliance_status` | enum | Yes | `A`, `B`, `C`, `D` |
| `research_status` | string | No | `VERIFIED/FULL`, `VERIFIED/PARTIAL`, `STRONG`, `UNVERIFIED` |
| `implementation_status` | string | No | `IMPLEMENTED`, `PROTOTYPE`, `PLANNED`, `BLOCKED` |
| `extraction_method` | enum | Yes | `official_api`, `public_json`, `static_html`, `playwright`, etc. |
| `enabled` | bool | Default False | Whether live extraction is enabled |
| `reason` | string | No | Reason for current status |
| `rate_limit_rpm` | int | Default 30 | Requests per minute limit |
| `min_delay_seconds` | float | Default 1.5 | Minimum inter-request delay |
| `max_delay_seconds` | float | Default 4.0 | Maximum inter-request delay |
| `notes` | string | No | Free-text notes |
| `evidence_url` | string | No | URL of compliance evidence |
| `evidence_captured_on` | string | No | ISO date of evidence capture |
| `evidence_summary` | string | No | Summary of compliance findings |

---

## DataQualityIssue

| Field | Type | Description |
|-------|------|-------------|
| `issue_id` | UUID string | Unique issue identifier |
| `source_id` | string | Source where issue was found |
| `entity_type` | string | `product`, `observation`, or `location` |
| `entity_id` | string | ID of the affected entity |
| `issue_code` | enum | Machine-readable issue code |
| `severity` | enum | `critical`, `high`, `medium`, `low`, `info` |
| `message` | string | Human-readable description |
| `raw_value` | string | The actual value that triggered the issue |
| `source_url` | string | URL of the source page |
| `detected_at` | datetime | UTC timestamp of detection |

### Issue Codes

| Code | Severity | Description |
|------|----------|-------------|
| `MISSING_FIELD` | medium | Required or important field is null |
| `DUPLICATE_PRODUCT` | high | Duplicate source_product_id within same source |
| `DUPLICATE_OBSERVATION` | medium | Same observation seen twice |
| `INVALID_PRICE` | high | Price is zero, negative, or unreasonably large |
| `PRICE_INCONSISTENCY` | medium | old_price < price (impossible discount) |
| `INVALID_URL` | medium | URL does not start with http |
| `INVALID_COORDINATES` | high | Lat/lng outside valid ranges |
| `OUT_OF_EGYPT_COORDINATES` | high | Coordinates outside Egypt's bounding box |
| `UNKNOWN_GOVERNORATE` | medium | Governorate field is "unknown" |
| `SCOPE_SEMANTICS_VIOLATION` | critical | Delivery zone treated as inventory location |
| `STOCK_QUANTITY_WITHOUT_EVIDENCE` | critical | stock_quantity set without evidence field |
| `AMBIGUOUS_AVAILABILITY` | medium | Availability status cannot be determined |
| `LOW_STOCK_SIGNAL_MISPARSE` | high | Low-stock text incorrectly parsed as quantity |
| `INVALID_DISCOUNT` | medium | Computed discount differs from stated by >2% |
| `MISSING_SKU` | low | SKU is null |

---

## ExtractionResult

| Field | Type | Description |
|-------|------|-------------|
| `source_id` | string | Source identifier |
| `extracted_at` | datetime | Timestamp of extraction run |
| `products` | list[Product] | Extracted products |
| `locations` | list[Location] | Extracted locations |
| `observations` | list[ProductObservation] | Extracted observations |
| `errors` | list[string] | Extraction errors encountered |
| `pages_visited` | int | Number of pages fetched |
| `duration_seconds` | float | Total extraction duration |
| `quality_issues` | list[DataQualityIssue] | Data quality issues detected |
| `mode` | string | `live`, `offline_fixture`, or `synthetic` |
