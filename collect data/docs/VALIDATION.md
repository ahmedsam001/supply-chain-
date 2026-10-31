# Validation Framework

## Overview

The `DataValidator` (`validation/data_validator.py`) checks the quality of
extracted data and emits structured `DataQualityIssue` records.

---

## Validation Report Structure

```python
report = validator.validate(result)

# Top-level keys:
report["source_id"]          # Source identifier
report["extracted_at"]       # Timestamp
report["products"]           # Product validation results
report["observations"]       # Observation validation results
report["locations"]          # Location validation results
report["overall"]            # Overall quality score
report["quality_issues"]     # List of DataQualityIssue dicts
```

### Overall Quality Score

```
quality_score = total_passed_checks / total_checks
```

Scores of ≥ 0.80 are acceptable for prototype data.

---

## Product Checks

| Check | Pass condition | Issue if fail |
|-------|---------------|---------------|
| Product name | Not empty | `MISSING_FIELD` (critical) |
| Product URL | Starts with `http` | `INVALID_URL` (medium) |
| source_product_id | Not empty | `MISSING_FIELD` (high) |
| brand | Not null | `MISSING_FIELD` (low) |
| category | Not null | `MISSING_FIELD` (low) |
| sku | Not null | `MISSING_SKU` (low) |
| Duplicate source_product_id | Not seen before | `DUPLICATE_PRODUCT` (high) |

---

## Observation Checks

| Check | Pass condition | Issue if fail |
|-------|---------------|---------------|
| Price range | 1 ≤ price ≤ 5,000,000 EGP | `INVALID_PRICE` (high) |
| Price non-zero | price ≠ 0 | `INVALID_PRICE` (high) |
| Price consistency | old_price > price (if both present) | `PRICE_INCONSISTENCY` (medium) |
| Discount valid | 0 ≤ discount ≤ 99 | `INVALID_DISCOUNT` (medium) |
| Discount cross-check | computed vs stated within 2% | `INVALID_DISCOUNT` (medium) |
| availability_status | Not null | `MISSING_FIELD` (medium) |
| stock_quantity evidence | If quantity set, evidence required | `STOCK_QUANTITY_WITHOUT_EVIDENCE` (critical) |

---

## Location Checks

### Physical Locations (STORE, BRANCH, WAREHOUSE, FULFILLMENT_CENTER, PICKUP_POINT)

| Check | Pass condition |
|-------|---------------|
| branch_name | Not null |
| city OR governorate | At least one present |
| address | Not null |
| latitude | –90 to 90 (if set) |
| longitude | –180 to 180 (if set) |
| Egypt bounds | lat 22–31.5, lon 25–36.5 (if set) |

### Delivery Zones (DELIVERY_ZONE, DELIVERY_AREA)

> Delivery zones are **NOT penalized** for missing `branch_name` or `address`.

| Check | Pass condition |
|-------|---------------|
| governorate | Present and not "unknown" |

This is the **critical delivery-zone fix** introduced in this implementation.
Prior to the fix, Jumia's delivery zone records (which legitimately have no
branch_name or address) were incorrectly penalized, producing artificially low
quality scores.

---

## Quality Issues Output

Quality issues are written to `quality_issues.json` when the extractor saves results:

```json
[
  {
    "issue_id": "uuid...",
    "source_id": "jumia",
    "entity_type": "product",
    "entity_id": "133802131",
    "issue_code": "MISSING_SKU",
    "severity": "low",
    "message": "Product 133802131: missing SKU",
    "raw_value": null,
    "source_url": null,
    "detected_at": "2026-09-28T10:05:07Z"
  }
]
```

Write issues to file:
```python
DataValidator.write_quality_issues(issues, Path("output/quality_issues.json"))
```

---

## Expected Quality Scores (Reference)

After the delivery-zone penalty fix:

| Source | Expected Score | Notes |
|--------|---------------|-------|
| Jumia | ≥ 85% | Delivery zone fix removes false penalty |
| Carrefour | ≥ 85% | Branch locations have good coverage |
| Tradeline | ≥ 95% | Shopify data is well-structured |
| Dream 2000 | ≥ 95% | Shopify data is well-structured |
| 2B Egypt | ≥ 85% | Some products missing brand (JSON-LD limitation) |
| Raya Shop | ≥ 85% | Same as 2B |

---

## Adding Custom Checks

Add a new method to `DataValidator`:

```python
def _check_price_currency_consistency(
    self,
    observations: list[ProductObservation],
) -> list[DataQualityIssue]:
    issues = []
    for obs in observations:
        if obs.currency != Currency.EGP:
            issues.append(DataQualityIssue(
                source_id=obs.source_id or "unknown",
                entity_type="observation",
                entity_id=obs.product_id,
                issue_code=IssueCode.MISSING_FIELD,
                severity=IssueSeverity.MEDIUM,
                message=f"Unexpected currency: {obs.currency}",
                raw_value=str(obs.currency),
            ))
    return issues
```

Then call it from `validate()` and add its output to `quality_issues`.


---

## Cross-Source GTIN Collision Report & Connector Contract (WP8)

- **GTIN Collision Report (`DataValidator.generate_gtin_collision_report`)**: Indexes 8–14 digit EAN/UPC/GTIN codes across sources into `data/quality/gtin_collisions.json` and `samples/gtin_collisions.json` as an informational report without performing speculative fuzzy product matching.
- **Connector Contract**: Every connector output is verified to populate `source_id`, `source_product_id`, `source_url`, `collected_at`, a valid `AvailabilityScope`, and `stock_quantity = None` unless backed by structured `stock_quantity_evidence`.
